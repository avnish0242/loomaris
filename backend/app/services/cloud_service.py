import asyncio
import uuid
from datetime import datetime, timezone

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decrypt_value, encrypt_value
from app.models.platform import CloudAccount


async def validate_aws_credentials(access_key: str, secret_key: str, region: str) -> dict:
    """Call STS GetCallerIdentity to verify credentials are valid.
    Raises ValueError with a user-readable message on failure.
    """
    def _call():
        client = boto3.client(
            "sts",
            aws_access_key_id=access_key,
            aws_secret_access_key=secret_key,
            region_name=region,
        )
        return client.get_caller_identity()

    try:
        resp = await asyncio.get_event_loop().run_in_executor(None, _call)
    except ClientError as exc:
        code = exc.response["Error"]["Code"]
        if code in ("InvalidClientTokenId", "SignatureDoesNotMatch", "AuthFailure"):
            raise ValueError("AWS credentials are invalid. Check your Access Key ID and Secret.")
        raise ValueError(f"AWS error: {exc.response['Error']['Message']}")
    except NoCredentialsError:
        raise ValueError("AWS credentials are missing or malformed.")
    except Exception as exc:
        raise ValueError(f"Could not reach AWS: {exc}")

    return {
        "account_id": resp["Account"],
        "arn": resp["Arn"],
        "user_id": resp["UserId"],
    }


async def connect_aws_account(
    db: AsyncSession,
    org_id: uuid.UUID,
    display_name: str,
    access_key: str,
    secret_key: str,
    region: str,
) -> CloudAccount:
    """Validate credentials via STS, then upsert a CloudAccount row."""
    identity = await validate_aws_credentials(access_key, secret_key, region)

    access_key_enc = encrypt_value(access_key)
    secret_key_enc = encrypt_value(secret_key)

    # Upsert: if an account with this external_id already exists for this org, update it.
    result = await db.execute(
        select(CloudAccount).where(
            CloudAccount.org_id == org_id,
            CloudAccount.external_id == identity["account_id"],
            CloudAccount.provider == "aws",
        )
    )
    account = result.scalar_one_or_none()

    if account:
        account.display_name = display_name
        account.access_key_enc = access_key_enc
        account.secret_key_enc = secret_key_enc
        account.region = region
        account.status = "verified"
        account.last_verified_at = datetime.now(timezone.utc)
    else:
        account = CloudAccount(
            org_id=org_id,
            provider="aws",
            display_name=display_name,
            external_id=identity["account_id"],
            vault_path="",
            status="verified",
            access_key_enc=access_key_enc,
            secret_key_enc=secret_key_enc,
            region=region,
            last_verified_at=datetime.now(timezone.utc),
        )
        db.add(account)

    await db.commit()
    await db.refresh(account)

    # Attach the ARN for the response (not persisted separately)
    account._arn = identity["arn"]
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
    """Re-ping STS to refresh verification status."""
    result = await db.execute(
        select(CloudAccount).where(
            CloudAccount.id == account_id,
            CloudAccount.org_id == org_id,
        )
    )
    account = result.scalar_one_or_none()
    if not account:
        raise ValueError("Cloud account not found")
    if not account.access_key_enc or not account.secret_key_enc:
        raise ValueError("No credentials stored for this account")

    access_key = decrypt_value(account.access_key_enc)
    secret_key = decrypt_value(account.secret_key_enc)
    identity = await validate_aws_credentials(access_key, secret_key, account.region or "us-east-1")

    account.status = "verified"
    account.last_verified_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(account)

    account._arn = identity["arn"]
    return account


async def get_boto3_session(
    db: AsyncSession, account_id: uuid.UUID, org_id: uuid.UUID
) -> boto3.Session:
    """Decrypt stored credentials and return a boto3 Session for Pulumi/deploy use."""
    result = await db.execute(
        select(CloudAccount).where(
            CloudAccount.id == account_id,
            CloudAccount.org_id == org_id,
            CloudAccount.status == "verified",
        )
    )
    account = result.scalar_one_or_none()
    if not account or not account.access_key_enc or not account.secret_key_enc:
        raise ValueError("No verified cloud account found")

    return boto3.Session(
        aws_access_key_id=decrypt_value(account.access_key_enc),
        aws_secret_access_key=decrypt_value(account.secret_key_enc),
        region_name=account.region or "us-east-1",
    )
