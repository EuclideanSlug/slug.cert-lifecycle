output "lambda_function_name" {
  description = "Name of the expiry checker Lambda function."
  value       = aws_lambda_function.expiry_checker.function_name
}

output "lambda_function_arn" {
  description = "ARN of the expiry checker Lambda function."
  value       = aws_lambda_function.expiry_checker.arn
}

output "lambda_execution_role_arn" {
  description = "ARN of the Lambda execution IAM role. Provide this to the spoke module as lambda_execution_role_arn."
  value       = aws_iam_role.lambda_exec.arn
}

output "lambda_execution_role_name" {
  description = "Name of the Lambda execution IAM role."
  value       = aws_iam_role.lambda_exec.name
}

output "cloudwatch_log_group_name" {
  description = "Name of the Lambda CloudWatch log group."
  value       = aws_cloudwatch_log_group.lambda_logs.name
}

output "cloudwatch_log_group_arn" {
  description = "ARN of the Lambda CloudWatch log group."
  value       = aws_cloudwatch_log_group.lambda_logs.arn
}

output "daily_schedule_name" {
  description = "Name of the EventBridge Scheduler schedule that invokes the Lambda daily."
  value       = aws_scheduler_schedule.daily_expiry_check.name
}

output "daily_schedule_arn" {
  description = "ARN of the EventBridge Scheduler schedule that invokes the Lambda daily."
  value       = aws_scheduler_schedule.daily_expiry_check.arn
}
