resource "random_password" "jwt_secret" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "app" {
  name                    = "${local.name}/production/app"
  description             = "Loomaris production application secrets"
  kms_key_id              = aws_kms_key.main.arn
  recovery_window_in_days = 7
  tags                    = merge(local.tags, { Name = "${local.name}-app-secrets" })
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id

  # DATABASE_URL is constructed here once RDS is provisioned.
  # To rotate credentials: update the secret version manually and redeploy ECS tasks.
  secret_string = jsonencode({
    DATABASE_URL         = "postgresql+asyncpg://loomaris:${random_password.db_password.result}@${aws_db_instance.postgres.address}:5432/loomaris"
    POSTGRES_PASSWORD    = random_password.db_password.result
    GOOGLE_CLIENT_ID     = var.google_client_id
    GOOGLE_CLIENT_SECRET = var.google_client_secret
    JWT_SECRET_KEY       = random_password.jwt_secret.result
    ENCRYPTION_KEY       = var.encryption_key
    ANTHROPIC_API_KEY    = var.anthropic_api_key
  })
}
