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


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _restore_engine_globals():
    """Tests that point the engine at synthetic homes, or the router at a fake engine, must not leak into others."""
    from backend.app.llm import api as llm_api
    from backend.app.llm import engine as llm_engine
    source, runner = llm_engine._home_source, llm_api._runner
    yield
    llm_engine._home_source, llm_api._runner = source, runner
