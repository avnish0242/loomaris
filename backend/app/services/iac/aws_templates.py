"""
Pre-built Pulumi Python program templates for AWS deployment targets.
Each function returns a complete, runnable Pulumi program as a string.
"""


def static_site_program(app_slug: str, aws_region: str, static_files: list[tuple[str, str]]) -> str:
    """S3 + CloudFront static site. files is list of (path, content) tuples."""
    files_code = "\n    ".join(
        f'aws.s3.BucketObject("{p.replace("/", "-")}", bucket=bucket.id, '
        f'key="{p}", content=open("/app/static/{p}").read() if False else {repr(c[:200]+"...")}, '
        f'content_type=_mime("{p}")),'
        for p, c in static_files[:5]  # show first 5 as example; actual upload done separately
    )
    return f'''\
"""Loomaris-generated Pulumi program — {app_slug} static site on AWS S3 + CloudFront"""
import pulumi
import pulumi_aws as aws

# ── S3 Bucket ─────────────────────────────────────────────────────────────────
bucket = aws.s3.Bucket(
    "{app_slug}-site",
    website=aws.s3.BucketWebsiteArgs(
        index_document="index.html",
        error_document="index.html",
    ),
    versioning=aws.s3.BucketVersioningArgs(enabled=True),
    tags={{"loomaris:app": "{app_slug}", "loomaris:managed": "true"}},
)

# Block all public access; CloudFront OAC handles access
bucket_pab = aws.s3.BucketPublicAccessBlock(
    "{app_slug}-pab",
    bucket=bucket.id,
    block_public_acls=True,
    block_public_policy=True,
    ignore_public_acls=True,
    restrict_public_buckets=True,
)

# ── CloudFront OAC ────────────────────────────────────────────────────────────
oac = aws.cloudfront.OriginAccessControl(
    "{app_slug}-oac",
    description="OAC for {app_slug}",
    origin_access_control_origin_type="s3",
    signing_behavior="always",
    signing_protocol="sigv4",
)

# ── CloudFront Distribution ───────────────────────────────────────────────────
distribution = aws.cloudfront.Distribution(
    "{app_slug}-cdn",
    enabled=True,
    default_root_object="index.html",
    origins=[
        aws.cloudfront.DistributionOriginArgs(
            domain_name=bucket.bucket_regional_domain_name,
            origin_id="{app_slug}-s3",
            origin_access_control_id=oac.id,
        )
    ],
    default_cache_behavior=aws.cloudfront.DistributionDefaultCacheBehaviorArgs(
        target_origin_id="{app_slug}-s3",
        viewer_protocol_policy="redirect-to-https",
        allowed_methods=["GET", "HEAD"],
        cached_methods=["GET", "HEAD"],
        forwarded_values=aws.cloudfront.DistributionDefaultCacheBehaviorForwardedValuesArgs(
            query_string=False,
            cookies=aws.cloudfront.DistributionDefaultCacheBehaviorForwardedValuesCookiesArgs(
                forward="none"
            ),
        ),
        min_ttl=0,
        default_ttl=3600,
        max_ttl=86400,
    ),
    custom_error_responses=[
        aws.cloudfront.DistributionCustomErrorResponseArgs(
            error_code=404,
            response_code=200,
            response_page_path="/index.html",
        )
    ],
    restrictions=aws.cloudfront.DistributionRestrictionsArgs(
        geo_restriction=aws.cloudfront.DistributionRestrictionsGeoRestrictionArgs(
            restriction_type="none"
        )
    ),
    viewer_certificate=aws.cloudfront.DistributionViewerCertificateArgs(
        cloudfront_default_certificate=True
    ),
    tags={{"loomaris:app": "{app_slug}", "loomaris:managed": "true"}},
    opts=pulumi.ResourceOptions(depends_on=[bucket_pab]),
)

# ── S3 Bucket Policy (allow CloudFront OAC) ───────────────────────────────────
import json
bucket_policy = aws.s3.BucketPolicy(
    "{app_slug}-policy",
    bucket=bucket.id,
    policy=pulumi.Output.all(bucket.arn, distribution.arn).apply(
        lambda args: json.dumps({{
            "Version": "2012-10-17",
            "Statement": [{{
                "Sid": "AllowCloudFrontOAC",
                "Effect": "Allow",
                "Principal": {{"Service": "cloudfront.amazonaws.com"}},
                "Action": "s3:GetObject",
                "Resource": f"{{args[0]}}/*",
                "Condition": {{"StringEquals": {{"AWS:SourceArn": args[1]}}}},
            }}],
        }})
    ),
    opts=pulumi.ResourceOptions(depends_on=[bucket_pab]),
)

pulumi.export("cdn_url", distribution.domain_name.apply(lambda d: f"https://{{d}}"))
pulumi.export("bucket_name", bucket.id)
pulumi.export("distribution_id", distribution.id)
'''


def container_program(app_slug: str, aws_region: str, aws_account_id: str) -> str:
    """ECR + ECS Fargate + ALB containerised application."""
    return f'''\
"""Loomaris-generated Pulumi program — {app_slug} container on AWS ECS Fargate"""
import pulumi
import pulumi_aws as aws

# ── ECR Repository ────────────────────────────────────────────────────────────
repo = aws.ecr.Repository(
    "{app_slug}-repo",
    name="{app_slug}",
    image_scanning_configuration=aws.ecr.RepositoryImageScanningConfigurationArgs(
        scan_on_push=True
    ),
    image_tag_mutability="MUTABLE",
    tags={{"loomaris:app": "{app_slug}", "loomaris:managed": "true"}},
)

# ── VPC (default) ─────────────────────────────────────────────────────────────
default_vpc = aws.ec2.get_vpc(default=True)
default_subnets = aws.ec2.get_subnets(
    filters=[aws.ec2.GetSubnetsFilterArgs(name="vpc-id", values=[default_vpc.id])]
)

# ── Security Groups ───────────────────────────────────────────────────────────
alb_sg = aws.ec2.SecurityGroup(
    "{app_slug}-alb-sg",
    vpc_id=default_vpc.id,
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(from_port=80, to_port=80, protocol="tcp", cidr_blocks=["0.0.0.0/0"]),
        aws.ec2.SecurityGroupIngressArgs(from_port=443, to_port=443, protocol="tcp", cidr_blocks=["0.0.0.0/0"]),
    ],
    egress=[aws.ec2.SecurityGroupEgressArgs(from_port=0, to_port=0, protocol="-1", cidr_blocks=["0.0.0.0/0"])],
    tags={{"loomaris:app": "{app_slug}"}},
)

app_sg = aws.ec2.SecurityGroup(
    "{app_slug}-app-sg",
    vpc_id=default_vpc.id,
    ingress=[
        aws.ec2.SecurityGroupIngressArgs(from_port=8000, to_port=8000, protocol="tcp", security_groups=[alb_sg.id]),
    ],
    egress=[aws.ec2.SecurityGroupEgressArgs(from_port=0, to_port=0, protocol="-1", cidr_blocks=["0.0.0.0/0"])],
    tags={{"loomaris:app": "{app_slug}"}},
)

# ── ECS Cluster ───────────────────────────────────────────────────────────────
cluster = aws.ecs.Cluster(
    "{app_slug}-cluster",
    settings=[aws.ecs.ClusterSettingArgs(name="containerInsights", value="enabled")],
    tags={{"loomaris:app": "{app_slug}"}},
)

# ── IAM Task Execution Role ───────────────────────────────────────────────────
import json
exec_role = aws.iam.Role(
    "{app_slug}-exec-role",
    assume_role_policy=json.dumps({{
        "Version": "2012-10-17",
        "Statement": [{{
            "Action": "sts:AssumeRole",
            "Effect": "Allow",
            "Principal": {{"Service": "ecs-tasks.amazonaws.com"}},
        }}],
    }}),
)
aws.iam.RolePolicyAttachment(
    "{app_slug}-exec-policy",
    role=exec_role.name,
    policy_arn="arn:aws:iam::aws:policy/service-role/AmazonECSTaskExecutionRolePolicy",
)

# ── Task Definition ───────────────────────────────────────────────────────────
task_def = aws.ecs.TaskDefinition(
    "{app_slug}-task",
    family="{app_slug}",
    cpu="256",
    memory="512",
    network_mode="awsvpc",
    requires_compatibilities=["FARGATE"],
    execution_role_arn=exec_role.arn,
    container_definitions=repo.repository_url.apply(lambda url: json.dumps([{{
        "name": "{app_slug}",
        "image": f"{{url}}:latest",
        "portMappings": [{{"containerPort": 8000, "protocol": "tcp"}}],
        "essential": True,
        "environment": [],
        "logConfiguration": {{
            "logDriver": "awslogs",
            "options": {{
                "awslogs-group": "/ecs/{app_slug}",
                "awslogs-region": "{aws_region}",
                "awslogs-stream-prefix": "ecs",
            }},
        }},
    }}])),
    tags={{"loomaris:app": "{app_slug}"}},
)

# ── CloudWatch Log Group ──────────────────────────────────────────────────────
log_group = aws.cloudwatch.LogGroup(
    "{app_slug}-logs",
    name="/ecs/{app_slug}",
    retention_in_days=7,
)

# ── ALB ───────────────────────────────────────────────────────────────────────
alb = aws.lb.LoadBalancer(
    "{app_slug}-alb",
    internal=False,
    load_balancer_type="application",
    security_groups=[alb_sg.id],
    subnets=default_subnets.ids,
    tags={{"loomaris:app": "{app_slug}"}},
)

target_group = aws.lb.TargetGroup(
    "{app_slug}-tg",
    port=8000,
    protocol="HTTP",
    target_type="ip",
    vpc_id=default_vpc.id,
    health_check=aws.lb.TargetGroupHealthCheckArgs(path="/health", interval=30),
    tags={{"loomaris:app": "{app_slug}"}},
)

listener = aws.lb.Listener(
    "{app_slug}-listener",
    load_balancer_arn=alb.arn,
    port=80,
    protocol="HTTP",
    default_actions=[aws.lb.ListenerDefaultActionArgs(
        type="forward",
        target_group_arn=target_group.arn,
    )],
)

# ── ECS Service ───────────────────────────────────────────────────────────────
service = aws.ecs.Service(
    "{app_slug}-service",
    cluster=cluster.arn,
    task_definition=task_def.arn,
    desired_count=1,
    launch_type="FARGATE",
    network_configuration=aws.ecs.ServiceNetworkConfigurationArgs(
        subnets=default_subnets.ids,
        security_groups=[app_sg.id],
        assign_public_ip=True,
    ),
    load_balancers=[aws.ecs.ServiceLoadBalancerArgs(
        target_group_arn=target_group.arn,
        container_name="{app_slug}",
        container_port=8000,
    )],
    tags={{"loomaris:app": "{app_slug}"}},
    opts=pulumi.ResourceOptions(depends_on=[listener]),
)

pulumi.export("alb_url", alb.dns_name.apply(lambda d: f"http://{{d}}"))
pulumi.export("ecr_repo_url", repo.repository_url)
pulumi.export("cluster_arn", cluster.arn)
pulumi.export("service_name", service.name)
'''


def lambda_program(app_slug: str, aws_region: str) -> str:
    """Lambda function + API Gateway v2 HTTP API."""
    return f'''\
"""Loomaris-generated Pulumi program — {app_slug} on AWS Lambda + API Gateway"""
import pulumi
import pulumi_aws as aws
import json

# ── IAM Role ──────────────────────────────────────────────────────────────────
lambda_role = aws.iam.Role(
    "{app_slug}-lambda-role",
    assume_role_policy=json.dumps({{
        "Version": "2012-10-17",
        "Statement": [{{
            "Action": "sts:AssumeRole",
            "Effect": "Allow",
            "Principal": {{"Service": "lambda.amazonaws.com"}},
        }}],
    }}),
)

aws.iam.RolePolicyAttachment(
    "{app_slug}-lambda-basic",
    role=lambda_role.name,
    policy_arn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole",
)

# ── Lambda Function ───────────────────────────────────────────────────────────
# The function code is expected to be zipped and available at /app/function.zip
lambda_fn = aws.lambda_.Function(
    "{app_slug}-fn",
    name="{app_slug}",
    role=lambda_role.arn,
    runtime="python3.12",
    handler="handler.handler",
    code=pulumi.FileArchive("/app/function.zip"),
    timeout=30,
    memory_size=256,
    environment=aws.lambda_.FunctionEnvironmentArgs(variables={{}}),
    tags={{"loomaris:app": "{app_slug}", "loomaris:managed": "true"}},
)

# ── API Gateway v2 HTTP API ───────────────────────────────────────────────────
api = aws.apigatewayv2.Api(
    "{app_slug}-api",
    protocol_type="HTTP",
    name="{app_slug}",
    cors_configuration=aws.apigatewayv2.ApiCorsConfigurationArgs(
        allow_origins=["*"],
        allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["*"],
    ),
    tags={{"loomaris:app": "{app_slug}"}},
)

integration = aws.apigatewayv2.Integration(
    "{app_slug}-integration",
    api_id=api.id,
    integration_type="AWS_PROXY",
    integration_uri=lambda_fn.invoke_arn,
    payload_format_version="2.0",
)

route = aws.apigatewayv2.Route(
    "{app_slug}-route",
    api_id=api.id,
    route_key="$default",
    target=integration.id.apply(lambda i: f"integrations/{{i}}"),
)

stage = aws.apigatewayv2.Stage(
    "{app_slug}-stage",
    api_id=api.id,
    name="$default",
    auto_deploy=True,
    opts=pulumi.ResourceOptions(depends_on=[route]),
)

permission = aws.lambda_.Permission(
    "{app_slug}-permission",
    action="lambda:InvokeFunction",
    function=lambda_fn.name,
    principal="apigateway.amazonaws.com",
    source_arn=api.execution_arn.apply(lambda arn: f"{{arn}}/*"),
)

pulumi.export("api_url", stage.invoke_url)
pulumi.export("function_name", lambda_fn.name)
pulumi.export("function_arn", lambda_fn.arn)
'''
