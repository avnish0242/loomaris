data "aws_iam_policy_document" "ecs_task_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["ecs-tasks.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "sim_task_exec" {
  name               = "loomaris-sim-exec"
  assume_role_policy = data.aws_iam_policy_document.ecs_task_assume.json
  tags               = { "loomaris:sim-cost-center" = "sim" }
}

resource "aws_iam_role_policy_attachment" "sim_task_exec_policy" {
  role       = aws_iam_role.sim_task_exec.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy"
}

# Allow deployer to assume sim exec role (for EventBridge Scheduler target)
data "aws_iam_policy_document" "scheduler_assume" {
  statement {
    actions = ["sts:AssumeRole"]
    principals {
      type        = "Service"
      identifiers = ["scheduler.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "scheduler" {
  name               = "loomaris-sim-scheduler"
  assume_role_policy = data.aws_iam_policy_document.scheduler_assume.json
}

resource "aws_iam_role_policy" "scheduler_invoke_lambda" {
  role = aws_iam_role.scheduler.name
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect   = "Allow"
      Action   = ["lambda:InvokeFunction"]
      Resource = aws_lambda_function.teardown.arn
    }]
  })
}

# Allow deployer IAM user from control-plane account to call ECS/ECR/EventBridge in sim account
resource "aws_iam_policy" "deployer_sim_access" {
  name = "loomaris-deployer-sim-access"
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid    = "ECSSimAccess"
        Effect = "Allow"
        Action = [
          "ecs:RegisterTaskDefinition", "ecs:RunTask", "ecs:StopTask",
          "ecs:DescribeTasks", "ecs:DeregisterTaskDefinition",
        ]
        Resource = "*"
      },
      {
        Sid    = "ECRSimAccess"
        Effect = "Allow"
        Action = [
          "ecr:GetAuthorizationToken", "ecr:BatchGetImage",
          "ecr:InitiateLayerUpload", "ecr:UploadLayerPart",
          "ecr:CompleteLayerUpload", "ecr:PutImage",
          "ecr:CreateRepository", "ecr:BatchDeleteImage",
          "ecr:DescribeRepositories",
        ]
        Resource = "*"
      },
      {
        Sid    = "EC2Describe"
        Effect = "Allow"
        Action = ["ec2:DescribeNetworkInterfaces"]
        Resource = "*"
      },
      {
        Sid    = "SchedulerAccess"
        Effect = "Allow"
        Action = [
          "scheduler:CreateSchedule", "scheduler:DeleteSchedule",
          "scheduler:GetSchedule",
        ]
        Resource = "*"
      },
      {
        Sid    = "PassSchedulerRole"
        Effect = "Allow"
        Action = ["iam:PassRole"]
        Resource = aws_iam_role.scheduler.arn
      },
      {
        Sid    = "CloudWatchLogsCreate"
        Effect = "Allow"
        Action = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "*"
      },
    ]
  })
}
