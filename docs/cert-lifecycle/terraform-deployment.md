# Terraform Deployment Guide — SCIP Certificate Lifecycle

This document covers deploying and managing the SCIP certificate lifecycle AWS infrastructure using Terraform. It covers both the Jenkins pipeline and the local Makefile workflow.

---

## Account reference

### Shared-services accounts (TARGET_TYPE=shared)

| ENVIRONMENT | Account name | Notes |
| --- | --- | --- |
| `preprod` | preprod | Hosts the expiry checker Lambda for preprod spoke accounts |
| `prod` | prodc | Hosts the expiry checker Lambda for prod spoke accounts |

> `dev` and `test` have no shared-services account. `TARGET_TYPE=shared` is only valid with `ENVIRONMENT=preprod` or `prod`. The Jenkins pipeline rejects other combinations at parameter validation.

### Spoke accounts (TARGET_TYPE=spoke)

| ENVIRONMENT | Valid SPOKE_ACCOUNT_NAME values |
| --- | --- |
| `dev` | `Dev` `deva` `devb` `devc` `devd` `deve` `devf` `devg` |
| `test` | `testa` `testb` `testc` `testd` `teste` `testf` `testg` |
| `preprod` | `preproda` `preprodb` `preprodc` `preprodd` `preprode` `preprodf` `preprodg` |
| `prod` | `prodd` `prode` `prodf` `prodg` `prodh` `prodi` `prodj` |

> `prodc` is the prod shared-services account and does not appear in the spoke list. The Jenkins pipeline enforces the environment-to-account mapping and fails immediately if an invalid combination is selected.

---

## Architecture summary

Two independent Terraform root modules are applied separately:

```text
terraform/shared-services/   — applied once into the shared services account
terraform/spoke/             — applied once per spoke account
```

The shared-services root must be applied first. The `lambda_execution_role_arn` output from that apply is an input to every spoke apply.

Modules used by both roots live under `terraform/modules/`.

---

## Prerequisites

### Credentials

AWS credentials for the target account must be active in the environment before running any Terraform command. Acceptable credential sources:

- EC2 instance profile (Jenkins agents `preprod`, `prodc`)
- `aws-vault exec <profile>` for local use
- `AWS_PROFILE` exported in the shell

Credentials are never hardcoded in the Makefile or pipeline.

### Terraform version

Shared-services root requires Terraform `>= 1.9.0`.  
Spoke root requires Terraform `>= 1.3.0`.

### Backend config files

Each environment/account requires an S3 backend config file. These files are **operator-created and not committed to the repository**. Create them before the first `terraform init`.

**Shared-services backend config** (`terraform/shared-services/envs/<environment>-backend.hcl`):

```hcl
bucket         = "scip-tfstate-<shared-account-id>"
key            = "cert-lifecycle/shared-services/<environment>.tfstate"
region         = "eu-west-2"
dynamodb_table = "scip-tfstate-lock"
encrypt        = true
```

**Spoke backend config** (`terraform/spoke/envs/<environment>-<account>-backend.hcl`):

```hcl
bucket         = "scip-tfstate-<shared-account-id>"
key            = "cert-lifecycle/spoke/<account>/<environment>.tfstate"
region         = "eu-west-2"
dynamodb_table = "scip-tfstate-lock"
encrypt        = true
```

### Variable files

Copy the relevant `.tfvars.example` file and fill in real values:

```bash
# Shared-services
cp terraform/shared-services/envs/preprod.tfvars.example \
   terraform/shared-services/envs/preprod.tfvars

# Spoke
cp terraform/spoke/envs/preprod-preprodc.tfvars.example \
   terraform/spoke/envs/preprod-preprodc.tfvars
```

Edit the copied file and replace all `<placeholder>` values. Do not commit the filled-in `.tfvars` files.

---

## Jenkins pipeline

### Pipeline file

`Jenkinsfile.terraform` at the repo root. Configure a separate Jenkins job pointing to this file. The existing `Jenkinsfile` (certificate issuance) remains unchanged.

### Parameters

| Parameter | Values | Notes |
| --- | --- | --- |
| `TARGET_TYPE` | `shared` \| `spoke` | `shared` applies the shared-services root; `spoke` applies the spoke root |
| `ACTION` | `plan` \| `apply` \| `destroy` | `plan` produces a plan only; `apply` and `destroy` require confirmation |
| `ENVIRONMENT` | `dev` \| `test` \| `preprod` \| `prod` | Selects which tfvars and backend config to load |
| `SPOKE_ACCOUNT_NAME` | e.g. `devc`, `preprodc`, `prodd` | Required when `TARGET_TYPE=spoke`; must match the `envs/` filename suffix |
| `TF_VAR_FILE` | path string | Optional. Overrides the auto-derived var file path. Relative to repo root. |
| `AUTO_APPROVE` | `true` \| `false` | Default `false`. When `true`, skips the manual confirmation input step. |

### Pipeline stages

1. **Checkout** — checks out the repository.
2. **Validate parameters** — fails immediately if `TARGET_TYPE=spoke` and `SPOKE_ACCOUNT_NAME` is empty, or if `TARGET_TYPE=shared` is used with `ENVIRONMENT=dev` or `test` (no shared-services account exists for those environments).
3. **Resolve paths** — prints target type, action, environment, spoke account, Terraform root, var file, and backend config. No secret values are printed.
4. **terraform fmt** — runs `terraform fmt -check -recursive` from repo root. Fails if any file is not formatted.
5. **terraform init** — initialises the target root with the resolved backend config.
6. **terraform validate** — validates the Terraform configuration.
7. **terraform plan** — runs plan with the resolved var file; saves output to `tfplan` or `tfdestroy`.
8. **Confirm apply/destroy** — requires a manual `Proceed` click in Jenkins (skipped if `AUTO_APPROVE=true`). Review the plan output in the stage above before clicking.
9. **terraform apply** — applies the saved plan file. Runs only for `ACTION=apply` or `ACTION=destroy`.
10. **Workspace cleanup** — always runs; removes the workspace including plan files.

### Usage examples

**Plan the shared-services account for preprod:**

```text
TARGET_TYPE=shared  ACTION=plan  ENVIRONMENT=preprod
```

**Plan a spoke account:**

```text
TARGET_TYPE=spoke  ACTION=plan  ENVIRONMENT=preprod  SPOKE_ACCOUNT_NAME=preprodc
```

**Apply a spoke account (requires confirmation):**

```text
TARGET_TYPE=spoke  ACTION=apply  ENVIRONMENT=preprod  SPOKE_ACCOUNT_NAME=preprodc
```

**Destroy a dev spoke account (requires confirmation):**

```text
TARGET_TYPE=spoke  ACTION=destroy  ENVIRONMENT=dev  SPOKE_ACCOUNT_NAME=devc
```

### Agent and credential expectations

The Jenkins pipeline selects the agent label based on `ENVIRONMENT`:

- `prod` → `prodc` agent
- Everything else → `preprod` agent

These agents must have AWS credentials (instance profile or credential binding) scoped to the correct account. The pipeline does not inject or manage credentials.

For `TARGET_TYPE=shared`, the agent must be authenticated to the shared services account.  
For `TARGET_TYPE=spoke`, the agent must be authenticated to the target spoke account.

---

## Local Makefile usage

### Quick start

```bash
# Check formatting across all Terraform
make tf-fmt-check

# Plan the shared-services root for preprod
make tf-plan TARGET_TYPE=shared ENVIRONMENT=preprod

# Plan a spoke account
make tf-plan TARGET_TYPE=spoke ENVIRONMENT=preprod SPOKE_ACCOUNT_NAME=preprodc

# Apply the saved plan
make tf-apply TARGET_TYPE=spoke ENVIRONMENT=preprod SPOKE_ACCOUNT_NAME=preprodc

# Destroy dev spoke account (explicit confirmation required)
make tf-destroy TARGET_TYPE=spoke ENVIRONMENT=dev SPOKE_ACCOUNT_NAME=devc CONFIRM_DESTROY=true
```

### Target reference

| Target | Description |
| --- | --- |
| `tf-help` | Print all targets, examples, and current variable values |
| `tf-fmt` | Run `terraform fmt -recursive` across all Terraform code |
| `tf-fmt-check` | Check formatting without modifying files |
| `tf-init` | Initialise Terraform with backend config for the target environment |
| `tf-validate` | Validate configuration (run `tf-init` first) |
| `tf-plan` | Run plan and save to `tfplan` inside the target root directory |
| `tf-apply` | Apply the saved `tfplan` (run `tf-plan` first) |
| `tf-destroy` | Plan destroy then apply destroy (requires `CONFIRM_DESTROY=true`) |
| `tf-clean` | Remove plan files and `.terraform/` from the target root |

### Variable reference

| Variable | Default | Description |
| --- | --- | --- |
| `TARGET_TYPE` | `shared` | `shared` or `spoke` |
| `ENVIRONMENT` | `dev` | `dev`, `test`, `preprod`, or `prod` |
| `SPOKE_ACCOUNT_NAME` | _(empty)_ | Required when `TARGET_TYPE=spoke`; e.g. `devc`, `preprodc`, `prodc` |
| `TF_ROOT` | Derived from `TARGET_TYPE` | Override the Terraform root path |
| `TF_VAR_FILE` | Derived from `TARGET_TYPE`/`ENVIRONMENT`/`SPOKE_ACCOUNT_NAME` | Path to `.tfvars`, relative to `TF_ROOT` (or absolute) |
| `BACKEND_CFG` | Derived from `TARGET_TYPE`/`ENVIRONMENT`/`SPOKE_ACCOUNT_NAME` | Path to backend config, relative to `TF_ROOT` |
| `AUTO_APPROVE` | `false` | When `true`, passes `-auto-approve` to `terraform apply` |
| `CONFIRM_DESTROY` | `false` | Must be `true` to run `tf-destroy` |

### File path conventions

Var files and backend configs are loaded from an `envs/` subdirectory inside the target root:

```text
terraform/shared-services/envs/
  preprod.tfvars                   ← variable values (operator-created, do not commit)
  preprod.tfvars.example           ← placeholder template (committed)
  preprod-backend.hcl              ← backend config (operator-created, do not commit)

terraform/spoke/envs/
  preprod-preprodc.tfvars          ← variable values (do not commit)
  preprod-preprodc.tfvars.example  ← placeholder template (committed)
  preprod-preprodc-backend.hcl     ← backend config (do not commit)
```

To use a non-standard path, override explicitly:

```bash
make tf-plan TARGET_TYPE=shared ENVIRONMENT=preprod \
  TF_VAR_FILE=/tmp/custom.tfvars \
  BACKEND_CFG=/tmp/custom-backend.hcl
```

### Standard local workflow

```bash
# 1. Ensure AWS credentials are active for the target account.

# 2. Create the backend config file if it does not exist.
#    See the Backend config section above.

# 3. Copy and fill in the var file.
cp terraform/shared-services/envs/preprod.tfvars.example \
   terraform/shared-services/envs/preprod.tfvars
# Edit preprod.tfvars and replace all placeholders.

# 4. Initialise.
make tf-init TARGET_TYPE=shared ENVIRONMENT=preprod

# 5. Validate.
make tf-validate TARGET_TYPE=shared ENVIRONMENT=preprod

# 6. Plan.
make tf-plan TARGET_TYPE=shared ENVIRONMENT=preprod

# 7. Review the plan output.

# 8. Apply.
make tf-apply TARGET_TYPE=shared ENVIRONMENT=preprod

# 9. Clean up plan files.
make tf-clean TARGET_TYPE=shared ENVIRONMENT=preprod
```

---

## Shared vs spoke deployment order

The shared-services root must be applied before any spoke root that depends on it. Apply in this order within each environment tier.

### Preprod deployment

**Step 1 — Apply preprod shared-services** (credentials: preprod shared-services account):

```bash
make tf-plan  TARGET_TYPE=shared ENVIRONMENT=preprod
make tf-apply TARGET_TYPE=shared ENVIRONMENT=preprod
```

Note the `lambda_execution_role_arn` output:

```bash
terraform -chdir=terraform/shared-services output lambda_execution_role_arn
```

**Step 2 — Apply each preprod spoke** (credentials: target spoke account):

```bash
make tf-plan  TARGET_TYPE=spoke ENVIRONMENT=preprod SPOKE_ACCOUNT_NAME=preproda
make tf-apply TARGET_TYPE=spoke ENVIRONMENT=preprod SPOKE_ACCOUNT_NAME=preproda
# Repeat for preprodb through preprodg
```

Set `lambda_execution_role_arn` in each spoke's var file to the value noted in Step 1.

### Dev and test spokes

There is no dev or test shared-services account. Dev and test spokes use the Lambda from the preprod shared-services account. The `lambda_execution_role_arn` for dev and test spoke var files must be set to the ARN from the **preprod** shared-services apply.

Each dev/test account ID must also be added to `spoke_account_ids` in `terraform/shared-services/envs/preprod.tfvars` so that the preprod Lambda's IAM policy permits assuming `CertLifecycleRole` there. Re-apply preprod shared-services after editing that list.

```bash
# Apply a dev spoke (credentials: target dev spoke account)
make tf-plan  TARGET_TYPE=spoke ENVIRONMENT=dev SPOKE_ACCOUNT_NAME=devc
make tf-apply TARGET_TYPE=spoke ENVIRONMENT=dev SPOKE_ACCOUNT_NAME=devc
```

### Prod deployment

**Step 1 — Apply prod shared-services into `prodc`** (credentials: prodc account):

```bash
make tf-plan  TARGET_TYPE=shared ENVIRONMENT=prod
make tf-apply TARGET_TYPE=shared ENVIRONMENT=prod
```

Note the `lambda_execution_role_arn` output:

```bash
terraform -chdir=terraform/shared-services output lambda_execution_role_arn
```

**Step 2 — Apply each prod spoke** (credentials: target spoke account). Prod spokes are `prodd` through `prodj`; `prodc` is the shared-services account and is not a spoke:

```bash
make tf-plan  TARGET_TYPE=spoke ENVIRONMENT=prod SPOKE_ACCOUNT_NAME=prodd
make tf-apply TARGET_TYPE=spoke ENVIRONMENT=prod SPOKE_ACCOUNT_NAME=prodd
# Repeat for prode through prodj
```

Set `lambda_execution_role_arn` in each spoke's var file to the ARN from the prod shared-services apply (Step 1).

### Step 3 — Manual post-apply steps

After both applies:

1. Insert the Bitbucket token into Secrets Manager (shared services account):

   ```bash
   aws secretsmanager put-secret-value \
     --secret-id "/scip/cert-lifecycle/bitbucket-token" \
     --secret-string '{"token":"<token>"}' \
     --region eu-west-2
   ```

2. Create an EventBridge schedule rule targeting the Lambda ARN.
3. Subscribe to the SNS topics (`scip-cert-renewal`, `scip-cert-p1-alerts`).

---

## Plan / apply / destroy flow

### plan only

```text
terraform fmt -check → terraform init → terraform validate → terraform plan
```

Output: plan written to `tfplan` inside the target root. No changes made.

### apply

```text
terraform fmt -check → terraform init → terraform validate → terraform plan
  → [confirmation required] → terraform apply tfplan
```

Output: plan applied. Plan file removed by `cleanWs()` in Jenkins or by `make tf-clean` locally.

### destroy

```text
terraform fmt -check → terraform init → terraform validate → terraform plan -destroy
  → [confirmation required] → terraform apply tfdestroy
```

Output: resources destroyed.

---

## Safe destroy process

Destroying resources is irreversible for some resource types (SNS topics, IAM roles, Lambda functions). Follow this process:

1. **Run plan first** — `make tf-destroy` always runs a destroy plan before applying. Review the plan output carefully. Confirm that only the expected resources appear.
2. **Confirm explicitly** — the Makefile requires `CONFIRM_DESTROY=true`. The Jenkins pipeline requires a manual `Proceed` click on the confirmation step.
3. **Do not use `AUTO_APPROVE=true` with destroy** unless the intent is fully understood and tested.
4. **Spoke accounts before shared-services** — destroying the shared-services root while spoke roles still exist leaves those roles with a dangling trust relationship but does not cause data loss. Destroy spoke roots first.
5. **Certificate secrets are not managed by Terraform** — destroying either root does not delete certificate secrets in Secrets Manager. Those must be cleaned up manually if required.

---

## What Terraform does not manage

Terraform in this project explicitly does not manage:

- Certificate private keys or PEM certificate bodies
- Secrets Manager secret values (only the secret container shell for the Bitbucket token)
- Certificate catalogue YAML files
- Vault PKI configuration
- Ansible roles or playbooks
- Jenkins job configuration
- EventBridge schedule rules (create manually post-apply)
- SNS topic subscriptions (create manually post-apply)
- Application-specific jagent IAM roles — those are externally owned; see `scip/cert-lifecycle/iam/`

---

## Troubleshooting

### `terraform init` fails with backend config error

The backend config file does not exist or contains incorrect values. Create it at:

```text
terraform/<root>/envs/<environment>[-<account>]-backend.hcl
```

See the Prerequisites section for the required content.

### `terraform validate` fails with provider errors

Run `terraform init` first. The `.terraform/` directory must exist with the AWS provider downloaded.

### `make tf-apply` fails with "tfplan not found"

Run `make tf-plan` first. Plan files are ephemeral — the apply must follow plan in the same session.

### Jenkins: `SPOKE_ACCOUNT_NAME is required` error

The pipeline failed parameter validation. Set `SPOKE_ACCOUNT_NAME` to the account suffix (e.g. `preprodc`) when `TARGET_TYPE=spoke`.

### Jenkins: fmt check fails

Run `make tf-fmt` locally and commit the formatted files before re-running the pipeline.

### Sensitive variable in plan output

Terraform masks sensitive variables in plan output by default (since Terraform 0.14). If a value appears in plan output that should not, check whether the relevant variable is marked `sensitive = true` in the module variable definition.

### `terraform apply` succeeds but Lambda cannot read Secrets Manager in a spoke

Verify that the `lambda_execution_role_arn` value in the spoke var file matches the actual ARN output from the shared-services apply. Cross-account assume-role failures appear in CloudTrail in the shared services account.
