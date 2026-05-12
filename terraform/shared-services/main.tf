locals {
  tags = merge(
    {
      "managed-by" = "terraform"
      "project"    = "scip-cert-lifecycle"
      "component"  = "cert-lifecycle"
    },
    var.tags,
  )

  # Pre-compute spoke CertLifecycleRole ARNs from account IDs.
  # Avoids a cross-account circular dependency: Lambda policy needs spoke ARNs
  # at plan time, before spoke root modules are applied.
  spoke_cert_lifecycle_role_arns = [
    for account_id in var.spoke_account_ids :
    "arn:aws:iam::${account_id}:role/${var.spoke_role_name}"
  ]

  # Resolve which Bitbucket token secret ARN the Lambda policy should reference.
  bitbucket_token_secret_arn = (
    var.create_bitbucket_token_secret
    ? aws_secretsmanager_secret.bitbucket_token[0].arn
    : var.bitbucket_token_secret_arn
  )
}

# ── SNS topics ────────────────────────────────────────────────────────────────

module "sns" {
  source = "../modules/cert-lifecycle-sns"

  cert_renewal_topic_name  = var.cert_renewal_topic_name
  cert_p1_alert_topic_name = var.cert_p1_alert_topic_name
  tags                     = local.tags
}

# ── Bitbucket token secret (metadata/container only) ─────────────────────────
#
# Creates the Secrets Manager secret shell so the Lambda IAM policy can
# reference a fixed ARN. The token value must be set manually by the operator —
# never managed by Terraform.

resource "aws_secretsmanager_secret" "bitbucket_token" {
  count = var.create_bitbucket_token_secret ? 1 : 0

  name        = var.bitbucket_token_secret_name
  description = "Bitbucket API token for the SCIP certificate expiry checker Lambda. Set the value manually — never via Terraform."
  tags        = local.tags
}

# ── Lambda expiry checker ─────────────────────────────────────────────────────

module "cert_expiry_checker" {
  source = "../modules/cert-expiry-checker"

  lambda_function_name       = var.lambda_function_name
  lambda_execution_role_name = var.lambda_execution_role_name
  lambda_handler             = var.lambda_handler
  lambda_runtime             = var.lambda_runtime
  lambda_timeout             = var.lambda_timeout
  lambda_memory_size         = var.lambda_memory_size
  lambda_log_retention_days  = var.lambda_log_retention_days

  lambda_package_path      = var.lambda_package_path
  lambda_s3_bucket         = var.lambda_s3_bucket
  lambda_s3_key            = var.lambda_s3_key
  lambda_s3_object_version = var.lambda_s3_object_version

  bitbucket_token_secret_arn     = local.bitbucket_token_secret_arn
  bitbucket_token_secret_name    = var.bitbucket_token_secret_name
  catalogue_urls                 = var.catalogue_urls
  spoke_role_name                = var.spoke_role_name
  spoke_cert_lifecycle_role_arns = local.spoke_cert_lifecycle_role_arns

  cert_renewal_topic_arn  = module.sns.cert_renewal_topic_arn
  cert_p1_alert_topic_arn = module.sns.cert_p1_alert_topic_arn

  jenkins_job_name = var.jenkins_job_name
  jenkins_job_url  = var.jenkins_job_url
  runbook_url      = var.runbook_url

  tags = local.tags
}
