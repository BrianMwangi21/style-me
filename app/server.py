"""FastAPI app: serves the page, the base look, the outputs, and the Gemini endpoints."""

from __future__ import annotations

import base64
import re
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app import config, gemini

app = FastAPI(title="style-me")
app.mount("/outputs", StaticFiles(directory=config.OUTPUTS), name="outputs")

_DATA_URL = re.compile(r"^data:(image/[\w.+-]+);base64,(.+)$", re.S)


class GenerateBody(BaseModel):
    prompt: str = ""
    source: str = "base"           # "base" | "current" | an output id
    garments: list[str] = []       # data URLs pasted/dropped in the browser


class SuggestBody(BaseModel):
    brief: str = ""
    count: int = 4


@app.get("/")
def index():
    return FileResponse(config.STATIC / "index.html")


@app.get("/base.png")
def base_png():
    if not config.BASE_LOOK.exists():
        raise HTTPException(404, "Base look not generated yet")
    return FileResponse(config.BASE_LOOK)


@app.get("/api/state")
def state():
    return {
        "has_base": config.BASE_LOOK.exists(),
        "outputs": gemini.list_outputs(),
        "image_model": config.IMAGE_MODEL,
        "text_model": config.TEXT_MODEL,
    }


@app.post("/api/base")
def make_base():
    try:
        gemini.make_base_look()
    except Exception as e:
        raise HTTPException(500, str(e))
    return {"ok": True}


def _resolve_source(key: str) -> Path:
    if key in ("base", "body", ""):
        return gemini.ensure_source()
    if key == "current":
        return config.BASE_LOOK if config.BASE_LOOK.exists() else gemini.ensure_source()
    matches = list(config.OUTPUTS.glob(f"{key}.*"))
    imgs = [m for m in matches if m.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}]
    if not imgs:
        raise HTTPException(404, f"Unknown source '{key}'")
    return imgs[0]


@app.post("/api/generate")
def generate(body: GenerateBody):
    garments: list[bytes] = []
    for g in body.garments:
        m = _DATA_URL.match(g.strip())
        if not m:
            raise HTTPException(400, "Garment images must be base64 data URLs")
        garments.append(base64.b64decode(m.group(2)))
    try:
        record = gemini.try_on(body.prompt, _resolve_source(body.source), garments)
    except ValueError as e:
        raise HTTPException(400, str(e))
    except Exception as e:
        raise HTTPException(500, str(e))
    return record


@app.post("/api/suggest")
def suggest(body: SuggestBody):
    try:
        return {"outfits": gemini.suggest(body.brief, max(1, min(body.count, 8)))}
    except Exception as e:
        raise HTTPException(500, str(e))


@app.delete("/api/outputs/{oid}")
def delete(oid: str):
    if not re.fullmatch(r"[\w-]+", oid):
        raise HTTPException(400, "bad id")
    gemini.delete_output(oid)
    return JSONResponse({"ok": True})
