import importlib.util
import os
import sys
import types
import unittest
from pathlib import Path


MODULE_PATH = (
    Path(__file__).resolve().parents[1]
    / 'slug/cert-lifecycle/lambda/expiry_checker/handler.py'
)


def load_handler_module():
    os.environ.setdefault('AWS_REGION', 'eu-west-2')
    os.environ.setdefault('BITBUCKET_TOKEN_SECRET_ID', 'bitbucket-secret')
    os.environ.setdefault('BITBUCKET_CATALOGUE_URLS', '')
    os.environ.setdefault('SPOKE_ROLE_NAME', 'CertLifecycleRole')
    os.environ.setdefault('CERT_RENEWAL_TOPIC_ARN', 'arn:aws:sns:test:renewal')
    os.environ.setdefault('CERT_P1_ALERT_TOPIC_ARN', 'arn:aws:sns:test:p1')
    os.environ.setdefault('JENKINS_JOB_NAME', 'slug-cert-lifecycle/issue-certificate')
    os.environ.setdefault(
        'JENKINS_JOB_URL',
        'https://jenkins.example.com/job/slug-cert-lifecycle/job/issue-certificate',
    )
    os.environ.setdefault('RUNBOOK_URL', 'https://runbook.example.com')

    boto3 = types.ModuleType('boto3')
    boto3.client = lambda *args, **kwargs: None
    sys.modules['boto3'] = boto3

    requests = types.ModuleType('requests')
    requests.Session = object
    requests.get = lambda *args, **kwargs: None
    sys.modules['requests'] = requests

    yaml = types.ModuleType('yaml')
    yaml.safe_load = lambda text: {}
    sys.modules['yaml'] = yaml

    cryptography = types.ModuleType('cryptography')
    x509 = types.ModuleType('cryptography.x509')
    x509.load_pem_x509_certificate = lambda pem: None
    cryptography.x509 = x509
    sys.modules['cryptography'] = cryptography
    sys.modules['cryptography.x509'] = x509

    spec = importlib.util.spec_from_file_location('expiry_checker_handler', MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class FakeResponse:
    def __init__(self, status_code, headers=None, payload=None):
        self.status_code = status_code
        self.headers = headers or {}
        self._payload = payload or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f'HTTP {self.status_code}')

    def json(self):
        return self._payload


class FakeSession:
    def __init__(self, post_response):
        self.post_response = post_response
        self.post_calls = []

    def get(self, url, timeout):  # noqa: ARG002
        return FakeResponse(404)

    def post(self, url, data, headers, timeout, allow_redirects):  # noqa: ARG002
        self.post_calls.append({
            'url': url,
            'data': data,
            'headers': headers,
            'allow_redirects': allow_redirects,
        })
        return self.post_response


class JenkinsBuildWithParametersTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.handler = load_handler_module()
        cls.base_url = 'https://jenkins.example.com'
        cls.job_url = (
            'https://jenkins.example.com/job/slug-cert-lifecycle/job/issue-certificate'
        )
        cls.parameters = {
            'PRODUCT_TEAM': 'PT2',
            'ENVIRONMENT': 'preprod',
            'APP_NAME': 'payments-api-preprodc',
        }

    def trigger(self, response):
        return self.handler._jenkins_build_with_parameters(
            FakeSession(response),
            self.base_url,
            self.job_url,
            self.parameters,
        )

    def test_accepts_jenkins_queue_redirect(self):
        location = 'https://jenkins.example.com/queue/item/123/'

        result = self.trigger(FakeResponse(302, headers={'Location': location}))

        self.assertEqual(result, location)

    def test_accepts_jenkins_build_redirect(self):
        location = (
            'https://jenkins.example.com/job/slug-cert-lifecycle/'
            'job/issue-certificate/42/'
        )

        result = self.trigger(FakeResponse(303, headers={'Location': location}))

        self.assertEqual(result, location)

    def test_rejects_login_redirect(self):
        with self.assertRaisesRegex(RuntimeError, 'unexpected redirect'):
            self.trigger(
                FakeResponse(
                    302,
                    headers={'Location': 'https://jenkins.example.com/login'},
                )
            )

    def test_rejects_failed_status(self):
        with self.assertRaisesRegex(RuntimeError, 'HTTP 403'):
            self.trigger(FakeResponse(403))

    def test_parameters_match_required_jenkins_values(self):
        actions = [{
            'parameters': [
                {'name': 'PRODUCT_TEAM', 'value': 'PT2'},
                {'name': 'ENVIRONMENT', 'value': 'preprod'},
                {'name': 'APP_NAME', 'value': 'payments-api-preprodc'},
            ],
        }]

        result = self.handler._jenkins_parameters_match(actions, self.parameters)

        self.assertTrue(result)


if __name__ == '__main__':
    unittest.main()
