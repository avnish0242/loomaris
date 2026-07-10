resource "aws_ecs_cluster" "main" {
  name = local.name

  setting {
    name  = "containerInsights"
    value = "enabled"
  }

  tags = merge(local.tags, { Name = "${local.name}-cluster" })
}

# Register both FARGATE and FARGATE_SPOT so services can choose their strategy.
# Backend stays on on-demand (launch_type = FARGATE).
# Frontend uses mixed spot/on-demand via capacity_provider_strategy.
resource "aws_ecs_cluster_capacity_providers" "main" {
  cluster_name       = aws_ecs_cluster.main.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]

  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
    base              = 1
  }
}

resource "aws_cloudwatch_log_group" "backend" {
  name              = "/ecs/${local.name}/backend"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn
  tags              = local.tags
}

resource "aws_cloudwatch_log_group" "frontend" {
  name              = "/ecs/${local.name}/frontend"
  retention_in_days = 30
  kms_key_id        = aws_kms_key.main.arn
  tags              = local.tags
}
