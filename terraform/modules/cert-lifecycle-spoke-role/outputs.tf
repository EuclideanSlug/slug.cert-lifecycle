output "spoke_cert_lifecycle_role_arn" {
  description = "ARN of the CertLifecycleRole created in the spoke account."
  value       = aws_iam_role.certlifecycle.arn
}

output "spoke_cert_lifecycle_role_name" {
  description = "Name of the CertLifecycleRole created in the spoke account."
  value       = aws_iam_role.certlifecycle.name
}
