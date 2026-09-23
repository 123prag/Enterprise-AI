"""Shared base schemas for tool inputs/outputs.

Every tool follows the same contract: a typed Pydantic input, a typed
Pydantic output that always includes ``success``/``error`` so callers
(the tool agent, LangGraph nodes) can branch on failure without
exceptions crossing agent boundaries.
"""

from __future__ import annotations

from pydantic import BaseModel


class ToolOutput(BaseModel):
    success: bool = True
    error: str | None = None
