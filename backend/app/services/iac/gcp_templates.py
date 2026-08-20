"""
Pre-built Pulumi Python program templates for GCP deployment targets, mirroring
aws_templates.py's three shapes using the pulumi_gcp provider. Cloud Run's own
serverless HTTPS endpoint replaces the ALB/App-Gateway layer AWS and Azure need —
there's no separate load balancer resource for the container case.
"""


def static_site_program(app_slug: str, gcp_region: str, static_files: list[tuple[str, str]]) -> str:
    """GCS bucket configured as a public static website. files kept for signature
    parity with aws_templates.py; actual object upload happens separately."""
    return f'''\
"""Loomaris-generated Pulumi program — {app_slug} static site on Google Cloud Storage"""
import pulumi
import pulumi_gcp as gcp

bucket = gcp.storage.Bucket(
    "{app_slug}-site",
    location="{gcp_region}",
    uniform_bucket_level_access=True,
    website=gcp.storage.BucketWebsiteArgs(
        main_page_suffix="index.html",
        not_found_page="index.html",
    ),
    labels={{"loomaris-app": "{app_slug}", "loomaris-managed": "true"}},
)

public_access = gcp.storage.BucketIAMMember(
    "{app_slug}-public-read",
    bucket=bucket.name,
    role="roles/storage.objectViewer",
    member="allUsers",
)

backend_bucket = gcp.compute.BackendBucket(
    "{app_slug}-backend",
    bucket_name=bucket.name,
    enable_cdn=True,
)

url_map = gcp.compute.URLMap(
    "{app_slug}-urlmap",
    default_service=backend_bucket.id,
)

http_proxy = gcp.compute.TargetHttpProxy(
    "{app_slug}-proxy",
    url_map=url_map.id,
)

forwarding_rule = gcp.compute.GlobalForwardingRule(
    "{app_slug}-fr",
    target=http_proxy.id,
    port_range="80",
    opts=pulumi.ResourceOptions(depends_on=[public_access]),
)

pulumi.export("cdn_url", forwarding_rule.ip_address.apply(lambda ip: f"http://{{ip}}"))
pulumi.export("bucket_name", bucket.name)
'''


def container_program(app_slug: str, gcp_region: str, gcp_project: str) -> str:
    """Artifact Registry + Cloud Run — the closest single-container analog to ECS
    Fargate + ALB. Cloud Run's own managed HTTPS endpoint and built-in startup/liveness
    probing replace the platform's usual port-8000/`/health` ALB contract, but the
    generated app should still expose /health and listen on 8000 for parity with the
    other providers' generated-code expectations."""
    return f'''\
"""Loomaris-generated Pulumi program — {app_slug} container on Google Cloud Run"""
import pulumi
import pulumi_gcp as gcp

repository = gcp.artifactregistry.Repository(
    "{app_slug}-repo",
    location="{gcp_region}",
    repository_id="{app_slug}",
    format="DOCKER",
    labels={{"loomaris-app": "{app_slug}", "loomaris-managed": "true"}},
)

service = gcp.cloudrunv2.Service(
    "{app_slug}-service",
    location="{gcp_region}",
    ingress="INGRESS_TRAFFIC_ALL",
    template=gcp.cloudrunv2.ServiceTemplateArgs(
        containers=[gcp.cloudrunv2.ServiceTemplateContainerArgs(
            image=f"{gcp_region}-docker.pkg.dev/{gcp_project}/{app_slug}/{app_slug}:latest",
            ports=gcp.cloudrunv2.ServiceTemplateContainerPortsArgs(container_port=8000),
            resources=gcp.cloudrunv2.ServiceTemplateContainerResourcesArgs(
                limits={{"cpu": "1", "memory": "512Mi"}},
            ),
            liveness_probe=gcp.cloudrunv2.ServiceTemplateContainerLivenessProbeArgs(
                http_get=gcp.cloudrunv2.ServiceTemplateContainerLivenessProbeHttpGetArgs(path="/health"),
                period_seconds=30,
            ),
        )],
        scaling=gcp.cloudrunv2.ServiceTemplateScalingArgs(min_instance_count=0, max_instance_count=3),
    ),
    labels={{"loomaris-app": "{app_slug}", "loomaris-managed": "true"}},
    opts=pulumi.ResourceOptions(depends_on=[repository]),
)

public_invoker = gcp.cloudrunv2.ServiceIamMember(
    "{app_slug}-public-invoke",
    name=service.name,
    location=service.location,
    role="roles/run.invoker",
    member="allUsers",
)

pulumi.export("run_url", service.uri)
pulumi.export("repository_url", pulumi.Output.concat(
    "{gcp_region}-docker.pkg.dev/{gcp_project}/", repository.repository_id
))
pulumi.export("service_name", service.name)
'''


def lambda_program(app_slug: str, gcp_region: str) -> str:
    """Cloud Function (2nd gen, HTTP-triggered) — the GCP analog to Lambda + API Gateway;
    2nd-gen functions already sit behind a managed HTTPS endpoint, no separate gateway needed."""
    return f'''\
"""Loomaris-generated Pulumi program — {app_slug} on Google Cloud Functions (2nd gen)"""
import pulumi
import pulumi_gcp as gcp

bucket = gcp.storage.Bucket(
    "{app_slug}-fn-source",
    location="{gcp_region}",
    uniform_bucket_level_access=True,
    labels={{"loomaris-app": "{app_slug}", "loomaris-managed": "true"}},
)

# Function source is expected to be zipped and available at /app/function.zip,
# uploaded to this bucket by the platform's deploy pipeline before `pulumi up`.
source_object = gcp.storage.BucketObject(
    "{app_slug}-fn-zip",
    bucket=bucket.name,
    source=pulumi.FileAsset("/app/function.zip"),
)

function = gcp.cloudfunctionsv2.Function(
    "{app_slug}-fn",
    location="{gcp_region}",
    build_config=gcp.cloudfunctionsv2.FunctionBuildConfigArgs(
        runtime="python312",
        entry_point="handler",
        source=gcp.cloudfunctionsv2.FunctionBuildConfigSourceArgs(
            storage_source=gcp.cloudfunctionsv2.FunctionBuildConfigSourceStorageSourceArgs(
                bucket=bucket.name,
                object=source_object.name,
            ),
        ),
    ),
    service_config=gcp.cloudfunctionsv2.FunctionServiceConfigArgs(
        max_instance_count=3,
        available_memory="256M",
        timeout_seconds=30,
    ),
    labels={{"loomaris-app": "{app_slug}", "loomaris-managed": "true"}},
)

public_invoker = gcp.cloudfunctionsv2.FunctionIamMember(
    "{app_slug}-public-invoke",
    project=function.project,
    location=function.location,
    cloud_function=function.name,
    role="roles/cloudfunctions.invoker",
    member="allUsers",
)

pulumi.export("function_url", function.service_config.uri)
pulumi.export("function_name", function.name)
'''
