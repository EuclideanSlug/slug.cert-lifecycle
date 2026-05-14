locals {
  # AWS_REGION is intentionally excluded: the Lambda runtime provides it automatically.
  lambda_env_vars = {
    BITBUCKET_TOKEN_SECRET_ID = var.bitbucket_token_secret_name
    BITBUCKET_CATALOGUE_URLS  = var.catalogue_urls
    SPOKE_ROLE_NAME           = var.spoke_role_name
    CERT_RENEWAL_TOPIC_ARN    = var.cert_renewal_topic_arn
    CERT_P1_ALERT_TOPIC_ARN   = var.cert_p1_alert_topic_arn
    JENKINS_JOB_NAME          = var.jenkins_job_name
    JENKINS_JOB_URL           = var.jenkins_job_url
    RUNBOOK_URL               = var.runbook_url
  }
}

# ── Lambda execution role ──────────────────────────────────────────────────────

data "aws_iam_policy_document" "lambda_exec_assume" {
  statement {
    sid    = "AllowLambdaServiceToAssume"
    effect = "Allow"

    principals {
      type        = "Service"
      identifiers = ["lambda.amazonaws.com"]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "lambda_exec" {
  name               = var.lambda_execution_role_name
  assume_role_policy = data.aws_iam_policy_document.lambda_exec_assume.json
  tags               = var.tags
}

# ── CloudWatch log group ───────────────────────────────────────────────────────

resource "aws_cloudwatch_log_group" "lambda_logs" {
  name              = "/aws/lambda/${var.lambda_function_name}"
  retention_in_days = var.lambda_log_retention_days
  tags              = var.tags
}

# ── Lambda IAM policy (least privilege) ───────────────────────────────────────

data "aws_iam_policy_document" "lambda_exec_policy" {
  statement {
    sid     = "ReadBitbucketToken"
    effect  = "Allow"
    actions = ["secretsmanager:GetSecretValue"]

    resources = [var.bitbucket_token_secret_arn]
  }

  statement {
    sid     = "AssumeSpokeCertLifecycleRoles"
    effect  = "Allow"
    actions = ["sts:AssumeRole"]

    resources = var.spoke_cert_lifecycle_role_arns
  }

  statement {
    sid     = "PublishCertificateNotifications"
    effect  = "Allow"
    actions = ["sns:Publish"]

    resources = [
      var.cert_renewal_topic_arn,
      var.cert_p1_alert_topic_arn,
    ]
  }

  statement {
    sid    = "WriteLambdaLogs"
    effect = "Allow"

    actions = [
      "logs:CreateLogStream",
      "logs:PutLogEvents",
    ]

    resources = [
      aws_cloudwatch_log_group.lambda_logs.arn,
      "${aws_cloudwatch_log_group.lambda_logs.arn}:*",
    ]
  }
}

resource "aws_iam_policy" "lambda_exec" {
  name        = "${var.lambda_function_name}-policy"
  description = "Least-privilege policy for the Slug certificate expiry checker Lambda."
  policy      = data.aws_iam_policy_document.lambda_exec_policy.json
  tags        = var.tags
}

resource "aws_iam_role_policy_attachment" "lambda_exec" {
  role       = aws_iam_role.lambda_exec.name
  policy_arn = aws_iam_policy.lambda_exec.arn
}

# ── Lambda function ────────────────────────────────────────────────────────────
#
# Packaging: supply exactly one of lambda_package_path (local zip) or
# lambda_s3_bucket + lambda_s3_key (S3 zip). The lifecycle preconditions
# enforce this at plan time. Both default to null so terraform validate
# passes without a pre-built package.

resource "aws_lambda_function" "expiry_checker" {
  function_name = var.lambda_function_name
  role          = aws_iam_role.lambda_exec.arn
  handler       = var.lambda_handler
  runtime       = var.lambda_runtime
  timeout       = var.lambda_timeout
  memory_size   = var.lambda_memory_size

  # Local zip path (mutually exclusive with s3_bucket)
  filename         = var.lambda_package_path
  source_code_hash = var.lambda_package_path != null ? filebase64sha256(var.lambda_package_path) : null

  # S3 zip reference (mutually exclusive with filename)
  s3_bucket         = var.lambda_s3_bucket
  s3_key            = var.lambda_s3_key
  s3_object_version = var.lambda_s3_object_version

  environment {
    variables = local.lambda_env_vars
  }

  depends_on = [
    aws_iam_role_policy_attachment.lambda_exec,
    aws_cloudwatch_log_group.lambda_logs,
  ]

  lifecycle {
    precondition {
      condition     = (var.lambda_package_path != null) != (var.lambda_s3_bucket != null)
      error_message = "Exactly one of lambda_package_path or lambda_s3_bucket must be provided."
    }

    precondition {
      condition     = var.lambda_s3_bucket == null || var.lambda_s3_key != null
      error_message = "lambda_s3_key is required when lambda_s3_bucket is set."
    }
  }

  tags = var.tags
}
