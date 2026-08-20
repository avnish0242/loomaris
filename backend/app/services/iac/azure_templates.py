"""
Pre-built Pulumi Python program templates for Azure deployment targets, mirroring
aws_templates.py's three shapes (static / container / lambda-equivalent) using the
pulumi_azure_native provider.
"""


def static_site_program(app_slug: str, azure_region: str, static_files: list[tuple[str, str]]) -> str:
    """Storage Account static website + Azure CDN. files is list of (path, content) tuples —
    kept for signature parity with aws_templates.py; actual blob upload happens separately."""
    return f'''\
"""Loomaris-generated Pulumi program — {app_slug} static site on Azure Storage + CDN"""
import pulumi
import pulumi_azure_native as azure_native

resource_group = azure_native.resources.ResourceGroup(
    "{app_slug}-rg",
    resource_group_name="{app_slug}-rg",
    location="{azure_region}",
    tags={{"loomaris:app": "{app_slug}", "loomaris:managed": "true"}},
)

storage = azure_native.storage.StorageAccount(
    "{app_slug}sa",
    resource_group_name=resource_group.name,
    location=resource_group.location,
    sku=azure_native.storage.SkuArgs(name=azure_native.storage.SkuName.STANDARD_LRS),
    kind=azure_native.storage.Kind.STORAGE_V2,
    tags={{"loomaris:app": "{app_slug}"}},
)

static_website = azure_native.storage.StorageAccountStaticWebsite(
    "{app_slug}-website",
    account_name=storage.name,
    resource_group_name=resource_group.name,
    index_document="index.html",
    error404_document="index.html",
)

cdn_profile = azure_native.cdn.Profile(
    "{app_slug}-cdn-profile",
    resource_group_name=resource_group.name,
    location="global",
    sku=azure_native.cdn.SkuArgs(name=azure_native.cdn.SkuName.STANDARD_MICROSOFT),
    tags={{"loomaris:app": "{app_slug}"}},
)

cdn_endpoint = azure_native.cdn.Endpoint(
    "{app_slug}-cdn-endpoint",
    resource_group_name=resource_group.name,
    profile_name=cdn_profile.name,
    is_https_allowed=True,
    origins=[azure_native.cdn.DeepCreatedOriginArgs(
        name="{app_slug}-origin",
        host_name=storage.primary_endpoints.web.apply(
            lambda w: w.replace("https://", "").rstrip("/")
        ),
    )],
    origin_host_header=storage.primary_endpoints.web.apply(
        lambda w: w.replace("https://", "").rstrip("/")
    ),
    opts=pulumi.ResourceOptions(depends_on=[static_website]),
)

pulumi.export("cdn_url", cdn_endpoint.host_name.apply(lambda h: f"https://{{h}}"))
pulumi.export("storage_account", storage.name)
pulumi.export("origin_url", storage.primary_endpoints.web)
'''


def container_program(app_slug: str, azure_region: str) -> str:
    """Azure Container Instances behind an Application Gateway-free public IP — the
    closest single-container analog to ECS Fargate + ALB without the extra App Service
    plan machinery. Health check + port 8000 match the same contract the platform's
    local preview and AWS ECS templates assume."""
    return f'''\
"""Loomaris-generated Pulumi program — {app_slug} container on Azure Container Instances"""
import pulumi
import pulumi_azure_native as azure_native

resource_group = azure_native.resources.ResourceGroup(
    "{app_slug}-rg",
    resource_group_name="{app_slug}-rg",
    location="{azure_region}",
    tags={{"loomaris:app": "{app_slug}", "loomaris:managed": "true"}},
)

registry = azure_native.containerregistry.Registry(
    "{app_slug}acr",
    resource_group_name=resource_group.name,
    location=resource_group.location,
    sku=azure_native.containerregistry.SkuArgs(name=azure_native.containerregistry.SkuName.BASIC),
    admin_user_enabled=True,
    tags={{"loomaris:app": "{app_slug}"}},
)

log_workspace = azure_native.operationalinsights.Workspace(
    "{app_slug}-logs",
    resource_group_name=resource_group.name,
    location=resource_group.location,
    sku=azure_native.operationalinsights.WorkspaceSkuArgs(name="PerGB2018"),
    retention_in_days=7,
)

registry_creds = pulumi.Output.all(resource_group.name, registry.name).apply(
    lambda args: azure_native.containerregistry.list_registry_credentials(
        resource_group_name=args[0], registry_name=args[1],
    )
)

container_group = azure_native.containerinstance.ContainerGroup(
    "{app_slug}-cg",
    resource_group_name=resource_group.name,
    location=resource_group.location,
    os_type=azure_native.containerinstance.OperatingSystemTypes.LINUX,
    restart_policy=azure_native.containerinstance.ContainerGroupRestartPolicy.ALWAYS,
    ip_address=azure_native.containerinstance.IpAddressArgs(
        type=azure_native.containerinstance.ContainerGroupIpAddressType.PUBLIC,
        dns_name_label="{app_slug}",
        ports=[azure_native.containerinstance.PortArgs(port=8000, protocol="TCP")],
    ),
    image_registry_credentials=[azure_native.containerinstance.ImageRegistryCredentialArgs(
        server=registry.login_server,
        username=registry_creds.username,
        password=registry_creds.passwords[0]["value"],
    )],
    containers=[azure_native.containerinstance.ContainerArgs(
        name="{app_slug}",
        image=registry.login_server.apply(lambda s: f"{{s}}/{app_slug}:latest"),
        resources=azure_native.containerinstance.ResourceRequirementsArgs(
            requests=azure_native.containerinstance.ResourceRequestsArgs(cpu=0.5, memory_in_gb=1.0),
        ),
        ports=[azure_native.containerinstance.ContainerPortArgs(port=8000, protocol="TCP")],
        # Azure Container Instances has no native ALB-style health check target — the
        # platform's own simulate/deploy status polling substitutes for that here.
    )],
    diagnostics=azure_native.containerinstance.ContainerGroupDiagnosticsArgs(
        log_analytics=azure_native.containerinstance.LogAnalyticsArgs(
            workspace_id=log_workspace.customer_id,
            workspace_key=azure_native.operationalinsights.get_shared_keys_output(
                resource_group_name=resource_group.name, workspace_name=log_workspace.name,
            ).primary_shared_key,
        ),
    ),
    tags={{"loomaris:app": "{app_slug}", "loomaris:managed": "true"}},
)

pulumi.export("aci_url", container_group.ip_address.fqdn.apply(lambda f: f"http://{{f}}:8000"))
pulumi.export("registry_login_server", registry.login_server)
pulumi.export("container_group_name", container_group.name)
'''


def lambda_program(app_slug: str, azure_region: str) -> str:
    """Azure Function (Consumption plan) + Function App with an HTTP-triggered default route."""
    return f'''\
"""Loomaris-generated Pulumi program — {app_slug} on Azure Functions"""
import pulumi
import pulumi_azure_native as azure_native

resource_group = azure_native.resources.ResourceGroup(
    "{app_slug}-rg",
    resource_group_name="{app_slug}-rg",
    location="{azure_region}",
    tags={{"loomaris:app": "{app_slug}", "loomaris:managed": "true"}},
)

storage = azure_native.storage.StorageAccount(
    "{app_slug}fnsa",
    resource_group_name=resource_group.name,
    location=resource_group.location,
    sku=azure_native.storage.SkuArgs(name=azure_native.storage.SkuName.STANDARD_LRS),
    kind=azure_native.storage.Kind.STORAGE_V2,
    tags={{"loomaris:app": "{app_slug}"}},
)

plan = azure_native.web.AppServicePlan(
    "{app_slug}-plan",
    resource_group_name=resource_group.name,
    location=resource_group.location,
    kind="functionapp",
    sku=azure_native.web.SkuDescriptionArgs(name="Y1", tier="Dynamic"),
)

function_app = azure_native.web.WebApp(
    "{app_slug}-fn",
    resource_group_name=resource_group.name,
    location=resource_group.location,
    server_farm_id=plan.id,
    kind="functionapp,linux",
    site_config=azure_native.web.SiteConfigArgs(
        linux_fx_version="Python|3.12",
        app_settings=[
            azure_native.web.NameValuePairArgs(name="FUNCTIONS_WORKER_RUNTIME", value="python"),
            azure_native.web.NameValuePairArgs(name="FUNCTIONS_EXTENSION_VERSION", value="~4"),
        ],
    ),
    tags={{"loomaris:app": "{app_slug}", "loomaris:managed": "true"}},
)

pulumi.export("function_url", function_app.default_host_name.apply(lambda h: f"https://{{h}}"))
pulumi.export("function_app_name", function_app.name)
pulumi.export("storage_account", storage.name)
'''
