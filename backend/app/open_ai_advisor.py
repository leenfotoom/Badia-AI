"""Open, auditable environmental action advisor with optional Gemini wording.

The deterministic recommendation is always derived from the supplied risk category;
a language model never changes the measured risk or invents observations.
"""
from __future__ import annotations

import json
import os
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/ai", tags=["open-source-ai"])

ACTIONS = {
    "Low": ("Monitor periodically", "راقب المنطقة بشكل دوري"),
    "Moderate": ("Review source freshness and check conditions locally", "راجع حداثة البيانات وتحقق من الظروف ميدانيًا"),
    "High": ("Prioritize field verification and review water availability", "أعطِ الأولوية للتحقق الميداني ومراجعة توفر المياه"),
    "N/A": ("Acquire valid observations before making a decision", "احصل على بيانات صالحة قبل اتخاذ قرار"),
}

class AdviceRequest(BaseModel):
    risk_level: str = Field(description="Low, Moderate, High, or N/A")
    location: str = Field(default="Jordan", max_length=100)
    horizon_days: int = Field(default=16, ge=0, le=32)
    language: str = Field(default="ar", pattern="^(ar|en)$")
    use_gemini: bool = False

@router.post("/advice", summary="Transparent open-source decision support, optional Gemini explanation")
def advice(payload: AdviceRequest) -> dict:
    level = next((key for key in ACTIONS if key.casefold() == payload.risk_level.strip().casefold()), None)
    if level is None:
        raise HTTPException(422, "risk_level must be Low, Moderate, High or N/A")
    action = ACTIONS[level][1 if payload.language == "ar" else 0]
    result = {
        "risk_level": level, "location": payload.location, "horizon_days": payload.horizon_days,
        "action": action, "provider": "open-source-rules", "gemini_used": False,
        "disclaimer": "Historical relative index; not a live observation, probability, diagnosis or automated prescription.",
    }
    if not payload.use_gemini:
        return result
    key = os.getenv("GEMINI_API_KEY", "")
    if not key:
        return {**result, "note": "Gemini unavailable: GEMINI_API_KEY not configured."}
    model = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    if not model.replace("-", "").replace(".", "").replace("_", "").isalnum():
        return {**result, "note": "Invalid Gemini model configuration."}
    endpoint = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    prompt = (
        "Translate and explain this *predefined* environmental follow-up action in 1-2 "
        "short sentences. Do not change risk, invent data, claim current observations, "
        "or issue unverified irrigation instructions. Language: " + payload.language +
        ". Area: " + payload.location + ". Saved outlook days: " + str(payload.horizon_days) +
        ". Category: " + level + ". Approved action: " + action
    )
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}],
                       "generationConfig": {"temperature": 0.2, "maxOutputTokens": 180}}).encode()
    request = Request(endpoint, body, headers={
        "Content-Type": "application/json", "x-goog-api-key": key}, method="POST")
    try:
        with urlopen(request, timeout=8) as response:
            data = json.load(response)
        explanation = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return {**result, "gemini_used": True, "provider": "gemini-optional",
                "explanation": explanation[:1200]}
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError, IndexError, TypeError):
        return {**result, "note": "Gemini request failed; transparent local rule was used."}
