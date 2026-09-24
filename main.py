"""AURA-3 backend — AI startup evaluation engine and FinScope advisory agents.

Run locally:   .venv/bin/python main.py        (http://localhost:8010, docs at /docs)
"""

import asyncio
import io
import logging
import os
import threading
import uuid
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any, Dict, List, Optional

import httpx
import socketio
import uvicorn
from fastapi import BackgroundTasks, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from pydantic import BaseModel, Field, HttpUrl

from aura import store, vector_store
from aura.config import (
    CHAT_MODEL, CORS_ORIGINS, DOCLING_ENABLED, EMBEDDING_MODEL, MCA_API_KEY, PORT, RAPIDAPI_KEY,
)
from aura.documents import chunk_text, extract_text, warm_up_docling
from aura.evaluation import collection_name, document_context, run_evaluation, to_frontend
from aura.guardrails import BLOCKED_MESSAGE, is_blocked
from aura.llm import get_llm
from aura.mca import consistency_flags, is_valid_cin, normalise_cin, run_verification
from aura.reports import build_pdf_report
from aura.store import analysis_results, startups_db
from finscope_agents import fetch_stock_news, run_finscope_chat, store_session_document

# ─── Logging + Socket.IO log streaming ────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
for _noisy in ("httpx", "httpx2", "primp", "openai", "docling", "rapidocr"):
    logging.getLogger(_noisy).setLevel(logging.WARNING)
logger = logging.getLogger("aura.api")

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins="*")
socket_loop: Optional[asyncio.AbstractEventLoop] = None


class SocketIOLogHandler(logging.Handler):
    """Streams the agents' progress logs to the UI over the 'log_stream' channel."""

    def emit(self, record: logging.LogRecord) -> None:
        if not record.name.startswith("aura") or record.name == "aura.api":
            return
        try:
            if socket_loop and socket_loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    sio.emit("log_stream", {"message": self.format(record)}), socket_loop
                )
        except Exception:
            pass


_socket_handler = SocketIOLogHandler()
_socket_handler.setFormatter(logging.Formatter("%(message)s"))
logging.getLogger().addHandler(_socket_handler)

_docling_status = "disabled" if not DOCLING_ENABLED else "loading"


def _warm_docling() -> None:
    global _docling_status
    error = warm_up_docling()
    _docling_status = "ready" if error is None else "unavailable (using pypdf/pdfplumber)"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global socket_loop
    socket_loop = asyncio.get_running_loop()
    store.load()
    if DOCLING_ENABLED:
        threading.Thread(target=_warm_docling, daemon=True).start()
    logger.info(f"AURA-3 backend ready — model {CHAT_MODEL}, embeddings {EMBEDDING_MODEL}")
    yield
    socket_loop = None


api = FastAPI(
    title="AURA-3 — AI Startup Evaluation Platform",
    description=(
        "Multi-agent startup due diligence (LangGraph), MCA compliance checks, document RAG, "
        "investor PDF reports and the FinScope advisory chatbot."
    ),
    version="3.0.0",
    lifespan=lifespan,
)
api.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials="*" not in CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _now() -> str:
    return datetime.utcnow().isoformat() + "Z"


def _get_startup(startup_id: str) -> Dict[str, Any]:
    record = startups_db.get(startup_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Startup '{startup_id}' not found")
    return record


# ─── Models ───────────────────────────────────────────────────────────────────

class StartupCreate(BaseModel):
    name:             str           = Field(..., min_length=1, description="Startup name")
    domain:           Optional[str] = Field(None, description="Industry / domain")
    description:      Optional[str] = Field(None, description="Product or idea description")
    team:             Optional[str] = Field(None, description="Team members and experience")
    extras:           Optional[str] = Field(None, description="Anything else (traction, revenue, ...)")
    cin:              Optional[str] = Field(None, description="Company Identification Number (India)")
    stage:            Optional[str] = None
    funding_required: Optional[str] = None
    founder_address:  Optional[str] = Field(None, description="Founder wallet address")
    # Legacy field names accepted from older frontends
    startupId:        Optional[str] = None
    idea:             Optional[str] = None
    fundingRequired:  Optional[str] = None
    teamSize:         Optional[int] = None


class StartupUpdate(BaseModel):
    name:             Optional[str] = None
    domain:           Optional[str] = None
    description:      Optional[str] = None
    team:             Optional[str] = None
    extras:           Optional[str] = None
    stage:            Optional[str] = None
    funding_required: Optional[str] = None


class StartupResponse(BaseModel):
    startup_id:           str
    name:                 str
    domain:               str
    description:          str
    team:                 str
    extras:               Optional[str] = None
    stage:                Optional[str] = None
    funding_required:     Optional[str] = None
    founder_address:      Optional[str] = None
    created_at:           str
    updated_at:           str
    document_collections: List[str] = []
    documents:            List[Dict[str, Any]] = []
    verification:         Dict[str, Any] = {}
    compliance_flags:     List[str] = []
    analysis_status:      str = "not_started"
    score:                Optional[float] = None
    recommendation_label: Optional[str] = None


def _startup_response(record: Dict[str, Any]) -> StartupResponse:
    analysis = analysis_results.get(record["startup_id"]) or {}
    result = analysis.get("result") or {}
    return StartupResponse(
        **{k: record.get(k) for k in (
            "startup_id", "name", "domain", "description", "team", "extras", "stage",
            "funding_required", "founder_address", "created_at", "updated_at",
        )},
        document_collections=record.get("document_collections", []),
        documents=record.get("documents", []),
        verification=record.get("verification", {}),
        compliance_flags=consistency_flags(record),
        analysis_status=analysis.get("status", "not_started"),
        score=result.get("overall_score"),
        recommendation_label=result.get("recommendation_label"),
    )


class DocumentUploadRequest(BaseModel):
    document_url: HttpUrl = Field(..., description="Public URL of a PDF or DOCX")


class ChatTurn(BaseModel):
    role: str
    content: str


class ChatMessage(BaseModel):
    question: str = Field(..., description="Investor question about the startup")
    history: List[ChatTurn] = Field(default_factory=list, description="Earlier turns in this chat")


class ChatResponse(BaseModel):
    answer:       str
    startup_name: str
    sources:      List[str] = []


class FinScopeChatRequest(BaseModel):
    question: str
    user_profile: str = "beginner"
    session_id: str = ""


class MCAVerificationRequest(BaseModel):
    cin: str = Field(..., description="Company Identification Number (CIN)")


# ─── Startup registry ─────────────────────────────────────────────────────────

@api.post("/startups", status_code=201, response_model=StartupResponse, summary="Register a startup")
async def create_startup(body: StartupCreate):
    startup_id = body.startupId or str(uuid.uuid4())
    now = _now()
    record: Dict[str, Any] = {
        "startup_id": startup_id,
        "id": startup_id,
        "name": body.name.strip(),
        "domain": (body.domain or "General").strip(),
        "description": (body.description or body.idea or "N/A").strip(),
        "team": (body.team or "Not specified").strip(),
        "extras": body.extras or (f"Team size: {body.teamSize}" if body.teamSize else None),
        "stage": body.stage,
        "funding_required": body.funding_required or body.fundingRequired,
        "founder_address": (body.founder_address or "").lower() or None,
        "created_at": now,
        "updated_at": now,
        "document_collections": [],
        "documents": [],
        "verification": {"cin": None, "mca_verified": False, "company_status": None,
                         "company_name": None, "directors": [], "last_checked": None},
    }
    if body.cin and body.cin.strip():
        await asyncio.to_thread(run_verification, record, body.cin)
    startups_db[startup_id] = record
    store.save()
    logger.info(f"Startup registered: {record['name']} ({startup_id})")
    return _startup_response(record)


@api.post("/api/startups/register", response_model=StartupResponse, include_in_schema=False)
async def register_startup_alias(body: StartupCreate):
    return await create_startup(body)


@api.put("/startups/{startup_id}", response_model=StartupResponse, summary="Update a startup profile")
async def update_startup(startup_id: str, body: StartupUpdate):
    record = _get_startup(startup_id)
    record.update(body.model_dump(exclude_none=True))
    record["updated_at"] = _now()
    store.save()
    return _startup_response(record)


@api.get("/startups", response_model=List[StartupResponse], summary="List startups (newest first)")
async def list_startups():
    records = sorted(startups_db.values(), key=lambda r: r.get("created_at", ""), reverse=True)
    return [_startup_response(r) for r in records]


@api.get("/startups/{startup_id}", response_model=StartupResponse, summary="Get a startup")
async def get_startup(startup_id: str):
    return _startup_response(_get_startup(startup_id))


# ─── Documents (Docling → chunks → embeddings → vector index) ─────────────────

async def _ingest_document(record: Dict[str, Any], file_bytes: bytes, filename: str) -> Dict[str, Any]:
    suffix = os.path.splitext(filename)[1].lower() or ".pdf"
    try:
        text = await extract_text(file_bytes, suffix)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    chunks = chunk_text(text, source=filename)
    record["extracted_text"] = (record.get("extracted_text", "") + "\n\n" + text).strip()[:200000]
    indexed = 0
    collection = collection_name(record["startup_id"])
    try:
        indexed = await asyncio.to_thread(
            vector_store.add_texts, collection, [c["text"] for c in chunks], [c["metadata"] for c in chunks]
        )
        if collection not in record["document_collections"]:
            record["document_collections"].append(collection)
    except Exception as e:
        logger.warning(f"Embedding failed for {filename}; the analyst will use raw text instead: {e}")

    record.setdefault("documents", []).append(
        {"name": filename, "characters": len(text), "chunks": len(chunks), "indexed": indexed, "uploaded_at": _now()}
    )
    record["updated_at"] = _now()
    store.save()
    return {"status": "success", "startup_id": record["startup_id"], "chunks": len(chunks), "indexed": indexed}


@api.post("/api/startups/{startup_id}/documents/upload", summary="Upload a pitch deck (multipart)")
async def upload_document_form(startup_id: str, documents: UploadFile = File(...)):
    record = _get_startup(startup_id)
    return await _ingest_document(record, await documents.read(), documents.filename or "pitch_deck.pdf")


@api.post("/startups/{startup_id}/documents", summary="Ingest a document from a URL")
async def upload_startup_document(startup_id: str, body: DocumentUploadRequest):
    record = _get_startup(startup_id)
    url = str(body.document_url)
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            resp = await client.get(url)
            resp.raise_for_status()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not download document: {e}")
    return await _ingest_document(record, resp.content, url.rsplit("/", 1)[-1] or "document.pdf")


# ─── Evaluation pipeline ──────────────────────────────────────────────────────

def _analysis_payload(startup_id: str) -> Dict[str, Any]:
    entry = analysis_results.get(startup_id)
    if not entry:
        return {"status": "not_started"}
    payload = {k: entry.get(k) for k in ("status", "stage", "error", "started_at", "completed_at")}
    if entry.get("status") == "complete" and entry.get("result"):
        payload["analysis"] = to_frontend(entry["result"])
    return payload


def _evaluate_blocking(startup_id: str) -> Dict[str, Any]:
    record = startups_db[startup_id]

    def progress(stage: str) -> None:
        analysis_results[startup_id]["stage"] = stage

    result = run_evaluation(record, progress)
    analysis_results[startup_id].update(
        {"status": "complete", "stage": "Report ready", "result": result, "completed_at": _now(), "error": None}
    )
    store.save()
    return result


async def process_analysis_task(startup_id: str) -> None:
    try:
        await asyncio.to_thread(_evaluate_blocking, startup_id)
    except Exception as e:
        logger.exception(f"Analysis failed for {startup_id}")
        analysis_results[startup_id].update({"status": "failed", "error": str(e), "stage": "Failed"})
        store.save()


def _start_analysis(startup_id: str) -> None:
    analysis_results[startup_id] = {
        "status": "processing", "stage": "Queued", "result": None, "error": None, "started_at": _now(),
    }
    store.save()


@api.post("/api/startups/{startup_id}/analyze", summary="Start the multi-agent evaluation (background)")
async def trigger_full_analysis(startup_id: str, background_tasks: BackgroundTasks):
    _get_startup(startup_id)
    if (analysis_results.get(startup_id) or {}).get("status") == "processing":
        return {"status": "analysis_running", "id": startup_id}
    _start_analysis(startup_id)
    background_tasks.add_task(process_analysis_task, startup_id)
    return {"status": "analysis_started", "id": startup_id}


@api.get("/api/startups/{startup_id}/report/status", summary="Poll evaluation status")
async def get_analysis_status(startup_id: str):
    return _analysis_payload(startup_id)


@api.get("/api/startups/{startup_id}/analysis", summary="Full evaluation with profile and compliance")
async def get_full_analysis(startup_id: str):
    record = _get_startup(startup_id)
    return {"startup": _startup_response(record), **_analysis_payload(startup_id)}


async def _pdf_response(startup_id: str) -> StreamingResponse:
    record = _get_startup(startup_id)
    entry = analysis_results.get(startup_id) or {}
    if entry.get("status") == "processing":
        raise HTTPException(status_code=409, detail="Evaluation still running — try again when it completes.")
    if entry.get("status") != "complete":
        _start_analysis(startup_id)
        try:
            await asyncio.to_thread(_evaluate_blocking, startup_id)
        except Exception as e:
            analysis_results[startup_id].update({"status": "failed", "error": str(e)})
            store.save()
            raise HTTPException(status_code=500, detail=f"AI analysis pipeline failed: {e}")
    try:
        pdf = await asyncio.to_thread(build_pdf_report, record, analysis_results[startup_id]["result"])
    except Exception as e:
        logger.exception("PDF generation failed")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")
    filename = f"AURA3_{record['name'].replace(' ', '_')}_{startup_id[:8]}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf), media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@api.post("/reports/{startup_id}", summary="Investor PDF report (runs the evaluation if needed)")
async def generate_report(startup_id: str):
    return await _pdf_response(startup_id)


@api.get("/reports/{startup_id}", include_in_schema=False)
async def get_report(startup_id: str):
    return await _pdf_response(startup_id)


# ─── MCA compliance ───────────────────────────────────────────────────────────

@api.post("/startups/{startup_id}/verify/mca", summary="Verify a startup's CIN against the MCA registry")
async def verify_startup_mca(startup_id: str, body: MCAVerificationRequest):
    record = _get_startup(startup_id)
    cin = normalise_cin(body.cin)
    if not is_valid_cin(cin):
        raise HTTPException(
            status_code=422,
            detail="Invalid CIN format. Expected L/U + 5 digits + 2 letters + 4 digits + 3 letters + 6 digits "
                   "(e.g. U72900KA2021PTC150123).",
        )
    verification = await asyncio.to_thread(run_verification, record, cin)
    record["updated_at"] = _now()
    store.save()
    flags = consistency_flags(record)
    return {
        "startup_id": startup_id, **verification, "flags": flags,
        "message": "Verification successful." if not flags else f"Verified with warnings: {', '.join(flags)}",
    }


@api.get("/startups/{startup_id}/verify/mca", summary="Stored MCA verification status")
async def get_mca_status(startup_id: str):
    record = _get_startup(startup_id)
    return {"startup_id": startup_id, **(record.get("verification") or {}), "flags": consistency_flags(record)}


# ─── Investor Q&A chatbot (RAG over the startup's documents + evaluation) ─────

async def _run_chatbot(record: Dict[str, Any], msg: ChatMessage) -> ChatResponse:
    question = msg.question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    if is_blocked(question):
        return ChatResponse(answer=BLOCKED_MESSAGE, startup_name=record["name"])

    docs = await asyncio.to_thread(document_context, record, question, 6)
    result = (analysis_results.get(record["startup_id"]) or {}).get("result")
    evaluation = "No AI evaluation has been run yet."
    if result:
        s = result["sections"]
        evaluation = (
            f"Overall score {result['overall_score']}/10, recommendation {result['recommendation_label']}. "
            f"Category scores: {result['category_scores']}. Market sizing: TAM ${result['market_sizing']['tam_usd_b']}B, "
            f"SAM ${result['market_sizing']['sam_usd_b']}B, SOM ${result['market_sizing']['som_usd_b']}B, "
            f"CAGR {result['market_sizing']['cagr_pct']}%.\n\nExecutive summary: {s['executive_summary']}\n\n"
            f"Competition: {s['competitive_landscape'][:1500]}\n\nRisks: {s['risks_challenges'][:1500]}"
        )
    v = record.get("verification") or {}
    system = f"""You are AURA-3's Venture Analyst, answering an investor's questions about one startup.

STARTUP
Name: {record['name']} | Domain: {record['domain']} | Stage: {record.get('stage') or 'N/A'}
Description: {record['description']}
Team: {record['team']}
MCA: {'verified, status ' + str(v.get('company_status')) if v.get('mca_verified') else 'not verified'}; flags: {', '.join(consistency_flags(record)) or 'none'}

AI EVALUATION
{evaluation}

RELEVANT PASSAGES FROM THE STARTUP'S DOCUMENTS
{docs}

Answer only from the information above; say plainly when something is not covered. Be specific,
quote numbers, and keep answers to 2-3 short paragraphs or a compact list."""
    history = [
        HumanMessage(content=t.content) if t.role == "user" else AIMessage(content=t.content)
        for t in msg.history[-8:]
    ]
    try:
        response = await get_llm(temperature=0.2, max_tokens=1200).ainvoke(
            [SystemMessage(content=system)] + history + [HumanMessage(content=question)]
        )
    except Exception as e:
        logger.exception("Investor chatbot failed")
        raise HTTPException(status_code=502, detail=f"Chatbot error: {e}")
    sources = [d.get("name") for d in record.get("documents", [])]
    return ChatResponse(answer=str(response.content).strip(), startup_name=record["name"], sources=sources)


@api.post("/chat/{startup_id}", response_model=ChatResponse, summary="Investor chatbot (by startup ID)")
async def investor_chatbot(startup_id: str, msg: ChatMessage):
    return await _run_chatbot(_get_startup(startup_id), msg)


@api.post("/chat/by-name/{startup_name}", response_model=ChatResponse, summary="Investor chatbot (by name)")
async def investor_chatbot_by_name(startup_name: str, msg: ChatMessage):
    matches = [r for r in startups_db.values() if r["name"].lower() == startup_name.lower()]
    if not matches:
        raise HTTPException(status_code=404, detail=f"No startup named '{startup_name}'")
    return await _run_chatbot(max(matches, key=lambda r: r["created_at"]), msg)


# ─── FinScope multi-agent chat ────────────────────────────────────────────────

@api.post("/finscope/chat", summary="FinScope multi-agent chat")
async def finscope_chat(body: FinScopeChatRequest):
    if is_blocked(body.question):
        return {"answer": BLOCKED_MESSAGE, "agent_used": "Guardrails", "intent": "blocked"}
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")
    try:
        result = await run_finscope_chat(
            question=body.question.strip(),
            session_id=body.session_id or "anonymous",
            user_profile=body.user_profile,
        )
    except Exception as e:
        logger.exception("FinScope chat failed")
        raise HTTPException(status_code=502, detail=f"FinScope chat failed: {e}")
    return {"answer": result["answer"], "agent_used": result["agent"], "intent": result["intent"]}


@api.post("/finscope/analyze-document", summary="Upload a document to a FinScope chat and analyse it")
async def finscope_analyze_document(
    document: UploadFile = File(...),
    session_id: str = Form(""),
    user_profile: str = Form("beginner"),
    question: str = Form(""),
):
    filename = document.filename or "document.pdf"
    session_id = session_id or f"fs_{uuid.uuid4().hex[:10]}"
    await sio.emit("log_stream", {"message": f"FinScope ▸ Reading '{filename}'"})
    try:
        text = await extract_text(await document.read(), os.path.splitext(filename)[1].lower() or ".pdf")
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    await asyncio.to_thread(store_session_document, session_id, filename, text, chunk_text(text, filename))
    try:
        result = await run_finscope_chat(
            question=question.strip() or f"Analyze this document: {filename}",
            session_id=session_id,
            user_profile=user_profile,
            analyze_document=True,
        )
    except Exception as e:
        logger.exception("FinScope document analysis failed")
        raise HTTPException(status_code=502, detail=f"Document analysis failed: {e}")
    return {"analysis": result["answer"], "agent_used": result["agent"], "intent": result["intent"],
            "session_id": session_id}


@api.get("/finscope/sessions/{session_id}", summary="FinScope session history")
async def finscope_session(session_id: str):
    session = store.finscope_sessions.get(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")
    return {"session_id": session_id, "document_name": session.get("document_name"), "history": session["history"]}


@api.get("/api/finance-news/headlines", summary="Live market headlines")
async def finance_news_headlines(symbol: str = "stock market", limit: int = 10):
    try:
        headlines = await asyncio.to_thread(fetch_stock_news, symbol, max(1, min(limit, 20)))
        return {"headlines": headlines}
    except Exception as e:
        logger.warning(f"Headlines fetch failed: {e}")
        return {"headlines": []}


# ─── Health ───────────────────────────────────────────────────────────────────

@api.get("/health", summary="Health check")
async def health_check():
    return {
        "status": "healthy",
        "service": "AURA-3 AI Startup Evaluation Platform",
        "version": "3.0.0",
        "llm_model": CHAT_MODEL,
        "embedding_model": EMBEDDING_MODEL,
        "vector_store": "in-process cosine index (persisted to disk)",
        "docling": _docling_status,
        "startups": len(startups_db),
        "analyses_complete": sum(1 for a in analysis_results.values() if a.get("status") == "complete"),
        "mca_provider": "configured" if MCA_API_KEY else "sandbox",
        "news_provider": "rapidapi" if RAPIDAPI_KEY else "duckduckgo",
    }


# Serve Socket.IO (/socket.io) alongside the REST API.
app = socketio.ASGIApp(sio, api)


if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=PORT, reload=False)
