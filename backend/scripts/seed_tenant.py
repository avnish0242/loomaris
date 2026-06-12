#!/usr/bin/env python3
"""
Seed the Loomaris Labs test tenant.

Run via docker compose:
  docker compose -f docker-compose.dev.yml exec backend python scripts/seed_tenant.py

Or locally (with .env.local set):
  cd backend && python scripts/seed_tenant.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.core.config import settings
from app.database import AsyncSessionLocal
from app.models.platform import CloudAccount, Organization
from app.services.tenant_service import create_org_schema


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
                metadata_={"env": "dev", "description": "Internal development tenant"},
            )
            db.add(org)
            await db.flush()
            print(f"  ✓ Created org:          Loomaris Labs")
            print(f"    ID:                   {org.id}")
        else:
            print(f"  ✓ Org already exists:  Loomaris Labs ({org.id})")

        # ── Per-org schema ────────────────────────────────────────────────────
        schema = await create_org_schema(db, org.slug)
        print(f"  ✓ Schema ready:         {schema}")

        # ── LocalStack cloud account ──────────────────────────────────────────
        result = await db.execute(
            select(CloudAccount).where(
                CloudAccount.org_id == org.id,
                CloudAccount.provider == "aws",
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
            print(f"  ✓ Cloud account:        LocalStack Dev (AWS)")
            print(f"    ID:                   {cloud.id}")
        else:
            print(f"  ✓ Cloud account exists: LocalStack Dev (AWS) ({cloud.id})")

        await db.commit()

        print()
        print("━" * 52)
        print("  Tenant ready. Summary:")
        print(f"    Org:          Loomaris Labs  (slug: loomaris-labs)")
        print(f"    Plan:         pro  |  Cost cap: $10,000/mo")
        print(f"    Schema:       org_loomaris_labs")
        print(f"    Cloud acct:   LocalStack Dev (AWS)  [000000000000]")
        print()
        print("  Login flow:")
        print("    http://localhost:8000/api/v1/auth/google")
        print("    → authenticate with Google")
        print("    → auto-joined to Loomaris Labs as owner")
        print("    → token stored in localStorage")
        print()

        missing = []
        if not settings.GOOGLE_CLIENT_ID:
            missing.append("GOOGLE_CLIENT_ID")
        if not settings.GOOGLE_CLIENT_SECRET:
            missing.append("GOOGLE_CLIENT_SECRET")
        if not settings.ANTHROPIC_API_KEY:
            missing.append("ANTHROPIC_API_KEY  (or store per-user via POST /api/v1/auth/claude-key)")

        if missing:
            print("  ⚠  Missing in .env.local:")
            for m in missing:
                print(f"       {m}")
            print()
        print("━" * 52)


if __name__ == "__main__":
    asyncio.run(seed())
