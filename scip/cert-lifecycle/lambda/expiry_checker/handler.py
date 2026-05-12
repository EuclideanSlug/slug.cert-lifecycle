"""
SCIP Certificate Lifecycle — Expiry Checker Lambda

Reads enrolled application certificate catalogue files from Bitbucket, checks
the expiry of each application's certificate stored in spoke account AWS Secrets
Manager, and routes SNS notifications based on days remaining.

Threshold routing:
  days_left > 30          log only
  15 <= days_left <= 30   publish to cert-renewal SNS
  days_left <= 14         publish to cert-p1-alerts SNS  (includes expired)

Safe logging contract: this module never logs private_key, ca_chain, full_chain,
SecretString payloads, Bitbucket tokens, or AWS temporary credentials.

Packaging note: the 'cryptography' dependency includes native components and must
be built in a Lambda-compatible environment (Amazon Linux 2 or AL2023) before
deployment. Use a Lambda layer, container image, or a CI build step that targets
the correct architecture.
"""

import datetime
import json
import logging
import os

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
_RUNBOOK_URL = os.environ['RUNBOOK_URL']


# ── Lambda entry point ─────────────────────────────────────────────────────────

def handler(event, context):  # noqa: ARG001
    counters = {
        'checked': 0,
        'ok': 0,
        'renewal_needed': 0,
        'p1_action_required': 0,
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
        return counters

    apps = _load_all_apps(token)

    for app in apps:
        counters['checked'] += 1
        app_name = app.get('name', '<unknown>')
        try:
            result = _check_app(app, sts_client, sns_client)
            counters[result] += 1
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


def _load_all_apps(token: str) -> list:
    """Fetch every catalogue URL and return a flat list of app entries."""
    apps = []
    for raw_url in _BITBUCKET_CATALOGUE_URLS.split(','):
        url = raw_url.strip()
        if not url:
            continue
        try:
            catalogue = _fetch_catalogue(url, token)
            if catalogue and isinstance(catalogue.get('apps'), list):
                apps.extend(catalogue['apps'])
            else:
                logger.warning(
                    json.dumps({
                        'status': 'warning',
                        'message': 'Catalogue has no valid apps list',
                        'url': url,
                    })
                )
        except Exception as exc:
            logger.error(
                json.dumps({
                    'status': 'error',
                    'message': 'Failed to fetch catalogue',
                    'url': url,
                    'error': str(exc),
                })
            )
    return apps


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


def _check_app(app: dict, sts_client, sns_client) -> str:
    """
    Run the full expiry check for one catalogue entry.

    Returns a status string: 'ok', 'renewal_needed', or 'p1_action_required'.
    """
    app_name = app['name']
    account_id = app['deployment']['account_id']
    account_name = app['deployment']['account_name']
    secret_path = f'/scip/certs/{app_name}'

    spoke_sm = _assume_spoke_role(sts_client, account_id, account_name)
    cert_pem = _get_certificate_pem(spoke_sm, secret_path)

    expiry_epoch = _parse_pem_expiry_epoch(cert_pem)
    days, expiry_dt = _days_left(expiry_epoch)

    return _route(app_name, account_id, account_name, days, expiry_dt, sns_client)


def _route(
    app_name: str,
    account_id: str,
    account_name: str,
    days: int,
    expiry_dt: datetime.datetime,
    sns_client,
) -> str:
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
        return 'ok'

    if 15 <= days <= 30:
        subject, body = _build_renewal_message(
            app_name, account_id, account_name, days, expiry_iso
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
            })
        )
        return 'renewal_needed'

    # days <= 14, including expired (negative days)
    subject, body = _build_p1_message(
        app_name, account_id, account_name, days, expiry_iso
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
    return 'p1_action_required'


def _build_renewal_message(
    app_name: str,
    account_id: str,
    account_name: str,
    days_left: int,
    expiry_date: str,
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
        f'APP_NAME parameter:  {app_name}\n\n'
        f'Required action:\n'
        f'Run the Jenkins certificate issuance job using the APP_NAME value above.\n\n'
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
        f'APP_NAME parameter:  {app_name}\n\n'
        f'Required action:\n'
        f'1. Run the Jenkins certificate issuance job immediately.\n'
        f'2. Confirm the Secrets Manager secret has been updated.\n'
        f'3. Coordinate application restart/reload with the owning team if required.\n\n'
        f'Runbook:\n'
        f'{_RUNBOOK_URL}\n'
    )
    return subject, body
