output "ecs_cluster_arn" {
  description = "Set as SIM_ECS_CLUSTER in .env.local"
  value       = aws_ecs_cluster.sim.arn
}

output "ecr_base_uri" {
  description = "Set as SIM_ECR_BASE_URI in .env.local (omit trailing slash)"
  value       = "${var.aws_account_id}.dkr.ecr.${var.aws_region}.amazonaws.com/loomaris-previews"
}

output "sim_subnet_id" {
  description = "Set as SIM_SUBNET_ID in .env.local"
  value       = aws_subnet.sim_public.id
}

output "sim_security_group_id" {
  description = "Set as SIM_SECURITY_GROUP_ID in .env.local"
  value       = aws_security_group.sim_task.id
}

output "sim_task_execution_role_arn" {
  description = "Set as SIM_TASK_EXECUTION_ROLE in .env.local"
  value       = aws_iam_role.sim_task_exec.arn
}

output "teardown_lambda_arn" {
  description = "Set as SIM_TEARDOWN_LAMBDA_ARN in .env.local"
  value       = aws_lambda_function.teardown.arn
}
