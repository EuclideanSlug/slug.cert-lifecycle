# Architecture

Slug Certificate Lifecycle has two workflows: certificate issuance and expiry monitoring.

## Components

```text
Catalogue YAML
  slug/cert-lifecycle/certs/PTx-<env>-certs.yml
        |
        | Jenkins issuance
        v
Jenkinsfile -> issueCertificate(app) -> Ansible -> Vault PKI
        |                                      |
        | assumes jagent-ec2-role              v
        +----------------------------> AWS Secrets Manager
                                      /slug/certs/{app.name}

Shared-services Lambda
  invoked daily by EventBridge Scheduler at 07:30 Europe/London
  reads catalogue URLs from Bitbucket
  assumes CertLifecycleRole in spoke accounts
  reads /slug/certs/{app.name}
  parses PEM expiry with cryptography
  publishes SNS alerts
  triggers Jenkins renewal for 15-30 day certificates
```

## Source of truth

The certificate catalogue is the source of truth for enrolled applications. Each entry defines:

- application name
- certificate common name and SANs
- TTL
- deployment type
- target spoke account
- future activation and maintenance-window metadata

The canonical secret path is:

```text
/slug/certs/{app.name}
```

Do not append the account name again.

## Issuance flow

1. Jenkins runs `Jenkinsfile`.
2. `PRODUCT_TEAM` and `ENVIRONMENT` select `slug/cert-lifecycle/certs/${PRODUCT_TEAM}-${ENVIRONMENT}-certs.yml`.
3. `APP_NAME` selects one app, or an empty value processes all apps sequentially.
4. Jenkins calls `issueCertificate(app)` from `slug-platform-lib`.
5. The helper validates the app, derives `/slug/certs/{app.name}`, and assumes `jagent-ec2-role` in the spoke account.
6. Ansible runs `universal-vault-cert-issuer`.
7. The role issues the certificate from Vault, checks the active AWS account matches `deployment.account_id`, and creates or updates the Secrets Manager secret.

Existing Secrets Manager secrets are updated with a new version. They are not deleted and recreated.

## Expiry monitoring flow

1. EventBridge Scheduler invokes the Lambda once per day at 07:30 `Europe/London`.
2. The Lambda runs in a shared-services account.
3. It reads a Bitbucket token from Secrets Manager.
4. It fetches the configured raw catalogue URLs and derives Jenkins `PRODUCT_TEAM` and `ENVIRONMENT` from catalogue filenames such as `PT2-prod-certs.yml`.
5. For each app, it assumes `CertLifecycleRole` in the target spoke account.
6. It reads `/slug/certs/{app.name}` and extracts only the `certificate` field.
7. It parses expiry from the actual PEM certificate using Python `cryptography`.
8. It routes by days remaining:

| Days remaining | Action |
| --- | --- |
| `> 30` | log only |
| `15..30` | trigger Jenkins renewal with `PRODUCT_TEAM`, `ENVIRONMENT`, and `APP_NAME`, then publish to `slug-cert-renewal` |
| `<= 14` | publish to `slug-cert-p1-alerts` |

`expiry_epoch` is stored for reference only. Alerting is based on the PEM certificate.

Before triggering Jenkins, the Lambda has already checked the current PEM expiry from Secrets Manager. It also checks Jenkins queue and currently running builds for the same `PRODUCT_TEAM`, `ENVIRONMENT`, and `APP_NAME`; if one is already in flight, it skips the duplicate trigger and records that decision in logs and the renewal notification. Failed Jenkins trigger attempts are not stored as durable state, so the next daily run retries if the certificate is still in the renewal window.

## AWS accounts

| Account type | Purpose |
| --- | --- |
| Shared services | Lambda, Lambda execution role, EventBridge Scheduler schedule and scheduler invoke role, SNS topics, CloudWatch log group, Bitbucket token secret container, Jenkins trigger secret container |
| Spoke | `CertLifecycleRole`, optional jagent issuer permissions, certificate secrets consumed by applications |

Preprod shared services can monitor preprod, dev, and test spokes if those spoke account IDs are included in `spoke_account_ids`. Prod shared services runs in `prodc` and monitors prod spokes.

## IAM roles

| Role | Account | Used by | Access |
| --- | --- | --- | --- |
| `jagent-ec2-role` | Spoke | Jenkins issuance | create/update/tag `/slug/certs/*` |
| `CertLifecycleRole` | Spoke | Lambda expiry checker | read `/slug/certs/*` |
| `slug-cert-expiry-checker-role` | Shared services | Lambda runtime | read Bitbucket token and Jenkins trigger secret, assume spoke roles, publish SNS, write logs |
| `slug-cert-expiry-checker-scheduler-role` | Shared services | EventBridge Scheduler | invoke expiry checker Lambda |

Optional KMS permissions are required when certificate secrets use customer-managed keys.

## Out of scope

The certificate lifecycle system does not:

- restart or reload applications
- prove the running app has loaded a renewed certificate
- inspect live endpoints
- convert certificate formats
- provide durable renewal deduplication across Lambda invocations
- manage certificate secret values in Terraform
