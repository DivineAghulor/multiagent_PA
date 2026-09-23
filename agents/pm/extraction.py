"""LLM chain that extracts structured tasks from freeform user text."""
from __future__ import annotations

from llm.factory import get_structured_model

from .schemas import ExtractedTaskBatch

EXTRACTION_SYSTEM_PROMPT = """You extract actionable tasks from a user's freeform \
description of what they need to do. Split distinct actions into separate tasks — \
don't merge unrelated things into one. If the text mentions a project or area of \
work a task belongs to, capture it as project_hint; otherwise leave it null. Do not \
invent tasks that weren't mentioned."""


def extract_tasks(text: str) -> ExtractedTaskBatch:
    structured_model = get_structured_model(ExtractedTaskBatch)
    return structured_model.invoke(
        [
            ("system", EXTRACTION_SYSTEM_PROMPT),
            ("human", text),
        ]
    )
