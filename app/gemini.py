"""All Gemini calls live here: the try-on (Nano Banana) and outfit suggestions (text).

Try-on uses the Interactions API exactly like selah/art.py, but with image inputs:
    input=[{"type":"text",...}, {"type":"image","data":<b64>,"mime_type":...}, ...]
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path

from PIL import Image

from app import config

# What must never change between the input photo and the output.
IDENTITY_LOCK = (
    "This is a virtual try-on. Keep the exact same person: same face, expression, "
    "skin tone, hair, body shape, height, proportions, pose, hand positions and "
    "the smartwatch on the left wrist. Keep the plain white studio background and "
    "the same framing (full body, head to feet, centred). Do not slim, reshape or "
    "beautify the body. Change ONLY the clothing and footwear. Photorealistic, "
    "sharp, natural fabric drape, shadows and fit for this body. No text, no logos "
    "unless they are part of the described garment, no watermark."
)

BASE_LOOK_PROMPT = (
    "Dress the person in a plain fitted charcoal-grey cotton tank top (vest) and "
    "relaxed knee-length navy cotton shorts, barefoot. Simple, neutral, modest — "
    "this is the default 'mannequin' look, so nothing eye-catching."
)


# ----------------------------------------------------------------------------
# Image helpers
# ----------------------------------------------------------------------------

def ensure_source() -> Path:
    """Composite the transparent body photo onto a white 9:16 canvas once."""
    if config.SOURCE.exists():
        return config.SOURCE
    body = Image.open(config.BODY_RAW).convert("RGBA")
    w, h = body.size
    canvas_h = h + 60
    canvas_w = round(canvas_h * 9 / 16)
    canvas = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))
    canvas.alpha_composite(body, ((canvas_w - w) // 2, 30))
    canvas.convert("RGB").save(config.SOURCE)
    return config.SOURCE


def _img_part(path: Path | None = None, data: bytes | None = None, mime: str = "image/png") -> dict:
    if path is not None:
        data = path.read_bytes()
        mime = _sniff(data)
    return {"type": "image", "data": base64.b64encode(data).decode(), "mime_type": mime}


def _sniff(data: bytes) -> str:
    if data[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return "image/png"


def _ext(mime: str) -> str:
    return {"image/jpeg": "jpg", "image/webp": "webp"}.get(mime, "png")


# ----------------------------------------------------------------------------
# Try-on
# ----------------------------------------------------------------------------

def _run_image(parts: list[dict]) -> bytes:
    client = config.get_client()
    interaction = client.interactions.create(
        model=config.IMAGE_MODEL,
        input=parts,
        response_format={"type": "image", "aspect_ratio": config.ASPECT, "image_size": config.IMAGE_SIZE},
    )
    image = getattr(interaction, "output_image", None)
    if image is None or not getattr(image, "data", None):
        raise RuntimeError("Nano Banana returned no image (the request may have been blocked).")
    return base64.b64decode(image.data)


def try_on(prompt: str, source: Path, garments: list[bytes] | None = None) -> dict:
    """Dress the person in `source` per `prompt` and/or the garment reference images.

    Returns the saved output's metadata dict."""
    garments = garments or []
    prompt = (prompt or "").strip()
    if not prompt and not garments:
        raise ValueError("Give me a description or paste a garment image.")

    lines = ["Image 1 is the person to dress."]
    if garments:
        n = len(garments)
        refs = "Image 2" if n == 1 else f"Images 2 to {n + 1}"
        lines.append(
            f"{refs} show garment(s) from a shop listing. Put exactly these garments on the "
            "person: reproduce their colour, print, fabric, cut and fit faithfully as they "
            "would look worn by this body. If a reference shows a model wearing the item, "
            "take only the item, not the model."
        )
    if prompt:
        lines.append(f"Outfit request: {prompt}")
    lines.append(IDENTITY_LOCK)

    parts = [{"type": "text", "text": "\n".join(lines)}, _img_part(path=source)]
    for g in garments:
        parts.append(_img_part(data=g, mime=_sniff(g)))

    data = _run_image(parts)
    return _save_output(data, prompt=prompt, source=source, garment_count=len(garments))


def make_base_look() -> Path:
    """Generate the modest default look shown on the homepage."""
    src = ensure_source()
    parts = [{"type": "text", "text": f"Image 1 is the person to dress. {BASE_LOOK_PROMPT} {IDENTITY_LOCK}"}, _img_part(path=src)]
    data = _run_image(parts)
    config.BASE_LOOK.write_bytes(data)
    return config.BASE_LOOK


def _save_output(data: bytes, **meta) -> dict:
    stamp = time.strftime("%Y%m%d-%H%M%S")
    mime = _sniff(data)
    oid = f"{stamp}-{int(time.time() * 1000) % 1000:03d}"
    img = config.OUTPUTS / f"{oid}.{_ext(mime)}"
    img.write_bytes(data)
    record = {
        "id": oid,
        "file": img.name,
        "url": f"/outputs/{img.name}",
        "created": stamp,
        "prompt": meta.get("prompt", ""),
        "source": Path(meta["source"]).name if meta.get("source") else None,
        "garment_count": meta.get("garment_count", 0),
    }
    (config.OUTPUTS / f"{oid}.json").write_text(json.dumps(record, indent=2))
    return record


def list_outputs() -> list[dict]:
    items = []
    for p in sorted(config.OUTPUTS.glob("*.json"), reverse=True):
        try:
            items.append(json.loads(p.read_text()))
        except Exception:
            continue
    return items


def delete_output(oid: str) -> None:
    for p in config.OUTPUTS.glob(f"{oid}.*"):
        p.unlink(missing_ok=True)


# ----------------------------------------------------------------------------
# Suggestions (text model)
# ----------------------------------------------------------------------------

SUGGEST_SYSTEM = (
    "You are a sharp, practical personal stylist. The client is a Black man in his "
    "late twenties or thirties, average-to-stocky build with a soft midsection, "
    "broad shoulders. Suggest outfits that flatter that build (structured shoulders, "
    "clean lines, mid-weight fabrics, avoid clingy tops). Use REAL, currently sold "
    "items from real brands at a mix of price points (e.g. Uniqlo, COS, Zara, "
    "Nike, Adidas, Levi's, Carhartt WIP, Ralph Lauren, Massimo Dutti, Arket, "
    "Clarks, New Balance). Be specific about colour, fabric and fit. "
    "Return ONLY JSON matching the schema."
)

SUGGEST_SCHEMA = {
    "type": "object",
    "properties": {
        "outfits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "vibe": {"type": "string"},
                    "why": {"type": "string"},
                    "items": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "slot": {"type": "string"},
                                "brand": {"type": "string"},
                                "item": {"type": "string"},
                                "colour": {"type": "string"},
                            },
                            "required": ["slot", "brand", "item", "colour"],
                        },
                    },
                    "render_prompt": {"type": "string"},
                },
                "required": ["name", "vibe", "why", "items", "render_prompt"],
            },
        }
    },
    "required": ["outfits"],
}


def suggest(brief: str = "", count: int = 4) -> list[dict]:
    from google.genai import types

    client = config.get_client()
    ask = (
        f"Suggest {count} distinct complete outfits (top, bottom, shoes, plus one "
        f"optional layer or accessory). Brief from the client: '{brief or 'surprise me, everyday wear'}'. "
        "For each outfit write `render_prompt`: one dense sentence describing every "
        "garment (colour, fabric, cut, fit, how it is worn, footwear) so an image "
        "model can paint it accurately. Do not mention the person's body in render_prompt."
    )
    resp = client.models.generate_content(
        model=config.TEXT_MODEL,
        contents=ask,
        config=types.GenerateContentConfig(
            system_instruction=SUGGEST_SYSTEM,
            response_mime_type="application/json",
            response_json_schema=SUGGEST_SCHEMA,
            temperature=1.1,
        ),
    )
    return json.loads(resp.text)["outfits"]
