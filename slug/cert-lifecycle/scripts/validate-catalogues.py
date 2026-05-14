#!/usr/bin/env python3
"""
Validate all certificate catalogue YAML files under slug/cert-lifecycle/certs/.

Exit code:
  0 — all catalogues are valid
  1 — one or more validation errors found
"""

import os
import re
import sys
from pathlib import Path

import yaml

CERTS_DIR = Path(__file__).resolve().parent.parent / 'certs'

REQUIRED_APP_FIELDS = [
    'name', 'common_name', 'sans', 'ttl',
    'deployment', 'activation', 'maintenance_window',
]
REQUIRED_DEPLOYMENT_FIELDS = ['type', 'account_id', 'account_name']
VALID_DEPLOYMENT_TYPES = ['ec2', 'ecs']
ECS_REQUIRED_FIELDS = ['cluster', 'service']
PLACEHOLDER_ACCOUNT_IDS = {'000000000000', '<account-id>'}
APP_NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*-[A-Za-z0-9][A-Za-z0-9_.-]*$')
ACCOUNT_NAME_RE = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]*$')


def validate_catalogue(path, all_names, allow_placeholders=False):
    errors = []
    with open(path) as f:
        try:
            data = yaml.safe_load(f)
        except yaml.YAMLError as exc:
            return [f'{path}: YAML parse error: {exc}']

    if not isinstance(data, dict) or not isinstance(data.get('apps'), list):
        return [f'{path}: must contain a top-level "apps" list']

    for idx, app in enumerate(data['apps']):
        loc = f'{path}[{idx}]'
        if not isinstance(app, dict):
            errors.append(f'{loc}: app entry must be a mapping')
            continue

        name = app.get('name', f'<entry {idx}>')

        for field in REQUIRED_APP_FIELDS:
            if field not in app:
                errors.append(
                    f'{loc} ({name}): missing required field "{field}"'
                )

        dep = app.get('deployment', {})
        if not isinstance(dep, dict):
            errors.append(
                f'{loc} ({name}): "deployment" must be a mapping'
            )
            continue

        for field in REQUIRED_DEPLOYMENT_FIELDS:
            if field not in dep:
                errors.append(
                    f'{loc} ({name}): missing deployment.{field}'
                )

        account_id = str(dep.get('account_id', ''))
        account_name = dep.get('account_name', '')
        dep_type = dep.get('type')

        if not isinstance(name, str) or not APP_NAME_RE.fullmatch(name):
            errors.append(
                f'{loc} ({name}): name must contain only letters, numbers, '
                'dot, underscore, and hyphen, and must include an account suffix'
            )

        if account_name and (
            not isinstance(account_name, str)
            or not ACCOUNT_NAME_RE.fullmatch(account_name)
        ):
            errors.append(
                f'{loc} ({name}): deployment.account_name must contain only '
                'letters, numbers, dot, underscore, and hyphen'
            )

        if account_id in PLACEHOLDER_ACCOUNT_IDS:
            if not allow_placeholders:
                errors.append(
                    f'{loc} ({name}): deployment.account_id is still the '
                    f'placeholder "{account_id}". '
                    f'Replace with the real AWS account ID.'
                )

        if account_id not in PLACEHOLDER_ACCOUNT_IDS and (
            not account_id.isdigit() or len(account_id) != 12
        ):
            errors.append(
                f'{loc} ({name}): deployment.account_id must be a '
                f'12-digit AWS account ID.'
            )

        if dep_type and dep_type not in VALID_DEPLOYMENT_TYPES:
            errors.append(
                f'{loc} ({name}): deployment.type "{dep_type}" is invalid. '
                f'Must be one of: {", ".join(VALID_DEPLOYMENT_TYPES)}'
            )

        if account_name and not name.endswith(f'-{account_name}'):
            errors.append(
                f'{loc} ({name}): name must end with "-{account_name}"'
            )

        if dep_type == 'ecs':
            for field in ECS_REQUIRED_FIELDS:
                if field not in dep:
                    errors.append(
                        f'{loc} ({name}): ECS deployment missing '
                        f'deployment.{field}'
                    )

        if name in all_names:
            errors.append(
                f'{loc}: duplicate app name "{name}" '
                f'(also in {all_names[name]})'
            )
        else:
            all_names[name] = path

    return errors


def main():
    active_paths = sorted(CERTS_DIR.glob('*.yml'))
    example_paths = sorted(CERTS_DIR.glob('*.yml.example'))

    if not active_paths and not example_paths:
        print(
            f'No catalogue files found in {CERTS_DIR}',
            file=sys.stderr,
        )
        sys.exit(1)

    all_names = {}
    all_errors = []

    for path in active_paths:
        errors = validate_catalogue(path, all_names)
        all_errors.extend(errors)

    example_names = {}
    for path in example_paths:
        errors = validate_catalogue(
            path,
            example_names,
            allow_placeholders=True,
        )
        all_errors.extend(errors)

    if all_errors:
        for err in all_errors:
            print(f'ERROR: {err}', file=sys.stderr)
        print(
            f'\n{len(all_errors)} error(s) found across '
            f'{len(paths)} catalogue file(s).',
            file=sys.stderr,
        )
        sys.exit(1)

    print(
        f'OK: {len(active_paths)} active catalogue file(s) validated '
        f'({len(all_names)} enrolled app(s)); '
        f'{len(example_paths)} example catalogue file(s) validated.'
    )


if __name__ == '__main__':
    main()
