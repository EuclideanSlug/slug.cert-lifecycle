output "jagent_cert_write_policy_arn" {
  description = "ARN of the Secrets Manager write policy attached to the issuer role."
  value       = aws_iam_policy.jagent_cert_write.arn
}
