"""Minimal FastAPI T2 signup example (Section 10)."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "packages" / "ishuman-verify-py"))

from lemma_ishuman_verify import VerificationContext  # noqa: E402

app = FastAPI()
SITE_ID = os.getenv("SITE_ID", "app.example.com")
REQUIRED = os.getenv("REQUIRED_ASSURANCE", "ishuman")
_CTX = VerificationContext(site_id=SITE_ID, required_assurance=REQUIRED)


class SignupBody(BaseModel):
    presentation: dict[str, Any]


@app.post("/api/signup")
def signup(body: SignupBody):
    result = _CTX.verify(body.presentation)
    if not result.ok:
        raise HTTPException(status_code=401, detail=result.reason)
    return {"success": True, "ppid": result.ppid, "assurance": result.assurance}
