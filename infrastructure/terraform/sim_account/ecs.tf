resource "aws_ecs_cluster" "sim" {
  name = "loomaris-sim"
  setting {
    name  = "containerInsights"
    value = "disabled"   # save cost; re-enable for debugging
  }
  tags = { "loomaris:sim-cost-center" = "sim" }
}

resource "aws_ecs_cluster_capacity_providers" "sim" {
  cluster_name       = aws_ecs_cluster.sim.name
  capacity_providers = ["FARGATE", "FARGATE_SPOT"]
  default_capacity_provider_strategy {
    capacity_provider = "FARGATE"
    weight            = 1
  }
}
