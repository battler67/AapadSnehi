# Hosted deployment

## Free demo

The Render blueprint uses free compute without a disk. Data is ephemeral and may
reset on restart or redeploy; idle services sleep. The container displays a demo
notice. Use only fictional reports and photographs; live adapters are disabled.
The persistent-storage instructions below apply only to a separately approved paid setup.

The Dockerfile builds the React app and serves it with FastAPI on one origin.
Deploy from `aapad-snehi/`, never from the outer workspace. `.dockerignore` allowlists
application source and build inputs; local `.env`, SQLite files, uploads, Git metadata,
demo credentials and artifacts are excluded. No existing reports or photographs are
migrated. The host starts with a fresh database and existing labelled demo defaults.

```sh
docker build -t aapad-snehi .
docker volume create aapad-snehi-data
docker run --rm -p 8000:8000 -v aapad-snehi-data:/app/data aapad-snehi
```

For a hosting service, select the Dockerfile, configure a persistent volume at
`/app/data` writable by UID 10001, one instance/worker, and health check `/health`.
The process accepts the host's `PORT` variable, default 8000. Use HTTPS. The database
and private media must survive restarts and redeployments; an ephemeral filesystem
is insufficient. Set `AAPAD_CORS_ORIGINS` to the chosen HTTPS origin if cross-origin
clients are needed. The frontend uses same-origin requests and SPA navigation.

Keep live adapters and MQTT disabled for this demonstration. Provision new operational
credentials on the hosted server using the flood management command; never upload
local credential files. Existing legacy Admin/Volunteer routes remain public prototype
workflows. This deployment does not make those routes production-authorized services.

Hosting account and persistent-storage access are required before publishing. No paid
resource is provisioned by these files. After deployment verify `/health`, `/docs`,
`/flood`, `/flood/report`, report submission, reload persistence and media authorization
on the actual public URL before reporting success.

## Render

`render.yaml` declares one free Docker web service without persistent storage.
For durable reports, separately approve a paid service and a persistent disk.
The blueprint assumes the active `aapad-snehi` directory is the repository root.
If deploying the outer repository, set its service Root Directory to `aapad-snehi`
and use the nested blueprint path. Disable automatic deployments until the verified
source snapshot is chosen. No local records or secrets should be pushed to Git.
