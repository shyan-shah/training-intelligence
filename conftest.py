import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
# Repo root, so `ingest.*` and `engine.ti.*` import.
sys.path.insert(0, str(ROOT))
# engine/, so the engine's own tests can use the shorter `ti.*`.
sys.path.insert(0, str(ROOT / "engine"))
