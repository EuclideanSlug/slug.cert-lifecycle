resource "aws_sns_topic" "cert_renewal" {
  name = var.cert_renewal_topic_name
  tags = var.tags
}

resource "aws_sns_topic" "cert_p1_alerts" {
  name = var.cert_p1_alert_topic_name
  tags = var.tags
}
