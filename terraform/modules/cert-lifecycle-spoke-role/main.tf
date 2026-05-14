data "aws_iam_policy_document" "certlifecycle_assume" {
  statement {
    sid    = "TrustSharedCertExpiryLambda"
    effect = "Allow"

    principals {
      type        = "AWS"
      identifiers = [var.lambda_execution_role_arn]
    }

    actions = ["sts:AssumeRole"]
  }
}

resource "aws_iam_role" "certlifecycle" {
  name               = var.spoke_role_name
  assume_role_policy = data.aws_iam_policy_document.certlifecycle_assume.json
  tags               = var.tags
}

data "aws_iam_policy_document" "certlifecycle_read" {
  statement {
    sid    = "ReadCertificateSecrets"
    effect = "Allow"

    actions = [
      "secretsmanager:GetSecretValue",
      "secretsmanager:DescribeSecret",
    ]

    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${var.spoke_account_id}:secret:/slug/certs/*",
    ]
  }
}

resource "aws_iam_policy" "certlifecycle_read" {
  name        = "${var.spoke_role_name}-read-certs"
  description = "Read-only access to /slug/certs/* for Slug certificate expiry checking."
  policy      = data.aws_iam_policy_document.certlifecycle_read.json
  tags        = var.tags
}

resource "aws_iam_role_policy_attachment" "certlifecycle_read" {
  role       = aws_iam_role.certlifecycle.name
  policy_arn = aws_iam_policy.certlifecycle_read.arn
}

# Optional KMS decrypt permissions — only created when kms_key_arns is non-empty.
data "aws_iam_policy_document" "certlifecycle_kms" {
  count = length(var.kms_key_arns) > 0 ? 1 : 0

  statement {
    sid     = "DecryptCertificateSecretsViaSecretsManager"
    effect  = "Allow"
    actions = ["kms:Decrypt"]

    resources = var.kms_key_arns

    condition {
      test     = "StringEquals"
      variable = "kms:ViaService"
      values   = ["secretsmanager.${var.aws_region}.amazonaws.com"]
    }
  }
}

resource "aws_iam_policy" "certlifecycle_kms" {
  count       = length(var.kms_key_arns) > 0 ? 1 : 0
  name        = "${var.spoke_role_name}-kms-decrypt"
  description = "KMS decrypt permission for customer-managed key encrypted certificate secrets."
  policy      = data.aws_iam_policy_document.certlifecycle_kms[0].json
  tags        = var.tags
}

resource "aws_iam_role_policy_attachment" "certlifecycle_kms" {
  count      = length(var.kms_key_arns) > 0 ? 1 : 0
  role       = aws_iam_role.certlifecycle.name
  policy_arn = aws_iam_policy.certlifecycle_kms[0].arn
}
