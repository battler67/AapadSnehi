from fastapi import FastAPI
from fastapi.testclient import TestClient
from app.hosted import FrontendFiles


def test_hosted_routes_keep_api_and_files_separate(tmp_path):
    (tmp_path / "index.html").write_text("<h1>AapadSnehi test shell</h1>")
    (tmp_path / "asset.js").write_text("window.test=true;")
    app = FastAPI()

    @app.get("/api/health")
    def health():
        return {"ok": True}

    app.mount("/", FrontendFiles(directory=str(tmp_path), html=True))
    with TestClient(app) as client:
        assert client.get("/api/health").json() == {"ok": True}
        assert "AapadSnehi test shell" in client.get("/flood/report").text
        assert client.get("/asset.js").status_code == 200
        assert client.get("/api/missing").status_code == 404
        assert client.get("/missing.js").status_code == 404
        assert client.get("/.env").status_code == 404
