# Terraform

Terraform manages AWS infrastructure for certificate expiry monitoring and spoke-account read permissions.

## Roots

| Root | Applied in | Purpose |
| --- | --- | --- |
| `terraform/shared-services/` | shared-services account | Lambda, SNS, CloudWatch logs, Lambda execution role, optional Bitbucket token secret container |
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

The local Makefile passes `-auto-approve` when `AUTO_APPROVE=true`, including destroy if `CONFIRM_DESTROY=true` is also set. Use that combination only with deliberate operator intent.

## Jenkins Terraform pipeline

`Jenkinsfile.terraform` exposes:

| Parameter | Values |
| --- | --- |
| `TARGET_TYPE` | `shared` or `spoke` |
| `ACTION` | `plan`, `apply`, or `destroy` |
| `ENVIRONMENT` | `dev`, `test`, `preprod`, `prod` |
| `SPOKE_ACCOUNT_NAME` | required for spokes |
| `TF_VAR_FILE` | optional path override relative to repo root |
| `AUTO_APPROVE` | skips apply confirmation, but is blocked for destroy |

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
- `runbook_url`

Important shared-services outputs:

- `lambda_function_arn`
- `lambda_execution_role_arn`
- `cloudwatch_log_group_name`
- `cert_renewal_topic_arn`
- `cert_p1_alert_topic_arn`
- `bitbucket_token_secret_arn`

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
- `RUNBOOK_URL`

Terraform intentionally does not set `AWS_REGION`; Lambda provides it at runtime and `handler.py` reads it from the runtime environment.

## What Terraform does not manage

- certificate private keys or PEM bodies
- `/scip/certs/*` secret values
- Bitbucket token value
- catalogue YAML content
- Vault PKI configuration
- Jenkins job configuration
- EventBridge schedules
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
