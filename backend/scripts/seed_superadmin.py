#!/usr/bin/env python3
"""
Grant superadmin to a user by email. The user must have logged in at least once.

Usage:
  docker compose -f docker-compose.dev.yml exec backend python scripts/seed_superadmin.py
  docker compose -f docker-compose.dev.yml exec backend python scripts/seed_superadmin.py other@example.com
"""
import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.platform import User

TARGET_EMAIL = sys.argv[1] if len(sys.argv) > 1 else "avnish.kumar@loomaris.xyz"


async def seed() -> None:
    async with AsyncSessionLocal() as db:
        print("━" * 52)
        print("  Loomaris — Superadmin Seeder")
        print("━" * 52)

        result = await db.execute(select(User).where(User.email == TARGET_EMAIL))
        user = result.scalar_one_or_none()

        if not user:
            # First-time bootstrap: create a stub record so the flag survives first login.
            # get_or_create_user will match on email and fill in OAuth details.
            user = User(email=TARGET_EMAIL, is_superadmin=True)
            db.add(user)
            await db.commit()
            await db.refresh(user)
            print(f"  ✓ Stub user created + superadmin granted: {TARGET_EMAIL}")
            print()
            print("  User can now log in via OAuth — is_superadmin will be preserved.")
        else:
            user.is_superadmin = True
            await db.commit()
            print(f"  ✓ Superadmin granted: {TARGET_EMAIL} ({user.id})")
        print("━" * 52)


if __name__ == "__main__":
    asyncio.run(seed())
