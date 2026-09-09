"""Environment + client wiring. Mirrors selah/config.py so both projects feel the same."""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
IMAGE_MODEL = os.getenv("IMAGE_MODEL", "gemini-3.1-flash-image")
TEXT_MODEL = os.getenv("TEXT_MODEL", "gemini-3.7-flash")
IMAGE_SIZE = os.getenv("IMAGE_SIZE", "2K")
ASPECT = "9:16"  # the body photo is a tall portrait

ASSETS = ROOT / "assets"
OUTPUTS = ROOT / "outputs"
STATIC = ROOT / "app" / "static"

BODY_RAW = ASSETS / "body.png"      # the original photo — never served to the browser
SOURCE = ASSETS / "source.png"      # body.png on a white 9:16 canvas — what the model sees
BASE_LOOK = ASSETS / "base.png"     # vest + longer shorts — what the homepage shows

OUTPUTS.mkdir(exist_ok=True)


class ConfigError(RuntimeError):
    pass


@lru_cache(maxsize=1)
def get_client():
    if not GEMINI_API_KEY:
        raise ConfigError("GEMINI_API_KEY is not set. Copy .env.example to .env and paste your key.")
    from google import genai
    return genai.Client(api_key=GEMINI_API_KEY)
