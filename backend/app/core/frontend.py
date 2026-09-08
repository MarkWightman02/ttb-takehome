from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_frontend(app: FastAPI, dist: Path) -> None:
    """Serve the current single-page shell without swallowing missing API or asset routes."""
    dist = dist.resolve()
    index = dist / "index.html"
    if not index.is_file():
        raise ValueError("TTB_FRONTEND_DIST must contain a built frontend index.html.")

    @app.get("/", include_in_schema=False)
    async def frontend_index() -> FileResponse:
        return FileResponse(index, headers={"Cache-Control": "no-cache"})

    assets = dist / "assets"
    if assets.is_dir():
        app.mount("/assets", StaticFiles(directory=assets), name="frontend-assets")
