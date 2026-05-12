variable "jagent_role_name" {
  description = "Name of the pre-existing IAM role used by Jenkins and Ansible for certificate issuance. This role must already exist — this module only attaches a policy to it."
  type        = string
  default     = "jagent-ec2-role"
}

variable "spoke_account_id" {
  description = "AWS account ID of the spoke account. Used to scope the Secrets Manager resource ARN."
  type        = string
}

variable "aws_region" {
  description = "AWS region for scoping the Secrets Manager resource ARN."
  type        = string
  default     = "eu-west-2"
}

variable "kms_key_arns" {
  description = "List of customer-managed KMS key ARNs for certificate secrets. Leave empty if not using customer-managed keys."
  type        = list(string)
  default     = []
}

variable "tags" {
  description = "Tags to apply to all resources in this module."
  type        = map(string)
  default     = {}
}
