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
    "You are a sharp, opinionated personal stylist with encyclopaedic product knowledge. "
    "The client is a Black man in his late twenties or thirties, average-to-stocky build "
    "with a soft midsection and broad shoulders. Flatter that build: structured shoulders, "
    "clean lines, mid-weight fabrics, nothing clingy across the stomach.\n\n"
    "RULES:\n"
    "1. Every item must be a REAL, currently sold product: brand + exact product name + "
    "official colourway name (e.g. 'Nike Air Max 1 \'Bacon\' in Dark Stucco/Cider', "
    "'Uniqlo U Wide-Fit Pleated Chino in Dark Green', 'Clarks Wallabee in Maple Suede'). "
    "Mix price points across brands.\n"
    "2. Be exhaustively specific for EVERY piece, not just shoes. Each item's `details` "
    "field must state, as applicable: fabric and weight (e.g. 14oz raw selvedge, 200gsm "
    "Supima jersey, brushed melton wool), exact colour/wash, cut and fit (boxy, slim, "
    "wide-leg, cropped), rise and length/inseam for trousers, collar/neckline type, sleeve "
    "length, closure (buttons/zip/drawstring), hardware colour, and precisely how it is "
    "worn: tucked or untucked, cuffed how many times, sleeves rolled to where, buttoned to "
    "where, layered over what. Shoes: upper material and colour AND sole colour, lacing. "
    "Socks: colour, height, visible or not. Accessories: material, colour, size. Nothing "
    "vague, no 'nice shirt', no 'dark trousers'.\n"
    "3. The outfits you return must be VASTLY different from each other while still "
    "answering the same brief: different colour palettes, different silhouettes (e.g. one "
    "slim and tailored, one oversized and relaxed), different footwear categories, different "
    "layering. If they could be mistaken for each other, you have failed.\n"
    "4. Never repeat or closely resemble anything in the 'already generated' list.\n"
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
                                "details": {"type": "string"},
                            },
                            "required": ["slot", "brand", "item", "colour", "details"],
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


def suggest(brief: str = "", count: int = 2) -> list[dict]:
    from google.genai import types

    client = config.get_client()
    seen = [o["prompt"] for o in list_outputs() if o.get("prompt")][:20]
    seen_block = ""
    if seen:
        seen_block = "\n\nALREADY GENERATED (do not repeat these or anything close):\n- " + "\n- ".join(seen)
    ask = (
        f"Brief from the client: '{brief or 'surprise me, everyday wear'}'.\n"
        f"Give {count} complete outfits that each answer this brief from a completely "
        "different angle (palette, silhouette, footwear category, layering all different). "
        "Each outfit: top, bottom, shoes, socks, plus at least two of: outer layer, belt, "
        "hat, eyewear, jewellery, bag.\n"
        "For each outfit write `render_prompt`: one dense paragraph an image model can paint "
        "from. Walk through the outfit top to bottom and give EVERY piece the same depth: "
        "exact colour and wash, fabric and weight, cut, fit, rise, length, collar, sleeves, "
        "closure, hardware, and exactly how it is worn or layered; then shoes with upper and "
        "sole colour, then socks, then each accessory. It must contain everything in the "
        "items' `details` fields. Do not mention the person's body or face in render_prompt."
        + seen_block
    )
    resp = client.models.generate_content(
        model=config.TEXT_MODEL,
        contents=ask,
        config=types.GenerateContentConfig(
            system_instruction=SUGGEST_SYSTEM,
            response_mime_type="application/json",
            response_json_schema=SUGGEST_SCHEMA,
            temperature=1.3,
        ),
    )
    return json.loads(resp.text)["outfits"]
