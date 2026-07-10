#!/usr/bin/env python3
"""
Seed the platform superadmin.
Email is read from SUPERADMIN_EMAIL env var (default: avnish.dbg@gmail.com).

Usage:
  docker compose -f docker-compose.dev.yml exec backend python scripts/seed_superadmin.py
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.platform import User

SUPERADMIN_EMAIL = os.environ.get("SUPERADMIN_EMAIL", "avnish.dbg@gmail.com")


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        print("━" * 52)
        print("  Loomaris — Superadmin Seeder")
        print("━" * 52)

        result = await db.execute(select(User).where(User.email == SUPERADMIN_EMAIL))
        user = result.scalar_one_or_none()

        if not user:
            user = User(
                email=SUPERADMIN_EMAIL,
                name="Avnish Kumar (Admin)",
                is_superadmin=True,
            )
            db.add(user)
            await db.commit()
            await db.refresh(user)
            print(f"  ✓ Created superadmin:   {SUPERADMIN_EMAIL} ({user.id})")
        else:
            user.is_superadmin = True
            await db.commit()
            print(f"  ✓ Confirmed superadmin: {SUPERADMIN_EMAIL} ({user.id})")

        print()
        print("  This user must log in via Google or GitHub OAuth")
        print(f"  using the email: {SUPERADMIN_EMAIL}")
        print()
        print("  Login URLs:")
        print("    http://localhost:8000/api/v1/auth/google")
        print("    http://localhost:8000/api/v1/auth/github")
        print("━" * 52)


if __name__ == "__main__":
    asyncio.run(seed())
