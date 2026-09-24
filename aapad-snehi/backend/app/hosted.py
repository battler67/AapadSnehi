"""Same-origin container entry point. No source or data directories are served."""
import os
from pathlib import Path

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles


class FrontendFiles(StaticFiles):
    async def get_response(self, path, scope):
        # Starlette normalizes filesystem separators on Windows.
        path = path.replace("\\", "/").lstrip("/")
        if path == "api" or path.startswith("api/") or any(part.startswith(".") for part in path.split("/")):
            raise HTTPException(404)
        try:
            return await super().get_response(path, scope)
        except HTTPException as exc:
            if exc.status_code != 404 or Path(path).suffix:
                raise
            return await super().get_response("index.html", scope)


def create_app():
    from .main import app
    directory = Path(os.environ["AAPAD_WEB_DIST"]).resolve()
    if not (directory / "index.html").is_file():
        raise RuntimeError("AAPAD_WEB_DIST must contain the built frontend")
    # Keep the standalone API root unchanged; hosted mode serves the website here.
    from starlette.responses import FileResponse
    from starlette.routing import Route
    async def homepage(request):
        return FileResponse(directory / "index.html")
    app.router.routes.insert(0, Route("/", homepage, methods=["GET", "HEAD"]))
    app.mount("/", FrontendFiles(directory=str(directory), html=True), name="frontend")
    return app


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(create_app(), host="0.0.0.0", port=int(os.getenv("PORT", "8000")), workers=1)
