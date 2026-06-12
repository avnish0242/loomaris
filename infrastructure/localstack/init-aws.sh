#!/bin/bash
# LocalStack initialization — runs automatically when LocalStack is ready
set -e

echo "[LocalStack Init] Creating Loomaris dev AWS resources..."

# ─── S3 Buckets ──────────────────────────────────────────────────────────────
awslocal s3 mb s3://loomaris-pulumi-state-dev    2>/dev/null || true
awslocal s3 mb s3://loomaris-artifacts-dev        2>/dev/null || true
awslocal s3 mb s3://loomaris-logs-dev             2>/dev/null || true

# Enable versioning on state bucket (Pulumi state must be versioned)
awslocal s3api put-bucket-versioning \
  --bucket loomaris-pulumi-state-dev \
  --versioning-configuration Status=Enabled

# ─── KMS Key ─────────────────────────────────────────────────────────────────
KMS_KEY_ID=$(awslocal kms create-key \
  --description "Loomaris Dev Master Key" \
  --query 'KeyMetadata.KeyId' \
  --output text 2>/dev/null) || true

if [ -n "$KMS_KEY_ID" ]; then
  awslocal kms create-alias \
    --alias-name alias/loomaris-dev-master \
    --target-key-id "$KMS_KEY_ID" 2>/dev/null || true
fi

# ─── Secrets Manager (placeholder for dev secrets) ───────────────────────────
awslocal secretsmanager create-secret \
  --name "loomaris/dev/placeholder" \
  --secret-string '{"note":"dev placeholder"}' 2>/dev/null || true

echo "[LocalStack Init] Resources ready:"
echo "  s3://loomaris-pulumi-state-dev  (versioned)"
echo "  s3://loomaris-artifacts-dev"
echo "  s3://loomaris-logs-dev"
echo "  KMS alias: alias/loomaris-dev-master"
