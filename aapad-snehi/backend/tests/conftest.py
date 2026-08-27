import os
import io
import sys
import tempfile
from pathlib import Path

backend_dir = Path(__file__).resolve().parent.parent
if str(backend_dir) not in sys.path:
    sys.path.insert(0, str(backend_dir))

import pytest
from fastapi.testclient import TestClient
from PIL import Image

_test_dir = tempfile.mkdtemp(prefix="aapad_snehi_tests_")
os.environ["AAPAD_DATABASE_URL"] = f"sqlite:///{_test_dir}/test.db"
os.environ["AAPAD_ENABLE_LIVE_ADAPTERS"] = "false"
os.environ["OPENAI_API_KEY"] = ""
os.environ["CLOUDINARY_KEY"] = ""
os.environ["CLOUDINARY_CLOUD_NAME"] = ""
os.environ["CLOUDINARY_API_KEY"] = ""
os.environ["CLOUDINARY_API_SECRET"] = ""

from app.main import app  # noqa: E402


@pytest.fixture
def valid_jpeg_bytes() -> bytes:
    output = io.BytesIO()
    Image.new("RGB", (48, 32), (40, 90, 140)).save(output, format="JPEG")
    return output.getvalue()


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client
