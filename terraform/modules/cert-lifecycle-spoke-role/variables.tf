variable "spoke_role_name" {
  description = "Name of the IAM role to create in the spoke account for certificate expiry checking."
  type        = string
  default     = "CertLifecycleRole"
}

variable "lambda_execution_role_arn" {
  description = "ARN of the shared-account Lambda execution role. The spoke role trust policy allows this principal to assume the spoke role."
  type        = string
}

variable "spoke_account_id" {
  description = "AWS account ID of the spoke account. Used to scope the Secrets Manager resource ARN to this account."
  type        = string
}

variable "aws_region" {
  description = "AWS region for scoping the Secrets Manager resource ARN."
  type        = string
  default     = "eu-west-2"
}

variable "kms_key_arns" {
  description = "List of customer-managed KMS key ARNs used to encrypt certificate secrets. Leave empty if using AWS-managed keys."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags to apply to all resources in this module."
  type        = map(string)
  default     = {}
}
