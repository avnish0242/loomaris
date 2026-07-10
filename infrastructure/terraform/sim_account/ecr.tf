resource "aws_ecr_repository" "sim_previews" {
  name                 = "loomaris-previews"
  image_tag_mutability = "MUTABLE"
  force_delete         = true

  image_scanning_configuration {
    scan_on_push = false  # skip for ephemeral sim images
  }

  tags = { "loomaris:sim-cost-center" = "sim" }
}

resource "aws_ecr_lifecycle_policy" "sim_previews" {
  repository = aws_ecr_repository.sim_previews.name
  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Delete sim images older than 2 hours"
      selection = {
        tagStatus   = "any"
        countType   = "sinceImagePushed"
        countUnit   = "hours"
        countNumber = 2
      }
      action = { type = "expire" }
    }]
  })
}
