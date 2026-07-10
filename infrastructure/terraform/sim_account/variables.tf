variable "aws_region" {
  description = "AWS region for simulation infrastructure"
  type        = string
  default     = "us-east-1"
}

variable "aws_account_id" {
  description = "Loomaris simulation AWS account ID"
  type        = string
}

variable "loomaris_deployer_arn" {
  description = "ARN of the loomaris-deployer IAM user (in control-plane account)"
  type        = string
}

variable "alert_email" {
  description = "Email for budget alerts"
  type        = string
  default     = "avnish.dbg@gmail.com"
}
