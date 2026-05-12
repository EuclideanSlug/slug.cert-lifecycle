variable "aws_region" {
  description = "AWS region for all spoke resources."
  type        = string
  default     = "eu-west-2"
}

variable "spoke_account_id" {
  description = "AWS account ID of this spoke account. Used to scope Secrets Manager resource ARNs."
  type        = string
}

# ── CertLifecycleRole ─────────────────────────────────────────────────────────

variable "spoke_role_name" {
  description = "Name of the cross-account role the expiry checker Lambda assumes in this spoke account."
  type        = string
  default     = "CertLifecycleRole"
}

variable "lambda_execution_role_arn" {
  description = "ARN of the expiry checker Lambda execution role in the shared-services account. Granted sts:AssumeRole on CertLifecycleRole."
  type        = string
}

variable "kms_key_arns" {
  description = "Customer-managed KMS key ARNs used to encrypt certificate secrets in this spoke account. Leave empty if not using customer-managed keys."
  type        = list(string)
  default     = []
}

# ── jagent issuer permissions (optional) ─────────────────────────────────────

variable "enable_issuer_permissions" {
  description = "When true, attach the Secrets Manager write policy to jagent-ec2-role. Only set true if this Terraform state owns that role. See scip/cert-lifecycle/iam/spoke-account-jagent-policy.json for the manual alternative."
  type        = bool
  default     = false
}

variable "jagent_role_name" {
  description = "Name of the pre-existing jagent EC2 instance role. Only relevant when enable_issuer_permissions is true."
  type        = string
  default     = "jagent-ec2-role"
}

variable "jagent_kms_key_arns" {
  description = "KMS key ARNs to include in the jagent write policy. Only relevant when enable_issuer_permissions is true."
  type        = list(string)
  default     = []
}

# ── Tagging ───────────────────────────────────────────────────────────────────

variable "tags" {
  description = "Additional tags merged with the baseline managed-by/project/component tags."
  type        = map(string)
  default     = {}
}
