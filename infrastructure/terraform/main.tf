provider "aws" {
  region = var.aws_region
}

provider "cloudflare" {
  api_token = var.cloudflare_api_token
}

data "aws_caller_identity" "current" {}
data "aws_availability_zones" "available" { state = "available" }
data "aws_elb_service_account" "main" {}

locals {
  name        = "loomaris"
  environment = var.environment
  region      = var.aws_region
  account_id  = data.aws_caller_identity.current.account_id

  tags = {
    Project     = "loomaris"
    Environment = var.environment
    ManagedBy   = "terraform"
  }
}
