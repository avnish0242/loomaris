resource "aws_kms_key" "main" {
  description             = "Loomaris production master encryption key"
  deletion_window_in_days = 30
  enable_key_rotation     = true

  # Account root has full access; IAM policies on roles control fine-grained access.
  # Service principals (Secrets Manager, RDS) are granted directly here.
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "EnableRootIAMAccess"
        Effect = "Allow"
        Principal = { AWS = "arn:aws:iam::${local.account_id}:root" }
        Action   = "kms:*"
        Resource = "*"
      },
      {
        Sid    = "AllowSecretsManager"
        Effect = "Allow"
        Principal = { Service = "secretsmanager.amazonaws.com" }
        Action   = ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"]
        Resource = "*"
      },
      {
        Sid    = "AllowRDS"
        Effect = "Allow"
        Principal = { Service = "rds.amazonaws.com" }
        Action   = ["kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey", "kms:CreateGrant"]
        Resource = "*"
      },
      {
        Sid    = "AllowCloudWatchLogs"
        Effect = "Allow"
        Principal = { Service = "logs.us-east-1.amazonaws.com" }
        Action   = ["kms:Encrypt", "kms:Decrypt", "kms:GenerateDataKey", "kms:DescribeKey"]
        Resource = "*"
        Condition = {
          ArnLike = {
            "kms:EncryptionContext:aws:logs:arn" = "arn:aws:logs:us-east-1:${local.account_id}:*"
          }
        }
      }
    ]
  })

  tags = merge(local.tags, { Name = "${local.name}-kms" })
}

resource "aws_kms_alias" "main" {
  name          = "alias/${local.name}-prod"
  target_key_id = aws_kms_key.main.key_id
}
