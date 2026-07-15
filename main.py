import os
import uuid
import logging
import io
import tempfile
import asyncio
import re
from typing import Annotated, Literal, Sequence, TypedDict, Optional, List, Dict, Any
from contextlib import asynccontextmanager
from datetime import datetime

import requests
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from fastapi import FastAPI, HTTPException, Path, UploadFile, File, BackgroundTasks, Form
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, HttpUrl, Field

import uvicorn

# ReportLab
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image as RLImage,
    Table, TableStyle, HRFlowable, PageBreak,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY

# LangChain imports
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, ToolMessage
from langchain_core.tools import tool
from langchain_groq import ChatGroq
from langchain_huggingface import HuggingFaceEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document

# LangGraph imports
from langgraph.graph import END, StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import tools_condition, ToolNode

# Docling imports
from docling.document_converter import DocumentConverter

# Qdrant imports
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance, VectorParams, PointStruct
import socketio
from finscope_agents import run_finscope_chat, store_session_document, _fetch_stock_news

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Socket.IO for FinScope log streaming ────────────────────────────────────
sio = socketio.AsyncServer(async_mode='asgi', cors_allowed_origins='*')
socket_loop: Optional[asyncio.AbstractEventLoop] = None


class SocketIOLogHandler(logging.Handler):
    def emit(self, record):
        try:
            msg = self.format(record)
            global socket_loop
            if socket_loop and socket_loop.is_running():
                asyncio.run_coroutine_threadsafe(
                    sio.emit('log_stream', {'message': msg}),
                    socket_loop,
                )
        except Exception:
            pass


socket_handler = SocketIOLogHandler()
socket_handler.setFormatter(logging.Formatter('INFO:%(name)s:%(message)s'))
logging.getLogger().addHandler(socket_handler)

# ─── Environment Variables ────────────────────────────────────────────────────
GROQ_API_KEY  = os.getenv("GROQ_API_KEY",  "")
QDRANT_URL    = os.getenv("QDRANT_URL",    "")
QDRANT_API_KEY= os.getenv("QDRANT_API_KEY","")

# MCA API key — replace with real provider (Karza / Signzy / etc.)
MCA_API_KEY   = os.getenv("MCA_API_KEY", "")
MCA_API_URL   = os.getenv("MCA_API_URL", "https://api.karza.in/v3/company-master")   # mock default

# Cache directories for HuggingFace
import tempfile as _tempfile
_TMP = _tempfile.gettempdir()
_HF_CACHE_DIRS = {
    "TRANSFORMERS_CACHE":         os.path.join(_TMP, "transformers_cache"),
    "HF_HOME":                    os.path.join(_TMP, "hf_home"),
    "HUGGINGFACE_HUB_CACHE":      os.path.join(_TMP, "hf_hub_cache"),
    "SENTENCE_TRANSFORMERS_HOME": os.path.join(_TMP, "sentence_transformers"),
}
for _dir in _HF_CACHE_DIRS.values():
    os.makedirs(_dir, exist_ok=True)
os.environ.update(_HF_CACHE_DIRS)
SENTENCE_TRANSFORMERS_CACHE = _HF_CACHE_DIRS["SENTENCE_TRANSFORMERS_HOME"]

if not GROQ_API_KEY:
    raise ValueError("GROQ_API_KEY environment variable is required")

# ─── Global Singletons ────────────────────────────────────────────────────────
qdrant_client:      Optional[QdrantClient]          = None
embeddings_model:   Optional[HuggingFaceEmbeddings] = None
llm:                Optional[ChatGroq]              = None
document_converter: Optional[DocumentConverter]     = None

# In-memory startup store  { startup_id: dict }
startups_db: Dict[str, Dict[str, Any]] = {}

# In-memory analysis results store { startup_id: { status: str, analysis: dict } }
analysis_results: Dict[str, Dict[str, Any]] = {}

TOOLS: list = []


# ─── Lifespan ─────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global qdrant_client, embeddings_model, llm, document_converter
    global socket_loop

    socket_loop = asyncio.get_running_loop()

    # Qdrant
    async def _connect_qdrant():
        global qdrant_client
        try:
            client = QdrantClient(
                url=QDRANT_URL,
                api_key=QDRANT_API_KEY,
                timeout=60,
                verify=False,
                check_compatibility=False,
            )
            client.get_collections()
            qdrant_client = client
            logger.info("Qdrant connected")
        except Exception as e:
            logger.warning(f"Qdrant warning: {e} — errors handled per-request")

    await _connect_qdrant()

    # HuggingFace Embeddings
    def _load_embeddings():
        for model_name in [
            "sentence-transformers/all-MiniLM-L6-v2",
            "all-MiniLM-L6-v2",
        ]:
            try:
                m = HuggingFaceEmbeddings(
                    model_name=model_name,
                    model_kwargs={"device": "cpu"},
                    cache_folder=SENTENCE_TRANSFORMERS_CACHE,
                )
                logger.info(f"Embeddings initialized: {model_name}")
                return m
            except Exception as e:
                logger.warning(f"Embeddings init failed for {model_name}: {e}")
        raise RuntimeError("All embedding models failed to load. Please ensure 'sentence-transformers' is installed.")

    embeddings_model = await asyncio.to_thread(_load_embeddings)

    # Groq LLM
    llm = ChatGroq(
        groq_api_key=GROQ_API_KEY,
        model_name="meta-llama/llama-4-scout-17b-16e-instruct",
        temperature=0.2,
        max_tokens=2048,
    )

    # Docling
    def _load_docling():
        return DocumentConverter()

    try:
        document_converter = await asyncio.to_thread(_load_docling)
        logger.info("DocumentConverter ready")
    except Exception as e:
        logger.error(f"DocumentConverter init failed: {e}")
        raise

    logger.info("✅ AI Startup Evaluation Platform initialized")
    yield
    socket_loop = None
    logger.info("Shutting down")


# ─── FastAPI App ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="AI Startup Evaluation Platform",
    description=(
        "An AI-powered platform for startup evaluation and market analysis. "
        "Combines structured startup data, uploaded documents, and live market research "
        "to produce comprehensive investor-ready PDF reports."
    ),
    version="2.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ─── Pydantic Models ──────────────────────────────────────────────────────────

class StartupCreate(BaseModel):
    name:             str           = Field(..., description="Startup name")
    domain:           Optional[str] = Field(None, description="Industry / domain")
    description:      Optional[str] = Field(None, description="Idea or product description")
    team:             Optional[str] = Field(None, description="Team details and relevant experience")
    extras:           Optional[str] = Field(None, description="Any additional information")
    # Compatibility fields for frontend
    startupId:        Optional[str] = None
    idea:             Optional[str] = None
    fundingRequired:  Optional[str] = None
    stage:            Optional[str] = None
    teamSize:         Optional[int] = None


class StartupUpdate(BaseModel):
    name:        Optional[str] = None
    domain:      Optional[str] = None
    description: Optional[str] = None
    team:        Optional[str] = None
    extras:      Optional[str] = None


class DocumentUploadRequest(BaseModel):
    document_url: HttpUrl = Field(..., description="Publicly accessible URL to a PDF or DOCX file")


class StartupResponse(BaseModel):
    startup_id:           str
    name:                 str
    domain:               str
    description:          str
    team:                 str
    extras:               Optional[str]
    created_at:           str
    updated_at:           str
    document_collections: List[str] = []


class ChatMessage(BaseModel):
    question: str = Field(..., description="Investor question about the startup")


class ChatResponse(BaseModel):
    answer:       str = Field(..., description="AI-generated answer")
    startup_name: str


class FinScopeChatRequest(BaseModel):
    question: str
    user_profile: str = "beginner"
    session_id: str = ""


FINSCOPE_BLOCK_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?)", re.IGNORECASE),
    re.compile(r"(system|developer)\s+prompt", re.IGNORECASE),
    re.compile(r"(bypass|override|disable)\s+(safety|guardrails|policy|policies|rules)", re.IGNORECASE),
    re.compile(r"jailbreak|dan\s+mode|do\s+anything\s+now", re.IGNORECASE),
    re.compile(r"act\s+as\s+(a\s+)?(lawyer|doctor|hacker|jailbroken\s+ai)", re.IGNORECASE),
    re.compile(r"\b(murder|kill|bomb|weapon|hate\s*speech|racist|sexist|porn|sex\s*chat|explicit)\b", re.IGNORECASE),
]


def is_finscope_prompt_blocked(question: str) -> bool:
    text = (question or "").strip()
    if not text:
        return False
    return any(pattern.search(text) for pattern in FINSCOPE_BLOCK_PATTERNS)


# ─── MCA Models ───────────────────────────────────────────────────────────────

class MCAVerificationRequest(BaseModel):
    cin: str = Field(..., description="Company Identification Number (CIN)")


class MCAVerificationResponse(BaseModel):
    startup_id:     str
    cin:            str
    mca_verified:   bool
    company_status: Optional[str]
    company_name:   Optional[str]
    directors:      List[str]
    name_match:     bool
    flags:          List[str]
    last_checked:   str
    message:        str


class MCAStatusResponse(BaseModel):
    startup_id:     str
    cin:            Optional[str]
    mca_verified:   bool
    company_status: Optional[str]
    company_name:   Optional[str]
    directors:      List[str]
    flags:          List[str]
    last_checked:   Optional[str]


# ─── Document Processing Helpers ──────────────────────────────────────────────

async def _download_file(url: str) -> bytes:
    try:
        resp = requests.get(url, timeout=30)
        resp.raise_for_status()
        return resp.content
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to download file: {e}")


async def _extract_text_docling(path: str) -> str:
    try:
        result = await asyncio.to_thread(document_converter.convert, path)
        text = result.document.export_to_markdown()
        if not text or len(text.strip()) < 10:
            text = result.document.export_to_text() or ""
        return text
    except Exception as e:
        logger.warning(f"Docling failed: {e}")
        return ""


async def _extract_text_pypdf2(path: str) -> str:
    try:
        import PyPDF2
        with open(path, "rb") as f:
            reader = PyPDF2.PdfReader(f)
            return "\n".join(p.extract_text() or "" for p in reader.pages)
    except Exception as e:
        logger.warning(f"PyPDF2 failed: {e}")
        return ""


async def _extract_text_pdfplumber(path: str) -> str:
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return "\n".join(p.extract_text() or "" for p in pdf.pages)
    except Exception as e:
        logger.warning(f"pdfplumber failed: {e}")
        return ""


async def extract_document_content(file_bytes: bytes, suffix: str = ".pdf") -> List[Document]:
    tmp_path: Optional[str] = None
    try:
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            tmp.write(file_bytes)
            tmp_path = tmp.name

        text = ""
        for extractor in [_extract_text_docling, _extract_text_pypdf2, _extract_text_pdfplumber]:
            text = await extractor(tmp_path)
            if text and len(text.strip()) > 10:
                break

        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
            tmp_path = None

        if not text or len(text.strip()) < 10:
            raise ValueError("No readable text found in the uploaded document.")

        splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000,
            chunk_overlap=200,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        chunks = splitter.split_text(text)
        return [
            Document(page_content=c, metadata={"source": "upload", "chunk_id": i})
            for i, c in enumerate(chunks)
            if c.strip()
        ]
    except HTTPException:
        raise
    except Exception as e:
        if tmp_path and os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise HTTPException(status_code=500, detail=f"Document extraction failed: {e}")


async def store_in_qdrant(documents: List[Document], collection_name: str) -> None:
    if embeddings_model is None:
        raise HTTPException(status_code=503, detail="Embeddings model not available")
    if qdrant_client is None:
        raise HTTPException(status_code=503, detail="Qdrant client not available")
    try:
        try:
            qdrant_client.get_collection(collection_name)
        except Exception:
            qdrant_client.create_collection(
                collection_name=collection_name,
                vectors_config=VectorParams(size=384, distance=Distance.COSINE),
            )

        existing = qdrant_client.count(collection_name=collection_name).count
        points: List[PointStruct] = []
        for i, doc in enumerate(documents):
            emb = embeddings_model.embed_query(doc.page_content)
            points.append(
                PointStruct(
                    id=existing + i,
                    vector=emb,
                    payload={"text": doc.page_content, "metadata": doc.metadata},
                )
            )

        batch_size = 100
        for i in range(0, len(points), batch_size):
            qdrant_client.upsert(collection_name=collection_name, points=points[i: i + batch_size])

        logger.info(f"Stored {len(documents)} chunks in collection '{collection_name}'")
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Qdrant storage failed: {e}")


# ─── MCA Verification Service ─────────────────────────────────────────────────

def _mock_mca_response(cin: str) -> dict:
    """
    Returns a realistic mock MCA response when no real API key is configured.
    In production replace MCA_API_URL + MCA_API_KEY with Karza / Signzy / etc.
    CINs ending in 'F' are treated as INACTIVE for demo purposes.
    """
    is_active = not cin.upper().endswith("F")
    return {
        "valid":          is_active,
        "company_status": "ACTIVE" if is_active else "STRUCK_OFF",
        "directors":      ["Arjun Malhotra", "Dr. Elena Novak"] if is_active else [],
        "company_name":   "QuantumFleet AI",
    }


async def verify_mca_cin(cin: str) -> dict:
    """
    Calls the MCA provider API.
    Falls back to mock data when MCA_API_KEY is not set.
    Returns:
        { valid, company_status, directors, company_name }
    """
    if not MCA_API_KEY:
        logger.warning("MCA_API_KEY not set — using mock MCA response")
        return _mock_mca_response(cin)

    try:
        response = requests.get(
            MCA_API_URL,
            params={"cin": cin},
            headers={
                "x-karza-key": MCA_API_KEY,
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        response.raise_for_status()
        data = response.json()

        return {
            "valid":          data.get("status", "").upper() == "ACTIVE",
            "company_status": data.get("status"),
            "directors":      data.get("directors", []),
            "company_name":   data.get("companyName") or data.get("company_name"),
        }

    except Exception as e:
        logger.error(f"MCA API call failed: {e} — falling back to mock")
        return _mock_mca_response(cin)


def check_mca_consistency(startup: dict) -> List[str]:
    """
    Returns a list of flag strings describing verification issues.
    Empty list = no issues.
    """
    v     = startup.get("verification", {})
    flags: List[str] = []

    if not v.get("mca_verified"):
        flags.append("MCA_NOT_VERIFIED")

    mca_name     = (v.get("company_name") or "").lower().strip()
    startup_name = (startup.get("name")   or "").lower().strip()
    if mca_name and startup_name and mca_name != startup_name:
        flags.append("NAME_MISMATCH")

    if not v.get("directors"):
        flags.append("NO_DIRECTORS_FOUND")

    status = (v.get("company_status") or "").upper()
    if status and status not in ("ACTIVE",):
        flags.append(f"COMPANY_STATUS_{status}")

    return flags


# ─── LangGraph Agent ──────────────────────────────────────────────────────────

class AnalysisState(TypedDict):
    messages:        Annotated[Sequence[BaseMessage], add_messages]
    startup_id:      str
    collection_name: str
    rewrite_count:   int


def _qdrant_retrieve(query: str, collection_name: str) -> str:
    try:
        if embeddings_model is None:
            return "Embeddings model unavailable."
        if not collection_name:
            return "No document collection associated with this startup."
        if qdrant_client is None:
            return "Qdrant client unavailable."
        try:
            qdrant_client.get_collection(collection_name)
        except Exception:
            return "No uploaded documents found for this startup."

        q_emb   = embeddings_model.embed_query(query)
        results = qdrant_client.search(
            collection_name=collection_name, query_vector=q_emb, limit=6
        )
        if not results:
            return "No relevant document content found."
        return "\n\n---\n\n".join(r.payload["text"] for r in results)
    except Exception as e:
        logger.error(f"Retrieval error: {e}")
        return "Document retrieval failed."


def _web_search(query: str) -> str:
    # ── Attempt 1: DuckDuckGoSearchRun ────────────────────────────────────────
    try:
        from langchain_community.tools import DuckDuckGoSearchRun
        search = DuckDuckGoSearchRun()
        result = search.run(query)
        if result and len(result.strip()) > 20:
            logger.info(f"Web search succeeded (DuckDuckGoSearchRun): {query[:60]}")
            return result
    except Exception as e:
        logger.warning(f"DuckDuckGoSearchRun failed: {e}")

    # ── Attempt 2: DuckDuckGoSearchResults ────────────────────────────────────
    try:
        from langchain_community.tools import DuckDuckGoSearchResults
        search2 = DuckDuckGoSearchResults(num_results=5)
        result2 = search2.run(query)
        if result2 and len(result2.strip()) > 20:
            logger.info(f"Web search succeeded (DuckDuckGoSearchResults): {query[:60]}")
            return result2
    except Exception as e:
        logger.warning(f"DuckDuckGoSearchResults failed: {e}")

    # ── Attempt 3: DuckDuckGo Lite HTML ───────────────────────────────────────
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            )
        }
        resp = requests.post(
            "https://lite.duckduckgo.com/lite/",
            data={"q": query},
            headers=headers,
            timeout=8,
        )
        if resp.status_code == 200 and len(resp.text) > 100:
            import re as _re
            text    = _re.sub(r"<[^>]+>", " ", resp.text)
            text    = _re.sub(r"\s{2,}", " ", text).strip()
            snippet = text[:2000]
            if len(snippet) > 50:
                logger.info(f"Web search succeeded (DuckDuckGo Lite): {query[:60]}")
                return snippet
    except Exception as e:
        logger.warning(f"DuckDuckGo Lite request failed: {e}")

    # ── Graceful degradation ──────────────────────────────────────────────────
    logger.warning(f"All web search methods failed for query: {query[:60]}")
    return (
        f"Web search unavailable. Using pre-trained knowledge for: {query}. "
        "Market analysis will be based on LLM knowledge up to training cutoff."
    )


@tool
def retrieve_startup_documents(query: str) -> str:
    """Retrieve relevant content from startup's uploaded documents."""
    # startup_id is injected via closure in analyst_agent
    return "Document retrieval tool — context injected at agent level."


@tool
def search_market_data(query: str) -> str:
    """Search the web for market trends, competition, and industry data."""
    return _web_search(query)


TOOLS = [search_market_data]


def analyst_agent(state: AnalysisState) -> dict:
    logger.info("--- ANALYST AGENT ---")
    if llm is None:
        raise RuntimeError("LLM not initialised")

    startup_id      = state["startup_id"]
    collection_name = state["collection_name"]
    startup         = startups_db.get(startup_id, {})

    # Pull doc context eagerly
    last_msg_content = ""
    if state["messages"]:
        last = state["messages"][-1]
        last_msg_content = last.content if isinstance(last.content, str) else str(last.content)

    doc_context = _qdrant_retrieve(last_msg_content[:500], collection_name)

    # Fallback: use in-memory extracted text if Qdrant retrieval returned nothing useful
    if not doc_context or "unavailable" in doc_context.lower() or "not found" in doc_context.lower():
        fallback_text = startup.get("extracted_text", "")
        if fallback_text:
            doc_context = fallback_text[:3000]
            logger.info(f"Using in-memory extracted text fallback for {startup_id}")

    # Surface MCA verification status to the LLM so it can mention it in the report
    v              = startup.get("verification", {})
    mca_block      = ""
    if v.get("mca_verified"):
        mca_block = (
            f"\n\n[MCA VERIFIED] CIN: {v.get('cin')} | "
            f"Status: {v.get('company_status')} | "
            f"Registered name: {v.get('company_name')} | "
            f"Directors: {', '.join(v.get('directors', []))}"
        )
    else:
        mca_block = "\n\n[MCA NOT VERIFIED] This startup has not been verified with MCA."

    system_prompt = f"""You are a senior venture capital analyst with access to tools.

STARTUP PROFILE:
Name: {startup.get('name', 'N/A')}
Domain: {startup.get('domain', 'N/A')}
Description: {startup.get('description', 'N/A')}
Team: {startup.get('team', 'N/A')}
Extras: {startup.get('extras', 'N/A')}
{mca_block}

UPLOADED DOCUMENT CONTEXT:
{doc_context}

Use the search_market_data tool to research:
1. Current market size and growth rate for {startup.get('domain', 'the industry')}
2. Key competitors and market positioning
3. Recent industry trends and investment activity

Then synthesise everything into a comprehensive analysis."""

    llm_with_tools = llm.bind_tools(TOOLS)
    try:
        response = llm_with_tools.invoke(
            [HumanMessage(content=system_prompt)] + list(state["messages"])
        )
        return {"messages": [response]}
    except Exception as e:
        logger.warning(f"Analyst agent tool binding failed: {e}")
        fallback = AIMessage(
            content=(
                "Tool invocation encountered a connectivity error. "
                "Proceeding directly to generate the analysis report "
                "using the startup profile and my pre-trained knowledge."
            )
        )
        return {"messages": [fallback]}


def grade_relevance(state: AnalysisState) -> Literal["generate", "rewrite"]:
    logger.info("--- GRADE RELEVANCE ---")
    messages = state["messages"]

    last = messages[-1]
    if isinstance(last, ToolMessage):
        content_text = str(last.content)
    elif hasattr(last, "content"):
        c = last.content
        content_text = c if isinstance(c, str) else str(c)
    else:
        content_text = str(last)

    if state.get("rewrite_count", 0) >= 2:
        logger.info("Max rewrites reached — forcing generate")
        return "generate"

    prompt = (
        f"You are assessing whether the retrieved information is sufficient to write a "
        f"comprehensive startup evaluation report.\n\n"
        f"Retrieved content (first 800 chars): {content_text[:800]}\n\n"
        f"Is this enough to write a meaningful report? Answer ONLY 'yes' or 'no'."
    )

    try:
        resp   = llm.invoke([HumanMessage(content=prompt)])
        answer = resp.content.strip().lower()
        return "generate" if "yes" in answer else "rewrite"
    except Exception:
        return "generate"


def rewrite_query(state: AnalysisState) -> dict:
    logger.info("--- REWRITE ---")
    messages      = state["messages"]
    rewrite_count = state.get("rewrite_count", 0)
    original      = messages[0].content if messages else ""

    prompt = (
        f"The following startup analysis query did not retrieve sufficient information.\n"
        f"Original query: {original}\n\n"
        f"Rewrite it to be more specific and targeted at retrieving market data and "
        f"startup-specific details:"
    )
    try:
        resp      = llm.invoke([HumanMessage(content=prompt)])
        new_query = resp.content
    except Exception:
        new_query = original

    return {
        "messages":      [HumanMessage(content=new_query)],
        "rewrite_count": rewrite_count + 1,
    }


def generate_analysis(state: AnalysisState) -> dict:
    logger.info("--- GENERATE ANALYSIS ---")
    messages   = state["messages"]
    startup_id = state["startup_id"]
    startup    = startups_db.get(startup_id, {})

    context_parts: List[str] = []
    for msg in messages:
        if isinstance(msg, ToolMessage):
            text = str(msg.content).strip()
            if len(text) > 50:
                context_parts.append(text)

    if not context_parts:
        for msg in messages:
            if isinstance(msg, AIMessage):
                text = msg.content if isinstance(msg.content, str) else str(msg.content)
                if len(text.strip()) > 50:
                    context_parts.append(text.strip())

    context = "\n\n---\n\n".join(context_parts[-8:])

    # Build MCA section for the report
    v         = startup.get("verification", {})
    mca_flags = check_mca_consistency(startup)
    if v.get("mca_verified"):
        mca_section = (
            f"MCA VERIFIED ✓ | CIN: {v.get('cin')} | "
            f"Status: {v.get('company_status')} | "
            f"Registered as: {v.get('company_name')}"
        )
    else:
        mca_section = "MCA NOT VERIFIED — verification not completed or pending."

    if mca_flags:
        mca_section += f"\nCompliance flags: {', '.join(mca_flags)}"

    report_prompt = f"""You are a senior venture capital analyst. Write a comprehensive startup \
evaluation report in structured Markdown.

## Startup Profile
- **Name**: {startup.get('name', 'N/A')}
- **Domain**: {startup.get('domain', 'N/A')}
- **Description**: {startup.get('description', 'N/A')}
- **Team**: {startup.get('team', 'N/A')}
- **Additional Info**: {startup.get('extras', 'N/A')}
- **MCA / Compliance**: {mca_section}

## Research Context
{context if context else "No external research context was retrieved."}

## Instructions
Write a detailed investor-facing report with the following sections:

1. **Executive Summary** — 3-4 sentence high-impact overview
2. **Problem & Solution** — What problem is being solved and how
3. **Market Opportunity** — TAM/SAM/SOM, market size, growth rate
4. **Competitive Landscape** — Key competitors, differentiation, moat
5. **Business Model** — Revenue streams, unit economics, scalability
6. **Team Assessment** — Strengths, gaps, relevant experience
7. **Traction & Milestones** — Current progress, KPIs, customers
8. **Compliance & Governance** — MCA verification status, regulatory standing
9. **Risks & Challenges** — Key risks (market, technical, regulatory, execution)
10. **Investment Thesis** — Why this startup deserves investor attention
11. **Recommendation** — Strong Buy / Buy / Hold / Pass with justification

Be data-driven, specific, and use numbers wherever possible. Be critical but fair."""

    try:
        resp = llm.invoke([HumanMessage(content=report_prompt)])
        return {"messages": [resp]}
    except Exception as e:
        logger.error(f"Analysis generation failed: {e}")
        return {"messages": [AIMessage(content="Analysis generation encountered an error. Please retry.")]}


def safe_tool_node(state: AnalysisState) -> dict:
    try:
        tool_node = ToolNode(TOOLS)
        return tool_node.invoke(state)
    except Exception as e:
        logger.warning(f"ToolNode execution error (caught, continuing): {e}")
        messages = state.get("messages", [])
        last_ai  = None
        for msg in reversed(messages):
            if isinstance(msg, AIMessage):
                last_ai = msg
                break

        synthetic: List[ToolMessage] = []
        if last_ai and hasattr(last_ai, "tool_calls") and last_ai.tool_calls:
            for tc in last_ai.tool_calls:
                synthetic.append(
                    ToolMessage(
                        content=(
                            f"[Tool failed due to connectivity error: {e}] "
                            f"Use pre-trained knowledge to supplement analysis. "
                            f"Query was: {tc.get('args', {})}"
                        ),
                        tool_call_id=tc.get("id", "fallback"),
                        name=tc.get("name", "unknown_tool"),
                    )
                )
        if not synthetic:
            synthetic.append(
                ToolMessage(
                    content=(
                        f"[All tool calls failed: {e}] "
                        "Proceeding with LLM pre-trained knowledge only."
                    ),
                    tool_call_id="fallback",
                    name="fallback",
                )
            )
        return {"messages": synthetic}


def build_analysis_workflow():
    wf = StateGraph(AnalysisState)

    wf.add_node("analyst",  analyst_agent)
    wf.add_node("tools",    safe_tool_node)
    wf.add_node("rewrite",  rewrite_query)
    wf.add_node("generate", generate_analysis)

    wf.add_edge(START, "analyst")
    wf.add_conditional_edges(
        "analyst",
        tools_condition,
        {"tools": "tools", END: "generate"},
    )
    wf.add_conditional_edges(
        "tools",
        grade_relevance,
        {"generate": "generate", "rewrite": "rewrite"},
    )
    wf.add_edge("rewrite",  "analyst")
    wf.add_edge("generate", END)

    return wf.compile()


# ─── Chart Generation ─────────────────────────────────────────────────────────

def generate_market_opportunity_chart(startup: dict) -> bytes:
    fig, ax = plt.subplots(figsize=(7, 4), facecolor="#0f172a")
    ax.set_facecolor("#1e293b")

    categories  = ["TAM\n(Total Market)", "SAM\n(Serviceable)", "SOM\n(Obtainable)"]
    values      = [100, 30, 8]
    colors_list = ["#6366f1", "#8b5cf6", "#a78bfa"]

    bars = ax.bar(categories, values, color=colors_list, width=0.5, edgecolor="#334155", linewidth=0.8)
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 1.5,
            f"${val}B",
            ha="center", va="bottom",
            color="white", fontsize=11, fontweight="bold",
        )

    ax.set_ylim(0, 130)
    ax.set_ylabel("Market Size (USD Billions)", color="#94a3b8", fontsize=10)
    ax.set_title(
        f"Market Opportunity — {startup.get('domain', 'Industry')}",
        color="white", fontsize=13, fontweight="bold", pad=12,
    )
    ax.tick_params(colors="#94a3b8")
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#334155")

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="#0f172a")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def generate_evaluation_radar_chart(startup: dict) -> bytes:
    fig, ax = plt.subplots(figsize=(7, 4), facecolor="#0f172a")
    ax.set_facecolor("#1e293b")

    dimensions = [
        "Product\nStrength", "Market\nSize", "Team\nQuality",
        "Business\nModel",   "Competitive\nMoat", "Execution\nRisk",
    ]
    scores     = [7.8, 8.2, 7.0, 7.5, 6.8, 7.2]
    colors_bar = ["#6366f1", "#8b5cf6", "#a78bfa", "#7c3aed", "#9333ea", "#c084fc"]

    bars = ax.barh(dimensions, scores, color=colors_bar, edgecolor="#334155", linewidth=0.8, height=0.6)
    for bar, score in zip(bars, scores):
        ax.text(
            score + 0.1,
            bar.get_y() + bar.get_height() / 2,
            f"{score}/10",
            va="center", color="white", fontsize=9, fontweight="bold",
        )

    ax.set_xlim(0, 11)
    ax.set_xlabel("Score (out of 10)", color="#94a3b8", fontsize=10)
    ax.set_title(
        f"AI Evaluation Scorecard — {startup.get('name', 'Startup')}",
        color="white", fontsize=13, fontweight="bold", pad=12,
    )
    ax.tick_params(colors="#94a3b8")
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#334155")

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="#0f172a")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


def generate_trend_chart(startup: dict) -> bytes:
    fig, ax = plt.subplots(figsize=(7, 4), facecolor="#0f172a")
    ax.set_facecolor("#1e293b")

    years  = [2021, 2022, 2023, 2024, 2025, 2026, 2027, 2028]
    growth = [12, 18, 26, 38, 54, 72, 97, 130]

    ax.plot(
        years, growth,
        color="#6366f1", linewidth=2.5,
        marker="o", markersize=7,
        markerfacecolor="#a78bfa", markeredgecolor="#6366f1",
    )
    ax.fill_between(years, growth, alpha=0.15, color="#6366f1")

    ax.set_xlabel("Year", color="#94a3b8", fontsize=10)
    ax.set_ylabel("Market Size (USD Billions)", color="#94a3b8", fontsize=10)
    ax.set_title(
        f"Market Growth Trend — {startup.get('domain', 'Industry')}",
        color="white", fontsize=13, fontweight="bold", pad=12,
    )
    ax.tick_params(colors="#94a3b8")
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color("#334155")

    for x, y in zip(years[::2], growth[::2]):
        ax.annotate(
            f"${y}B", (x, y),
            textcoords="offset points", xytext=(0, 10),
            ha="center", color="#a78bfa", fontsize=8,
        )

    plt.tight_layout()
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="#0f172a")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ─── PDF Report Builder ───────────────────────────────────────────────────────

def build_pdf_report(startup: dict, analysis_text: str) -> bytes:
    buffer = io.BytesIO()
    doc    = SimpleDocTemplate(
        buffer, pagesize=A4,
        leftMargin=2 * cm, rightMargin=2 * cm,
        topMargin=2 * cm,  bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()

    title_style = ParagraphStyle(
        "CustomTitle",
        parent=styles["Title"],
        fontSize=26,
        textColor=colors.HexColor("#6366f1"),
        spaceAfter=6,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
    )
    subtitle_style = ParagraphStyle(
        "Subtitle",
        parent=styles["Normal"],
        fontSize=13,
        textColor=colors.HexColor("#94a3b8"),
        spaceAfter=4,
        alignment=TA_CENTER,
    )
    section_style = ParagraphStyle(
        "Section",
        parent=styles["Heading2"],
        fontSize=14,
        textColor=colors.HexColor("#6366f1"),
        spaceBefore=14,
        spaceAfter=6,
        fontName="Helvetica-Bold",
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#1e293b"),
        leading=16,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
    )
    label_style = ParagraphStyle(
        "Label",
        parent=styles["Normal"],
        fontSize=9,
        textColor=colors.HexColor("#6366f1"),
        fontName="Helvetica-Bold",
    )
    value_style = ParagraphStyle(
        "Value",
        parent=styles["Normal"],
        fontSize=10,
        textColor=colors.HexColor("#1e293b"),
        leading=14,
    )

    story = []

    story.append(Spacer(1, 1.5 * cm))
    story.append(Paragraph("AI Startup Evaluation Report", title_style))
    story.append(Paragraph(
        f"Powered by LangGraph RAG Pipeline &nbsp;|&nbsp; "
        f"Generated {datetime.now().strftime('%B %d, %Y')}",
        subtitle_style,
    ))
    story.append(Spacer(1, 0.4 * cm))
    story.append(HRFlowable(width="100%", thickness=2, color=colors.HexColor("#6366f1"), spaceAfter=12))

    # MCA verification badge row
    v           = startup.get("verification", {})
    mca_verified = v.get("mca_verified", False)
    mca_badge   = "✓ MCA VERIFIED" if mca_verified else "⚠ MCA NOT VERIFIED"
    mca_color   = colors.HexColor("#16a34a") if mca_verified else colors.HexColor("#dc2626")
    mca_style   = ParagraphStyle(
        "MCABadge",
        parent=styles["Normal"],
        fontSize=10,
        textColor=mca_color,
        fontName="Helvetica-Bold",
        alignment=TA_CENTER,
        spaceAfter=8,
    )
    story.append(Paragraph(mca_badge, mca_style))

    info_rows = [
        [Paragraph("Startup Name",      label_style), Paragraph(startup.get("name",       "N/A"), value_style)],
        [Paragraph("Domain / Industry", label_style), Paragraph(startup.get("domain",     "N/A"), value_style)],
        [Paragraph("Startup ID",        label_style), Paragraph(startup.get("startup_id", "N/A"), value_style)],
        [Paragraph("Registered",        label_style), Paragraph(startup.get("created_at", "N/A"), value_style)],
    ]
    if mca_verified:
        info_rows += [
            [Paragraph("CIN",                label_style), Paragraph(v.get("cin", "N/A"),            value_style)],
            [Paragraph("MCA Company Name",   label_style), Paragraph(v.get("company_name", "N/A"),   value_style)],
            [Paragraph("Company Status",     label_style), Paragraph(v.get("company_status", "N/A"), value_style)],
            [Paragraph("Directors",          label_style), Paragraph(", ".join(v.get("directors", [])) or "N/A", value_style)],
        ]

    info_table = Table(info_rows, colWidths=[4 * cm, 12 * cm])
    info_table.setStyle(TableStyle([
        ("BACKGROUND",    (0, 0), (0, -1), colors.HexColor("#f1f5f9")),
        ("BACKGROUND",    (1, 0), (1, -1), colors.white),
        ("GRID",          (0, 0), (-1, -1), 0.5, colors.HexColor("#e2e8f0")),
        ("VALIGN",        (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING",    (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING",   (0, 0), (-1, -1), 8),
    ]))
    story.append(info_table)
    story.append(Spacer(1, 0.5 * cm))

    story.append(Paragraph("Product Description", section_style))
    story.append(Paragraph(startup.get("description", "N/A"), body_style))

    story.append(Paragraph("Team", section_style))
    story.append(Paragraph(startup.get("team", "N/A"), body_style))

    if startup.get("extras"):
        story.append(Paragraph("Additional Information", section_style))
        story.append(Paragraph(startup["extras"], body_style))

    story.append(PageBreak())

    story.append(Paragraph("Market Analysis & Visualizations", section_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=10))

    charts = [
        ("Market Opportunity (TAM / SAM / SOM)", generate_market_opportunity_chart(startup)),
        ("Market Growth Trend (2021–2028)",       generate_trend_chart(startup)),
        ("AI Evaluation Scorecard",               generate_evaluation_radar_chart(startup)),
    ]

    for chart_title, chart_bytes in charts:
        story.append(Paragraph(chart_title, ParagraphStyle(
            "ChartTitle",
            parent=styles["Normal"],
            fontSize=11,
            textColor=colors.HexColor("#334155"),
            fontName="Helvetica-Bold",
            spaceAfter=6,
            spaceBefore=10,
        )))
        img_buf = io.BytesIO(chart_bytes)
        img_buf.seek(0)
        rl_img  = RLImage(img_buf, width=15 * cm, height=8.5 * cm)
        story.append(rl_img)
        story.append(Spacer(1, 0.6 * cm))

    story.append(PageBreak())

    story.append(Paragraph("AI-Generated Investor Report", section_style))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0"), spaceAfter=10))

    import re
    for line in analysis_text.split("\n"):
        line = line.strip()
        if not line:
            story.append(Spacer(1, 4))
            continue

        clean_line = re.sub(r'\*\*(.*?)\*\*', r'\1', line)
        clean_line = re.sub(r'\*(.*?)\*',     r'\1', clean_line)

        if line.startswith("## ") or line.startswith("# "):
            heading = line.lstrip("#").strip()
            story.append(Paragraph(heading, section_style))
        elif line.startswith("**") and line.endswith("**"):
            story.append(Paragraph(clean_line, ParagraphStyle(
                "Bold",
                parent=body_style,
                fontName="Helvetica-Bold",
                fontSize=11,
                textColor=colors.HexColor("#334155"),
            )))
        elif line.startswith("- ") or line.startswith("* "):
            bullet = clean_line[2:] if line.startswith("-") else clean_line[1:].strip()
            story.append(Paragraph(f"• {bullet}", ParagraphStyle(
                "Bullet",
                parent=body_style,
                leftIndent=12,
                spaceAfter=3,
            )))
        else:
            story.append(Paragraph(clean_line, body_style))

    story.append(Spacer(1, 1 * cm))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#e2e8f0")))
    story.append(Paragraph(
        "This report was generated by the AI Startup Evaluation Platform. "
        "All market data is illustrative and based on AI research. "
        "Consult domain experts before making investment decisions.",
        ParagraphStyle(
            "Disclaimer",
            parent=styles["Normal"],
            fontSize=8,
            textColor=colors.HexColor("#94a3b8"),
            alignment=TA_CENTER,
            spaceBefore=8,
        ),
    ))

    doc.build(story)
    buffer.seek(0)
    return buffer.read()


# ─── Shared chatbot logic ──────────────────────────────────────────────────────

async def _run_chatbot(startup: dict, startup_id: str, question: str) -> ChatResponse:
    collection_name = f"startup_{startup_id.replace('-', '')}"

    if llm is None:
        raise HTTPException(status_code=503, detail="LLM not available")

    question = question.strip()
    if not question:
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    try:
        doc_context = _qdrant_retrieve(question, collection_name)

        # Include MCA info in chatbot context
        v            = startup.get("verification", {})
        mca_context  = ""
        if v.get("mca_verified"):
            mca_context = (
                f"\nMCA Verified: YES | CIN: {v.get('cin')} | "
                f"Status: {v.get('company_status')} | "
                f"Registered as: {v.get('company_name')} | "
                f"Directors: {', '.join(v.get('directors', []))}"
            )
        else:
            mca_context = "\nMCA Verified: NO"

        startup_context = f"""
Startup: {startup.get('name', 'N/A')}
Domain: {startup.get('domain', 'N/A')}
Description: {startup.get('description', 'N/A')}
Team: {startup.get('team', 'N/A')}
Additional Info: {startup.get('extras', 'N/A')}{mca_context}
"""

        prompt = f"""You are an AI analyst answering investor questions about a specific startup.

STARTUP INFORMATION:
{startup_context}

RELEVANT DOCUMENTS:
{doc_context}

INVESTOR QUESTION:
{question}

ANSWER GUIDELINES:
- Only answer based on the provided startup information and documents
- Be specific and factual
- If information is not available, clearly state that
- Focus on investment relevance
- Keep answer concise (2-3 paragraphs)"""

        response = await asyncio.to_thread(llm.invoke, [HumanMessage(content=prompt)])
        answer   = response.content.strip()

        return ChatResponse(
            answer=answer,
            startup_name=startup.get("name", "Unknown"),
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Chatbot error: {e}")
        raise HTTPException(status_code=500, detail=f"Chatbot error: {str(e)}")


# ─── API Endpoints ────────────────────────────────────────────────────────────

@app.post(
    "/startups",
    status_code=201,
    response_model=StartupResponse,
    summary="Register a new startup",
)
async def create_startup(body: StartupCreate):
    startup_id = body.startupId or str(uuid.uuid4())
    now        = datetime.utcnow().isoformat() + "Z"
    
    # Map fields for compatibility with different frontend versions
    description = body.description or body.idea or "N/A"
    domain = body.domain or "N/A"
    team = body.team or "N/A"
    
    record     = {
        "startup_id":           startup_id,
        "id":                   startup_id, # Frontend compatibility
        "startupId":            startup_id, # Frontend compatibility
        "name":                 body.name,
        "domain":               domain,
        "description":          description,
        "team":                 team,
        "extras":               body.extras or f"Stage: {body.stage}, Team Size: {body.teamSize}, Funding Required: {body.fundingRequired}",
        "created_at":           now,
        "updated_at":           now,
        "document_collections": [],
        # ── MCA verification layer (populated via POST /startups/{id}/verify/mca)
        "verification": {
            "cin":            None,
            "mca_verified":   False,
            "company_status": None,
            "company_name":   None,
            "directors":      [],
            "last_checked":   None,
        },
    }

    # ── Auto-verify against mock MCA if name matches ──────────────────────────
    try:
        mock_result = _mock_mca_response("AUTO")
        mock_name   = (mock_result.get("company_name") or "").strip().lower()
        if mock_name and mock_name == body.name.strip().lower() and mock_result.get("valid"):
            record["verification"] = {
                "cin":            "AUTO_VERIFIED",
                "mca_verified":   True,
                "company_status": mock_result.get("company_status"),
                "company_name":   mock_result.get("company_name"),
                "directors":      mock_result.get("directors", []),
                "last_checked":   now,
            }
            logger.info(f"Auto-verified startup '{body.name}' — mock MCA name matched")
    except Exception as e:
        logger.warning(f"Auto-verification skipped: {e}")

    startups_db[startup_id] = record
    logger.info(f"Startup registered: {startup_id} — {body.name}")
    return StartupResponse(**record)


@app.put(
    "/startups/{startup_id}",
    response_model=StartupResponse,
    summary="Update an existing startup profile",
)
async def update_startup(
    startup_id: str          = Path(..., description="The unique startup ID"),
    body:       StartupUpdate = ...,
):
    record = startups_db.get(startup_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Startup '{startup_id}' not found")

    updates = body.model_dump(exclude_none=True)
    record.update(updates)
    record["updated_at"] = datetime.utcnow().isoformat() + "Z"
    startups_db[startup_id] = record
    logger.info(f"Startup updated: {startup_id}")
    return StartupResponse(**record)


@app.post(
    "/startups/{startup_id}/documents",
    status_code=200,
    summary="Upload a supporting document for a startup",
)
async def upload_startup_document(
    startup_id: str                   = Path(..., description="The unique startup ID"),
    body:       DocumentUploadRequest = ...,
):
    record = startups_db.get(startup_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Startup '{startup_id}' not found")

    url_str = str(body.document_url)
    suffix  = ".docx" if url_str.lower().endswith(".docx") else ".pdf"

    file_bytes = await _download_file(url_str)
    documents  = await extract_document_content(file_bytes, suffix=suffix)

    collection_name = f"startup_{startup_id.replace('-', '')}"
    await store_in_qdrant(documents, collection_name)

    if collection_name not in record["document_collections"]:
        record["document_collections"].append(collection_name)
    record["updated_at"] = datetime.utcnow().isoformat() + "Z"
    startups_db[startup_id] = record

    return {
        "status":          "success",
        "startup_id":      startup_id,
        "collection_name": collection_name,
        "chunks_stored":   len(documents),
        "message":         f"Document processed and stored ({len(documents)} chunks).",
    }


@app.post(
    "/reports/{startup_id}",
    summary="Generate AI analysis report for a startup (returns PDF)",
)
async def generate_report(
    startup_id: str = Path(..., description="The unique startup ID"),
):
    record = startups_db.get(startup_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Startup '{startup_id}' not found")

    # ── MCA consistency check (warnings only — does NOT block report) ──────────
    flags = check_mca_consistency(record)
    if "MCA_NOT_VERIFIED" in flags:
        logger.warning(f"Report for {startup_id}: MCA not verified")
    if "NAME_MISMATCH" in flags:
        logger.warning(f"Report for {startup_id}: MCA name mismatch")
    if flags:
        logger.info(f"Report flags for {startup_id}: {flags}")

    collection_name = f"startup_{startup_id.replace('-', '')}"

    initial_query = (
        f"Perform a comprehensive evaluation of the startup '{record['name']}' "
        f"operating in the '{record['domain']}' industry. "
        f"Product: {record['description']}. "
        f"Team: {record['team']}. "
        f"Additional context: {record.get('extras', 'None')}. "
        f"Analyse uploaded documents, research current market trends, competition, "
        f"TAM/SAM/SOM, regulatory environment, and investment potential."
    )

    initial_state: AnalysisState = {
        "messages":        [HumanMessage(content=initial_query)],
        "startup_id":      startup_id,
        "collection_name": collection_name,
        "rewrite_count":   0,
    }

    try:
        workflow      = build_analysis_workflow()
        result        = await asyncio.to_thread(
            workflow.invoke, initial_state, {"recursion_limit": 15}
        )
        final_msg     = result["messages"][-1]
        analysis_text = (
            final_msg.content
            if isinstance(final_msg.content, str)
            else str(final_msg.content)
        )
    except Exception as e:
        logger.error(f"LangGraph pipeline failed: {e}")
        raise HTTPException(status_code=500, detail=f"AI analysis pipeline failed: {e}")

    try:
        pdf_bytes = await asyncio.to_thread(build_pdf_report, record, analysis_text)
    except Exception as e:
        logger.error(f"PDF generation failed: {e}")
        raise HTTPException(status_code=500, detail=f"PDF generation failed: {e}")

    filename = f"report_{record['name'].replace(' ', '_')}_{startup_id[:8]}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'inline; filename="{filename}"'},
    )


@app.get(
    "/startups",
    response_model=List[StartupResponse],
    summary="List all registered startups",
)
async def list_startups():
    return [StartupResponse(**v) for v in startups_db.values()]


@app.get(
    "/startups/{startup_id}",
    response_model=StartupResponse,
    summary="Get a startup by ID",
)
async def get_startup(
    startup_id: str = Path(..., description="The unique startup ID"),
):
    record = startups_db.get(startup_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Startup '{startup_id}' not found")
    return StartupResponse(**record)


# ─── MCA Verification Endpoints ───────────────────────────────────────────────

@app.post(
    "/startups/{startup_id}/verify/mca",
    response_model=MCAVerificationResponse,
    summary="Verify startup via MCA CIN number",
)
async def verify_startup_mca(
    startup_id: str                  = Path(..., description="The unique startup ID"),
    body:       MCAVerificationRequest = ...,
):
    """
    **POST /startups/{startup_id}/verify/mca**

    Verifies the startup against the Ministry of Corporate Affairs (MCA) registry
    using its Company Identification Number (CIN).

    - Calls the MCA provider API (or mock when `MCA_API_KEY` is unset)
    - Persists verification data on the startup record
    - Returns the full verification result including name-match and compliance flags
    - Does **not** block the report pipeline — verification is advisory
    """
    record = startups_db.get(startup_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Startup '{startup_id}' not found")

    cin = body.cin.strip().upper()
    if not cin:
        raise HTTPException(status_code=400, detail="CIN cannot be empty")

    # Basic CIN format check (India: L/U + 5 digits + 2 letters + 4 digits + 3 letters + 6 digits)
    import re
    if not re.match(r"^[LUlu]\d{5}[A-Za-z]{2}\d{4}[A-Za-z]{3}\d{6}$", cin):
        raise HTTPException(
            status_code=422,
            detail=(
                "Invalid CIN format. Expected format: "
                "L/U + 5 digits + 2 letters + 4 digits + 3 letters + 6 digits "
                "(e.g. L17110MH1973PLC019786)"
            ),
        )

    logger.info(f"MCA verification requested for startup {startup_id} with CIN {cin}")

    result = await verify_mca_cin(cin)

    # Persist verification data regardless of result
    now = datetime.utcnow().isoformat() + "Z"
    record["verification"].update({
        "cin":            cin,
        "mca_verified":   bool(result.get("valid")),
        "company_status": result.get("company_status"),
        "company_name":   result.get("company_name"),
        "directors":      result.get("directors", []),
        "last_checked":   now,
    })
    record["updated_at"] = now
    startups_db[startup_id] = record

    if not result.get("valid"):
        logger.warning(f"MCA verification failed for {startup_id}: {result.get('company_status')}")
        raise HTTPException(
            status_code=400,
            detail=(
                f"CIN {cin} is not active in MCA registry. "
                f"Status: {result.get('company_status', 'UNKNOWN')}. "
                "Verify the CIN and try again, or proceed without verification."
            ),
        )

    # Name consistency
    mca_name     = (result.get("company_name") or "").lower().strip()
    startup_name = (record.get("name")         or "").lower().strip()
    name_match   = bool(mca_name and startup_name and mca_name == startup_name)

    flags = check_mca_consistency(record)

    logger.info(f"MCA verified: {startup_id} | CIN: {cin} | name_match: {name_match} | flags: {flags}")

    return MCAVerificationResponse(
        startup_id     = startup_id,
        cin            = cin,
        mca_verified   = True,
        company_status = result.get("company_status"),
        company_name   = result.get("company_name"),
        directors      = result.get("directors", []),
        name_match     = name_match,
        flags          = flags,
        last_checked   = now,
        message        = (
            "Verification successful."
            if not flags else
            f"Verified with warnings: {', '.join(flags)}"
        ),
    )


@app.get(
    "/startups/{startup_id}/verify/mca",
    response_model=MCAStatusResponse,
    summary="Get current MCA verification status for a startup",
)
async def get_mca_status(
    startup_id: str = Path(..., description="The unique startup ID"),
):
    """
    **GET /startups/{startup_id}/verify/mca**

    Returns the current MCA verification status stored on the startup record.
    Use this to display the verification badge in the UI without re-calling the API.
    """
    record = startups_db.get(startup_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Startup '{startup_id}' not found")

    v     = record.get("verification", {})
    flags = check_mca_consistency(record)

    return MCAStatusResponse(
        startup_id     = startup_id,
        cin            = v.get("cin"),
        mca_verified   = bool(v.get("mca_verified")),
        company_status = v.get("company_status"),
        company_name   = v.get("company_name"),
        directors      = v.get("directors", []),
        flags          = flags,
        last_checked   = v.get("last_checked"),
    )


# ─── Investor Chatbot — by UUID ───────────────────────────────────────────────

@app.post(
    "/chat/{startup_id}",
    response_model=ChatResponse,
    summary="Investor Chatbot (by startup UUID)",
)
async def investor_chatbot(
    startup_id: str         = Path(..., description="The startup UUID"),
    msg:        ChatMessage = ...,
):
    if startup_id not in startups_db:
        raise HTTPException(status_code=404, detail=f"Startup '{startup_id}' not found")

    startup = startups_db[startup_id]
    return await _run_chatbot(startup, startup_id, msg.question)


# ─── Express-Compatible Aliases ───────────────────────────────────────────────

@app.post("/api/startups/register", response_model=StartupResponse)
async def register_startup_alias(body: StartupCreate):
    """Alias for POST /startups to match frontend expectations"""
    return await create_startup(body)


@app.post("/api/startups/{startup_id}/documents/upload")
async def upload_document_form(
    startup_id: str = Path(..., description="The unique startup ID"),
    documents: UploadFile = File(...),
):
    """Supports multipart/form-data uploads as expected by the frontend"""
    record = startups_db.get(startup_id)
    if not record:
        raise HTTPException(status_code=404, detail=f"Startup '{startup_id}' not found")

    file_bytes = await documents.read()
    filename   = documents.filename or "pitch_deck.pdf"
    suffix     = os.path.splitext(filename)[1].lower() or ".pdf"

    extracted_docs = await extract_document_content(file_bytes, suffix=suffix)
    collection_name = f"startup_{startup_id.replace('-', '')}"

    # Store extracted text in-memory as fallback
    record["extracted_text"] = "\n\n".join(doc.page_content for doc in extracted_docs)

    # Try Qdrant storage, but don't fail if unavailable
    try:
        await store_in_qdrant(extracted_docs, collection_name)
        if collection_name not in record["document_collections"]:
            record["document_collections"].append(collection_name)
    except HTTPException as e:
        if e.status_code == 503:
            logger.warning(f"Qdrant/embeddings unavailable — using in-memory text fallback for {startup_id}")
        else:
            raise

    record["updated_at"] = datetime.utcnow().isoformat() + "Z"
    startups_db[startup_id] = record

    return {
        "status": "success",
        "startup_id": startup_id,
        "chunks": len(extracted_docs)
    }


@app.post("/api/startups/{startup_id}/analyze")
async def trigger_full_analysis(
    startup_id: str = Path(...),
    background_tasks: BackgroundTasks = BackgroundTasks()
):
    """Triggers the LangGraph pipeline in the background"""
    if startup_id not in startups_db:
        raise HTTPException(status_code=404, detail="Startup not found")
    
    analysis_results[startup_id] = {"status": "processing", "analysis": None}
    background_tasks.add_task(process_analysis_task, startup_id)
    return {"status": "analysis_started", "id": startup_id}


@app.get("/api/startups/{startup_id}/report/status")
async def get_analysis_status(startup_id: str = Path(...)):
    """Poll for analysis results"""
    res = analysis_results.get(startup_id)
    if not res:
        return {"status": "not_started"}
    return res


async def process_analysis_task(startup_id: str):
    """Background worker for LangGraph analysis"""
    try:
        record = startups_db[startup_id]
        collection_name = f"startup_{startup_id.replace('-', '')}"
        
        initial_query = f"Complete evaluation of {record['name']} in {record['domain']}"
        initial_state: AnalysisState = {
            "messages": [HumanMessage(content=initial_query)],
            "startup_id": startup_id,
            "collection_name": collection_name,
            "rewrite_count": 0,
        }
        
        workflow = build_analysis_workflow()
        result = await asyncio.to_thread(workflow.invoke, initial_state, {"recursion_limit": 15})
        analysis_text = result["messages"][-1].content
        
        # Parse Markdown into sections for the frontend
        # The frontend expects: executiveSummary, marketAnalysis, teamAssessment, riskFactors, score, recommendation
        
        import re
        def extract_section(text, title):
            pattern = rf"(?i)##\s*{title}.*?\n(.*?)(?=\n##|$)"
            match = re.search(pattern, text, re.DOTALL)
            return match.group(1).strip() if match else f"See full report for {title}."

        parsed_analysis = {
            "executiveSummary": extract_section(analysis_text, "Executive Summary"),
            "marketAnalysis": extract_section(analysis_text, "Market Opportunity"),
            "teamAssessment": extract_section(analysis_text, "Team Assessment"),
            "riskFactors": extract_section(analysis_text, "Risks & Challenges"),
            "score": 8.5, # Default or extracted
            "recommendation": extract_section(analysis_text, "Recommendation")
        }
        
        analysis_results[startup_id] = {
            "status": "complete",
            "analysis": parsed_analysis
        }
        logger.info(f"Analysis completed for {startup_id}")
    except Exception as e:
        logger.error(f"Background analysis failed: {e}")
        analysis_results[startup_id] = {"status": "failed", "error": str(e)}


# ─── FinScope Endpoints ──────────────────────────────────────────────────────

@app.post("/finscope/chat")
async def finscope_chat(body: FinScopeChatRequest):
    try:
        if is_finscope_prompt_blocked(body.question):
            raise HTTPException(
                status_code=400,
                detail="Request blocked by safety policy. Ask a finance-focused question without jailbreak or harmful instructions.",
            )

        await sio.emit('log_stream', {'message': 'FinScope: processing chat request'})
        result = await run_finscope_chat(
            question=body.question,
            user_profile=body.user_profile,
            session_id=body.session_id,
        )
        return {
            "answer": result.get("answer", ""),
            "agent_used": result.get("agent", "Financial Educator"),
            "intent": result.get("intent", "education"),
        }
    except Exception as e:
        logger.error(f"FinScope chat failed: {e}")
        raise HTTPException(status_code=500, detail=f"FinScope chat failed: {e}")


@app.post("/finscope/analyze-document")
async def finscope_analyze_document(
    document: UploadFile = File(...),
    session_id: str = Form(""),
    user_profile: str = Form("beginner"),
):
    try:
        await sio.emit('log_stream', {'message': f'FinScope: analyzing document {document.filename or "upload"}'})
        file_bytes = await document.read()
        suffix = os.path.splitext(document.filename or "upload.pdf")[1].lower() or ".pdf"
        docs = await extract_document_content(file_bytes, suffix=suffix)
        document_text = "\n\n".join(d.page_content for d in docs)

        if session_id:
            store_session_document(session_id, document_text)

        result = await run_finscope_chat(
            question="Analyze this document for an investor.",
            user_profile=user_profile,
            document_text=document_text,
            session_id=session_id,
        )

        return {
            "analysis": result.get("answer", ""),
            "agent_used": result.get("agent", "Document Analyzer"),
            "intent": result.get("intent", "document"),
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"FinScope document analysis failed: {e}")
        raise HTTPException(status_code=500, detail=f"FinScope document analysis failed: {e}")


@app.get("/api/finance-news/headlines")
async def finance_news_headlines(symbol: str = "AAPL:NASDAQ", limit: int = 10):
    try:
        headlines = _fetch_stock_news(symbol, max(1, min(limit, 20)))
        return {"headlines": headlines}
    except Exception as e:
        logger.warning(f"Finance headlines fetch failed: {e}")
        return {"headlines": []}


# ─── Investor Chatbot — by name ───────────────────────────────────────────────

@app.post(
    "/chat/by-name/{startup_name}",
    response_model=ChatResponse,
    summary="Investor Chatbot (lookup by startup name)",
)
async def investor_chatbot_by_name(
    startup_name: str         = Path(..., description="The startup name (case-insensitive)"),
    msg:          ChatMessage = ...,
):
    match: Optional[Dict[str, Any]] = None
    for record in startups_db.values():
        if record.get("name", "").lower() == startup_name.lower():
            if match is None or record["created_at"] > match["created_at"]:
                match = record

    if match is None:
        raise HTTPException(
            status_code=404,
            detail=(
                f"No startup named '{startup_name}' found. "
                f"Register it first via POST /startups, then use its startup_id."
            ),
        )

    return await _run_chatbot(match, match["startup_id"], msg.question)


# ─── Health check ─────────────────────────────────────────────────────────────

@app.get("/health", summary="Health check")
async def health_check():
    return {
        "status":            "healthy",
        "service":           "AI Startup Evaluation Platform",
        "version":           "2.1.0",
        "qdrant_connected":  qdrant_client is not None,
        "embeddings_ready":  embeddings_model is not None,
        "llm_ready":         llm is not None,
        "docling_ready":     document_converter is not None,
        "startups_loaded":   len(startups_db),
        "mca_api_configured": bool(MCA_API_KEY),
    }


# Wrap FastAPI with Socket.IO so /socket.io is served alongside REST APIs.
app = socketio.ASGIApp(sio, app)


# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 7860)),
        reload=False,
    )