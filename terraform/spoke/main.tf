locals {
  tags = merge(
    {
      "managed-by" = "terraform"
      "project"    = "slug-cert-lifecycle"
      "component"  = "cert-lifecycle"
    },
    var.tags,
  )
}

# ── CertLifecycleRole ─────────────────────────────────────────────────────────

module "spoke_role" {
  source = "../modules/cert-lifecycle-spoke-role"

  spoke_role_name           = var.spoke_role_name
  lambda_execution_role_arn = var.lambda_execution_role_arn
  spoke_account_id          = var.spoke_account_id
  aws_region                = var.aws_region
  kms_key_arns              = var.kms_key_arns
  tags                      = local.tags
}

# ── jagent issuer permissions (optional) ─────────────────────────────────────
#
# Only enable when this Terraform state owns jagent-ec2-role.
# If jagent-ec2-role is managed externally, apply the policy documented in
# slug/cert-lifecycle/iam/spoke-account-jagent-policy.json manually instead.

module "issuer_permissions" {
  count  = var.enable_issuer_permissions ? 1 : 0
  source = "../modules/cert-issuer-permissions"

  jagent_role_name = var.jagent_role_name
  spoke_account_id = var.spoke_account_id
  aws_region       = var.aws_region
  kms_key_arns     = var.jagent_kms_key_arns
  tags             = local.tags
}
