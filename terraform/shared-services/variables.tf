variable "aws_region" {
  description = "AWS region for all shared-services resources."
  type        = string
  default     = "eu-west-2"
}

variable "shared_account_id" {
  description = "AWS account ID of the shared-services account. Used as a provider guardrail so Terraform refuses to run against the wrong account."
  type        = string

  validation {
    condition     = can(regex("^[0-9]{12}$", var.shared_account_id))
    error_message = "shared_account_id must be a 12-digit AWS account ID."
  }
}

# ── SNS ───────────────────────────────────────────────────────────────────────

variable "cert_renewal_topic_name" {
  description = "Name of the SNS topic for certificate renewal notifications."
  type        = string
  default     = "slug-cert-renewal"
}

variable "cert_p1_alert_topic_name" {
  description = "Name of the SNS topic for P1 certificate alerts."
  type        = string
  default     = "slug-cert-p1-alerts"
}

# ── Bitbucket token secret ────────────────────────────────────────────────────

variable "create_bitbucket_token_secret" {
  description = "When true, create the Secrets Manager secret container for the Bitbucket token. Set false if the secret already exists outside this Terraform state."
  type        = bool
  default     = true
}

variable "bitbucket_token_secret_name" {
  description = "Name/path of the Bitbucket token secret in Secrets Manager."
  type        = string
  default     = "/slug/cert-lifecycle/bitbucket-token"
}

variable "bitbucket_token_secret_arn" {
  description = "ARN of a pre-existing Bitbucket token secret. Required when create_bitbucket_token_secret is false."
  type        = string
  default     = null

  validation {
    condition     = var.create_bitbucket_token_secret || var.bitbucket_token_secret_arn != null
    error_message = "bitbucket_token_secret_arn must be provided when create_bitbucket_token_secret is false."
  }
}

<<<<<<< HEAD
# ── Jenkins trigger secret ────────────────────────────────────────────────────

variable "create_jenkins_trigger_secret" {
  description = "When true, create the Secrets Manager secret container for Jenkins trigger credentials. Set false if the secret already exists outside this Terraform state."
  type        = bool
  default     = true
}

variable "jenkins_trigger_secret_name" {
  description = "Name/path of the Jenkins trigger credential secret in Secrets Manager."
  type        = string
  default     = "/slug/cert-lifecycle/jenkins-trigger"
}

variable "jenkins_trigger_secret_arn" {
  description = "ARN of a pre-existing Jenkins trigger credential secret. Required when create_jenkins_trigger_secret is false."
  type        = string
  default     = null

  validation {
    condition     = var.create_jenkins_trigger_secret || var.jenkins_trigger_secret_arn != null
    error_message = "jenkins_trigger_secret_arn must be provided when create_jenkins_trigger_secret is false."
  }
}

=======
>>>>>>> origin/main
# ── Lambda packaging ──────────────────────────────────────────────────────────

variable "lambda_package_path" {
  description = "Local path to the pre-built Lambda deployment zip. Mutually exclusive with lambda_s3_bucket."
  type        = string
  default     = null
}

variable "lambda_s3_bucket" {
  description = "S3 bucket containing the Lambda deployment zip. Mutually exclusive with lambda_package_path."
  type        = string
  default     = null
}

variable "lambda_s3_key" {
  description = "S3 key for the Lambda deployment zip. Required when lambda_s3_bucket is set."
  type        = string
  default     = null
}

variable "lambda_s3_object_version" {
  description = "S3 object version ID for the Lambda deployment zip."
  type        = string
  default     = null
}

# ── Lambda tuning ─────────────────────────────────────────────────────────────

variable "lambda_handler" {
  description = "Lambda handler in file.function format. The expiry checker entry point is handler.handler."
  type        = string
  default     = "handler.handler"
}

variable "lambda_runtime" {
  description = "Lambda Python runtime identifier."
  type        = string
  default     = "python3.12"
}

variable "lambda_function_name" {
  description = "Name of the expiry checker Lambda function."
  type        = string
  default     = "slug-cert-expiry-checker"
}

variable "lambda_execution_role_name" {
  description = "Name of the Lambda execution IAM role."
  type        = string
  default     = "slug-cert-expiry-checker-role"
}

variable "lambda_timeout" {
  description = "Lambda timeout in seconds."
  type        = number
  default     = 300
}

variable "lambda_memory_size" {
  description = "Lambda memory in MB."
  type        = number
  default     = 256
}

variable "lambda_log_retention_days" {
  description = "CloudWatch log group retention in days."
  type        = number
  default     = 30
}

# ── Lambda runtime configuration ──────────────────────────────────────────────

variable "catalogue_urls" {
  description = "Comma-separated Bitbucket raw file URLs for the certificate catalogue YAML files."
  type        = string
}

variable "spoke_role_name" {
  description = "Name of the CertLifecycleRole in each spoke account."
  type        = string
  default     = "CertLifecycleRole"
}

variable "spoke_account_ids" {
  description = "List of spoke AWS account IDs. Used to pre-compute CertLifecycleRole ARNs for the Lambda IAM policy."
  type        = list(string)
}

variable "jenkins_job_name" {
  description = "Jenkins certificate issuance job name. Included in alert notification bodies."
  type        = string
}

variable "jenkins_job_url" {
  description = "Jenkins certificate issuance job URL. Included in alert notification bodies."
  type        = string
}

variable "runbook_url" {
  description = "Runbook URL. Included in alert notification bodies."
  type        = string
}

<<<<<<< HEAD
# ── EventBridge Scheduler ─────────────────────────────────────────────────────

variable "daily_schedule_name" {
  description = "Name of the EventBridge Scheduler schedule that invokes the expiry checker Lambda daily."
  type        = string
  default     = "slug-cert-expiry-checker-daily"
}

variable "daily_schedule_expression" {
  description = "EventBridge Scheduler cron expression for the daily expiry checker run."
  type        = string
  default     = "cron(30 7 * * ? *)"
}

variable "daily_schedule_timezone" {
  description = "IANA timezone used by EventBridge Scheduler for the daily run."
  type        = string
  default     = "Europe/London"
}

variable "scheduler_role_name" {
  description = "Name of the IAM role assumed by EventBridge Scheduler to invoke the Lambda."
  type        = string
  default     = "slug-cert-expiry-checker-scheduler-role"
}

=======
>>>>>>> origin/main
# ── Tagging ───────────────────────────────────────────────────────────────────

variable "tags" {
  description = "Additional tags merged with the baseline managed-by/project/component tags."
  type        = map(string)
  default     = {}
}
