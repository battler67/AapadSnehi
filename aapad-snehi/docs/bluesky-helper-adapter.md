# Bluesky helper adapter

This feature turns the notebook's Bluesky search experiment into one small, read-only portal workflow. Deterministic rules identify assistance leads; an optional hosted Twitter-RoBERTa model adds advisory sentiment labels.

## Setup

Install the normal backend dependencies, then put the Bluesky values in the ignored project-root `.env`:

```dotenv
AAPAD_ENABLE_LIVE_ADAPTERS=true
AAPAD_BLUESKY_EMAIL=your-bluesky-email
AAPAD_BLUESKY_APP_PASSWORD=your-bluesky-app-password
AAPAD_BLUESKY_QUERY=floods in india
AAPAD_BLUESKY_MAX_POSTS=10
AAPAD_BLUESKY_SENTIMENT_ENABLED=true
AAPAD_BLUESKY_SENTIMENT_MODEL=cardiffnlp/twitter-roberta-base-sentiment-latest
AAPAD_BLUESKY_SENTIMENT_MAX_POSTS=10
AAPAD_HF_TOKEN=your-hugging-face-token
```

The interactive page always sends the user's query. `AAPAD_BLUESKY_QUERY` is only
the fallback for the legacy ingestion call or an empty API query; it does not
override text entered by the user.

Use a Bluesky app password rather than a reusable account password. The adapter never reads credentials from `bluesky_test.ipynb`, never sends them to the browser, and never stores them in the database. Rotate the credential that was pasted into the notebook before configuring the backend.

Start the API and web app and open `/bluesky-helpers`. Enter a query and select **Run Bluesky scan**. The page calls the public demo endpoint `POST /api/bluesky/scan`; there is no portal account, token, sign-in, or role check. The separate Bluesky app password remains backend-only because the provider requires it.

## What the scan does

The adapter follows the notebook's read path:

1. Create an `atproto.Client`.
2. Log in with the backend-only email and app password.
3. Call `client.app.bsky.feed.search_posts` with one query and a bounded limit.
4. Inspect the returned public post text and author fields.
5. Classify assistance signals into explicit offers, active aid, institutional support, and fundraising/donation leads.
6. Use a disaster term in the post when present. If an assistance post omits the hazard, use the recognized hazard from the user's query and label the result `query` context so a reviewer knows to inspect the thread.
7. Exclude negations and request-only posts such as “we need help” and “cannot help”. A post that describes needs and also states that aid is being delivered remains visible.
8. Deduplicate matches by author DID, retaining the strongest matching post, and return the confidence, category, context source, capabilities, excerpt, and safe public-post link.

Confidence is policy transparency, not a probability:

- `high`: an explicit offer or direct distribution statement;
- `medium`: active aid delivery or institutional support;
- `low`: fundraising, donations, charity events, or relief appeals.

Low-confidence and query-context matches are shown only as public leads requiring
human review. They are not implicitly converted into operational incidents by the
ingestion adapter.

## Sentiment layer

Matched assistance leads are optionally sent to the hosted
`cardiffnlp/twitter-roberta-base-sentiment-latest` text-classification model. URLs
and public handles are normalized before inference. The API returns the selected
`positive`, `neutral`, or `negative` label, its model score, model ID, provider
status, and aggregate counts. At most `AAPAD_BLUESKY_SENTIMENT_MAX_POSTS` matched
leads are scored per scan.

This sends the bounded public post text to the configured Hugging Face inference
provider. Review its current terms, retention, quotas, and token permissions before
enabling the feature in another environment. The token stays on the backend.

Sentiment never changes whether a post passes the assistance filter. Disaster
reports are naturally negative, operational updates are often neutral, and generic
encouragement can be positive without offering any help. Provider/configuration
failure produces an explicit `unavailable` label and does not block the scan.

Official references: [Hugging Face text classification](https://huggingface.co/docs/inference-providers/tasks/text-classification) and the [Twitter-RoBERTa model card](https://huggingface.co/cardiffnlp/twitter-roberta-base-sentiment-latest).

Results are held only in the current browser response; the feature does not build a people database. A scan does not send a post, like, follow, message, register a volunteer, or create an assignment.

## Interpretation limits

The assistance rule is intentionally simple and inspectable. The English sentiment model also does not reliably understand every language, joke, promotion, context change, thread relationship, disaster-domain nuance, or withdrawn offer. A returned account is a potential public lead only. Intent confidence and sentiment scores do not measure identity, credibility, present availability, proximity, skill, safety, or consent. A human must review the source post and obtain consent before treating the person as a volunteer.

Bluesky search is bounded and is not a complete firehose. Zero matches is a valid result.

## Verification

The tests inject a fake `atproto` client and never use a real account:

```powershell
cd backend
python -m pytest tests\test_sentiment.py tests\test_social_intent.py tests\test_bluesky_adapter.py tests\test_bluesky_api.py -q

cd ..\web
npm test
npm run build
```
