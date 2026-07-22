"""Backfill premium users into subscriptions (VERSION_2_MASTER_PLAN §15 Step 1, V2-D-024).

Turns every ``users.is_premium = true`` row into one ``active`` ``manual_grant`` premium
subscription, preserving the user's existing ``premium_expires_at``. Runs **dry-run by
default** — it prints a reconciliation report and writes nothing until ``--apply``.

Idempotent: a user who already has an active subscription is skipped, so re-running never
double-grants. Anomalies (null or already-past ``premium_expires_at``) are reported and, in
``--apply`` mode, **skipped** unless ``--null-expiry-days N`` is given — the script never
guesses an expiry the Owner has not chosen (design Decision 7).

Usage:
    python -m scripts.backfill_subscriptions               # dry-run report
    python -m scripts.backfill_subscriptions --apply       # perform it
    python -m scripts.backfill_subscriptions --apply --null-expiry-days 30
"""

from __future__ import annotations

import argparse
import asyncio
import datetime
from dataclasses import dataclass, field

from sqlalchemy import select

from core.config import Settings
from infrastructure.database.engine import create_engine
from infrastructure.database.models import User
from infrastructure.database.repositories.plan import PlanRepository
from infrastructure.database.repositories.subscription import SubscriptionRepository
from infrastructure.database.session import create_session_factory


@dataclass
class Report:
    premium_total: int = 0
    already_have_active: int = 0
    to_create: int = 0
    null_expiry: list[int] = field(default_factory=list)
    past_expiry: list[int] = field(default_factory=list)
    created: int = 0

    def render(self, *, applied: bool) -> str:
        lines = [
            "=== Subscription backfill report ===",
            f"mode:                 {'APPLY' if applied else 'DRY-RUN'}",
            f"premium users total:  {self.premium_total}",
            f"already have active:  {self.already_have_active}",
            f"eligible to create:   {self.to_create}",
            f"  null premium_expires_at: {len(self.null_expiry)} {self.null_expiry or ''}",
            f"  already-past expiry:     {len(self.past_expiry)} {self.past_expiry or ''}",
        ]
        if applied:
            lines.append(f"rows created:         {self.created}")
        return "\n".join(lines)


async def _run(*, apply: bool, null_expiry_days: int | None) -> Report:
    settings = Settings()  # type: ignore[call-arg]
    engine = create_engine(settings)
    session_factory = create_session_factory(engine)
    now = datetime.datetime.now(datetime.UTC)
    report = Report()
    try:
        async with session_factory() as session:
            plans = PlanRepository(session)
            subs = SubscriptionRepository(session)
            premium_plan = await plans.get_by_code("premium")
            if premium_plan is None:
                raise SystemExit("no 'premium' plan — run migration 2026072003 first")

            rows = (await session.execute(select(User).where(User.is_premium.is_(True)))).scalars()
            for user in rows:
                report.premium_total += 1
                if await subs.get_active_for_user(user.id) is not None:
                    report.already_have_active += 1
                    continue

                expires_at = user.premium_expires_at
                if expires_at is None:
                    report.null_expiry.append(user.id)
                    if null_expiry_days is None:
                        continue  # never guess an expiry
                    expires_at = now + datetime.timedelta(days=null_expiry_days)
                elif expires_at <= now:
                    report.past_expiry.append(user.id)

                report.to_create += 1
                if apply:
                    await subs.create_active(
                        user_id=user.id,
                        plan_id=premium_plan.id,
                        source="manual_grant",
                        starts_at=now,
                        expires_at=expires_at,
                        granted_by=None,
                    )
                    report.created += 1

            if apply:
                await session.commit()
            else:
                await session.rollback()
    finally:
        await engine.dispose()
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill premium users into subscriptions.")
    parser.add_argument(
        "--apply", action="store_true", help="perform the backfill (default: dry-run)"
    )
    parser.add_argument(
        "--null-expiry-days",
        type=int,
        default=None,
        help="grant this many days to premium users whose premium_expires_at is null "
        "(default: skip them and report)",
    )
    args = parser.parse_args()
    report = asyncio.run(_run(apply=args.apply, null_expiry_days=args.null_expiry_days))
    print(report.render(applied=args.apply))


if __name__ == "__main__":
    main()
