"""Minimal IAM action sets per deployment type — mirrors frontend permission-templates.ts."""

_STATIC = [
    "s3:CreateBucket", "s3:DeleteBucket", "s3:PutBucketPolicy", "s3:GetBucketPolicy",
    "s3:PutPublicAccessBlock", "s3:ListBucket",
    "s3:PutObject", "s3:GetObject", "s3:DeleteObject",
    "cloudfront:CreateDistribution", "cloudfront:UpdateDistribution",
    "cloudfront:GetDistribution", "cloudfront:DeleteDistribution",
    "cloudfront:CreateOriginAccessControl", "cloudfront:TagResource",
    "cloudfront:CreateInvalidation",
]

_CONTAINER_EXTRA = [
    "ecr:GetAuthorizationToken", "ecr:BatchGetImage", "ecr:InitiateLayerUpload",
    "ecr:UploadLayerPart", "ecr:CompleteLayerUpload", "ecr:PutImage",
    "ecr:CreateRepository", "ecr:DescribeRepositories",
    "ecs:CreateCluster", "ecs:RegisterTaskDefinition", "ecs:CreateService",
    "ecs:UpdateService", "ecs:DeleteService", "ecs:DescribeServices",
    "ecs:RunTask", "ecs:StopTask",
    "iam:PassRole",
    "elasticloadbalancing:CreateLoadBalancer", "elasticloadbalancing:CreateTargetGroup",
    "elasticloadbalancing:CreateListener", "elasticloadbalancing:RegisterTargets",
    "elasticloadbalancing:DescribeLoadBalancers",
    "ec2:DescribeVpcs", "ec2:DescribeSubnets", "ec2:DescribeSecurityGroups",
    "ec2:CreateSecurityGroup", "ec2:AuthorizeSecurityGroupIngress",
    "logs:CreateLogGroup", "logs:PutRetentionPolicy",
]

_LAMBDA = [
    "lambda:CreateFunction", "lambda:UpdateFunctionCode",
    "lambda:UpdateFunctionConfiguration", "lambda:DeleteFunction",
    "lambda:GetFunction", "lambda:AddPermission", "lambda:RemovePermission",
    "apigateway:POST", "apigateway:PUT", "apigateway:GET", "apigateway:DELETE",
    "iam:PassRole",
    "logs:CreateLogGroup", "logs:PutRetentionPolicy",
]

ACTIONS_BY_TYPE: dict[str, list[str]] = {
    "static": _STATIC,
    "container": list(dict.fromkeys(_STATIC + _CONTAINER_EXTRA)),
    "lambda": _LAMBDA,
}
