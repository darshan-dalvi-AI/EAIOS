"""Per-user AI spend limits.

Rate limiting caps how *often* someone can ask; it does not cap how much a
day's asking costs. A compromised account inside a legitimate workspace can
stay under every request limit and still generate a large bill.

This adds a rolling 24-hour token budget per user, computed from the usage
events the platform already records, so the control reuses existing data
rather than introducing a parallel counter that could drift.
"""
import logging
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models import UsageEvent, User

log = logging.getLogger("eaios.budget")


def tokens_used_today(db: Session, user_id: str) -> int:
    since = datetime.now(timezone.utc) - timedelta(hours=24)
    total = db.scalar(
        select(func.coalesce(
            func.sum(UsageEvent.prompt_tokens + UsageEvent.completion_tokens), 0))
        .where(UsageEvent.user_id == user_id, UsageEvent.created_at >= since)
    )
    return int(total or 0)


def check(db: Session, user: User) -> None:
    """Raise 429 when this user has exhausted their rolling daily allowance.

    Deliberately a 429 rather than a 402/403: it is a temporary limit that
    clears as the window rolls, which is what Retry-After communicates.
    """
    budget = settings.LLM_DAILY_TOKEN_BUDGET
    if budget <= 0:
        return
    used = tokens_used_today(db, user.id)
    if used < budget:
        return
    log.warning("AI budget exhausted for user=%s used=%s budget=%s", user.id, used, budget)
    raise HTTPException(
        status_code=429,
        detail="You have reached your AI usage limit for today. It resets on a rolling 24-hour window.",
        headers={"Retry-After": "3600"},
    )
