# ─── Security Group shells (no cross-SG references inline) ───────────────────
# Rules that reference another SG are in aws_security_group_rule resources below.
# This avoids the Terraform cycle that occurs when two SGs reference each other.

# ALB — accept HTTP/HTTPS from internet, outbound only to ECS task ports
resource "aws_security_group" "alb" {
  name        = "${local.name}-alb"
  description = "ALB: inbound HTTP/HTTPS from internet, outbound to ECS only"
  vpc_id      = aws_vpc.main.id

  ingress {
    from_port   = 80
    to_port     = 80
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  ingress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = merge(local.tags, { Name = "${local.name}-sg-alb" })
}

# ECS tasks — inbound from ALB only, egress locked to exactly what the app needs
resource "aws_security_group" "ecs" {
  name        = "${local.name}-ecs"
  description = "ECS tasks: inbound from ALB only, outbound HTTPS/DNS/Postgres/Redis"
  vpc_id      = aws_vpc.main.id

  # HTTPS only — Claude API, Google OAuth, ECR pulls, Secrets Manager, CloudWatch Logs
  egress {
    from_port   = 443
    to_port     = 443
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }
  # DNS via VPC resolver
  egress {
    from_port   = 53
    to_port     = 53
    protocol    = "udp"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }
  egress {
    from_port   = 53
    to_port     = 53
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }
  # PostgreSQL to RDS
  egress {
    from_port   = 5432
    to_port     = 5432
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }
  # Redis to ElastiCache
  egress {
    from_port   = 6379
    to_port     = 6379
    protocol    = "tcp"
    cidr_blocks = [aws_vpc.main.cidr_block]
  }

  tags = merge(local.tags, { Name = "${local.name}-sg-ecs" })
}

# RDS — inbound from ECS only, no outbound (SG is stateful; responses flow without egress rules)
resource "aws_security_group" "rds" {
  name        = "${local.name}-rds"
  description = "RDS: inbound from ECS tasks only, no outbound"
  vpc_id      = aws_vpc.main.id
  tags        = merge(local.tags, { Name = "${local.name}-sg-rds" })
}

# ElastiCache — inbound from ECS only, no outbound
resource "aws_security_group" "redis" {
  name        = "${local.name}-redis"
  description = "ElastiCache: inbound from ECS tasks only, no outbound"
  vpc_id      = aws_vpc.main.id
  tags        = merge(local.tags, { Name = "${local.name}-sg-redis" })
}

# ─── Cross-SG rules (separate resources to break the ALB ↔ ECS cycle) ────────

resource "aws_security_group_rule" "alb_egress_backend" {
  type                     = "egress"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.alb.id
  source_security_group_id = aws_security_group.ecs.id
}

resource "aws_security_group_rule" "alb_egress_frontend" {
  type                     = "egress"
  from_port                = 3000
  to_port                  = 3000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.alb.id
  source_security_group_id = aws_security_group.ecs.id
}

resource "aws_security_group_rule" "ecs_ingress_backend" {
  type                     = "ingress"
  from_port                = 8000
  to_port                  = 8000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.ecs.id
  source_security_group_id = aws_security_group.alb.id
}

resource "aws_security_group_rule" "ecs_ingress_frontend" {
  type                     = "ingress"
  from_port                = 3000
  to_port                  = 3000
  protocol                 = "tcp"
  security_group_id        = aws_security_group.ecs.id
  source_security_group_id = aws_security_group.alb.id
}

resource "aws_security_group_rule" "rds_ingress_ecs" {
  type                     = "ingress"
  from_port                = 5432
  to_port                  = 5432
  protocol                 = "tcp"
  security_group_id        = aws_security_group.rds.id
  source_security_group_id = aws_security_group.ecs.id
}

resource "aws_security_group_rule" "redis_ingress_ecs" {
  type                     = "ingress"
  from_port                = 6379
  to_port                  = 6379
  protocol                 = "tcp"
  security_group_id        = aws_security_group.redis.id
  source_security_group_id = aws_security_group.ecs.id
}
