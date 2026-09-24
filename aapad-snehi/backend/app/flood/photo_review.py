"""Private, advisory screening; never updates operational truth or dispatch."""
import asyncio
import json

from ..models import utcnow
from .models import PhotoReview


def review_view(db, media_id):
    review = db.get(PhotoReview, media_id)
    return json.loads(review.result) if review else {"status": "not_screened", "message": "No AI screening recorded; human review required."}


async def screen_photo(image):
    # Share the existing configured client and its hourly limiter with legacy APIs.
    from ..main import caption_client
    try:
        result = await asyncio.wait_for(caption_client.caption(image), timeout=25)
        return {"status": "screened", "message": "AI advisory only — human verification required.",
                "caption": result.caption, "evidence": result.evidence,
                "observations": list(result.observations), "hazards": list(result.hazards),
                "provider": result.provider, "model": result.model,
                "promptVersion": result.prompt_version}
    except Exception:
        # Do not expose provider errors, credentials or request content to clients.
        return {"status": "unavailable", "message": "AI screening unavailable or not configured. Photo attached; human review required."}


def save_review(db, media_id, result):
    review = db.get(PhotoReview, media_id)
    if review is None:
        review = PhotoReview(media_id=media_id, result=json.dumps(result))
        db.add(review)
    else:
        review.result = json.dumps(result)
        review.updated_at = utcnow()
