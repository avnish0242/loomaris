locals {
  redis_url = "redis://${aws_elasticache_cluster.redis.cache_nodes[0].address}:6379/0"
}

resource "aws_ecs_task_definition" "backend" {
  family                   = "${local.name}-backend"
  requires_compatibilities = ["FARGATE"]
  network_mode             = "awsvpc"
  cpu                      = 256
  memory                   = 512
  execution_role_arn       = aws_iam_role.ecs_execution.arn
  task_role_arn            = aws_iam_role.ecs_task.arn

  container_definitions = jsonencode([{
    name  = "backend"
    image = "${aws_ecr_repository.backend.repository_url}:${var.backend_image_tag}"

    portMappings = [{
      containerPort = 8000
      protocol      = "tcp"
    }]

    # Non-sensitive configuration as plain environment variables
    environment = [
      { name = "APP_ENV",             value = "production" },
      { name = "DOMAIN",              value = var.domain },
      { name = "FRONTEND_URL",        value = "https://app.${var.domain}" },
      { name = "BACKEND_URL",         value = "https://api.${var.domain}" },
      { name = "GOOGLE_REDIRECT_URI", value = "https://api.${var.domain}/api/v1/auth/google/callback" },
      { name = "GITHUB_REDIRECT_URI", value = "https://api.${var.domain}/api/v1/auth/github/callback" },
      { name = "ZOHO_REDIRECT_URI",          value = "https://api.${var.domain}/api/v1/auth/zoho/callback" },
      { name = "LOOMARIS_AWS_ACCOUNT_ID",    value = var.loomaris_aws_account_id },
      { name = "REDIS_URL",           value = local.redis_url },
      { name = "AWS_DEFAULT_REGION",  value = local.region },
      { name = "JWT_ALGORITHM",       value = "HS256" },
    ]

    # Sensitive secrets injected from Secrets Manager at task startup.
    # Format: <secret-arn>:<json-key>::
    secrets = [
      { name = "DATABASE_URL",         valueFrom = "${aws_secretsmanager_secret.app.arn}:DATABASE_URL::" },
      { name = "GOOGLE_CLIENT_ID",     valueFrom = "${aws_secretsmanager_secret.app.arn}:GOOGLE_CLIENT_ID::" },
      { name = "GOOGLE_CLIENT_SECRET", valueFrom = "${aws_secretsmanager_secret.app.arn}:GOOGLE_CLIENT_SECRET::" },
      { name = "GITHUB_CLIENT_ID",     valueFrom = "${aws_secretsmanager_secret.app.arn}:GITHUB_CLIENT_ID::" },
      { name = "GITHUB_CLIENT_SECRET", valueFrom = "${aws_secretsmanager_secret.app.arn}:GITHUB_CLIENT_SECRET::" },
      { name = "ZOHO_CLIENT_ID",                valueFrom = "${aws_secretsmanager_secret.app.arn}:ZOHO_CLIENT_ID::" },
      { name = "ZOHO_CLIENT_SECRET",            valueFrom = "${aws_secretsmanager_secret.app.arn}:ZOHO_CLIENT_SECRET::" },
      { name = "LOOMARIS_DEPLOYER_ACCESS_KEY",  valueFrom = "${aws_secretsmanager_secret.app.arn}:LOOMARIS_DEPLOYER_ACCESS_KEY::" },
      { name = "LOOMARIS_DEPLOYER_SECRET_KEY",  valueFrom = "${aws_secretsmanager_secret.app.arn}:LOOMARIS_DEPLOYER_SECRET_KEY::" },
      { name = "JWT_SECRET_KEY",       valueFrom = "${aws_secretsmanager_secret.app.arn}:JWT_SECRET_KEY::" },
      { name = "ENCRYPTION_KEY",       valueFrom = "${aws_secretsmanager_secret.app.arn}:ENCRYPTION_KEY::" },
      { name = "ANTHROPIC_API_KEY",    valueFrom = "${aws_secretsmanager_secret.app.arn}:ANTHROPIC_API_KEY::" },
    ]

    logConfiguration = {
      logDriver = "awslogs"
      options = {
        "awslogs-group"         = aws_cloudwatch_log_group.backend.name
        "awslogs-region"        = local.region
        "awslogs-stream-prefix" = "ecs"
      }
    }

    # ALB waits for this to pass before routing traffic to a new task
    healthCheck = {
      command     = ["CMD-SHELL", "curl -f http://localhost:8000/api/v1/health || exit 1"]
      interval    = 30
      timeout     = 5
      retries     = 3
      startPeriod = 60
    }
  }])

  tags = merge(local.tags, { Name = "${local.name}-backend-task" })
}

resource "aws_ecs_service" "backend" {
  name            = "${local.name}-backend"
  cluster         = aws_ecs_cluster.main.id
  task_definition = aws_ecs_task_definition.backend.arn
  desired_count   = 1
  launch_type     = "FARGATE"

  network_configuration {
    subnets          = aws_subnet.public[*].id
    security_groups  = [aws_security_group.ecs.id]
    assign_public_ip = true
  }

  load_balancer {
    target_group_arn = aws_lb_target_group.backend.arn
    container_name   = "backend"
    container_port   = 8000
  }

  # min=100% ensures a replacement task is healthy before the old one stops,
  # preventing downtime during deploys even with only 1 running task.
  deployment_minimum_healthy_percent = 100
  deployment_maximum_percent         = 200

  deployment_circuit_breaker {
    enable   = true
    rollback = true
  }

  depends_on = [aws_lb_listener.https, aws_iam_role_policy_attachment.ecs_execution_managed]
  tags       = local.tags

  lifecycle {
    # Ignore task_definition changes — the CI/CD pipeline manages deployments
    ignore_changes = [task_definition]
  }
}

resource "aws_appautoscaling_target" "backend" {
  max_capacity       = 5
  min_capacity       = 1
  resource_id        = "service/${aws_ecs_cluster.main.name}/${aws_ecs_service.backend.name}"
  scalable_dimension = "ecs:service:DesiredCount"
  service_namespace  = "ecs"
}

resource "aws_appautoscaling_policy" "backend_cpu" {
  name               = "${local.name}-backend-cpu"
  policy_type        = "TargetTrackingScaling"
  resource_id        = aws_appautoscaling_target.backend.resource_id
  scalable_dimension = aws_appautoscaling_target.backend.scalable_dimension
  service_namespace  = aws_appautoscaling_target.backend.service_namespace

  target_tracking_scaling_policy_configuration {
    predefined_metric_specification {
      predefined_metric_type = "ECSServiceAverageCPUUtilization"
    }
    target_value       = 60.0
    scale_in_cooldown  = 300
    scale_out_cooldown = 60
  }
}
