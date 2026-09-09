#!/usr/bin/env bash
cd "$(dirname "$0")"
exec .venv/bin/uvicorn app.server:app --host 127.0.0.1 --port 8765 --reload
