# main.py
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import List, Optional
from llm_core import get_response, get_current_stage, get_history
from schemas import FactCheckResponse
from pathlib import Path
import asyncio
import json
import os
import time
import uuid

BASE_DIR = Path(__file__).resolve().parent

app = FastAPI()

# Origini permise: implicit doar local; suprascriere prin variabila de mediu
# SNACTS_ALLOWED_ORIGINS="https://exemplu.ro,https://alt-domeniu.ro"
_default_origins = "http://localhost:8000,http://127.0.0.1:8000"
ALLOWED_ORIGINS = [
    o.strip() for o in os.getenv("SNACTS_ALLOWED_ORIGINS", _default_origins).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS,
    allow_credentials=False,  # combinația "*" + credentials era invalidă/riscantă
    allow_methods=["*"],
    allow_headers=["*"],
)


class Message(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    messages: List[Message]
    stream: Optional[bool] = False


# ─────────────────────────────────────────────
# Health check
# ─────────────────────────────────────────────
@app.get("/health")
async def health_check():
    return {"status": "ok", "language": "ro"}


@app.get("/")
async def serve_frontend():
    return FileResponse(BASE_DIR / "static" / "index.html")


# ─────────────────────────────────────────────
# Helper: rulează get_response pe thread pool
# (evită blocarea event loop-ului FastAPI)
# ─────────────────────────────────────────────
async def _run_fact_check(messages: list) -> FactCheckResponse:
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, get_response, messages, "ro")


# ─────────────────────────────────────────────
# Endpoint principal /chat (română)
# ─────────────────────────────────────────────
@app.post("/chat", response_model=FactCheckResponse)
async def chat(request: ChatRequest) -> FactCheckResponse:
    try:
        messages = [m.model_dump() for m in request.messages]
        return await _run_fact_check(messages)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Eroare internă: {e}")


@app.post("/ro/chat")
async def chat_ro(request: ChatRequest):
    """Endpoint explicit român (alias pentru /chat)."""
    return await chat(request)


# ─────────────────────────────────────────────
# /chat/stream — SSE cu progres real + rezultat structurat
# Evenimente: {"type":"progress","elapsed":N} la fiecare 2s,
# apoi {"type":"result","data":{FactCheckResponse}} sau {"type":"error",...}
# ─────────────────────────────────────────────
@app.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    messages = [m.model_dump() for m in request.messages]

    async def event_gen():
        loop = asyncio.get_event_loop()
        fut = loop.run_in_executor(None, get_response, messages, "ro")
        start = time.time()
        while True:
            try:
                # shield: timeout-ul nu anulează verificarea în curs
                result = await asyncio.wait_for(asyncio.shield(fut), timeout=2.0)
                break
            except asyncio.TimeoutError:
                # G2: include etapa reală a pipeline-ului, nu doar timpul scurs
                payload = {"type": "progress", "elapsed": round(time.time() - start),
                           **get_current_stage()}
                yield f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"
            except ValueError as e:
                yield f"data: {json.dumps({'type': 'error', 'status': 422, 'message': str(e)})}\n\n"
                return
            except Exception as e:
                yield f"data: {json.dumps({'type': 'error', 'status': 500, 'message': f'Eroare internă: {e}'})}\n\n"
                return
        yield f"data: {json.dumps({'type': 'result', 'data': result.model_dump()}, ensure_ascii=False)}\n\n"
        yield "data: [DONE]\n\n"

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


# ─────────────────────────────────────────────
# Istoric verificări (G4)
# ─────────────────────────────────────────────
@app.get("/history")
async def history(limit: int = 20):
    """Ultimele N verificări (claim, verdict, scor, timestamp)."""
    return {"history": get_history(limit)}


# ─────────────────────────────────────────────
# Models listing
# ─────────────────────────────────────────────
@app.get("/v1/models")
async def list_models():
    return {
        "object": "list",
        "data": [
            {
                "id": "infact-ro",
                "object": "model",
                "created": int(time.time()),
                "owned_by": "local",
                "description": "Pipeline de fact-checking în limba română"
            }
        ]
    }


# ─────────────────────────────────────────────
# Streaming generator (optimizat pe fraze, nu cuvinte)
# ─────────────────────────────────────────────
async def stream_response(response_text: str, model: str = "infact-ro"):
    chat_id = f"chatcmpl-{uuid.uuid4().hex[:8]}"
    created = int(time.time())

    # Trimite un rol-chunk inițial (necesar pentru Open WebUI)
    role_chunk = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [
            {
                "index": 0,
                "delta": {"role": "assistant", "content": ""},
                "finish_reason": None,
            }
        ],
    }
    yield f"data: {json.dumps(role_chunk)}\n\n"

    # Împarte textul cuvânt cu cuvânt pentru streaming autentic
    # Păstrează newline-urile ca token-uri separate
    tokens = []
    for line in response_text.split("\n"):
        words = line.split(" ")
        for j, word in enumerate(words):
            tokens.append(word + (" " if j < len(words) - 1 else ""))
        tokens.append("\n")
    # Elimină ultimul newline în plus
    if tokens and tokens[-1] == "\n":
        tokens.pop()

    for token in tokens:
        if not token:
            continue
        chunk = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {"content": token},
                    "finish_reason": None,
                }
            ],
        }
        yield f"data: {json.dumps(chunk)}\n\n"
        await asyncio.sleep(0.02)  # 20ms per token → ritm natural de citire

    final_chunk = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model,
        "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}],
    }
    yield f"data: {json.dumps(final_chunk)}\n\n"
    yield "data: [DONE]\n\n"


# ─────────────────────────────────────────────
# OpenAI-compatible /v1/chat/completions
# ─────────────────────────────────────────────
@app.post("/v1/chat/completions")
async def openai_chat(request: ChatRequest):
    try:
        messages = [m.model_dump() for m in request.messages]
        fc_response = await _run_fact_check(messages)

        # Construiește content text din FactCheckResponse pentru streaming/OpenAI compat
        # Secțiunea surselor ca tabel markdown
        source_rows = []
        for i, s in enumerate(fc_response.sources, 1):
            link_text = s.title or s.domain or s.url
            link = f"[{link_text}]({s.url})"
            tier_cell = f"`{s.tier}`" if s.tier else ""
            score_cell = f"{s.trust_score:.0f}/100" if s.trust_score is not None else "—"
            source_rows.append(f"| {i} | {link} | {tier_cell} | {score_cell} |")

        sources_table = ""
        if source_rows:
            sources_table = (
                f"\n\n### Surse utilizate ({len(fc_response.sources)})\n\n"
                "| # | Sursă | Credibilitate | Scor |\n"
                "|---|-------|---------------|------|\n"
                + "\n".join(source_rows)
            )

        # Detalii suplimentare pentru fiecare sursă (snippet + motiv clasificare)
        source_details = []
        for i, s in enumerate(fc_response.sources, 1):
            parts = []
            if s.snippet:
                parts.append(f"  *{s.snippet[:200]}*")
            if s.reason:
                parts.append(f"  Clasificare: {s.reason}")
            if parts:
                link_text = s.title or s.domain or s.url
                source_details.append(f"**{i}. {link_text}**\n" + "\n".join(parts))

        details_section = ""
        if source_details:
            details_section = "\n\n---\n\n#### Detalii surse\n\n" + "\n\n".join(source_details)

        # Scor global credibilitate
        truth = fc_response.truth_score
        truth_section = ""
        if truth:
            score_str = f"{truth.score:.1f}/100" if truth.score is not None else "N/A"
            truth_section = (
                f"\n\n---\n\n> **Scor credibilitate surse:** {score_str} — {truth.label} "
                f"(încredere: {truth.confidence}, surse analizate: {truth.source_count})"
            )
            if truth.warning:
                truth_section += f"\n>\n> {truth.warning}"

        response_text = (
            f"**Afirmație:** {fc_response.claim}\n\n"
            f"**Verdict:** {fc_response.verdict}\n\n"
            f"**Justificare:** {fc_response.justification}"
            + sources_table
            + details_section
            + truth_section
        )

        if request.stream:
            return StreamingResponse(
                stream_response(response_text),
                media_type="text/event-stream",
                headers={
                    "Cache-Control": "no-cache",
                    "X-Accel-Buffering": "no",
                    "Connection": "keep-alive",
                },
            )

        return {
            "id": f"chatcmpl-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": "infact-ro",
            "choices": [
                {
                    "index": 0,
                    "message": {"role": "assistant", "content": response_text},
                    "finish_reason": "stop",
                }
            ],
            "fact_check": fc_response.model_dump(),
        }
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Eroare internă: {e}")


app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")
