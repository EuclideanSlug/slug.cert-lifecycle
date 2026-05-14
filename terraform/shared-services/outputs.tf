output "lambda_function_name" {
  description = "Name of the expiry checker Lambda function."
  value       = module.cert_expiry_checker.lambda_function_name
}

output "lambda_function_arn" {
  description = "ARN of the expiry checker Lambda function."
  value       = module.cert_expiry_checker.lambda_function_arn
}

output "lambda_execution_role_arn" {
  description = "ARN of the Lambda execution role. Provide this to each spoke root module as lambda_execution_role_arn."
  value       = module.cert_expiry_checker.lambda_execution_role_arn
}

output "lambda_execution_role_name" {
  description = "Name of the Lambda execution IAM role."
  value       = module.cert_expiry_checker.lambda_execution_role_name
}

output "cloudwatch_log_group_name" {
  description = "Name of the Lambda CloudWatch log group."
  value       = module.cert_expiry_checker.cloudwatch_log_group_name
}

output "cloudwatch_log_group_arn" {
  description = "ARN of the Lambda CloudWatch log group."
  value       = module.cert_expiry_checker.cloudwatch_log_group_arn
}

output "cert_renewal_topic_arn" {
  description = "ARN of the certificate renewal SNS topic."
  value       = module.sns.cert_renewal_topic_arn
}

output "cert_p1_alert_topic_arn" {
  description = "ARN of the P1 certificate alert SNS topic."
  value       = module.sns.cert_p1_alert_topic_arn
}

output "bitbucket_token_secret_arn" {
  description = "ARN of the Bitbucket token Secrets Manager secret."
  value       = local.bitbucket_token_secret_arn
}

output "jenkins_trigger_secret_arn" {
  description = "ARN of the Jenkins trigger credential Secrets Manager secret."
  value       = local.jenkins_trigger_secret_arn
}

output "daily_schedule_name" {
  description = "Name of the EventBridge Scheduler schedule that invokes the Lambda daily."
  value       = module.cert_expiry_checker.daily_schedule_name
}

output "daily_schedule_arn" {
  description = "ARN of the EventBridge Scheduler schedule that invokes the Lambda daily."
  value       = module.cert_expiry_checker.daily_schedule_arn
}
