resource "aws_s3_bucket" "artifacts" {
  bucket        = "${local.name}-artifacts-prod"
  force_destroy = false
  tags          = merge(local.tags, { Name = "${local.name}-artifacts" })
}

resource "aws_s3_bucket" "logs" {
  bucket        = "${local.name}-logs-prod"
  force_destroy = false
  tags          = merge(local.tags, { Name = "${local.name}-logs" })
}

resource "aws_s3_bucket" "pulumi_state" {
  bucket        = "${local.name}-pulumi-state-prod"
  force_destroy = false
  tags          = merge(local.tags, { Name = "${local.name}-pulumi-state" })
}

# Versioning on all buckets
resource "aws_s3_bucket_versioning" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_versioning" "logs" {
  bucket = aws_s3_bucket.logs.id
  versioning_configuration { status = "Enabled" }
}
resource "aws_s3_bucket_versioning" "pulumi_state" {
  bucket = aws_s3_bucket.pulumi_state.id
  versioning_configuration { status = "Enabled" }
}

# KMS encryption
resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.main.arn
    }
    bucket_key_enabled = true
  }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "logs" {
  bucket = aws_s3_bucket.logs.id
  rule {
    apply_server_side_encryption_by_default {
      # ALB access logs require SSE-S3 (AES256) — CMK is not supported by the ELB service account
      sse_algorithm = "AES256"
    }
  }
}
resource "aws_s3_bucket_server_side_encryption_configuration" "pulumi_state" {
  bucket = aws_s3_bucket.pulumi_state.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.main.arn
    }
    bucket_key_enabled = true
  }
}

# Block all public access
resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_public_access_block" "logs" {
  bucket                  = aws_s3_bucket.logs.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
resource "aws_s3_bucket_public_access_block" "pulumi_state" {
  bucket                  = aws_s3_bucket.pulumi_state.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle rules — auto-expire objects to control storage costs

resource "aws_s3_bucket_lifecycle_configuration" "logs" {
  bucket     = aws_s3_bucket.logs.id
  depends_on = [aws_s3_bucket_versioning.logs]

  # ALB access logs: keep 90 days (compliance + debugging window)
  rule {
    id     = "expire-alb-logs"
    status = "Enabled"
    filter { prefix = "alb/" }
    expiration { days = 90 }
    noncurrent_version_expiration { noncurrent_days = 30 }
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "artifacts" {
  bucket     = aws_s3_bucket.artifacts.id
  depends_on = [aws_s3_bucket_versioning.artifacts]

  # Move artifacts to cheaper storage after 30 days; delete after 1 year
  rule {
    id     = "transition-and-expire-artifacts"
    status = "Enabled"
    filter { prefix = "" }
    transition {
      days          = 30
      storage_class = "STANDARD_IA"
    }
    expiration { days = 365 }
    noncurrent_version_expiration { noncurrent_days = 30 }
  }
}

# ALB access logs bucket policy — allows ELB service account to write access logs
resource "aws_s3_bucket_policy" "logs" {
  bucket     = aws_s3_bucket.logs.id
  depends_on = [aws_s3_bucket_public_access_block.logs]
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Sid    = "AllowELBAccessLogs"
      Effect = "Allow"
      Principal = { AWS = data.aws_elb_service_account.main.arn }
      Action   = "s3:PutObject"
      Resource = "${aws_s3_bucket.logs.arn}/alb/AWSLogs/${local.account_id}/*"
    }]
  })
}
