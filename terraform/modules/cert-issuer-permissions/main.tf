# This module attaches Secrets Manager write permissions to a pre-existing IAM role
# used by Jenkins and Ansible to issue certificates (jagent-ec2-role by default).
#
# Only enable this module (enable_issuer_permissions = true in the spoke root module)
# if this Terraform state owns the target role or the owning team has explicitly
# approved this state to attach policies to it.
#
# If jagent-ec2-role is owned by another team or Terraform state, provide the
# required policy from:
#   scip/cert-lifecycle/iam/spoke-account-jagent-policy.json
# to the role owner for manual application or application via the owning Terraform state.

data "aws_iam_policy_document" "jagent_cert_write" {
  statement {
    sid    = "CreateAndUpdateCertSecrets"
    effect = "Allow"

    actions = [
      "secretsmanager:CreateSecret",
      "secretsmanager:DescribeSecret",
      "secretsmanager:PutSecretValue",
      "secretsmanager:TagResource",
    ]

    resources = [
      "arn:aws:secretsmanager:${var.aws_region}:${var.spoke_account_id}:secret:/scip/certs/*",
    ]
  }

  dynamic "statement" {
    for_each = length(var.kms_key_arns) > 0 ? [1] : []

    content {
      sid    = "KmsForCertSecrets"
      effect = "Allow"

      actions = [
        "kms:Decrypt",
        "kms:GenerateDataKey",
      ]

      resources = var.kms_key_arns

      condition {
        test     = "StringEquals"
        variable = "kms:ViaService"
        values   = ["secretsmanager.${var.aws_region}.amazonaws.com"]
      }
    }
  }
}

resource "aws_iam_policy" "jagent_cert_write" {
  name        = "scip-cert-lifecycle-jagent-write-certs"
  description = "Secrets Manager write permissions for SCIP certificate issuance via the Jenkins issuer role."
  policy      = data.aws_iam_policy_document.jagent_cert_write.json
  tags        = var.tags
}

resource "aws_iam_role_policy_attachment" "jagent_cert_write" {
  role       = var.jagent_role_name
  policy_arn = aws_iam_policy.jagent_cert_write.arn
}
