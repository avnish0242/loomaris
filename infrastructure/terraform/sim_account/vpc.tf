resource "aws_vpc" "sim" {
  cidr_block           = "10.0.0.0/16"
  enable_dns_support   = true
  enable_dns_hostnames = true
  tags = { Name = "loomaris-sim", "loomaris:sim-cost-center" = "sim" }
}

resource "aws_internet_gateway" "sim" {
  vpc_id = aws_vpc.sim.id
  tags   = { Name = "loomaris-sim-igw" }
}

resource "aws_subnet" "sim_public" {
  vpc_id                  = aws_vpc.sim.id
  cidr_block              = "10.0.1.0/24"
  availability_zone       = "${var.aws_region}a"
  map_public_ip_on_launch = true
  tags                    = { Name = "loomaris-sim-public", "loomaris:sim-cost-center" = "sim" }
}

resource "aws_route_table" "sim_public" {
  vpc_id = aws_vpc.sim.id
  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.sim.id
  }
  tags = { Name = "loomaris-sim-rt" }
}

resource "aws_route_table_association" "sim_public" {
  subnet_id      = aws_subnet.sim_public.id
  route_table_id = aws_route_table.sim_public.id
}

resource "aws_security_group" "sim_task" {
  name        = "loomaris-sim-task"
  description = "Allow inbound app port + all outbound for simulation tasks"
  vpc_id      = aws_vpc.sim.id

  ingress {
    from_port   = 8000
    to_port     = 8000
    protocol    = "tcp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "loomaris-sim-task-sg", "loomaris:sim-cost-center" = "sim" }
}
