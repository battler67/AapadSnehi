FROM node:22-bookworm-slim AS web-build
WORKDIR /build
COPY web/package.json web/package-lock.json ./
RUN npm ci
COPY web/ ./
# A slash becomes the empty API prefix: all calls use the hosted origin.
ENV VITE_API_URL=/
ENV VITE_HOSTED_DEMO=true
RUN npm run build

FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    AAPAD_DATABASE_URL=sqlite:////app/data/aapad_snehi.db \
    AAPAD_ENABLE_LIVE_ADAPTERS=false \
    AAPAD_EDGE_MQTT_ENABLED=false \
    AAPAD_SACHET_POLL_SECONDS=0 \
    AAPAD_ML_MODEL_ROOT=/app/model-artifacts \
    AAPAD_WEB_DIST=/app/web-dist \
    PORT=8000
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
COPY backend/requirements-ml-deploy.txt ./requirements-ml-deploy.txt
RUN pip install --no-cache-dir -r requirements.txt -r requirements-ml-deploy.txt \
    && useradd --create-home --uid 10001 aapad \
    && mkdir -p /app/data/uploads \
    && chown -R aapad:aapad /app/data
COPY --chown=aapad:aapad backend/app/ ./app/
COPY --chown=aapad:aapad backend/model_artifacts/ ./model-artifacts/
COPY --from=web-build /build/dist/ /app/web-dist/
USER aapad
EXPOSE 8000
VOLUME ["/app/data"]
CMD ["python", "-m", "app.hosted"]
