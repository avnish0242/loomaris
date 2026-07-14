variable "aws_region" {
  description = "AWS region"
  type        = string
  default     = "us-east-1"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "production"
}

variable "domain" {
  description = "Primary domain name"
  type        = string
  default     = "loomaris.xyz"
}

variable "backend_image_tag" {
  description = "Docker image tag for the backend service"
  type        = string
  default     = "latest"
}

variable "frontend_image_tag" {
  description = "Docker image tag for the frontend service"
  type        = string
  default     = "latest"
}

variable "google_client_id" {
  description = "Google OAuth 2.0 client ID"
  type        = string
  sensitive   = true
}

variable "google_client_secret" {
  description = "Google OAuth 2.0 client secret"
  type        = string
  sensitive   = true
}

variable "github_client_id" {
  description = "GitHub OAuth App client ID"
  type        = string
  sensitive   = true
}

variable "github_client_secret" {
  description = "GitHub OAuth App client secret"
  type        = string
  sensitive   = true
}

variable "zoho_client_id" {
  description = "Zoho OAuth client ID"
  type        = string
  sensitive   = true
  default     = ""
}

variable "zoho_client_secret" {
  description = "Zoho OAuth client secret"
  type        = string
  sensitive   = true
  default     = ""
}

variable "loomaris_aws_account_id" {
  description = "AWS account ID of the Loomaris control-plane account (12-digit number, used in trust policy ARN)"
  type        = string
  default     = ""
}

variable "loomaris_deployer_access_key" {
  description = "Access key for the loomaris-deployer IAM user (used for cross-account STS assume-role)"
  type        = string
  sensitive   = true
  default     = ""
}

variable "loomaris_deployer_secret_key" {
  description = "Secret key for the loomaris-deployer IAM user"
  type        = string
  sensitive   = true
  default     = ""
}

variable "anthropic_api_key" {
  description = "Anthropic Claude API key (sk-ant-...)"
  type        = string
  sensitive   = true
}

variable "encryption_key" {
  description = "Fernet encryption key for secrets at rest. Generate: python3 -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
  type        = string
  sensitive   = true
}

variable "github_repository" {
  description = "GitHub repository in 'owner/repo' format (for OIDC trust policy)"
  type        = string
  default     = "avnish0242/loomaris"
}

variable "alert_email" {
  description = "Email address for budget alerts and cost anomaly notifications"
  type        = string
  default     = "avnish.dbg@gmail.com"
}

variable "monthly_budget_usd" {
  description = "Monthly spend ceiling in USD — alerts fire at 80% and 100%"
  type        = number
  default     = 160
}

variable "cloudflare_api_token" {
  description = "Cloudflare API token with Edit Zone DNS permissions for loomaris.xyz"
  type        = string
  sensitive   = true
}

variable "cloudflare_zone_id" {
  description = "Cloudflare Zone ID for loomaris.xyz (found on the Overview page)"
  type        = string
}
