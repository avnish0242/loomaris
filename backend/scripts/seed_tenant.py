#!/usr/bin/env python3
"""
Seed the Loomaris Labs tenant and set avnish.dbg@gmail.com as org admin.

Usage:
  docker compose -f docker-compose.dev.yml exec backend python scripts/seed_tenant.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.platform import CloudAccount, OrgMembership, Organization, User
from app.services.tenant_service import add_user_to_org, create_org_schema

ORG_ADMIN_EMAIL = "avnish.dbg@gmail.com"


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        print("━" * 52)
        print("  Loomaris Labs — Tenant Seeder")
        print("━" * 52)

        # ── Organization ──────────────────────────────────────────────────────
        result = await db.execute(
            select(Organization).where(Organization.slug == "loomaris-labs")
        )
        org = result.scalar_one_or_none()

        if not org:
            org = Organization(
                name="Loomaris Labs",
                slug="loomaris-labs",
                plan="pro",
                cost_hard_cap=10_000.00,
                description="Internal development tenant for Loomaris team.",
                join_policy="approval_required",
                metadata_={"env": "dev"},
            )
            db.add(org)
            await db.flush()
            print(f"  ✓ Created org:          Loomaris Labs ({org.id})")
        else:
            print(f"  ✓ Org already exists:  Loomaris Labs ({org.id})")

        # ── Per-org schema ────────────────────────────────────────────────────
        schema = await create_org_schema(db, org.slug)
        print(f"  ✓ Schema ready:         {schema}")

        # ── LocalStack cloud account ──────────────────────────────────────────
        result = await db.execute(
            select(CloudAccount).where(
                CloudAccount.org_id == org.id,
                CloudAccount.display_name == "LocalStack Dev (AWS)",
            )
        )
        cloud = result.scalar_one_or_none()
        if not cloud:
            cloud = CloudAccount(
                org_id=org.id,
                provider="aws",
                display_name="LocalStack Dev (AWS)",
                external_id="000000000000",
                vault_path="dev/localstack",
                status="verified",
            )
            db.add(cloud)
            await db.flush()
            print(f"  ✓ Cloud account:        LocalStack Dev (AWS) ({cloud.id})")
        else:
            print(f"  ✓ Cloud account exists: LocalStack Dev (AWS) ({cloud.id})")

        await db.commit()

        # ── Org admin user — pre-seed by email ───────────────────────────────
        # The user record is created here with no OAuth sub (they log in via Google
        # and the callback matches on email, upgrading their session to org admin).
        result = await db.execute(
            select(User).where(User.email == ORG_ADMIN_EMAIL)
        )
        admin_user = result.scalar_one_or_none()

        if not admin_user:
            admin_user = User(
                email=ORG_ADMIN_EMAIL,
                name="Avnish Kumar",
                is_superadmin=False,
            )
            db.add(admin_user)
            await db.flush()
            print(f"  ✓ Created user:         {ORG_ADMIN_EMAIL} ({admin_user.id})")
        else:
            print(f"  ✓ User exists:          {ORG_ADMIN_EMAIL} ({admin_user.id})")

        # Ensure they are an active owner of Loomaris Labs
        result = await db.execute(
            select(OrgMembership).where(
                OrgMembership.user_id == admin_user.id,
                OrgMembership.org_id == org.id,
            )
        )
        membership = result.scalar_one_or_none()
        if not membership:
            membership = OrgMembership(
                org_id=org.id,
                user_id=admin_user.id,
                role="owner",
                status="active",
            )
            db.add(membership)
            await db.commit()
            print(f"  ✓ Made org admin:       {ORG_ADMIN_EMAIL} → Loomaris Labs (owner)")
        else:
            if membership.role != "owner":
                membership.role = "owner"
            membership.status = "active"
            await db.commit()
            print(f"  ✓ Confirmed org admin:  {ORG_ADMIN_EMAIL} → role={membership.role}")

        print()
        print("━" * 52)
        print("  Tenant ready. Summary:")
        print(f"    Org:       Loomaris Labs  (slug: loomaris-labs)")
        print(f"    Schema:    org_loomaris_labs")
        print(f"    Org admin: {ORG_ADMIN_EMAIL}")
        print()
        print("  Login:")
        print("    http://localhost:8000/api/v1/auth/google")
        print("    http://localhost:8000/api/v1/auth/github")
        print("━" * 52)


if __name__ == "__main__":
    asyncio.run(seed())
