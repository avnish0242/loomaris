import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.database import get_db
from app.models.platform import CloudAccount, OrgMembership, Organization, User
from app.services.cloud_service import (
    connect_aws_account,
    delete_cloud_account,
    get_cloud_accounts,
    verify_cloud_account,
)

router = APIRouter(prefix="/cloud", tags=["cloud"])

AWS_REGIONS = [
    "us-east-1", "us-east-2", "us-west-1", "us-west-2",
    "eu-west-1", "eu-west-2", "eu-central-1",
    "ap-south-1", "ap-southeast-1", "ap-northeast-1",
]


class ConnectAwsRequest(BaseModel):
    display_name: str
    access_key_id: str
    secret_access_key: str
    region: str = "us-east-1"


def _account_out(account: CloudAccount) -> dict:
    return {
        "id": str(account.id),
        "display_name": account.display_name,
        "provider": account.provider,
        "external_id": account.external_id,
        "arn": getattr(account, "_arn", None),
        "region": account.region,
        "status": account.status,
        "last_verified_at": account.last_verified_at.isoformat() if account.last_verified_at else None,
        "created_at": account.created_at.isoformat(),
    }


async def _get_user_org_id(db: AsyncSession, user_id: uuid.UUID) -> uuid.UUID:
    result = await db.execute(
        select(OrgMembership.org_id).where(OrgMembership.user_id == user_id).limit(1)
    )
    row = result.scalar_one_or_none()
    if not row:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="User has no organisation")
    return row


@router.post("/accounts", summary="Connect AWS account")
async def connect_account(
    body: ConnectAwsRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if body.region not in AWS_REGIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported region: {body.region}")

    org_id = await _get_user_org_id(db, current_user.id)

    try:
        account = await connect_aws_account(
            db,
            org_id=org_id,
            display_name=body.display_name,
            access_key=body.access_key_id,
            secret_key=body.secret_access_key,
            region=body.region,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))

    return _account_out(account)


@router.get("/accounts", summary="List cloud accounts")
async def list_accounts(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_user_org_id(db, current_user.id)
    accounts = await get_cloud_accounts(db, org_id)
    return [_account_out(a) for a in accounts]


@router.delete("/accounts/{account_id}", summary="Remove cloud account")
async def remove_account(
    account_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_user_org_id(db, current_user.id)
    await delete_cloud_account(db, account_id, org_id)
    return {"ok": True}


@router.post("/accounts/{account_id}/verify", summary="Re-verify cloud account credentials")
async def reverify_account(
    account_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    org_id = await _get_user_org_id(db, current_user.id)
    try:
        account = await verify_cloud_account(db, account_id, org_id)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    return _account_out(account)
