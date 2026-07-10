resource "aws_elasticache_subnet_group" "main" {
  name        = "${local.name}-redis-subnet-group"
  description = "ElastiCache subnet group for Loomaris"
  subnet_ids  = aws_subnet.private[*].id
  tags        = local.tags
}

resource "aws_elasticache_cluster" "redis" {
  cluster_id           = "${local.name}-redis"
  engine               = "redis"
  node_type            = "cache.t3.micro"
  num_cache_nodes      = 1
  parameter_group_name = "default.redis7"
  engine_version       = "7.1"
  port                 = 6379

  subnet_group_name  = aws_elasticache_subnet_group.main.name
  security_group_ids = [aws_security_group.redis.id]

  maintenance_window       = "sun:05:00-sun:06:00"
  snapshot_retention_limit = 7
  snapshot_window          = "04:00-05:00"

  tags = merge(local.tags, { Name = "${local.name}-redis" })
}
