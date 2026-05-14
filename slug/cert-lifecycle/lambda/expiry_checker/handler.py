"""
Slug Certificate Lifecycle — Expiry Checker Lambda

Reads enrolled application certificate catalogue files from Bitbucket, checks
the expiry of each application's certificate stored in spoke account AWS Secrets
Manager, and routes SNS notifications based on days remaining.

Threshold routing:
  days_left > 30          log only
<<<<<<< HEAD
  15 <= days_left <= 30   trigger Jenkins, publish to cert-renewal SNS
  days_left <= 14         publish to cert-p1-alerts SNS  (includes expired)

Safe logging contract: this module never logs private_key, ca_chain, full_chain,
SecretString payloads, Bitbucket tokens, Jenkins tokens, or AWS temporary
credentials.
=======
  15 <= days_left <= 30   publish to cert-renewal SNS
  days_left <= 14         publish to cert-p1-alerts SNS  (includes expired)

Safe logging contract: this module never logs private_key, ca_chain, full_chain,
SecretString payloads, Bitbucket tokens, or AWS temporary credentials.
>>>>>>> origin/main

Packaging note: the 'cryptography' dependency includes native components and must
be built in a Lambda-compatible environment (Amazon Linux 2 or AL2023) before
deployment. Use a Lambda layer, container image, or a CI build step that targets
the correct architecture.
"""

import datetime
import json
import logging
import os
<<<<<<< HEAD
import re
from dataclasses import dataclass
from urllib.parse import unquote, urlparse
=======
>>>>>>> origin/main

import boto3
import requests
import yaml
from cryptography import x509

logger = logging.getLogger()
logger.setLevel(logging.INFO)

# ── Environment variables (read at import time; missing vars fail immediately) ──
_AWS_REGION = os.environ['AWS_REGION']
_BITBUCKET_TOKEN_SECRET_ID = os.environ['BITBUCKET_TOKEN_SECRET_ID']
_BITBUCKET_CATALOGUE_URLS = os.environ['BITBUCKET_CATALOGUE_URLS']
_SPOKE_ROLE_NAME = os.environ['SPOKE_ROLE_NAME']
_CERT_RENEWAL_TOPIC_ARN = os.environ['CERT_RENEWAL_TOPIC_ARN']
_CERT_P1_ALERT_TOPIC_ARN = os.environ['CERT_P1_ALERT_TOPIC_ARN']
_JENKINS_JOB_NAME = os.environ['JENKINS_JOB_NAME']
_JENKINS_JOB_URL = os.environ['JENKINS_JOB_URL']
<<<<<<< HEAD
_JENKINS_TRIGGER_SECRET_ID = os.environ.get('JENKINS_TRIGGER_SECRET_ID', '')
_RUNBOOK_URL = os.environ['RUNBOOK_URL']

_CATALOGUE_FILE_RE = re.compile(
    r'^(?P<product_team>[A-Za-z0-9]+)-(?P<environment>[A-Za-z0-9]+)-certs\.ya?ml$'
)


@dataclass(frozen=True)
class CatalogueContext:
    product_team: str | None
    environment: str | None
    url: str
    filename: str

=======
_RUNBOOK_URL = os.environ['RUNBOOK_URL']

>>>>>>> origin/main

# ── Lambda entry point ─────────────────────────────────────────────────────────

def handler(event, context):  # noqa: ARG001
    counters = {
        'checked': 0,
        'ok': 0,
        'renewal_needed': 0,
        'p1_action_required': 0,
<<<<<<< HEAD
        'jenkins_triggered': 0,
        'jenkins_skipped': 0,
        'jenkins_trigger_failed': 0,
=======
>>>>>>> origin/main
        'errors': 0,
    }

    sm_client = boto3.client('secretsmanager', region_name=_AWS_REGION)
    sts_client = boto3.client('sts', region_name=_AWS_REGION)
    sns_client = boto3.client('sns', region_name=_AWS_REGION)

    try:
        token = _get_bitbucket_token(sm_client)
    except Exception as exc:
        logger.error('Failed to retrieve Bitbucket token from Secrets Manager: %s', exc)
        logger.info(json.dumps({'summary': counters}))
        raise RuntimeError('Failed to retrieve Bitbucket token') from exc

    apps, catalogue_errors = _load_all_apps(token)
    counters['errors'] += catalogue_errors

    if not apps:
        logger.error(
            json.dumps({
                'status': 'error',
                'message': 'No applications loaded from configured catalogue URLs',
            })
        )
        logger.info(json.dumps({'summary': counters}))
        raise RuntimeError('No applications loaded from configured catalogue URLs')

<<<<<<< HEAD
    for app_record in apps:
        counters['checked'] += 1
        app = app_record.get('app') if isinstance(app_record, dict) else None
        app_name = app.get('name', '<unknown>') if isinstance(app, dict) else '<invalid>'
        try:
            result = _check_app(app_record, sts_client, sns_client, sm_client)
            counters[result['status']] += 1
            jenkins_status = result.get('jenkins_status')
            if jenkins_status:
                counters[jenkins_status] += 1
=======
    for app in apps:
        counters['checked'] += 1
        app_name = app.get('name', '<unknown>') if isinstance(app, dict) else '<invalid>'
        try:
            result = _check_app(app, sts_client, sns_client)
            counters[result] += 1
>>>>>>> origin/main
        except Exception as exc:
            logger.error(
                json.dumps({
                    'status': 'error',
                    'app_name': app_name,
                    'error': str(exc),
                })
            )
            counters['errors'] += 1

    logger.info(json.dumps({'summary': counters}))
    return counters


# ── Private helpers ────────────────────────────────────────────────────────────

def _get_bitbucket_token(sm_client) -> str:
    """Retrieve the Bitbucket API token from Secrets Manager. Never logged."""
    response = sm_client.get_secret_value(SecretId=_BITBUCKET_TOKEN_SECRET_ID)
    payload = json.loads(response['SecretString'])
    return payload['token']


def _load_all_apps(token: str) -> tuple[list, int]:
<<<<<<< HEAD
    """Fetch every catalogue URL and return (flat app record list, error count)."""
=======
    """Fetch every catalogue URL and return (flat app list, catalogue error count)."""
>>>>>>> origin/main
    apps = []
    errors = 0
    for raw_url in _BITBUCKET_CATALOGUE_URLS.split(','):
        url = raw_url.strip()
        if not url:
            continue
<<<<<<< HEAD
        context = _catalogue_context_from_url(url)
        if not context.product_team or not context.environment:
            logger.warning(
                json.dumps({
                    'status': 'warning',
                    'message': 'Could not derive Jenkins parameters from catalogue filename',
                    'catalogue_filename': context.filename,
                    'url': url,
                })
            )
        try:
            catalogue = _fetch_catalogue(url, token)
            if catalogue and isinstance(catalogue.get('apps'), list):
                for app in catalogue['apps']:
                    apps.append({
                        'app': app,
                        'catalogue': context,
                    })
=======
        try:
            catalogue = _fetch_catalogue(url, token)
            if catalogue and isinstance(catalogue.get('apps'), list):
                apps.extend(catalogue['apps'])
>>>>>>> origin/main
            else:
                logger.warning(
                    json.dumps({
                        'status': 'warning',
                        'message': 'Catalogue has no valid apps list',
                        'url': url,
                    })
                )
                errors += 1
        except Exception as exc:
            logger.error(
                json.dumps({
                    'status': 'error',
                    'message': 'Failed to fetch catalogue',
                    'url': url,
                    'error': str(exc),
                })
            )
            errors += 1
    return apps, errors


<<<<<<< HEAD
def _catalogue_context_from_url(url: str) -> CatalogueContext:
    """Derive Jenkins PRODUCT_TEAM and ENVIRONMENT from a catalogue URL path."""
    parsed = urlparse(url)
    filename = unquote(os.path.basename(parsed.path))
    match = _CATALOGUE_FILE_RE.fullmatch(filename)
    if not match:
        return CatalogueContext(
            product_team=None,
            environment=None,
            url=url,
            filename=filename,
        )
    return CatalogueContext(
        product_team=match.group('product_team'),
        environment=match.group('environment'),
        url=url,
        filename=filename,
    )


=======
>>>>>>> origin/main
def _fetch_catalogue(url: str, token: str) -> dict:
    """HTTP GET a raw Bitbucket catalogue URL with Bearer auth."""
    response = requests.get(
        url,
        headers={'Authorization': f'Bearer {token}'},
        timeout=30,
    )
    response.raise_for_status()
    return yaml.safe_load(response.text)


def _assume_spoke_role(sts_client, account_id: str, account_name: str):
    """
    Assume CertLifecycleRole in the target spoke account.

    Returns a Secrets Manager client scoped to the spoke account.
    Temporary credentials are consumed immediately and never logged.
    """
    role_arn = f'arn:aws:iam::{account_id}:role/{_SPOKE_ROLE_NAME}'
    session_name = f'cert-expiry-{account_name}'[:64]
    response = sts_client.assume_role(
        RoleArn=role_arn,
        RoleSessionName=session_name,
        DurationSeconds=900,
    )
    creds = response['Credentials']
    return boto3.client(
        'secretsmanager',
        region_name=_AWS_REGION,
        aws_access_key_id=creds['AccessKeyId'],
        aws_secret_access_key=creds['SecretAccessKey'],
        aws_session_token=creds['SessionToken'],
    )


def _get_certificate_pem(sm_client, secret_path: str) -> str:
    """
    Read the Secrets Manager secret and return only the 'certificate' field.

    The full SecretString (which contains private_key, ca_chain, etc.)
    is parsed in memory and never logged or stored beyond this function.
    """
    response = sm_client.get_secret_value(SecretId=secret_path)
    payload = json.loads(response['SecretString'])
    return payload['certificate']


def _parse_pem_expiry_epoch(certificate_pem: str) -> int:
    """Parse the expiry timestamp from the actual PEM certificate."""
    cert = x509.load_pem_x509_certificate(certificate_pem.encode('utf-8'))
    return int(cert.not_valid_after_utc.timestamp())


def _days_left(expiry_epoch: int) -> tuple[int, datetime.datetime]:
    """
    Calculate days remaining until expiry.

    Returns (days, expiry_dt). days is negative for expired certificates.
    Uses floor division via timedelta.days, so 29.9 days remaining -> 29.
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    expiry_dt = datetime.datetime.fromtimestamp(expiry_epoch, tz=datetime.timezone.utc)
    return (expiry_dt - now).days, expiry_dt


<<<<<<< HEAD
def _check_app(app_record: dict, sts_client, sns_client, sm_client) -> dict:
    """
    Run the full expiry check for one catalogue entry.

    Returns a routing result with status 'ok', 'renewal_needed', or
    'p1_action_required', plus optional Jenkins trigger status.
    """
    app = app_record['app']
    catalogue = app_record['catalogue']
=======
def _check_app(app: dict, sts_client, sns_client) -> str:
    """
    Run the full expiry check for one catalogue entry.

    Returns a status string: 'ok', 'renewal_needed', or 'p1_action_required'.
    """
>>>>>>> origin/main
    app_name = app['name']
    account_id = app['deployment']['account_id']
    account_name = app['deployment']['account_name']
    secret_path = f'/slug/certs/{app_name}'

    spoke_sm = _assume_spoke_role(sts_client, account_id, account_name)
    cert_pem = _get_certificate_pem(spoke_sm, secret_path)

    expiry_epoch = _parse_pem_expiry_epoch(cert_pem)
    days, expiry_dt = _days_left(expiry_epoch)

<<<<<<< HEAD
    return _route(
        app_name,
        account_id,
        account_name,
        days,
        expiry_dt,
        sns_client,
        sm_client,
        catalogue,
    )
=======
    return _route(app_name, account_id, account_name, days, expiry_dt, sns_client)
>>>>>>> origin/main


def _route(
    app_name: str,
    account_id: str,
    account_name: str,
    days: int,
    expiry_dt: datetime.datetime,
    sns_client,
<<<<<<< HEAD
    sm_client,
    catalogue: CatalogueContext,
) -> dict:
=======
) -> str:
>>>>>>> origin/main
    expiry_iso = expiry_dt.strftime('%Y-%m-%dT%H:%M:%SZ')

    if days > 30:
        logger.info(
            json.dumps({
                'status': 'ok',
                'app_name': app_name,
                'account_name': account_name,
                'days_left': days,
                'expiry_date': expiry_iso,
            })
        )
<<<<<<< HEAD
        return {'status': 'ok'}

    if 15 <= days <= 30:
        jenkins_result = _trigger_jenkins_with_guardrails(
            sm_client,
            app_name,
            catalogue,
        )
        subject, body = _build_renewal_message(
            app_name,
            account_id,
            account_name,
            days,
            expiry_iso,
            catalogue,
            jenkins_result,
=======
        return 'ok'

    if 15 <= days <= 30:
        subject, body = _build_renewal_message(
            app_name, account_id, account_name, days, expiry_iso
>>>>>>> origin/main
        )
        sns_client.publish(
            TopicArn=_CERT_RENEWAL_TOPIC_ARN,
            Subject=subject,
            Message=body,
        )
        logger.info(
            json.dumps({
                'status': 'renewal_needed',
                'app_name': app_name,
                'account_name': account_name,
                'days_left': days,
                'expiry_date': expiry_iso,
<<<<<<< HEAD
                'jenkins_status': jenkins_result['status'],
                'jenkins_message': jenkins_result['message'],
            })
        )
        return {
            'status': 'renewal_needed',
            'jenkins_status': jenkins_result['status'],
        }

    # days <= 14, including expired (negative days)
    subject, body = _build_p1_message(
        app_name, account_id, account_name, days, expiry_iso, catalogue
=======
            })
        )
        return 'renewal_needed'

    # days <= 14, including expired (negative days)
    subject, body = _build_p1_message(
        app_name, account_id, account_name, days, expiry_iso
>>>>>>> origin/main
    )
    sns_client.publish(
        TopicArn=_CERT_P1_ALERT_TOPIC_ARN,
        Subject=subject,
        Message=body,
    )
    logger.info(
        json.dumps({
            'status': 'p1_action_required',
            'app_name': app_name,
            'account_name': account_name,
            'days_left': days,
            'expiry_date': expiry_iso,
        })
    )
<<<<<<< HEAD
    return {'status': 'p1_action_required'}


def _trigger_jenkins_with_guardrails(
    sm_client,
    app_name: str,
    catalogue: CatalogueContext,
) -> dict:
    """
    Trigger the Jenkins issuance job unless a matching build is queued/running.

    Failures are intentionally not persisted. If the certificate is still in the
    renewal window tomorrow, the next scheduled Lambda run will retry.
    """
    if not catalogue.product_team or not catalogue.environment:
        return {
            'status': 'jenkins_trigger_failed',
            'message': (
                'missing PRODUCT_TEAM or ENVIRONMENT derived from catalogue '
                f'filename {catalogue.filename}'
            ),
        }
    if not _JENKINS_TRIGGER_SECRET_ID:
        return {
            'status': 'jenkins_trigger_failed',
            'message': 'JENKINS_TRIGGER_SECRET_ID is not configured',
        }

    parameters = {
        'PRODUCT_TEAM': catalogue.product_team,
        'ENVIRONMENT': catalogue.environment,
        'APP_NAME': app_name,
    }

    try:
        session = _build_jenkins_session(sm_client)
        job_url = _normalise_jenkins_job_url(_JENKINS_JOB_URL)
        base_url = _jenkins_base_url(job_url)

        inflight, reason = _jenkins_has_matching_inflight_build(
            session,
            base_url,
            job_url,
            parameters,
        )
        if inflight:
            logger.info(
                json.dumps({
                    'status': 'jenkins_skipped',
                    'app_name': app_name,
                    'reason': reason,
                    'product_team': catalogue.product_team,
                    'environment': catalogue.environment,
                })
            )
            return {
                'status': 'jenkins_skipped',
                'message': reason,
            }

        queued_url = _jenkins_build_with_parameters(
            session,
            base_url,
            job_url,
            parameters,
        )
        logger.info(
            json.dumps({
                'status': 'jenkins_triggered',
                'app_name': app_name,
                'product_team': catalogue.product_team,
                'environment': catalogue.environment,
                'queue_url': queued_url or '',
            })
        )
        return {
            'status': 'jenkins_triggered',
            'message': queued_url or 'Jenkins accepted buildWithParameters request',
        }
    except Exception as exc:
        logger.error(
            json.dumps({
                'status': 'jenkins_trigger_failed',
                'app_name': app_name,
                'product_team': catalogue.product_team,
                'environment': catalogue.environment,
                'error': str(exc),
            })
        )
        return {
            'status': 'jenkins_trigger_failed',
            'message': str(exc),
        }


def _build_jenkins_session(sm_client) -> requests.Session:
    """Build an authenticated Jenkins HTTP session from Secrets Manager."""
    username, token = _get_jenkins_credentials(sm_client)
    session = requests.Session()
    session.auth = (username, token)
    return session


def _get_jenkins_credentials(sm_client) -> tuple[str, str]:
    """
    Retrieve Jenkins trigger credentials from Secrets Manager. Never logged.

    Expected SecretString JSON:
      {"username":"<jenkins-user>","api_token":"<jenkins-api-token>"}
    The token key is also accepted as "token" for operator convenience.
    """
    response = sm_client.get_secret_value(SecretId=_JENKINS_TRIGGER_SECRET_ID)
    payload = json.loads(response['SecretString'])
    username = payload.get('username')
    token = payload.get('api_token') or payload.get('token')
    if not username or not token:
        raise RuntimeError(
            'Jenkins trigger secret must contain username and api_token'
        )
    return username, token


def _normalise_jenkins_job_url(job_url: str) -> str:
    parsed = urlparse(job_url)
    if parsed.scheme not in ('http', 'https') or not parsed.netloc:
        raise RuntimeError('JENKINS_JOB_URL must be an absolute HTTP(S) URL')
    return job_url.rstrip('/')


def _jenkins_base_url(job_url: str) -> str:
    parsed = urlparse(job_url)
    return f'{parsed.scheme}://{parsed.netloc}'


def _jenkins_has_matching_inflight_build(
    session: requests.Session,
    base_url: str,
    job_url: str,
    parameters: dict,
) -> tuple[bool, str | None]:
    queue_match = _jenkins_queue_has_matching_item(
        session,
        base_url,
        job_url,
        parameters,
    )
    if queue_match:
        return True, queue_match

    running_match = _jenkins_job_has_matching_running_build(
        session,
        job_url,
        parameters,
    )
    if running_match:
        return True, running_match

    return False, None


def _jenkins_queue_has_matching_item(
    session: requests.Session,
    base_url: str,
    job_url: str,
    parameters: dict,
) -> str | None:
    response = session.get(
        f'{base_url}/queue/api/json',
        params={'tree': 'items[id,task[url],actions[parameters[name,value]]]'},
        timeout=15,
    )
    response.raise_for_status()
    job_url_normalised = job_url.rstrip('/') + '/'

    for item in response.json().get('items', []):
        task_url = (item.get('task') or {}).get('url', '')
        if task_url.rstrip('/') + '/' != job_url_normalised:
            continue
        if _jenkins_parameters_match(item.get('actions', []), parameters):
            return f'matching Jenkins queue item {item.get("id")}'

    return None


def _jenkins_job_has_matching_running_build(
    session: requests.Session,
    job_url: str,
    parameters: dict,
) -> str | None:
    response = session.get(
        f'{job_url}/api/json',
        params={
            'tree': (
                'builds[number,url,building,actions[parameters[name,value]]]'
            )
        },
        timeout=15,
    )
    response.raise_for_status()

    for build in response.json().get('builds', [])[:20]:
        if not build.get('building'):
            continue
        if _jenkins_parameters_match(build.get('actions', []), parameters):
            return f'matching Jenkins running build {build.get("number")}'

    return None


def _jenkins_parameters_match(actions: list, expected: dict) -> bool:
    actual = {}
    for action in actions or []:
        for parameter in action.get('parameters') or []:
            name = parameter.get('name')
            if name:
                actual[name] = str(parameter.get('value', ''))

    return all(actual.get(name) == str(value) for name, value in expected.items())


def _jenkins_build_with_parameters(
    session: requests.Session,
    base_url: str,
    job_url: str,
    parameters: dict,
) -> str | None:
    headers = _jenkins_crumb_header(session, base_url)
    response = session.post(
        f'{job_url}/buildWithParameters',
        data=parameters,
        headers=headers,
        timeout=15,
        allow_redirects=False,
    )
    if response.status_code in (200, 201, 202):
        return response.headers.get('Location')

    if response.status_code in (302, 303):
        location = response.headers.get('Location', '')
        if _jenkins_redirect_is_expected(location, base_url, job_url):
            return location
        raise RuntimeError(
            f'Jenkins trigger returned unexpected redirect to {location or "<empty>"}'
        )

    raise RuntimeError(
        f'Jenkins trigger failed with HTTP {response.status_code}'
    )


def _jenkins_redirect_is_expected(location: str, base_url: str, job_url: str) -> bool:
    if not location:
        return False

    parsed = urlparse(location)
    if parsed.scheme or parsed.netloc:
        normalised = location.rstrip('/') + '/'
        base = base_url.rstrip('/') + '/'
    else:
        normalised = f'{base_url.rstrip("/")}/{location.lstrip("/")}'.rstrip('/') + '/'
        base = base_url.rstrip('/') + '/'

    job = re.escape(job_url.rstrip('/') + '/')
    return (
        normalised.startswith(f'{base}queue/item/')
        or re.fullmatch(f'{job}[0-9]+/.*', normalised) is not None
    )


def _jenkins_crumb_header(session: requests.Session, base_url: str) -> dict:
    response = session.get(f'{base_url}/crumbIssuer/api/json', timeout=15)
    if response.status_code == 404:
        return {}
    response.raise_for_status()
    payload = response.json()
    field = payload.get('crumbRequestField')
    crumb = payload.get('crumb')
    if not field or not crumb:
        return {}
    return {field: crumb}
=======
    return 'p1_action_required'
>>>>>>> origin/main


def _build_renewal_message(
    app_name: str,
    account_id: str,
    account_name: str,
    days_left: int,
    expiry_date: str,
<<<<<<< HEAD
    catalogue: CatalogueContext,
    jenkins_result: dict,
=======
>>>>>>> origin/main
) -> tuple[str, str]:
    subject = f'[CERT RENEWAL NEEDED] {app_name} expires in {days_left} days'
    subject = subject[:100]
    body = (
        f'Certificate renewal is required.\n\n'
        f'Application:         {app_name}\n'
        f'Account name:        {account_name}\n'
        f'Account ID:          {account_id}\n'
        f'Current expiry date: {expiry_date}\n'
        f'Days remaining:      {days_left}\n\n'
        f'Jenkins renewal job: {_JENKINS_JOB_NAME}\n'
        f'Jenkins job URL:     {_JENKINS_JOB_URL}\n'
<<<<<<< HEAD
        f'PRODUCT_TEAM:        {catalogue.product_team or "unknown"}\n'
        f'ENVIRONMENT:         {catalogue.environment or "unknown"}\n'
        f'APP_NAME parameter:  {app_name}\n\n'
        f'Auto-trigger status: {jenkins_result["status"]}\n'
        f'Auto-trigger detail: {jenkins_result["message"]}\n\n'
        f'Required action:\n'
        f'Confirm the Jenkins job completes and the Secrets Manager secret is updated. '
        f'If auto-trigger failed or was skipped unexpectedly, run the Jenkins '
        f'certificate issuance job manually using the parameters above.\n\n'
=======
        f'APP_NAME parameter:  {app_name}\n\n'
        f'Required action:\n'
        f'Run the Jenkins certificate issuance job using the APP_NAME value above.\n\n'
>>>>>>> origin/main
        f'Runbook:\n'
        f'{_RUNBOOK_URL}\n'
    )
    return subject, body


def _build_p1_message(
    app_name: str,
    account_id: str,
    account_name: str,
    days_left: int,
    expiry_date: str,
<<<<<<< HEAD
    catalogue: CatalogueContext,
=======
>>>>>>> origin/main
) -> tuple[str, str]:
    if days_left < 0:
        subject = (
            f'[CERT P1 - ACTION REQUIRED] {app_name} '
            f'certificate expired {abs(days_left)} days ago'
        )
    else:
        subject = f'[CERT P1 - ACTION REQUIRED] {app_name} expires in {days_left} days'
    subject = subject[:100]

    body = (
        f'P1 certificate action is required.\n\n'
        f'Application:         {app_name}\n'
        f'Account name:        {account_name}\n'
        f'Account ID:          {account_id}\n'
        f'Current expiry date: {expiry_date}\n'
        f'Days remaining:      {days_left}\n\n'
        f'Jenkins renewal job: {_JENKINS_JOB_NAME}\n'
        f'Jenkins job URL:     {_JENKINS_JOB_URL}\n'
<<<<<<< HEAD
        f'PRODUCT_TEAM:        {catalogue.product_team or "unknown"}\n'
        f'ENVIRONMENT:         {catalogue.environment or "unknown"}\n'
=======
>>>>>>> origin/main
        f'APP_NAME parameter:  {app_name}\n\n'
        f'Required action:\n'
        f'1. Run the Jenkins certificate issuance job immediately.\n'
        f'2. Confirm the Secrets Manager secret has been updated.\n'
        f'3. Coordinate application restart/reload with the owning team if required.\n\n'
        f'Runbook:\n'
        f'{_RUNBOOK_URL}\n'
    )
    return subject, body
