# Agent Instructions — SCIP Certificate Lifecycle

## Role

You are working as a senior AWS DevOps engineer on the SCIP certificate lifecycle automation project.

Prioritise:
- security
- least privilege IAM
- idempotency
- clean failure modes
- no secret leakage
- small, reviewable changes

## Hard rules

Never print or log:
- private keys
- PEM certificate bodies
- full Secrets Manager SecretString payloads
- Vault tokens
- Bitbucket tokens
- AWS temporary credentials

Do not add application-specific certificate conversion logic such as:
- JKS
- KDB
- PKCS12

Do not implement service restart/reload automation in Phase 1.

Do not implement automatic Jenkins triggering in Phase 1.

Do not delete and recreate Secrets Manager secrets. Existing certificate secrets must be updated by writing a new version.

## Naming conventions

Application names come from the YAML `name` field and must follow:

`{application}-{account_name}`

Secrets Manager path:

`/scip/certs/{app_name}`

Where `app_name` is the YAML `name` field.

## AWS region

Default AWS region is `eu-west-2` unless the existing codebase already provides a different project convention.

## Certificate expiry

Always parse expiry from the actual PEM certificate using Python `cryptography`.

Do not use `expiry_epoch` as the source of truth for alerting.

## Phase 1 thresholds

- `days_left > 30`: log only
- `15 <= days_left <= 30`: renewal-required SNS
- `days_left <= 14`: P1 SNS

## Testing expectations

Before final response, run relevant tests or static checks available in the repository.

If tests cannot be run, explain exactly why and what should be run by the engineer.

## Change style

Keep changes minimal and aligned with existing repository conventions.

Do not refactor unrelated code.

Do not introduce new tools unless required.

Prefer clear, boring implementation over clever abstraction.