import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
for p in (ROOT, HERE, ROOT / "eval"):  # team convention: import backend.app.* from the repo root
    if str(p) not in sys.path:
        sys.path.insert(0, str(p))

# Tests never call a real provider or touch the shared cache, even with keys in .env.
os.environ["LLM_ENABLED"] = "0"
os.environ["LLM_CACHE"] = "0"
