from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parents[1]
PROJECT_DIR = BASE_DIR.parent

# Local secrets live at the project root. Process-level configuration always wins.
load_dotenv(PROJECT_DIR / ".env", override=False)
load_dotenv(BASE_DIR / ".env", override=False)


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _bounded_int(name: str, default: int, minimum: int, maximum: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        value = default
    return max(minimum, min(maximum, value))


@dataclass(frozen=True)
class Settings:
    database_url: str
    cors_origins: tuple[str, ...]
    enable_live_adapters: bool
    reliefweb_appname: str
    serper_api_key: str
    government_hosts: tuple[str, ...]
    sachet_poll_seconds: int
    bluesky_email: str
    bluesky_app_password: str
    bluesky_query: str
    bluesky_max_posts: int
    openai_api_key: str
    openai_vision_model: str
    openai_timeout_seconds: float
    openai_max_calls_per_hour: int
    cloudinary_key: str
    cloudinary_cloud_name: str
    cloudinary_api_key: str
    cloudinary_api_secret: str
    cloudinary_review_url_seconds: int
    hf_token: str
    hf_caption_model: str
    max_upload_bytes: int
    upload_dir: Path


def get_settings() -> Settings:
    database_url = os.getenv(
        "AAPAD_DATABASE_URL",
        f"sqlite:///{(BASE_DIR / 'data' / 'aapad_snehi.db').as_posix()}",
    )
    cors = tuple(
        item.strip()
        for item in os.getenv(
            "AAPAD_CORS_ORIGINS",
            "http://localhost:5173,http://127.0.0.1:5173",
        ).split(",")
        if item.strip()
    )
    hosts = tuple(
        item.strip().lower()
        for item in os.getenv(
            "AAPAD_GOVERNMENT_HOSTS",
            "mausam.imd.gov.in,api.imd.gov.in,cap-sources.s3.amazonaws.com,sachet.ndma.gov.in,ndma.gov.in",
        ).split(",")
        if item.strip()
    )

    return Settings(
        database_url=database_url,
        cors_origins=cors,
        enable_live_adapters=_as_bool(os.getenv("AAPAD_ENABLE_LIVE_ADAPTERS")),
        reliefweb_appname=os.getenv("AAPAD_RELIEFWEB_APPNAME", "").strip(),
        serper_api_key=os.getenv("AAPAD_SERPER_API_KEY", "").strip(),
        government_hosts=hosts,
        sachet_poll_seconds=max(0, int(os.getenv("AAPAD_SACHET_POLL_SECONDS", "300"))),
        bluesky_email=os.getenv("AAPAD_BLUESKY_EMAIL", "").strip(),
        bluesky_app_password=os.getenv("AAPAD_BLUESKY_APP_PASSWORD", "").strip(),
        bluesky_query=(
            os.getenv("AAPAD_BLUESKY_QUERY", "floods in india").strip()[:100]
            or "floods in india"
        ),
        bluesky_max_posts=_bounded_int("AAPAD_BLUESKY_MAX_POSTS", 10, 1, 50),
        openai_api_key=os.getenv("OPENAI_API_KEY", "").strip(),
        openai_vision_model=os.getenv("OPENAI_VISION_MODEL", "gpt-4.1-mini").strip(),
        openai_timeout_seconds=max(
            1.0,
            min(120.0, float(os.getenv("OPENAI_TIMEOUT_SECONDS", "45"))),
        ),
        openai_max_calls_per_hour=max(
            0,
            min(1000, int(os.getenv("OPENAI_MAX_CALLS_PER_HOUR", "20"))),
        ),
        cloudinary_key=os.getenv("CLOUDINARY_KEY", "").strip(),
        cloudinary_cloud_name=os.getenv("CLOUDINARY_CLOUD_NAME", "").strip(),
        cloudinary_api_key=os.getenv("CLOUDINARY_API_KEY", "").strip(),
        cloudinary_api_secret=os.getenv("CLOUDINARY_API_SECRET", "").strip(),
        cloudinary_review_url_seconds=max(
            60,
            min(3600, int(os.getenv("CLOUDINARY_REVIEW_URL_SECONDS", "300"))),
        ),
        hf_token=(
            os.getenv("AAPAD_HF_TOKEN", "").strip()
            or os.getenv("AAPAD_BLIP_HF_TOKEN", "").strip()
        ),
        hf_caption_model=os.getenv(
            "AAPAD_HF_CAPTION_MODEL",
            "Qwen/Qwen3-VL-2B-Instruct:featherless-ai",
        ).strip(),
        max_upload_bytes=int(os.getenv("AAPAD_MAX_UPLOAD_MB", "6")) * 1024 * 1024,
        upload_dir=BASE_DIR / "data" / "uploads",
    )


settings = get_settings()
