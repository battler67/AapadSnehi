# Bluesky helper adapter

This feature turns the notebook's Bluesky search experiment into one small, read-only portal workflow. It does not use Hugging Face, Transformers, or any other model.

## Setup

Install the normal backend dependencies, then put the Bluesky values in the ignored project-root `.env`:

```dotenv
AAPAD_ENABLE_LIVE_ADAPTERS=true
AAPAD_BLUESKY_EMAIL=your-bluesky-email
AAPAD_BLUESKY_APP_PASSWORD=your-bluesky-app-password
AAPAD_BLUESKY_QUERY=floods in india
AAPAD_BLUESKY_MAX_POSTS=10
```

Use a Bluesky app password rather than a reusable account password. The adapter never reads credentials from `bluesky_test.ipynb`, never sends them to the browser, and never stores them in the database. Rotate the credential that was pasted into the notebook before configuring the backend.

Start the API and web app and open `/bluesky-helpers`. Enter a query and select **Run Bluesky scan**. The page calls the public demo endpoint `POST /api/bluesky/scan`; there is no portal account, token, sign-in, or role check. The separate Bluesky app password remains backend-only because the provider requires it.

## What the scan does

The adapter follows the notebook's read path:

1. Create an `atproto.Client`.
2. Log in with the backend-only email and app password.
3. Call `client.app.bsky.feed.search_posts` with one query and a bounded limit.
4. Inspect the returned public post text and author fields.
5. Keep posts containing both a recognized disaster term and an explicit offer such as “we can help”, “willing to help”, “providing food”, or “boats are available”.
6. Exclude obvious requests and negations such as “we need help” and “cannot help”.
7. Deduplicate matches by the author's DID and return the DID, current handle, display name, matched terms, capabilities, excerpt, and safe public-post link.

Results are held only in the current browser response; the feature does not build a people database. A scan does not send a post, like, follow, message, register a volunteer, or create an assignment.

## Interpretation limits

The rule is intentionally simple and inspectable. It is not sentiment analysis and does not understand every language, joke, promotion, context change, or withdrawn offer. A returned account is a potential public lead only. A human must review the source post and obtain consent before treating the person as a volunteer.

Bluesky search is bounded and is not a complete firehose. Zero matches is a valid result.

## Verification

The tests inject a fake `atproto` client and never use a real account:

```powershell
cd backend
python -m pytest tests\test_social_intent.py tests\test_bluesky_adapter.py tests\test_bluesky_api.py -q

cd ..\web
npm test
npm run build
```
