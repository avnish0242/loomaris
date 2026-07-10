output "alb_dns_name" {
  description = "ALB DNS name"
  value       = aws_lb.main.dns_name
}

output "backend_ecr_url" {
  description = "ECR URL for backend image"
  value       = aws_ecr_repository.backend.repository_url
}

output "frontend_ecr_url" {
  description = "ECR URL for frontend image"
  value       = aws_ecr_repository.frontend.repository_url
}

output "rds_endpoint" {
  description = "RDS PostgreSQL endpoint (host only)"
  value       = aws_db_instance.postgres.address
  sensitive   = true
}

output "redis_endpoint" {
  description = "ElastiCache Redis endpoint"
  value       = aws_elasticache_cluster.redis.cache_nodes[0].address
  sensitive   = true
}

output "secrets_manager_arn" {
  description = "Secrets Manager ARN for app secrets"
  value       = aws_secretsmanager_secret.app.arn
}

output "kms_key_arn" {
  description = "KMS master key ARN"
  value       = aws_kms_key.main.arn
}

output "github_actions_role_arn" {
  description = "IAM role ARN to set as AWS_ROLE_ARN in GitHub repo secrets"
  value       = aws_iam_role.github_actions.arn
}

output "ecs_cluster_name" {
  description = "ECS cluster name"
  value       = aws_ecs_cluster.main.name
}

output "s3_vpce_id" {
  description = "S3 Gateway VPC Endpoint ID"
  value       = aws_vpc_endpoint.s3.id
}

output "monthly_budget_name" {
  description = "AWS Budget name (monthly spend guardrail)"
  value       = aws_budgets_budget.monthly.name
}

output "waf_web_acl_arn" {
  description = "WAF WebACL ARN protecting the ALB"
  value       = aws_wafv2_web_acl.main.arn
}
