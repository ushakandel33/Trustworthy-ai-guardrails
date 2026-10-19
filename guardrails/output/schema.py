"""Schema validation of the model's response.

The model must return JSON matching AssistantResponse. Pydantic checks field
presence, types and value ranges; extra checks make sure the cited sources are
documents that were actually given to the model.

Action on failure: retry the model once with a stricter reminder. If the
second attempt is still invalid, return a safe fallback message.

Limitations: a response can be perfectly valid JSON and still be wrong; schema
validation only says the shape is right, not that the content is true.
"""

from __future__ import annotations

import json
import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from guardrails.models import GuardrailResult


class AssistantResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    answer: str = Field(min_length=1, max_length=1200)
    sources: list[str] = Field(max_length=5)
    confidence: float = Field(ge=0.0, le=1.0)
    status: Literal["answered", "not_found"]

    @field_validator("sources")
    @classmethod
    def _source_ids(cls, value: list[str]) -> list[str]:
        for s in value:
            if not re.fullmatch(r"KB-\d{3}", s):
                raise ValueError(f"invalid source id {s!r}")
        return value


def _extract_json(raw: str) -> str:
    """Accept a bare JSON object or one wrapped in a ```json fence."""
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", raw, re.DOTALL)
    return fenced.group(1) if fenced else raw.strip()


def validate_schema(raw: str, allowed_sources: set[str]) -> tuple[GuardrailResult, AssistantResponse | None]:
    errors: list[str] = []
    parsed: AssistantResponse | None = None
    try:
        data = json.loads(_extract_json(raw))
        parsed = AssistantResponse.model_validate(data)
    except json.JSONDecodeError as exc:
        errors.append(f"not valid JSON: {exc.msg}")
    except ValidationError as exc:
        errors.extend(f"{'.'.join(map(str, e['loc'])) or 'root'}: {e['msg']}" for e in exc.errors())

    if parsed is not None:
        unknown = [s for s in parsed.sources if s not in allowed_sources]
        if unknown:
            errors.append(f"sources not in retrieved context: {unknown}")
        if parsed.status == "answered" and not parsed.sources:
            errors.append("status is 'answered' but no sources are cited")

    if errors:
        return GuardrailResult("schema", True, "retry", "; ".join(errors), {"errors": errors}), None
    return GuardrailResult("schema", False, "allow"), parsed
