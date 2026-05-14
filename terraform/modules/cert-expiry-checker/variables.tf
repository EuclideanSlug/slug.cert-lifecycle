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

variable "lambda_timeout" {
  description = "Lambda timeout in seconds. Minimum recommended value is 300 (5 minutes)."
  type        = number
  default     = 300
}

variable "lambda_memory_size" {
  description = "Lambda memory allocation in MB. Minimum recommended value is 256."
  type        = number
  default     = 256
}

variable "lambda_log_retention_days" {
  description = "CloudWatch log group retention period in days."
  type        = number
  default     = 30
}

variable "lambda_package_path" {
  description = "Local path to the pre-built Lambda deployment zip. Mutually exclusive with lambda_s3_bucket. The zip must be built in a Lambda-compatible environment because the cryptography dependency contains native components."
  type        = string
  default     = null
}

variable "lambda_s3_bucket" {
  description = "S3 bucket containing the Lambda deployment zip. Mutually exclusive with lambda_package_path."
  type        = string
  default     = null
}

variable "lambda_s3_key" {
  description = "S3 object key for the Lambda deployment zip. Required when lambda_s3_bucket is set."
  type        = string
  default     = null
}

variable "lambda_s3_object_version" {
  description = "S3 object version ID for the Lambda deployment zip. Optional; use for immutable versioned deployments."
  type        = string
  default     = null
}

variable "bitbucket_token_secret_arn" {
  description = "ARN of the Secrets Manager secret containing the Bitbucket API token. Scoped in the Lambda IAM policy to this exact ARN."
  type        = string
}

variable "bitbucket_token_secret_name" {
  description = "Name or path of the Bitbucket token secret. Used as the BITBUCKET_TOKEN_SECRET_ID Lambda environment variable."
  type        = string
  default     = "/slug/cert-lifecycle/bitbucket-token"
}

variable "catalogue_urls" {
  description = "Comma-separated Bitbucket raw file URLs for the certificate catalogue YAML files."
  type        = string
}

variable "spoke_role_name" {
  description = "Name of the IAM role to assume in each spoke account. Used as the SPOKE_ROLE_NAME Lambda environment variable."
  type        = string
  default     = "CertLifecycleRole"
}

variable "spoke_cert_lifecycle_role_arns" {
  description = "List of spoke-account CertLifecycleRole ARNs the Lambda is authorised to assume. Scoped in the sts:AssumeRole IAM statement."
  type        = list(string)
}

variable "cert_renewal_topic_arn" {
  description = "ARN of the SNS topic for certificate renewal notifications."
  type        = string
}

variable "cert_p1_alert_topic_arn" {
  description = "ARN of the SNS topic for P1 certificate alerts."
  type        = string
}

variable "jenkins_job_name" {
  description = "Jenkins certificate issuance job name. Included in Lambda alert notification bodies."
  type        = string
}

variable "jenkins_job_url" {
  description = "Jenkins certificate issuance job URL. Included in Lambda alert notification bodies."
  type        = string
}

<<<<<<< HEAD
variable "jenkins_trigger_secret_arn" {
  description = "ARN of the Secrets Manager secret containing Jenkins trigger credentials. Scoped in the Lambda IAM policy to this exact ARN."
  type        = string
}

variable "jenkins_trigger_secret_name" {
  description = "Name or path of the Jenkins trigger secret. Used as the JENKINS_TRIGGER_SECRET_ID Lambda environment variable."
  type        = string
}

=======
>>>>>>> origin/main
variable "runbook_url" {
  description = "Runbook URL. Included in Lambda alert notification bodies."
  type        = string
}

<<<<<<< HEAD
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
variable "tags" {
  description = "Tags to apply to all resources in this module."
  type        = map(string)
  default     = {}
}
