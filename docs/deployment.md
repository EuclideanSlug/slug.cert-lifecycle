# Deployment

This is the end-to-end deployment order for Slug Certificate Lifecycle.

For Terraform command details, see [Terraform](terraform.md).

## Deployment model

Terraform has two root modules:

```text
terraform/shared-services/   applied once per shared-services tier
terraform/spoke/             applied once per spoke account
```

Apply shared services before spokes. Each spoke needs the `lambda_execution_role_arn` output from its shared-services apply.

## Shared services

Shared services creates:

- expiry checker Lambda
- Lambda execution role and IAM policy
- CloudWatch log group
- `slug-cert-renewal` SNS topic
- `slug-cert-p1-alerts` SNS topic
- optional Bitbucket token secret container

Shared-services applies are valid for:

| Environment | Account |
| --- | --- |
| `preprod` | preprod shared-services account |
| `prod` | `prodc` |

There is no dev or test shared-services account. Dev and test spokes are monitored by the preprod Lambda when their account IDs are included in `terraform/shared-services/envs/preprod.tfvars`.

## Spokes

Spoke applies create:

- `CertLifecycleRole`
- read-only Secrets Manager policy for `/slug/certs/*`
- optional KMS decrypt policy
- optional jagent write policy, only when `enable_issuer_permissions = true`

The spoke root does not create or update live certificate secret values.

## First deployment checklist

1. Build and upload the Lambda zip, or prepare a local zip path.
2. Create backend config files for the target roots.
3. Copy `.tfvars.example` files to untracked `.tfvars` files and replace placeholders.
4. Apply shared services.
5. Record `lambda_execution_role_arn`.
6. Insert the Bitbucket token value into Secrets Manager.
7. Apply each spoke with the correct `lambda_execution_role_arn`.
8. Create an EventBridge schedule for the Lambda.
9. Subscribe recipients to both SNS topics.
10. Copy any required catalogue `.yml.example` templates to `.yml` and replace `deployment.account_id` placeholders.
11. Run the catalogue validator.
12. Run a non-prod single-app Jenkins issuance.
13. Confirm the secret version and Lambda log output.

## Preprod, dev, and test

1. Apply preprod shared services:

   ```bash
   make tf-plan TARGET_TYPE=shared ENVIRONMENT=preprod
   make tf-apply TARGET_TYPE=shared ENVIRONMENT=preprod
   ```

2. Add preprod, dev, and test spoke account IDs to `spoke_account_ids` in `terraform/shared-services/envs/preprod.tfvars` as needed, then re-apply shared services.
3. Apply each spoke:

   ```bash
   make tf-plan TARGET_TYPE=spoke ENVIRONMENT=preprod SPOKE_ACCOUNT_NAME=preprodc
   make tf-apply TARGET_TYPE=spoke ENVIRONMENT=preprod SPOKE_ACCOUNT_NAME=preprodc
   ```

   ```bash
   make tf-plan TARGET_TYPE=spoke ENVIRONMENT=dev SPOKE_ACCOUNT_NAME=devc
   make tf-apply TARGET_TYPE=spoke ENVIRONMENT=dev SPOKE_ACCOUNT_NAME=devc
   ```

## Prod

1. Apply prod shared services into `prodc`:

   ```bash
   make tf-plan TARGET_TYPE=shared ENVIRONMENT=prod
   make tf-apply TARGET_TYPE=shared ENVIRONMENT=prod
   ```

2. Apply prod spokes. `prodc` can also be targeted as a spoke because it is dual-purpose:

   ```bash
   make tf-plan TARGET_TYPE=spoke ENVIRONMENT=prod SPOKE_ACCOUNT_NAME=prodc
   make tf-apply TARGET_TYPE=spoke ENVIRONMENT=prod SPOKE_ACCOUNT_NAME=prodc
   ```

   Repeat for `prodd` through `prodj` as required.

## Manual post-apply steps

Terraform does not insert the Bitbucket token value:

```bash
aws secretsmanager put-secret-value \
  --secret-id "/slug/cert-lifecycle/bitbucket-token" \
  --secret-string '{"token":"<token>"}' \
  --region eu-west-2
```

Terraform also does not manage:

- EventBridge schedules
- SNS subscriptions
- Jenkins job configuration
- Vault PKI configuration
- live certificate secret values

## Lambda packaging

`cryptography` contains native components. Build in a Lambda-compatible environment, for example:

```bash
docker run --rm \
  -v "$(pwd)/slug/cert-lifecycle/lambda/expiry_checker":/src \
  -v "$(pwd)/dist":/out \
  public.ecr.aws/lambda/python:3.12 \
  bash -c "pip install -r /src/requirements.txt -t /tmp/pkg && cp /src/*.py /tmp/pkg/ && cd /tmp/pkg && zip -r /out/expiry_checker.zip ."
```

Terraform accepts either:

- `lambda_s3_bucket` + `lambda_s3_key`
- `lambda_package_path`

Use exactly one packaging method.
