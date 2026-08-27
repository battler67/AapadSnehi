# OpenAI image verification and Cloudinary evidence lifecycle

## Purpose and boundary

New citizen images are screened by `gpt-4.1-mini` through OpenAI's Responses API.
The backend asks for a short factual description, visible disaster evidence,
canonical hazards, and bounded observations. The Hugging Face/Qwen client and its
historical smoke script remain in the repository, but application startup does not
instantiate or call them.

No image model proves identity, authenticity, location, capture time, causation, or
severity. A model result is a community-signal screening aid, not an official alert.
See the official [OpenAI image-input guide](https://developers.openai.com/api/docs/guides/images-vision)
and [GPT-4.1 mini model page](https://developers.openai.com/api/docs/models/gpt-4.1-mini).

## Request flow

```text
Citizen uploads JPEG, PNG, or WebP (at most 6 MiB) and consents
        |
Signature check + full safe decode + EXIF transpose + pixel limit
        |
Original -> authenticated Cloudinary asset
Bounded metadata-free JPEG -> OpenAI Responses API (`store: false`)
        |
OpenAI visible evidence + 53-keyword/damage policy + selected hazard
        |
all three agree -> accepted and AI screened
anything else -> inactive and needs volunteer review
        |
volunteer approve -> community reviewed and active
volunteer reject -> delete evidence first, then reject
```

The inference copy is RGB JPEG, maximum edge 1280, maximum 2 MiB, and contains no
preserved EXIF metadata. Invalid decoded input returns HTTP 415 and is never stored.
Provider failure, malformed output, limits, or cloud-storage failure never discard
a possible emergency: the report and a private local evidence fallback are retained
for volunteer review.

## Structured response and decision policy

Prompt version `aapad-openai-visible-disaster-v2` uses strict JSON Structured
Outputs with these validated fields:

```json
{
  "caption": "A short factual description of visible content.",
  "disaster_evidence": "yes | no | unclear",
  "hazards": ["flood"],
  "observations": ["Water covers the road."]
}
```

Automatic acceptance requires all of the following:

1. OpenAI returns `yes` and a canonical hazard.
2. The independent 53-keyword/damage policy finds that same hazard in the
   description or observations.
3. That hazard matches the incident type selected by the reporter.
4. The original image was stored successfully in Cloudinary.

Every other valid result is `needs_volunteer_review`. There is no AI automatic
rejection path. This intentionally favors human review over losing genuine disaster
reports when the image is ordinary, ambiguous, mistyped, or outside the taxonomy.

## Storage and deletion

Cloudinary uploads use `resource_type=image` and `type=authenticated` beneath
`aapad-snehi/reports`. The API stores only Cloudinary identifiers and format; it
does not expose them to the browser. `GET /api/reports/{tracking_id}/image` returns
a short-lived signed Cloudinary redirect, or streams a validated local fallback.
Rejected reports return 404 for this endpoint. Responses use `private, no-store`.

Cloudinary recommends authenticated assets and signed access for protected media;
see [access-controlled media](https://cloudinary.com/documentation/control_access_to_media)
and the [upload API](https://cloudinary.com/documentation/image_upload_api_reference).

Rejection is fail-closed for deletion: the asset is destroyed before the database
state changes. If Cloudinary does not confirm deletion, the API returns 502 and the
report remains in the review queue. Local fallback files follow the same delete-first
rule. Approval retains evidence for the active community-reviewed report.

## Configuration

The root `.env` is loaded by the backend with process environment variables taking
precedence. Keep real values out of `.env.example` and Git.

```env
OPENAI_API_KEY=
OPENAI_VISION_MODEL=gpt-4.1-mini
OPENAI_TIMEOUT_SECONDS=45
OPENAI_MAX_CALLS_PER_HOUR=20

# Preferred single-value form:
CLOUDINARY_KEY=cloudinary://api_key:api_secret@cloud_name
CLOUDINARY_REVIEW_URL_SECONDS=300

# Or use all three separate values instead of CLOUDINARY_KEY:
CLOUDINARY_CLOUD_NAME=
CLOUDINARY_API_KEY=
CLOUDINARY_API_SECRET=
```

A bare API key or API secret in `CLOUDINARY_KEY` is incomplete and deliberately
treated as unconfigured. The backend needs all three credential parts to upload,
sign review access, and delete rejected evidence.

OpenAI calls have a process-local rolling hourly limit and concurrency limit of two.
There are no automatic retries. These are demo safeguards, not multi-worker quotas,
account budget caps, authentication, or abuse protection.

## Provider and policy replacement seams

`backend/app/services/image_triage.py` separates:

- `prepare_inference_image`, which produces a bounded `PreparedImage`;
- `OpenAIVisionCaptionClient.caption`, which produces a validated `CaptionResult`;
- `triage_report_assessment`, which produces the two-outcome automated decision.

`backend/app/services/image_storage.py` separately owns Cloudinary credentials,
upload, signed review URLs, and deletion. A future Hugging Face or other vision
provider can implement the same async `caption(PreparedImage) -> CaptionResult`
contract without changing storage, persistence, or moderation. Preserve the rule
that provider uncertainty becomes review, never rejection.

## Current prototype security boundary

The admin and volunteer pages intentionally have no login or RBAC. Consequently,
the review image endpoint and moderation endpoint are not an authorization boundary
in this prototype. Before real-world deployment, add authenticated volunteer roles,
audit events, malware scanning, retention policy, moderation conflict handling,
distributed rate/spend controls, and a consented Indian disaster evaluation set.

## Verification

The backend suite mocks OpenAI and Cloudinary. It covers the Responses payload,
`store: false`, strict output parsing, secret-safe failures, three-way agreement,
no automatic rejection, authenticated upload options, signed URLs, deletion,
delete-failure rollback, migrations, image access, and local fallback. No model is
downloaded.

```powershell
cd backend
python -m pytest

cd ..\web
npm test
npm run build
```
