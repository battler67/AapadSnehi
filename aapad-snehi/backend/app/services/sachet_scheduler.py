from __future__ import annotations

import asyncio
import logging
from time import monotonic

from sqlalchemy import select

from ..database import SessionLocal
from ..models import Source
from .ingestion import run_ingestion


logger = logging.getLogger(__name__)


async def poll_sachet_once() -> int:
    with SessionLocal() as db:
        source_id = db.scalar(
            select(Source.id).where(
                Source.slug == "sachet-india",
                Source.adapter_type == "sachet",
                Source.enabled.is_(True),
            )
        )
        if source_id is None:
            return 0
        runs = await run_ingestion(db, source_ids=[source_id], live=True)
        return len(runs)


async def run_sachet_poll_loop(interval_seconds: int) -> None:
    while True:
        started = monotonic()
        try:
            await poll_sachet_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Scheduled SACHET ingestion failed")
        elapsed = monotonic() - started
        await asyncio.sleep(max(1.0, interval_seconds - elapsed))
