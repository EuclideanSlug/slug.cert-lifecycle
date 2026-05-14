variable "cert_renewal_topic_name" {
  description = "Name of the SNS topic for certificate renewal notifications (15-30 days remaining)."
  type        = string
  default     = "slug-cert-renewal"
}

variable "cert_p1_alert_topic_name" {
  description = "Name of the SNS topic for P1 certificate alerts (14 days or fewer remaining, including expired)."
  type        = string
  default     = "slug-cert-p1-alerts"
}

variable "tags" {
  description = "Tags to apply to all resources in this module."
  type        = map(string)
  default     = {}
}
