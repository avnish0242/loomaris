data "archive_file" "teardown_zip" {
  type        = "zip"
  output_path = "${path.module}/.terraform/teardown.zip"
  source {
    content  = <<-PYTHON
import json, boto3, os

CLUSTER = os.environ["ECS_CLUSTER"]
REGION  = os.environ.get("AWS_REGION", "us-east-1")

def handler(event, context):
    task_arn  = event.get("task_arn")
    image_uri = event.get("image_uri", "")

    if task_arn:
        ecs = boto3.client("ecs", region_name=REGION)
        try:
            ecs.stop_task(cluster=CLUSTER, task=task_arn, reason="Loomaris sim TTL expired")
        except Exception as e:
            print(f"stop_task error: {e}")

    if image_uri and ".amazonaws.com/" in image_uri:
        ecr = boto3.client("ecr", region_name=REGION)
        try:
            repo_tag  = image_uri.split("/", 1)[-1]
            repo, tag = repo_tag.rsplit(":", 1)
            ecr.batch_delete_image(repositoryName=repo, imageIds=[{"imageTag": tag}])
        except Exception as e:
            print(f"batch_delete_image error: {e}")

    return {"statusCode": 200, "body": "Teardown complete"}
PYTHON
    filename = "handler.py"
  }
}

resource "aws_lambda_function" "teardown" {
  function_name    = "loomaris-sim-teardown"
  filename         = data.archive_file.teardown_zip.output_path
  source_code_hash = data.archive_file.teardown_zip.output_base64sha256
  runtime          = "python3.12"
  handler          = "handler.handler"
  role             = aws_iam_role.sim_task_exec.arn
  timeout          = 30

  environment {
    variables = {
      ECS_CLUSTER = aws_ecs_cluster.sim.name
    }
  }

  tags = { "loomaris:sim-cost-center" = "sim" }
}
