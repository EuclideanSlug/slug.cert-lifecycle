# SCIP Certificate Lifecycle

SCIP Certificate Lifecycle provides catalogue-driven TLS certificate issuance, renewal, and expiry alerting for applications running across AWS spoke accounts.

The repository contains:

- certificate catalogues under `scip/cert-lifecycle/certs/`
- a Jenkins issuance pipeline in `Jenkinsfile`
- a Jenkins shared-library step in `scip-platform-lib/vars/issueCertificate.groovy`
- an Ansible role that issues certificates from Vault and writes them to AWS Secrets Manager
- an expiry checker Lambda under `scip/cert-lifecycle/lambda/expiry_checker/`
- Terraform for shared-services and spoke-account infrastructure under `terraform/`

## Start here

| Task | Read |
| --- | --- |
| Understand the system | [Architecture](docs/architecture.md) |
| Add or validate a catalogue entry | [Catalogue reference](docs/catalogue-reference.md) |
| Deploy infrastructure | [Deployment](docs/deployment.md) and [Terraform](docs/terraform.md) |
| Respond to alerts or renew a certificate | [Operations runbook](docs/operations-runbook.md) |
| Review original Phase 1 design context | [Archived statement of need](docs/archive/phase-1-statement-of-need.md) |

## Quick model

1. A YAML catalogue entry defines an enrolled application.
2. Jenkins reads the catalogue and calls `issueCertificate(app)`.
3. The shared-library step assumes `jagent-ec2-role` in the spoke account.
4. Ansible issues a PEM certificate from Vault and writes `/scip/certs/{app.name}` in Secrets Manager.
5. A shared-services Lambda reads catalogues from Bitbucket, assumes `CertLifecycleRole` in each spoke account, parses actual PEM certificate expiry, and publishes SNS alerts.

## What Phase 1 does not do

- restart or reload applications
- trigger Jenkins automatically from Lambda
- check live application endpoints
- convert certificates to JKS, KDB, or PKCS12
- manage certificate secret values in Terraform
- create EventBridge schedules or SNS subscriptions in Terraform

## Common commands

```bash
python3 scip/cert-lifecycle/scripts/validate-catalogues.py
make tf-fmt-check
make tf-plan TARGET_TYPE=shared ENVIRONMENT=preprod
make tf-plan TARGET_TYPE=spoke ENVIRONMENT=preprod SPOKE_ACCOUNT_NAME=preprodc
```

The committed catalogue and Terraform `.tfvars.example` files contain placeholders. Copy examples to untracked `.tfvars` files and replace catalogue `deployment.account_id` placeholders before first issuance.
