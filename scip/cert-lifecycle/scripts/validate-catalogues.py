#!/usr/bin/env python3
"""
Validate all certificate catalogue YAML files under scip/cert-lifecycle/certs/.

Exit code:
  0 — all catalogues are valid
  1 — one or more validation errors found
"""

import glob
import os
import sys

import yaml

CERTS_DIR = os.path.join(os.path.dirname(__file__), '..', 'certs')

REQUIRED_APP_FIELDS = [
    'name', 'common_name', 'sans', 'ttl',
    'deployment', 'activation', 'maintenance_window',
]
REQUIRED_DEPLOYMENT_FIELDS = ['type', 'account_id', 'account_name']
VALID_DEPLOYMENT_TYPES = ['ec2', 'ecs']
ECS_REQUIRED_FIELDS = ['cluster', 'service']
PLACEHOLDER_ACCOUNT_ID = '000000000000'


def validate_catalogue(path, all_names):
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

        if account_id == PLACEHOLDER_ACCOUNT_ID:
            errors.append(
                f'{loc} ({name}): deployment.account_id is still the '
                f'placeholder "{PLACEHOLDER_ACCOUNT_ID}". '
                f'Replace with the real AWS account ID.'
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
    pattern = os.path.join(CERTS_DIR, '*.yml')
    paths = sorted(glob.glob(pattern))

    if not paths:
        print(
            f'No catalogue files found in {CERTS_DIR}',
            file=sys.stderr,
        )
        sys.exit(1)

    all_names = {}
    all_errors = []

    for path in paths:
        errors = validate_catalogue(path, all_names)
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
        f'OK: {len(paths)} catalogue file(s) validated. '
        f'{len(all_names)} app(s) enrolled.'
    )


if __name__ == '__main__':
    main()
