"""HTTP-обёртка: POST /resolve {"inn": "7721581040"} -> {"domain": "dadata.ru"}.

Формат ответа ровно такой, как в задании. Подробности (уверенность, кандидаты,
доказательства) отдаются только при ?trace=1 — это диагностика, а не контракт.

Запуск: uvicorn inn2domain.api:app --port 8000
"""
from __future__ import annotations

from fastapi import FastAPI, Query
from pydantic import BaseModel, Field

from .pipeline import Pipeline

app = FastAPI(title="inn2domain", version="0.1.0")
_pipeline = Pipeline()


class ResolveRequest(BaseModel):
    inn: str = Field(..., examples=["7721581040"])


@app.post("/resolve")
def resolve(request: ResolveRequest, trace: bool = Query(False)) -> dict:
    result = _pipeline.run(request.inn)
    if trace:
        return result.model_dump()
    return result.answer()


@app.get("/health")
def health() -> dict:
    settings = _pipeline.settings
    return {
        "status": "ok",
        "search_provider": settings.search_provider,
        "search_configured": settings.has_search,
        "llm_configured": settings.has_llm,
        "card_source_configured": bool(settings.dadata_token),
    }
