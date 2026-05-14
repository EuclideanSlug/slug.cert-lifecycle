# Changelog

All notable changes to slug-platform-lib are recorded here.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.0.0/).
Versioning: [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.1] - 2026-05-14

### Changed

- Hardened `vars/issueCertificate.groovy` by validating safe catalogue app names,
  validating 12-digit AWS account IDs, using a random temporary vars filename, and
  shell-quoting temporary file paths passed to `ansible-playbook` and cleanup.

## [1.0.0] - 2026-05-12

### Added

- `vars/issueCertificate.groovy`: Jenkins shared library step for Slug Phase 1 certificate
  issuance and renewal.
  - Accepts a single `Map app` representing one entry from a `PTx-<env>-certs.yml` catalogue file.
  - Validates all required fields (`name`, `common_name`, `ttl`, `deployment.type`,
    `deployment.account_id`, `deployment.account_name`).
  - Validates `deployment.type` is `ec2` or `ecs`.
  - Validates `app.name` ends with `-{deployment.account_name}`.
  - Validates ECS-specific fields (`deployment.cluster`, `deployment.service`) when type is `ecs`.
  - Derives `secret_name` as `/slug/certs/{app.name}`.
  - Assumes `jagent-ec2-role` in the target spoke account via `withAWS`.
  - Writes a non-secret Ansible vars file and invokes `universal-vault-cert-issuer` via
    `ansible-playbook`.
  - Removes the vars file in a `finally` block.
  - Never logs certificate material, private keys, or secret payloads.
