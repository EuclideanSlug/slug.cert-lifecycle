# SCIP Certificate Lifecycle — Certificate Catalogue

## Purpose

The certificate catalogue is the single source of truth for every application enrolled in the SCIP certificate lifecycle process.

Each catalogue entry defines:

- the application name and certificate parameters (common name, SANs, TTL)
- the target AWS spoke account
- the deployment type (EC2 or ECS)
- the activation behaviour and maintenance window for Phase 2

Every other component — the Jenkins issuance pipeline, the shared library helper, and the expiry checker Lambda — reads these files to determine what to do and where.

---

## Directory structure

Catalogue files live under:

```
scip/cert-lifecycle/certs/
```

---

## File naming convention

```
PTx-<env>-certs.yml
```

Where:

- `PTx` is the product team identifier, for example `PT2`, `PT3`, `PT5`
- `env` is the environment: `dev`, `test`, `preprod`, or `prod`

Examples:

```
PT2-dev-certs.yml
PT2-test-certs.yml
PT2-preprod-certs.yml
PT2-prod-certs.yml
PT5-preprod-certs.yml
```

One file per product team per environment. Add a new file when a new product team or environment is enrolled.

---

## Application naming convention

The `name` field must be globally unique and must follow:

```
{application}-{account_name}
```

The `deployment.account_name` value must match the suffix after the final `-` in `name`.

Valid:

```yaml
name: b2bi-preprodc
deployment:
  account_name: preprodc
```

Invalid (suffix mismatch):

```yaml
name: b2bi-preprodc
deployment:
  account_name: devc
```

Account name examples: `devc`, `testc`, `preprodc`, `prodc`.

Application name examples: `b2bi-devc`, `datapower-high-preprodc`, `ibm-b2bi-prodc`.

---

## Secret path convention

Each application's certificate is stored in the target spoke account Secrets Manager under:

```
/scip/certs/{name}
```

Where `{name}` is the `name` field from the catalogue entry.

Example: an entry with `name: b2bi-preprodc` produces:

```
/scip/certs/b2bi-preprodc
```

Do not append the account name a second time. The following is incorrect:

```
/scip/certs/b2bi-preprodc-preprodc   ← WRONG
```

---

## YAML schema

Each catalogue file must contain a top-level `apps` list. Every item in the list is one enrolled application.

### Minimal EC2 entry

```yaml
apps:
  - name: b2bi-preprodc
    common_name: b2bi.c0081-preprodc.local
    sans: []
    ttl: 2160h
    deployment:
      type: ec2
      account_id: '<account-id>'
      account_name: preprodc
    activation: maintenance-window
    maintenance_window: sun:02:00-04:00
```

### Minimal ECS entry

```yaml
apps:
  - name: datapower-high-preprodc
    common_name: dp-high.c0081-preprodc.local
    sans: []
    ttl: 2160h
    deployment:
      type: ecs
      account_id: '<account-id>'
      account_name: preprodc
      cluster: c0081-preprodc-DP-high
      service: c0081-preprodc-DP-high-service
    activation: rolling
    maintenance_window: mon-fri:22:00-06:00
```

### Required fields

Every entry must contain:

| Field | Description |
|---|---|
| `name` | Globally unique enrolled app name. Must follow `{application}-{account_name}`. |
| `common_name` | Certificate common name requested from Vault. |
| `sans` | List of subject alternative names. Use `[]` if none. |
| `ttl` | Certificate TTL. Standard value is `2160h` (90 days). |
| `deployment.type` | `ec2` or `ecs`. |
| `deployment.account_id` | AWS spoke account ID as a quoted string. |
| `deployment.account_name` | Account/environment suffix, for example `devc`, `preprodc`, `prodc`. |
| `activation` | Phase 2 activation behaviour. Required in Phase 1 but not acted on. |
| `maintenance_window` | Phase 2 maintenance window. Required in Phase 1 but not acted on. |

ECS entries must also include:

| Field | Description |
|---|---|
| `deployment.cluster` | ECS cluster name. |
| `deployment.service` | ECS service name. |

### Deployment types

| Type | When to use |
|---|---|
| `ec2` | Application runs on EC2. Certificate is consumed by the instance at startup. |
| `ecs` | Application runs as an ECS service. Certificate is consumed by the container. |

---

## TTL standard

All certificates use a TTL of `2160h` (90 days). Do not use a different value unless a specific application requirement has been agreed with the security team.

The expiry checker Lambda routes alerts based on actual PEM expiry parsed from the certificate stored in Secrets Manager:

| Days remaining | Action |
|---|---|
| > 30 | Log only — no alert |
| 15–30 | Renewal-required notification via SNS |
| ≤ 14 (including expired) | P1 action-required notification via SNS |

---

## How to add a new application

1. Identify the correct catalogue file for the product team and environment, for example `PT2-preprod-certs.yml`. Create the file if it does not exist, following the naming convention.

2. Add a new entry to the `apps` list following the schema above.

3. Use a `name` that follows `{application}-{account_name}` and is unique across the file.

4. Set `deployment.account_id` to the AWS account ID of the target spoke account (quoted string).

5. Confirm `deployment.account_name` matches the suffix of `name`.

6. Set `deployment.type` to `ec2` or `ecs`. For ECS, add `deployment.cluster` and `deployment.service`.

7. Leave `ttl` as `2160h` unless a specific deviation has been agreed.

8. Set `activation` and `maintenance_window` to appropriate values. These are not acted on in Phase 1.

9. Open a pull request. The PR must be reviewed by at least one other team member before merge.

10. After merge, run the Jenkins cert-issuance pipeline with:
    - `PRODUCT_TEAM` = the PTx value
    - `ENVIRONMENT` = the environment
    - `APP_NAME` = the `name` value from the new entry

---

## How Jenkins uses the catalogue

The Jenkins cert-issuance pipeline reads the catalogue file selected by the `PRODUCT_TEAM` and `ENVIRONMENT` parameters:

```
scip/cert-lifecycle/certs/${PRODUCT_TEAM}-${ENVIRONMENT}-certs.yml
```

If `APP_NAME` is provided, the pipeline finds and processes exactly one matching entry. If `APP_NAME` is empty, the pipeline processes all entries sequentially.

For each entry the pipeline calls `issueCertificate(app)` from `scip-platform-lib`, which:

1. Validates required fields.
2. Derives the secret path as `/scip/certs/{app.name}`.
3. Assumes `jagent-ec2-role` in the spoke account.
4. Invokes the `universal-vault-cert-issuer` Ansible role.
5. The role writes the issued certificate to `/scip/certs/{app.name}` in the spoke account Secrets Manager, creating it if absent or writing a new version if it exists.

---

## How the expiry checker Lambda uses the catalogue

The expiry checker Lambda runs on a schedule in the shared services account. It:

1. Reads catalogue files from the Bitbucket API using a token stored in shared-account Secrets Manager.
2. Iterates every enrolled application.
3. Assumes `CertLifecycleRole` in the relevant spoke account.
4. Reads `/scip/certs/{app.name}` from that spoke account's Secrets Manager.
5. Extracts the `certificate` field and parses actual PEM expiry using the Python `cryptography` library.
6. Routes the result to log-only, renewal SNS, or P1 SNS based on days remaining.
7. Continues processing if an individual application fails.

The Lambda reads `deployment.account_id` and `deployment.account_name` directly from each catalogue entry. No separate configuration is required.

---

## Ansible role variables

The `universal-vault-cert-issuer` role has the following defaults (defined in `ansible/roles/universal-vault-cert-issuer/defaults/main.yml`):

| Variable | Default | Description |
| --- | --- | --- |
| `aws_region` | `eu-west-2` | AWS region for Secrets Manager operations. |
| `vault_pki_path` | `pki` | Mount path of the Vault PKI secrets engine. |
| `vault_pki_role` | `internal-tls` | Vault PKI role used for certificate issuance. |
| `sans` | `[]` | List of subject alternative names. |

To override `vault_pki_path` or `vault_pki_role` for a specific run, pass them as Ansible extra vars:

```
ansible-playbook scip/cert-lifecycle/ansible/playbooks/issue-certificate.yml \
    --extra-vars @vars.json \
    --extra-vars '{"vault_pki_path": "pki_internal", "vault_pki_role": "my-role"}'
```

---

## Lambda configuration (expiry checker)

The expiry checker Lambda (`scip/cert-lifecycle/lambda/expiry_checker/handler.py`) requires the following configuration when deployed.

### Required environment variables

| Variable | Description |
| --- | --- |
| `AWS_REGION` | AWS region for all AWS API calls, e.g. `eu-west-2`. |
| `BITBUCKET_TOKEN_SECRET_ID` | Secrets Manager secret ID holding the Bitbucket API token. Expected format: `{"token": "<value>"}`. |
| `BITBUCKET_CATALOGUE_URLS` | Comma-separated list of raw Bitbucket file URLs for the catalogue YAML files to process. |
| `SPOKE_ROLE_NAME` | IAM role name to assume in each spoke account, e.g. `CertLifecycleRole`. |
| `CERT_RENEWAL_TOPIC_ARN` | ARN of the SNS topic for renewal notifications (15–30 days remaining). |
| `CERT_P1_ALERT_TOPIC_ARN` | ARN of the SNS topic for P1 alerts (≤14 days remaining, including expired). |
| `JENKINS_JOB_NAME` | Jenkins job name included in notification bodies. |
| `JENKINS_JOB_URL` | Jenkins job URL included in notification bodies. |
| `RUNBOOK_URL` | Runbook URL included in notification bodies. |

### Recommended Lambda settings

| Setting | Recommended value |
| --- | --- |
| Timeout | 300 seconds (5 minutes) minimum. Scale up with the number of enrolled apps. |
| Memory | 256 MB minimum. |
| Runtime | Python 3.12 (or 3.9+). |

### Packaging

The `cryptography` dependency includes native (C) components and must be compiled in a Lambda-compatible environment before packaging:

- Build using the official Lambda container image: `public.ecr.aws/lambda/python:<runtime>`
- Or build on an Amazon Linux 2 / AL2023 EC2 instance

### Schedule

Deploy an EventBridge Scheduler rule to invoke the Lambda on a recurring schedule. A daily schedule (e.g. `rate(1 day)`) is recommended so alerts are raised promptly when a certificate crosses a threshold.

---

## Terraform infrastructure

The AWS infrastructure for Phase 1 is managed using Terraform. Source lives under `terraform/` at the repository root.

### What Terraform manages

| Resource | Account |
| --- | --- |
| Expiry checker Lambda, IAM execution role, CloudWatch log group | Shared-services |
| `scip-cert-renewal` and `scip-cert-p1-alerts` SNS topics | Shared-services |
| Optional Bitbucket token Secrets Manager secret container (metadata only) | Shared-services |
| `CertLifecycleRole` cross-account role with read-only cert access | Each spoke account |

Terraform does **not** manage live certificate secret values, private keys, PEM bodies, or the Bitbucket token value.

### Deployment overview

Two root modules are applied independently. Apply shared-services first, then spoke once per account:

```bash
# Step 1 — shared-services account
cd terraform/shared-services
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — set spoke_account_ids, catalogue_urls, Jenkins URLs, runbook_url
terraform init && terraform plan -out=tfplan && terraform apply tfplan

# Note the Lambda execution role ARN — required for spoke applies
terraform output lambda_execution_role_arn

# Step 2 — insert Bitbucket token (never managed by Terraform)
aws secretsmanager put-secret-value \
  --secret-id "/scip/cert-lifecycle/bitbucket-token" \
  --secret-string '{"token":"<token>"}' \
  --region eu-west-2

# Step 3 — each spoke account (repeat per account, switching credentials)
cd terraform/spoke
cp terraform.tfvars.example terraform.tfvars
# Edit terraform.tfvars — set spoke_account_id and lambda_execution_role_arn from Step 1
terraform init && terraform plan -out=tfplan && terraform apply tfplan
```

After both applies, complete these manual steps:

- Create an EventBridge schedule rule targeting the Lambda ARN (`terraform output lambda_function_arn`).
- Subscribe to both SNS topics (`terraform output cert_renewal_topic_arn` and `cert_p1_alert_topic_arn`).

### Lambda packaging

The `cryptography` dependency contains native components and must be built in a Lambda-compatible environment before packaging:

```bash
docker run --rm \
  -v "$(pwd)/scip/cert-lifecycle/lambda/expiry_checker":/src \
  -v "$(pwd)/dist":/out \
  public.ecr.aws/lambda/python:3.12 \
  bash -c "pip install -r /src/requirements.txt -t /tmp/pkg && cp /src/*.py /tmp/pkg/ && cd /tmp/pkg && zip -r /out/expiry_checker.zip ."
```

Pass the zip to Terraform via `lambda_s3_bucket` + `lambda_s3_key` (recommended for CI) or `lambda_package_path` (local path).

### jagent-ec2-role permissions

`jagent-ec2-role` is externally owned and is not managed by this Terraform state. The required policies are:

- `scip/cert-lifecycle/iam/spoke-account-jagent-policy.json` — Secrets Manager write permissions
- `scip/cert-lifecycle/iam/spoke-account-jagent-kms-addon.json` — KMS addon (customer-managed keys only)

Apply these through whichever process owns that role. Do not set `enable_issuer_permissions = true` in the spoke module unless this Terraform state explicitly owns `jagent-ec2-role`.

### Ongoing operations

| Task | Action |
| --- | --- |
| Update Lambda code | Build new zip, upload to S3, update `lambda_s3_object_version`, re-apply shared-services |
| Add spoke account | Add account ID to `spoke_account_ids` in shared-services tfvars, re-apply, then fresh spoke apply |
| Rotate Bitbucket token | `aws secretsmanager put-secret-value` directly — no Terraform change needed |
| Validate code | `terraform fmt -check -recursive terraform/` and `terraform validate` in each root module |

### Security constraints

- Never import or manage certificate secrets (`/scip/certs/*`) in Terraform state.
- Never set the Bitbucket token value in Terraform variables, locals, or outputs.
- `terraform.tfvars` is gitignored — do not commit it.
- Store Terraform state in an encrypted S3 bucket with DynamoDB locking and restricted access.

---

## Phase 1 limitations

The following are out of scope for Phase 1 and are not implemented:

- Application restart or reload automation
- Automatic Jenkins triggering after expiry detection
- Live application endpoint certificate checking
- Restart-overdue detection
- KDB, JKS, or PKCS12 certificate format conversion
- Vault PKI role changes
- EventBridge scheduling (unless implemented as a separate story)
- DynamoDB alert deduplication

The `activation` and `maintenance_window` fields are present in the catalogue schema to support Phase 2 but are not read or acted on by any Phase 1 component.
