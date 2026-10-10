"""Dev-only FastAPI app: the LLM routes on the team's REAL engine with the SYNTHETIC test homes
(eval/synthetic_homes.py), so the React app can be built against real response shapes without York data.

    venv/bin/uvicorn dev_app:app --app-dir tests/llm --reload --port 8000
    curl -s localhost:8000/homes
    curl -s localhost:8000/llm/explain -H 'content-type: application/json' \
         -d '{"property_id": "syn-poor-semi", "template_mode": true}'

With York data under data/processed, use backend.app.llm.engine.run_scenario directly instead.
"""

import conftest  # noqa: F401  (puts the repo root, tests/llm and eval on sys.path)
import synthetic_homes as sh
from fastapi import FastAPI

from backend.app.llm.api import configure_engine, router

app = FastAPI(title="Green Home LLM dev server (real engine, SYNTHETIC homes)")
configure_engine(sh.run)
app.include_router(router)


@app.get("/homes")
def homes() -> list[str]:
    return list(sh.HOMES)
