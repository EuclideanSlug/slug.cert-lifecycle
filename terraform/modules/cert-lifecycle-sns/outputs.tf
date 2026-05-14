output "cert_renewal_topic_arn" {
  description = "ARN of the certificate renewal SNS topic."
  value       = aws_sns_topic.cert_renewal.arn
}

output "cert_p1_alert_topic_arn" {
  description = "ARN of the P1 certificate alert SNS topic."
  value       = aws_sns_topic.cert_p1_alerts.arn
}

output "cert_renewal_topic_name" {
  description = "Name of the certificate renewal SNS topic."
  value       = aws_sns_topic.cert_renewal.name
}

output "cert_p1_alert_topic_name" {
  description = "Name of the P1 certificate alert SNS topic."
  value       = aws_sns_topic.cert_p1_alerts.name
}
