# Citizen flood reports and rescue coordination

Implemented on `feature/citizen-flood-rescue`. Open `/flood/report` to report and
`/flood` for the synchronized map, geographic summaries, list and operational panel.
The existing Users page links to the extended flood workflow. Historical/general
hazard reporting, public prototype dispatch and the edge-warning lab are preserved.

## Records and trust

`CitizenReport` and `Incident` retain their existing identities. Additive
`flood_report_details` and `flood_operations` hold private observations and reviewed
operational state. `flood_places` identifies locality/ward, street, building/door and
landmark groupings using normalized address components and parent identities.
`flood_rescue_tasks` holds independent rescue progress; `flood_audit` records actors,
timestamps, observation receipt, location corrections, review, grouping and tasks.
Teams can retain references to existing volunteers through `volunteer_ids`; a
protected team credential, not a public volunteer profile, grants rescue access.

New observations do not establish verified conditions. A coordinator explicitly
selects the canonical report and records evidence, verification, urgency and a
reason. Responder-confirmed counts require `responder_verified` evidence. Corroboration
requires at least two reporter access identities plus human-reviewed evidence;
these keys are not proof of distinct people, so no automatic corroboration occurs.
Citizen water levels are estimates. No image model is invoked by this workflow.

New reports start separate incidents. An owner can append timestamped observations
using their private key. Other witnesses submit separately for coordinator grouping.
Candidate suggestions compare distance/accuracy, locality, street, door, time and
type. They never auto-merge households. The same door on different streets has a
different place identity. Original address strings are retained; normalization only
collapses whitespace and case, preserving punctuation such as `12-4/7A`.

## Location and uncertainty

The form asks “Where was this photo taken?” Device GPS, JPEG EXIF GPS, address search
and manually positioned pins are suggestions until confirmed. Device accuracy is
shown and retained. Building precision is rejected for GPS accuracy over 50 metres.
Address lookup results deliberately retain locality/street precision; they cannot
become building points from an address label alone. Unknown coordinates are SQL NULL.
Unconfirmed locations remain in lists and the clarification queue, not on the map.
GPS denial, absent/malformed EXIF and failed map tiles retain the text workflow.

Coordinators can correct or clear a selected report location and record a reason.
Reporters can correct their own location through the protected API or submit an
updated observation. Administrative edits never change the observation timestamp.

Public coordinates are computed on the server as the centre of a fixed 0.02-degree
grid cell (roughly 2 km north/south, varying east/west). Public payloads omit private
points, door/building/floor, access notes, contacts, assistance details, headcounts,
media identifiers and activity details. No actual household point is sent and hidden
with CSS. These are citizen point observations, not validated flood polygons.

## Counting and grouping

The backend applies the same filters before producing map/list pages and statistics.
The UI shows up to 50 incidents per page (API maximum 100); counts span all matching
records. Selecting a geographic group selects its summary and incidents. Viewport
mode explicitly excludes unknown/unplotted points; disable it to include textual
reports. Queries have a 2,000-incident processing ceiling and fail visibly when too
broad instead of returning silently truncated statistics. Common status, place,
coordinate and observation/receipt timestamp columns are indexed.

- Buildings: distinct normalized named buildings, or house/door identities when no
  building name exists, never labelled households. Units in one named apartment
  building share one building identity.
- Active incidents: operationally active or monitoring, independent of rescue state.
- Open rescue requests: incidents with any non-resolved/non-cancelled task.
- Reported/estimated people: the explicitly reviewed canonical situation, not a sum
  of observations. Exact citizen counts and estimates are separate.
- If multiple incidents share a building and unit/door identity, their headcounts are
  withheld from totals as unknown/review-needed until grouping resolves possible
  duplication. Explicitly different units can have separate reviewed counts.
- Responder-confirmed people: explicit reviewed confirmation, not photo inference.
- Assigned teams: distinct team identities across open tasks, never task count.
- Blocked access: number of reports, not a claim that an entire street is blocked.
- Unresolved locations: number of reports needing location clarification.
- Stale: all observation times old or unknown; receipt/admin times never refresh them.
- Conflicting report counts remain flagged even after a canonical choice is recorded.

Landmark text groups are clearly labelled as text associations. Authorized proximity
search accepts an explicitly known landmark latitude/longitude and a 50–5,000 metre
straight-line radius (default 500 m). This is not an access-route calculation. No
street boundaries, flood extent or safe route is invented. Navigation is an explicit
external OpenStreetMap handoff with an uncertainty label.

Moving a report preserves its identity and audit trail, invalidates canonical counts,
and warns that original tasks remain at their source for explicit review. A rescue
report moved to a new incident gets a task awaiting review. Empty source incidents
remain accessible with their tasks and history. Merge requires both versions and
acknowledgement of retained task relationships. More than one open task blocks merging
until a coordinator explicitly resolves/cancels the conflict. Reports/tasks move;
source histories remain accessible and are referenced in the target timeline.

## Rescue workflow and concurrency

`needs_review → ready → assigned → en_route → on_scene → resolved`.
Explicit branches support `unable_to_reach`, cancellation, reassignment and reopening
to `needs_review`. Backend transition validation is authoritative. Assignment requires
a reviewed situation and a team authorized for the incident city. Responders can
advance only their own team's tasks; coordinators handle grouping and assignment.
Resolution requires an outcome and remaining needs (including an explicit “none”),
with optional assisted count and notes. Flood status does not change automatically.

Incident and task version checks occur in the write transaction; competing assignments
return HTTP 409 rather than overwrite. Task transitions lock the parent version so
merges cannot silently race assignment. Every transition records its actor and time.

## Permissions and photographs

The existing application has **no authentication for its old prototype routes**.
This feature therefore adds narrow, locally provisioned operational bearer credentials
instead of treating route names as permission boundaries. Credentials are random,
hashed in the database, revocable, and scoped to a normalized city or `*`. Responders
are tied to a team. Tokens are held only in page memory, not localStorage or URLs.
The implementation is suitable for local evaluation; agency SSO/MFA, identity vetting,
credential rotation policy and production abuse controls are not included.

Reporter access uses a high-entropy private key generated before submission. Keep the
receipt reference and key to load status or append an observation. This is a capability
key, not verified personal identity. Public legacy queries exclude all protected
flood incidents/reports, preventing old review/assignment/image routes from bypassing
these controls. Flood APIs and media are `no-store`; the service worker excludes APIs
and authenticated requests entirely.

Four photos per report, each at most 8 MB and 20 megapixels. Browser compression emits
a JPEG with metadata removed. The server re-decodes actual image content using the
existing Pillow validation service and creates a metadata-free display JPEG. The
original submitted bytes and derivative are held privately as SQLite blobs, not
public files. Original access is controlled and downloaded as an attachment.
Photos are withheld from public view by default and public publication is disabled.
There is no claimed automatic face/house redaction. Private storage requires normal
filesystem/database protection and backups; encryption at rest is not implemented.

## Offline and retries

The existing IndexedDB database is upgraded additively to version 2 with a flood draft
store. Draft text, stable submission key, owner key and compressed photos survive
refresh. There is no dependency on background sync. Submit/Retry explicitly sends the
text/location first; optional photo failures never undo a received rescue request.
Per-photo progress, errors and retry are shown. The same submission key/content returns
the existing receipt; different content under that key is rejected. Identical media
retries attach once. Completed drafts, photos and contact details are deleted locally;
partly uploaded drafts remain for retry. The receipt key must be saved before leaving.

## Development migration and configuration

From `aapad-snehi/backend`:

```powershell
python -m app.flood.manage migrate
```

Startup also applies the migration. Existing incident latitude/longitude become
nullable through a SQLite table rebuild preserving data and indexes. Before rebuilding,
a consistent `<database>.before-flood.sqlite` backup is made and never overwritten.
Stop writers before migrating an important existing development database. To recover,
stop the API and restore this backup to a new database path, then select it through
`AAPAD_DATABASE_URL`. This work migrated the local development database and a separate
demo database; no production environment was changed. SQLite is the verified target;
an existing PostgreSQL database needs separately reviewed DDL before use.

Operational provisioning (generated secrets go only to ignored local files):

```powershell
python -m app.flood.manage team --team-id local-water-team --name "Local Water Team" --scope "your city"
python -m app.flood.manage provision --name "Coordinator" --scope "your city" --credentials ../../.artifacts/coordinator-access.json
python -m app.flood.manage provision --role responder --name "Responder" --scope "your city" --team-id local-water-team --credentials ../../.artifacts/responder-access.json
python -m app.flood.manage revoke --identity-id "identity-id-from-provisioning"
```

Unspecified textual city has an empty scope and requires a `*` coordinator to triage.
Geographic authorization uses entered city names, not jurisdiction polygons. Deployments
need agency-approved jurisdiction mapping before field use.

`AAPAD_FLOOD_STALE_HOURS` defaults to 6 and supports 1–168 hours.
The API otherwise uses existing `AAPAD_DATABASE_URL`, `AAPAD_CORS_ORIGINS` and map tile
configuration. No-credential mode remains deterministic, with public reporting and no
unlocked operational access.

Address lookup is optional: set `AAPAD_ENABLE_LIVE_ADAPTERS=true` and
`AAPAD_FLOOD_GEOCODER_USER_AGENT` to an identifying application/contact string to allow
explicit OpenStreetMap Nominatim searches. No autocomplete. A process-local 1.1-second
request interval is enforced. Use one worker for this demo integration; a shared
rate-limit/cache and an appropriate provider agreement are required for scale. Enabling
the existing live-adapter gate can also enable other configured ingestion providers;
keep it false for the isolated demo. Missing configuration/provider failure returns
503 and preserves manual/text reporting. Live geocoding was not exercised in development.

## Explicit synthetic demo

From `backend`, seed a new isolated database; the command refuses to overwrite a seed
or credential file and requires `demo` in the database filename:

```powershell
python -m app.flood.manage seed --database data/flood-demo.db --credentials ../../.artifacts/flood-demo-access.json
$env:AAPAD_DATABASE_URL="sqlite:///C:/absolute/path/to/aapad-snehi/backend/data/flood-demo.db"
$env:AAPAD_ENABLE_LIVE_ADAPTERS="false"
$env:AAPAD_CORS_ORIGINS="http://127.0.0.1:5178,http://127.0.0.1:5179"
python -m uvicorn app.main:app --host 127.0.0.1 --port 8012
```

From `web` in another terminal:

```powershell
$env:VITE_API_URL="http://127.0.0.1:8012"
node node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5178
```

Open `/flood`, check **Show isolated synthetic demo reports**, and unlock with a
generated coordinator credential. Fixtures include multiple photos of one incident,
different houses on one street, identical door numbers on different streets, unresolved
text, corrected GPS, a stale observation received recently, conflicting headcounts,
blocked access, an assigned team, resolved rescue with active flooding, an idempotent
retry, and several reports mentioning the fictional Lantern Clock. The fictional
landmark radius example is latitude 17.431, longitude 78.492, radius 500 m.

Walkthrough: submit a new report at `/flood/report`; its normal report partition is
visible with the synthetic toggle off, still within the separate demo database.
Inspect receipt/photo state, select it in the list, review location/evidence/count,
mark task ready, assign Synthetic Water Team, then lock and unlock as the responder.
Advance en route → on scene → resolved, record assisted/remaining needs, and confirm
flooding stays active. No actual notification, dispatch communication or production
deployment happens. Updates are refreshed explicitly or every 20 seconds.

## Verification

```powershell
# backend
python -m pytest
# web
npm test
npm run build
# repository root, with the isolated API/web running and Playwright installed
python aapad-snehi/scripts/verify-flood-browser.py
```

The browser script uses a real API/database, a 390px mobile viewport and a 1440px
desktop viewport, an actual offline interval, IndexedDB recovery, real photo upload,
coordinator review/assignment and responder resolution. Screenshots go to ignored
`.artifacts/`. It creates clearly named synthetic browser reports in the isolated
database. No mocked API success responses are used.

Verified 2026-09-09: **237 backend tests**, **15 frontend tests**, TypeScript/Vite
production build, and the integrated browser workflow passed. For the additionally
verified full offline reload, build with the demo `VITE_API_URL`, start
`node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 5179`, then run
`python aapad-snehi/scripts/verify-flood-browser.py --web http://127.0.0.1:5179 --offline-refresh`
from the repository root. Map tiles are deliberately unavailable in this check.

Concrete limits: single durable draft per browser; only JPEG GPS EXIF is interpreted;
public photos intentionally unavailable; no automated redaction/AI inference; no real
emergency notifications or blockage-aware routing; manual agency credential provisioning;
SQLite blob media and bounded in-process summaries are for local prototype scale.
The old public prototype routes still require a separate security project before
production. Build output currently has a non-failing bundle-size warning.
