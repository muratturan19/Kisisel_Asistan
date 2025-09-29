"""Lightweight FastAPI stub for future expansion."""
from __future__ import annotations

from fastapi import FastAPI

from ..core.intent import Action

app = FastAPI(title="Mira Assistant API")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/actions")
def receive_action(action: Action) -> dict:
    # TODO: Integrate with command handling pipeline.
    return {"intent": action.intent, "payload": action.payload}


__all__ = ["app"]
