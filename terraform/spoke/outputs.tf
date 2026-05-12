output "spoke_cert_lifecycle_role_arn" {
  description = "ARN of the CertLifecycleRole created in this spoke account."
  value       = module.spoke_role.spoke_cert_lifecycle_role_arn
}

output "spoke_cert_lifecycle_role_name" {
  description = "Name of the CertLifecycleRole created in this spoke account."
  value       = module.spoke_role.spoke_cert_lifecycle_role_name
}

output "jagent_cert_write_policy_arn" {
  description = "ARN of the jagent Secrets Manager write policy. Only set when enable_issuer_permissions is true."
  value       = var.enable_issuer_permissions ? module.issuer_permissions[0].jagent_cert_write_policy_arn : null
}
