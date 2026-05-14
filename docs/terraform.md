# Terraform

Terraform manages AWS infrastructure for certificate expiry monitoring and spoke-account read permissions.

## Roots

| Root | Applied in | Purpose |
| --- | --- | --- |
| `terraform/shared-services/` | shared-services account | Lambda, EventBridge Scheduler, SNS, CloudWatch logs, Lambda execution role, optional Bitbucket and Jenkins trigger secret containers |
| `terraform/spoke/` | each spoke account | `CertLifecycleRole`, read policy, optional KMS decrypt, optional jagent write policy |

`shared-services` requires Terraform `>= 1.9.0`. `spoke` requires Terraform `>= 1.3.0`.

Both providers use `allowed_account_ids` as a guardrail. Active AWS credentials must match the target account.

## Backend files

Backend files are operator-created and not committed.

Shared-services path:

```text
terraform/shared-services/envs/<environment>-backend.hcl
```

Spoke path:

```text
terraform/spoke/envs/<environment>-<account>-backend.hcl
```

## Variable files

Copy an example and fill real values:

```bash
cp terraform/shared-services/envs/preprod.tfvars.example \
   terraform/shared-services/envs/preprod.tfvars

cp terraform/spoke/envs/preprod-preprodc.tfvars.example \
   terraform/spoke/envs/preprod-preprodc.tfvars
```

Do not commit filled `.tfvars` files.

## Makefile workflow

```bash
make tf-fmt-check
make tf-init TARGET_TYPE=shared ENVIRONMENT=preprod
make tf-validate TARGET_TYPE=shared ENVIRONMENT=preprod
make tf-plan TARGET_TYPE=shared ENVIRONMENT=preprod
make tf-apply TARGET_TYPE=shared ENVIRONMENT=preprod
```

Spoke example:

```bash
make tf-plan TARGET_TYPE=spoke ENVIRONMENT=preprod SPOKE_ACCOUNT_NAME=preprodc
make tf-apply TARGET_TYPE=spoke ENVIRONMENT=preprod SPOKE_ACCOUNT_NAME=preprodc
```

Destroy requires explicit confirmation:

```bash
make tf-destroy TARGET_TYPE=spoke ENVIRONMENT=dev SPOKE_ACCOUNT_NAME=devc CONFIRM_DESTROY=true
```

The local Makefile passes `-auto-approve` when `AUTO_APPROVE=true` for normal apply. `AUTO_APPROVE=true` is rejected for destroy.

## Jenkins Terraform pipeline

`Jenkinsfile.terraform` exposes:

| Parameter | Values |
| --- | --- |
| `TARGET_TYPE` | `shared` or `spoke` |
| `ACTION` | `plan`, `apply`, or `destroy` |
| `ENVIRONMENT` | `dev`, `test`, `preprod`, `prod` |
| `SPOKE_ACCOUNT_NAME` | required for spokes |
| `TF_VAR_FILE` | optional `.tfvars` override under the selected root's `envs/` directory |
| `AUTO_APPROVE` | skips apply confirmation for normal apply, but is blocked for destroy |

Pipeline flow:

```text
checkout -> parameter validation -> terraform fmt -check -> init -> validate -> plan -> optional confirmation -> apply
```

For Jenkins, `AUTO_APPROVE=true` is not allowed with `ACTION=destroy`; destroy always requires manual confirmation.

## Valid targets

Shared-services applies are only valid for:

| Environment | Account |
| --- | --- |
| `preprod` | preprod |
| `prod` | `prodc` |

Valid spokes:

| Environment | Spokes |
| --- | --- |
| `dev` | `Dev`, `deva`, `devb`, `devc`, `devd`, `deve`, `devf`, `devg` |
| `test` | `testa`, `testb`, `testc`, `testd`, `teste`, `testf`, `testg` |
| `preprod` | `preprod`, `preproda`, `preprodb`, `preprodc`, `preprodd`, `preprode`, `preprodf`, `preprodg` |
| `prod` | `prodc`, `prodd`, `prode`, `prodf`, `prodg`, `prodh`, `prodi`, `prodj` |

`preprod` and `prodc` are dual-purpose shared-services and spoke accounts.

## Inputs and outputs

Important shared-services inputs:

- `shared_account_id`
- `catalogue_urls`
- `spoke_account_ids`
- `lambda_s3_bucket` and `lambda_s3_key`, or `lambda_package_path`
- `jenkins_job_name`
- `jenkins_job_url`
- `jenkins_trigger_secret_name`
- `runbook_url`
- `daily_schedule_expression`
- `daily_schedule_timezone`

Important shared-services outputs:

- `lambda_function_arn`
- `lambda_execution_role_arn`
- `cloudwatch_log_group_name`
- `cert_renewal_topic_arn`
- `cert_p1_alert_topic_arn`
- `bitbucket_token_secret_arn`
- `jenkins_trigger_secret_arn`
- `daily_schedule_name`
- `daily_schedule_arn`

Important spoke inputs:

- `spoke_account_id`
- `lambda_execution_role_arn`
- `kms_key_arns`
- `enable_issuer_permissions`

Only set `enable_issuer_permissions = true` if this Terraform state is allowed to attach policies to `jagent-ec2-role`.

## Lambda environment

Terraform sets:

- `BITBUCKET_TOKEN_SECRET_ID`
- `BITBUCKET_CATALOGUE_URLS`
- `SPOKE_ROLE_NAME`
- `CERT_RENEWAL_TOPIC_ARN`
- `CERT_P1_ALERT_TOPIC_ARN`
- `JENKINS_JOB_NAME`
- `JENKINS_JOB_URL`
- `JENKINS_TRIGGER_SECRET_ID`
- `RUNBOOK_URL`

Terraform intentionally does not set `AWS_REGION`; Lambda provides it at runtime and `handler.py` reads it from the runtime environment.

## Daily schedule

Shared-services Terraform creates an EventBridge Scheduler schedule named `slug-cert-expiry-checker-daily` by default. It runs:

```text
cron(30 7 * * ? *)
```

with `schedule_expression_timezone = "Europe/London"`, so the Lambda runs at 07:30 UK local time across GMT and BST changes.

The schedule invokes the Lambda once. It does not iterate certificates itself; the Lambda loads catalogues, checks actual PEM expiry from Secrets Manager, sends SNS notifications, and triggers Jenkins when a certificate is in the 15-30 day renewal window.

## Jenkins trigger secret

Terraform can create the Secrets Manager secret container `/slug/cert-lifecycle/jenkins-trigger`, but operators must set the value manually:

```json
{"username":"<jenkins-user>","api_token":"<jenkins-api-token>"}
```

The Lambda reads this secret only when it needs to trigger Jenkins. The Jenkins job URL remains a Terraform variable and credentials are not stored in Terraform.

## What Terraform does not manage

- certificate private keys or PEM bodies
- `/slug/certs/*` secret values
- Bitbucket token value
- Jenkins trigger credential value
- catalogue YAML content
- Vault PKI configuration
- Jenkins job configuration
- SNS subscriptions
- application restart or reload

## Troubleshooting

| Symptom | Fix |
| --- | --- |
| `TARGET_TYPE=shared` rejected for dev/test | Use preprod shared services for dev/test monitoring |
| `SPOKE_ACCOUNT_NAME is required` | Provide a valid spoke account name |
| `terraform init` backend error | Create the expected `*-backend.hcl` file |
| `tfplan not found` | Run `make tf-plan` before `make tf-apply` |
| fmt check fails | Run `make tf-fmt` and commit formatting |
| Lambda cannot assume spoke role | Confirm `spoke_account_ids`, `lambda_execution_role_arn`, and spoke trust policy |
| Lambda cannot decrypt a cert secret | Add the relevant KMS key ARN to `kms_key_arns` and re-apply spoke Terraform |
