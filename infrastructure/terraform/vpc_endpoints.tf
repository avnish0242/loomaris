# S3 Gateway Endpoint — zero cost, routes all S3 traffic through the AWS backbone
# instead of the NAT Gateway. Saves $0.045/GB on every ECR image layer pull,
# artifact upload, and Terraform state read/write.
# S3 Gateway Endpoint on both route tables — ECS tasks (public subnets) and
# private subnets all route S3 traffic through the AWS backbone, not the internet.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${local.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.public.id, aws_route_table.private.id]
  tags              = merge(local.tags, { Name = "${local.name}-vpce-s3" })
}
