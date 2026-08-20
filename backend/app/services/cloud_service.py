import asyncio
import json
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_value, encrypt_value
from app.models.platform import CloudAccount


def _loomaris_deployer_session() -> boto3.Session:
    """Return a boto3 session using Loomaris's own deployer IAM user credentials."""
    from app.core.config import settings
    if not settings.LOOMARIS_DEPLOYER_ACCESS_KEY:
        raise ValueError(
            "LOOMARIS_DEPLOYER_ACCESS_KEY is not configured. "
            "Create arn:aws:iam::LOOMARIS_ACCT:user/loomaris-deployer and set the credentials."
        )
    return boto3.Session(
        aws_access_key_id=settings.LOOMARIS_DEPLOYER_ACCESS_KEY,
        aws_secret_access_key=settings.LOOMARIS_DEPLOYER_SECRET_KEY,
        region_name="us-east-1",
    )


async def validate_aws_role(role_arn: str, sts_external_id: str) -> dict:
    """Attempt STS AssumeRole and GetCallerIdentity to verify the trust relationship.
    Raises ValueError with a user-readable message on failure.
    """
    def _call():
        session = _loomaris_deployer_session()
        sts = session.client("sts")
        resp = sts.assume_role(
            RoleArn=role_arn,
            RoleSessionName="loomaris-verification",
            ExternalId=sts_external_id,
            DurationSeconds=900,
        )
        creds = resp["Credentials"]
        # Verify the assumed identity
        verify_client = boto3.client(
            "sts",
            aws_access_key_id=creds["AccessKeyId"],
            aws_secret_access_key=creds["SecretAccessKey"],
            aws_session_token=creds["SessionToken"],
        )
        identity = verify_client.get_caller_identity()
        return identity

    try:
        return await asyncio.get_event_loop().run_in_executor(None, _call)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        msg = exc.response["Error"]["Message"]
        if code == "AccessDenied":
            raise ValueError(
                f"Could not assume role: {role_arn}\n"
                "Possible causes:\n"
                "• Trust policy is missing — your role must trust the Loomaris deployer ARN\n"
                f"• ExternalId mismatch — ensure sts:ExternalId = '{sts_external_id}'\n"
                "• Role ARN typo — check for extra spaces or wrong account ID"
            )
        if code == "NoSuchEntity":
            raise ValueError(f"Role not found: {role_arn} — check the ARN for typos")
        raise ValueError(f"AWS error ({code}): {msg}")
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Could not reach AWS: {exc}")


async def connect_aws_role_account(
    db: AsyncSession,
    org_id: uuid.UUID,
    display_name: str,
    role_arn: str,
    sts_external_id: str,
    region: str = "us-east-1",
) -> CloudAccount:
    """Validate cross-account role via STS, then upsert a CloudAccount row."""
    identity = await validate_aws_role(role_arn, sts_external_id)
    aws_account_id = identity["Account"]

    result = await db.execute(
        select(CloudAccount).where(
            CloudAccount.org_id == org_id,
            CloudAccount.external_id == aws_account_id,
            CloudAccount.provider == "aws",
        )
    )
    account = result.scalar_one_or_none()

    now = datetime.now(timezone.utc)
    if account:
        account.display_name = display_name
        account.role_arn = role_arn
        account.sts_external_id = sts_external_id
        account.region = region
        account.connection_type = "role"
        account.status = "verified"
        account.last_verified_at = now
        # Clear old key-based credentials (migration)
        account.access_key_enc = None
        account.secret_key_enc = None
    else:
        account = CloudAccount(
            org_id=org_id,
            provider="aws",
            display_name=display_name,
            external_id=aws_account_id,
            vault_path="",
            connection_type="role",
            role_arn=role_arn,
            sts_external_id=sts_external_id,
            region=region,
            status="verified",
            last_verified_at=now,
        )
        db.add(account)

    await db.commit()
    await db.refresh(account)
    account._caller_arn = identity.get("Arn")
    return account


async def get_cloud_accounts(db: AsyncSession, org_id: uuid.UUID) -> list[CloudAccount]:
    result = await db.execute(
        select(CloudAccount)
        .where(CloudAccount.org_id == org_id)
        .order_by(CloudAccount.created_at.desc())
    )
    return list(result.scalars().all())


async def delete_cloud_account(db: AsyncSession, account_id: uuid.UUID, org_id: uuid.UUID) -> None:
    result = await db.execute(
        select(CloudAccount).where(
            CloudAccount.id == account_id,
            CloudAccount.org_id == org_id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        return
    await db.delete(account)
    await db.commit()


async def verify_cloud_account(
    db: AsyncSession, account_id: uuid.UUID, org_id: uuid.UUID
) -> CloudAccount:
    """Re-validate the cloud account's connection (role-based only)."""
    result = await db.execute(
        select(CloudAccount).where(
            CloudAccount.id == account_id,
            CloudAccount.org_id == org_id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise ValueError("Cloud account not found")

    if account.connection_type == "keys" or account.status == "reconnect_required":
        raise ValueError(
            "This account uses long-lived IAM keys which are no longer supported. "
            "Please reconnect using a cross-account IAM role."
        )

    if not account.role_arn or not account.sts_external_id:
        raise ValueError("Role ARN or External ID missing — please reconnect the account")

    identity = await validate_aws_role(account.role_arn, account.sts_external_id)
    account.status = "verified"
    account.last_verified_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(account)
    account._caller_arn = identity.get("Arn")
    return account


async def connect_azure_account(
    db: AsyncSession,
    org_id: uuid.UUID,
    display_name: str,
    tenant_id: str,
    client_id: str,
    client_secret: str,
    subscription_id: str,
) -> CloudAccount:
    """Validate Azure service principal via MSAL, then store credentials."""
    await _validate_azure_credentials(tenant_id, client_id, client_secret, subscription_id)

    # Generic credentials_enc blob (new connections) — legacy access_key_enc/secret_key_enc/
    # region columns are also kept populated for now so nothing else that reads them breaks,
    # but get_credentials() below prefers credentials_enc whenever it's present.
    credentials_enc = encrypt_value(json.dumps({
        "tenant_id": tenant_id,
        "client_id": client_id,
        "client_secret": client_secret,
    }))
    tenant_id_enc = encrypt_value(tenant_id)
    client_id_enc = encrypt_value(client_id)
    client_secret_enc = encrypt_value(client_secret)

    result = await db.execute(
        select(CloudAccount).where(
            CloudAccount.org_id == org_id,
            CloudAccount.external_id == subscription_id,
            CloudAccount.provider == "azure",
        )
    )
    account = result.scalar_one_or_none()

    if account:
        account.display_name = display_name
        account.access_key_enc = client_id_enc
        account.secret_key_enc = client_secret_enc
        account.region = tenant_id_enc
        account.credentials_enc = credentials_enc
        account.status = "verified"
        account.last_verified_at = datetime.now(timezone.utc)
    else:
        account = CloudAccount(
            org_id=org_id,
            provider="azure",
            display_name=display_name,
            external_id=subscription_id,
            vault_path="",
            connection_type="keys",  # Azure still uses key-based for now
            status="verified",
            access_key_enc=client_id_enc,
            secret_key_enc=client_secret_enc,
            region=tenant_id_enc,
            credentials_enc=credentials_enc,
            last_verified_at=datetime.now(timezone.utc),
        )
        db.add(account)

    await db.commit()
    await db.refresh(account)
    return account


async def connect_gcp_account(
    db: AsyncSession,
    org_id: uuid.UUID,
    display_name: str,
    project_id: str,
    service_account_json: str,
) -> CloudAccount:
    """Validate a GCP service account key, then store it (encrypted) as this
    account's credentials. `service_account_json` is the raw contents of a
    downloaded service-account key file."""
    await _validate_gcp_credentials(project_id, service_account_json)

    credentials_enc = encrypt_value(json.dumps({
        "project_id": project_id,
        "service_account_json": service_account_json,
    }))

    result = await db.execute(
        select(CloudAccount).where(
            CloudAccount.org_id == org_id,
            CloudAccount.external_id == project_id,
            CloudAccount.provider == "gcp",
        )
    )
    account = result.scalar_one_or_none()

    if account:
        account.display_name = display_name
        account.credentials_enc = credentials_enc
        account.status = "verified"
        account.last_verified_at = datetime.now(timezone.utc)
    else:
        account = CloudAccount(
            org_id=org_id,
            provider="gcp",
            display_name=display_name,
            external_id=project_id,
            vault_path="",
            connection_type="keys",
            status="verified",
            credentials_enc=credentials_enc,
            last_verified_at=datetime.now(timezone.utc),
        )
        db.add(account)

    await db.commit()
    await db.refresh(account)
    return account


async def _validate_gcp_credentials(project_id: str, service_account_json: str) -> dict:
    """Validate a GCP service account key by requesting an access token for it."""
    def _call():
        try:
            from google.oauth2 import service_account as gcp_service_account
            import google.auth.transport.requests
        except ImportError:
            raise ValueError(
                "google-auth package not installed — run: pip install google-auth"
            )
        try:
            info = json.loads(service_account_json)
        except json.JSONDecodeError:
            raise ValueError("Service account key is not valid JSON")

        creds = gcp_service_account.Credentials.from_service_account_info(
            info, scopes=["https://www.googleapis.com/auth/cloud-platform"]
        )
        creds.refresh(google.auth.transport.requests.Request())
        return {"project_id": project_id, "token": creds.token[:20] + "..."}

    try:
        return await asyncio.get_event_loop().run_in_executor(None, _call)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"GCP credential validation failed: {exc}")


def get_credentials(account: CloudAccount) -> dict:
    """Return this account's provider-shaped credentials dict, decrypted.

    Prefers the generic `credentials_enc` blob; falls back to decoding the
    legacy AWS-named columns for Azure rows connected before that column
    existed. AWS accounts don't use this at all — they go through STS
    AssumeRole (see deploy_task._get_provider_creds) rather than stored keys.
    """
    if account.credentials_enc:
        creds = json.loads(decrypt_value(account.credentials_enc))
    elif account.provider == "azure" and account.access_key_enc and account.secret_key_enc and account.region:
        creds = {
            "client_id": decrypt_value(account.access_key_enc),
            "client_secret": decrypt_value(account.secret_key_enc),
            "tenant_id": decrypt_value(account.region),
        }
    else:
        creds = {}
    creds.setdefault("subscription_id", account.external_id)
    creds.setdefault("project_id", account.external_id)
    return creds


async def _validate_azure_credentials(
    tenant_id: str, client_id: str, client_secret: str, subscription_id: str
) -> dict:
    """Validate Azure SP credentials via MSAL token acquisition."""
    def _call():
        try:
            import msal
        except ImportError:
            raise ValueError("msal package not installed — run: pip install msal")

        app = msal.ConfidentialClientApplication(
            client_id=client_id,
            client_credential=client_secret,
            authority=f"https://login.microsoftonline.com/{tenant_id}",
        )
        result = app.acquire_token_for_client(
            scopes=["https://management.azure.com/.default"]
        )
        if "error" in result:
            raise ValueError(
                f"Azure auth failed: {result.get('error_description', result.get('error'))}"
            )
        return {"subscription_id": subscription_id, "token": result["access_token"][:20] + "..."}

    try:
        return await asyncio.get_event_loop().run_in_executor(None, _call)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Azure credential validation failed: {exc}")


async def run_permission_preflight(
    db: AsyncSession,
    app_slug: str,
    cloud_account_id: uuid.UUID,
    org_id: uuid.UUID,
) -> dict:
    """Run iam:SimulatePrincipalPolicy against the assumed role to verify required permissions.
    Returns { passed, checked: [{action, allowed}], missing, skipped }.
    If iam:SimulatePrincipalPolicy is not authorized, returns skipped=True.
    """
    from app.services.iac.detector import detect_app_type
    from app.services.git_service import get_current_files

    # Detect app type so we know which actions to check
    files = get_current_files(app_slug)
    target = detect_app_type(files) if files else None
    app_type = target.type if target else "static"

    from app.services.permission_actions import ACTIONS_BY_TYPE
    actions_to_check = ACTIONS_BY_TYPE.get(app_type, ACTIONS_BY_TYPE["static"])

    # Get the boto3 session + caller ARN
    try:
        boto_session = await get_boto3_session(db, cloud_account_id, org_id)
    except ValueError as exc:
        return {"passed": False, "checked": [], "missing": [], "skipped": False, "error": str(exc)}

    def _simulate():
        sts = boto_session.client("sts")
        identity = sts.get_caller_identity()
        caller_arn = identity["Arn"]

        iam = boto_session.client("iam")
        result = iam.simulate_principal_policy(
            PolicySourceArn=caller_arn,
            ActionNames=list(actions_to_check),
        )
        return result["EvaluationResults"]

    try:
        results = await asyncio.get_event_loop().run_in_executor(None, _simulate)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in ("AccessDenied", "UnauthorizedOperation"):
            return {"passed": True, "checked": [], "missing": [], "skipped": True}
        return {"passed": False, "checked": [], "missing": [], "skipped": False,
                "error": f"AWS error ({code}): {exc.response['Error']['Message']}"}
    except Exception as exc:
        return {"passed": True, "checked": [], "missing": [], "skipped": True,
                "error": str(exc)}

    checked = [
        {"action": r["EvalActionName"], "allowed": r["EvalDecision"] == "allowed"}
        for r in results
    ]
    missing = [r["EvalActionName"] for r in results if r["EvalDecision"] != "allowed"]
    return {
        "passed": len(missing) == 0,
        "checked": checked,
        "missing": missing,
        "skipped": False,
    }


async def get_boto3_session(
    db: AsyncSession, account_id: uuid.UUID, org_id: uuid.UUID
) -> boto3.Session:
    """Return a boto3 Session using STS assumed credentials for a cloud account."""
    result = await db.execute(
        select(CloudAccount).where(
            CloudAccount.id == account_id,
            CloudAccount.org_id == org_id,
            CloudAccount.status == "verified",
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise ValueError("No verified cloud account found")

    if account.connection_type == "keys" or account.status == "reconnect_required":
        raise ValueError(
            "This cloud account uses deprecated long-lived keys. "
            "Please reconnect via cross-account IAM role."
        )

    if not account.role_arn or not account.sts_external_id:
        raise ValueError("Role ARN or External ID not configured")

    def _assume():
        session = _loomaris_deployer_session()
        sts = session.client("sts")
        resp = sts.assume_role(
            RoleArn=account.role_arn,
            RoleSessionName=f"loomaris-deploy-{str(account_id)[:8]}",
            ExternalId=account.sts_external_id,
            DurationSeconds=3600,
        )
        c = resp["Credentials"]
        return boto3.Session(
            aws_access_key_id=c["AccessKeyId"],
            aws_secret_access_key=c["SecretAccessKey"],
            aws_session_token=c["SessionToken"],
            region_name=account.region or "us-east-1",
        )

    return await asyncio.get_event_loop().run_in_executor(None, _assume)
