# style-me

Virtual try-on for one person (you), powered by Nano Banana (Gemini image) — same
Google house and the same `client.interactions.create` pattern as **selah**.

```
./run.sh            # http://127.0.0.1:8765
```

## What it does

- **Base look** — the homepage never shows the raw photo. `assets/base.png` is a
  generated "mannequin" look (grey vest + navy shorts). Regenerate it from the UI.
- **Describe an outfit** — type what you're picturing, hit *Try it on* (or Ctrl+Enter).
- **Paste a garment** — copy a product image from any shop page and Ctrl+V anywhere
  on the page (or drag/drop, or browse). Several garments at once is fine.
  Add an optional note ("with beige chinos") in the text box.
- **Suggest** — Gemini (text) proposes complete outfits with real brands and a
  one-click *Try it on*. Give it a brief: "wedding guest", "streetwear", "Sunday service".
- **Build on current look** — tick this to layer onto whatever is on screen instead
  of starting from the clean base (e.g. "add a denim jacket").
- **Looks so far** — every result is saved to `outputs/` with its prompt; click to
  revisit, hover to delete, *Download* to save.

## Setup

```
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env    # paste your Gemini API key (aistudio.google.com)
mkdir -p assets          # drop your full-body photo here as assets/body.png
                         # (front-facing, plain or transparent background)
```

Photos, generated looks and `.env` are git-ignored — nothing personal leaves the machine
except the API calls to Gemini.

`.env` knobs: `IMAGE_MODEL` (default `gemini-3.1-flash-image`), `TEXT_MODEL`
(`gemini-3.7-flash`), `IMAGE_SIZE` (`1K` fast ≈ 20s · `2K` ≈ 1–2 min).

## Layout

```
app/config.py        env + client (mirrors selah)
app/gemini.py        try_on(), make_base_look(), suggest()  — all API calls
app/server.py        FastAPI routes
app/static/index.html the whole UI
assets/body.png      your original photo (git-ignored, never served)
assets/source.png    body.png on a white 9:16 canvas — what the model actually sees
assets/base.png      the generated default look shown on the homepage
outputs/             results + json sidecars
```

## Notes

- Try-ons always start from the *clean* photo unless "Build on current look" is
  ticked — the model does a better job dressing a bare body than swapping clothes.
- Nano Banana occasionally drifts on hands or the watch. Just re-roll.
