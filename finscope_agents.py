"""
FinScope — Multi-Subagent Financial Analysis & Education System
Built with LangChain + LangGraph + Groq

Includes React Agent to natively use CustomYTSearch tool when users ask for videos.
"""

import os
import logging
import asyncio
import json
import requests as _requests
from typing import Annotated, Literal, Sequence, TypedDict, Optional, List, Dict, Any

from langchain_core.messages import BaseMessage, HumanMessage, AIMessage, SystemMessage
from langchain_groq import ChatGroq
from langchain_core.tools import BaseTool, tool
from langgraph.graph import END, StateGraph, START
from langgraph.graph.message import add_messages
from langgraph.prebuilt import create_react_agent

logger = logging.getLogger(__name__)

# ─── Groq LLM ────────────────────────────────────────────────────────────────

GROQ_API_KEY =  os.getenv("GROQ_API_KEY", "")


def _get_llm(temperature: float = 0.3, max_tokens: int = 2048) -> ChatGroq:
    if not GROQ_API_KEY:
        raise RuntimeError("GROQ_API_KEY is not set")
    return ChatGroq(
        groq_api_key=GROQ_API_KEY,
        model_name="meta-llama/llama-4-scout-17b-16e-instruct",
        temperature=temperature,
        max_tokens=max_tokens,
    )


# ─── In-Memory Session Store (document context) ──────────────────────────────

_session_store: Dict[str, str] = {}


def store_session_document(session_id: str, document_text: str) -> None:
    _session_store[session_id] = document_text
    logger.info(f"Stored document context for session {session_id}")


def get_session_document(session_id: str) -> str:
    return _session_store.get(session_id, "")


def clear_session(session_id: str) -> None:
    _session_store.pop(session_id, None)


# ─── RapidAPI Finance Data ────────────────────────────────────────────────────

RAPIDAPI_KEY = os.getenv("RAPIDAPI_KEY", "")
RAPIDAPI_HOST = "real-time-finance-data.p.rapidapi.com"
RAPIDAPI_BASE_URL = "https://real-time-finance-data.p.rapidapi.com"

# In-memory news cache (avoid hammering the API)
_news_cache: Dict[str, Any] = {}
_news_cache_ts: Dict[str, float] = {}
_NEWS_CACHE_TTL = 300  # 5 minutes


def _fetch_stock_news(symbol: str, limit: int = 5) -> list:
    """Fetch stock news from RapidAPI with caching."""
    import time
    if not RAPIDAPI_KEY:
        logger.warning("RAPIDAPI_KEY is not set; skipping stock news fetch")
        return []
    now = time.time()
    cache_key = f"news_{symbol}"
    if cache_key in _news_cache and (now - _news_cache_ts.get(cache_key, 0)) < _NEWS_CACHE_TTL:
        return _news_cache[cache_key][:limit]
    try:
        url = f"{RAPIDAPI_BASE_URL}/stock-news"
        headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": RAPIDAPI_HOST}
        params = {"symbol": symbol, "language": "en"}
        resp = _requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        news = data.get("data", {}).get("news", [])
        _news_cache[cache_key] = news
        _news_cache_ts[cache_key] = now
        return news[:limit]
    except Exception as e:
        logger.warning(f"RapidAPI news fetch failed for {symbol}: {e}")
        return []


def _fetch_cash_flow(symbol: str) -> list:
    """Fetch company cash flow from RapidAPI."""
    if not RAPIDAPI_KEY:
        logger.warning("RAPIDAPI_KEY is not set; skipping cash flow fetch")
        return []
    try:
        url = f"{RAPIDAPI_BASE_URL}/company-cash-flow"
        headers = {"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": RAPIDAPI_HOST}
        params = {"symbol": symbol, "period": "QUARTERLY", "language": "en"}
        resp = _requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data.get("data", {}).get("cash_flow", [])[:5]
    except Exception as e:
        logger.warning(f"RapidAPI cash flow fetch failed: {e}")
        return []


_SYMBOL_MAP = {
    "apple": "AAPL:NASDAQ", "google": "GOOGL:NASDAQ", "microsoft": "MSFT:NASDAQ",
    "amazon": "AMZN:NASDAQ", "tesla": "TSLA:NASDAQ", "meta": "META:NASDAQ",
    "nvidia": "NVDA:NASDAQ", "netflix": "NFLX:NASDAQ", "reliance": "RELIANCE:NSE",
    "tcs": "TCS:NSE", "infosys": "INFY:NSE", "wipro": "WIPRO:NSE",
    "hdfc": "HDFCBANK:NSE", "icici": "ICICIBANK:NSE", "sbi": "SBIN:NSE",
}


def _resolve_symbol(query: str) -> str:
    """Resolve a user query to a stock symbol."""
    q = query.lower().strip()
    for name, sym in _SYMBOL_MAP.items():
        if name in q:
            return sym
    # If it already looks like a symbol
    if ":" in query:
        return query.strip()
    # Fallback: treat as NASDAQ symbol
    token = query.strip().split()[0].upper()
    if len(token) <= 5 and token.isalpha():
        return f"{token}:NASDAQ"
    return "AAPL:NASDAQ"


@tool
def finance_news_search(query: str) -> str:
    """Search for the latest financial news about a stock, company, or market topic. Input can be a company name like 'Apple' or symbol like 'AAPL:NASDAQ'."""
    symbol = _resolve_symbol(query)
    news = _fetch_stock_news(symbol, limit=5)
    if not news:
        return f"No news found for {symbol}."
    output = []
    for item in news:
        output.append(
            f"📰 {item.get('article_title', 'N/A')}\n"
            f"   Source: {item.get('source', 'N/A')} | {item.get('post_time_utc', '')}\n"
            f"   {item.get('snippet', '')[:200]}"
        )
    return "\n\n".join(output)


@tool
def finance_cash_flow(query: str) -> str:
    """Fetch quarterly cash flow data for a company. Input can be a company name like 'Apple' or symbol like 'AAPL:NASDAQ'."""
    symbol = _resolve_symbol(query)
    cf = _fetch_cash_flow(symbol)
    if not cf:
        return f"No cash flow data found for {symbol}."
    output = []
    for item in cf:
        output.append(
            f"📊 Date: {item.get('date', 'N/A')}\n"
            f"💰 Operating Cash Flow: {item.get('operating_cash_flow', 'N/A')}\n"
            f"📉 Free Cash Flow: {item.get('free_cash_flow', 'N/A')}"
        )
    return "\n\n".join(output)


# ─── YouTube Search Tool (User Requested) ────────────────────────────────────

@tool
def custom_yt_search(query: str) -> str:
    """search for youtube videos associated with a specific query or topic. The input should be a search string like 'startup basics'."""
    try:
        from youtube_search import YoutubeSearch
        val = query.split(",")[0] if "," in query else query
        results = YoutubeSearch(val, max_results=3).to_json()
        data = json.loads(results)
        urls = []
        for video in data.get('videos', []):
            title = video.get('title')
            url = f"https://www.youtube.com{video.get('url_suffix')}"
            urls.append(f"- **{title}**: {url}")
        return "\n".join(urls) if urls else "No videos found."
    except Exception as e:
        return f"Error searching YouTube: {e}"


# ─── State ────────────────────────────────────────────────────────────────────

class FinScopeState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], add_messages]
    intent: str
    document_text: str
    user_profile: str


# ─── System Prompts ──────────────────────────────────────────────────────────

INTENT_CLASSIFIER_PROMPT = """You classify user messages into ONE category. Reply with ONLY the category word.

Categories:
- "education" — Questions about investment concepts, requests for YouTube videos or tutorials, terms, how things work
- "document" — Questions about an uploaded/analyzed document, or requests to analyze content
- "market" — Questions about market trends, sectors, specific stocks/funds, current data
- "strategy" — Questions about personal investment strategy, portfolio allocation, risk management
- "news" — Requests for latest news, headlines, stock updates, breaking news, what's happening with a company

If the user references "this document", "the document", "this startup", "what does it say" — classify as "document".
If the user asks "what is", "explain", "how does", "teach me", "video", "youtube" — classify as "education".
If the user asks "news", "latest", "headlines", "what's happening", "updates", "breaking" — classify as "news".

Reply with ONLY one keyword: education, document, market, strategy, or news."""

FINANCIAL_EDUCATOR_PROMPT = """You are FinScope's Financial Educator.
INSTRUCTIONS:
1. Teach investment concepts clearly.
2. If YouTube video results are provided below, you MUST weave them into your response exactly as provided.
3. Keep responses concise."""

DOCUMENT_ANALYZER_PROMPT = """You are FinScope's Document Analyzer — an expert at reading financial documents for non-expert investors.

RULES:
- You MUST start your response with a flashcard summary formatted EXACTLY like this (use these exact tags):
[FLASHCARD]
Title: <Name of the company/startup>
Highlight: <1 sentence summarizing the most important takeaway>
Verdict: <Positive / Neutral / Warning>
Team: <Comma separated list of key team members, or 'Not specified'>
KeyMetrics: <List most important metric like '$1M ARR', or 'Pre-revenue'>
What It Does: <1 concise sentence explaining the product/service>
[/FLASHCARD]

- IMMEDIATELY after the [/FLASHCARD] tag, you MUST also include a competitor comparison chart block formatted EXACTLY like this:
[COMPETITOR_CHART]
{
  "company": "<Name of the company from the document>",
  "competitors": ["<Competitor1>", "<Competitor2>", "<Competitor3>"],
  "metrics": {
    "marketShare": { "company": <number 0-100>, "competitors": [<number>, <number>, <number>] },
    "accuracy": { "company": <number 0-100>, "competitors": [<number>, <number>, <number>] },
    "growthRate": { "company": <number 0-100>, "competitors": [<number>, <number>, <number>] },
    "fundingM": { "company": <number in millions>, "competitors": [<number>, <number>, <number>] },
    "customerBase": { "company": <number>, "competitors": [<number>, <number>, <number>] }
  },
  "strengths": ["<strength1>", "<strength2>", "<strength3>"],
  "weaknesses": ["<weakness1>", "<weakness2>"]
}
[/COMPETITOR_CHART]

IMPORTANT for the [COMPETITOR_CHART] block:
- Use REAL competitor names mentioned in the document, or well-known competitors in the same industry.
- Use REALISTIC numbers based on publicly known data about the competitors and the company's claims.
- For medical AI: competitors could include Qure.ai, Lunit, Aidoc, Zebra Medical, etc.
- For fintech: competitors could include Stripe, Square, Razorpay, etc.
- marketShare is estimated % of addressable market, accuracy is product accuracy/quality score (%), growthRate is YoY growth %, fundingM is total funding in millions USD, customerBase is approximate number of clients/hospitals/users.
- Provide at least 3 competitors with realistic data.
- Strengths and weaknesses should be brief 5-8 word phrases.

- After both blocks, provide your detailed analysis.
- Highlight key financial metrics and explain them.
- Flag red flags or concerns.
- Ensure the flashcard strictly uses the tags [FLASHCARD] and [/FLASHCARD].
- Ensure the competitor chart strictly uses the tags [COMPETITOR_CHART] and [/COMPETITOR_CHART]."""

MARKET_RESEARCHER_PROMPT = """You are FinScope's Market Researcher. Provide data-driven market analysis and sector trends."""

NEWS_REPORTER_PROMPT = """You are FinScope's News Reporter — a real-time financial news analyst.

You have been provided with LIVE financial news data fetched from real-time APIs.

RULES:
- You MUST format the news as flashcards using the [NEWS_CARD] tag.
- Format EXACTLY like this:
[NEWS_CARD]
{
  "symbol": "<STOCK_SYMBOL>",
  "articles": [
    {
      "title": "<article title>",
      "source": "<source name>",
      "time": "<publication time>",
      "snippet": "<brief summary, 1-2 sentences>",
      "sentiment": "positive" or "negative" or "neutral",
      "url": "<article url if available>",
      "photo": "<photo url if available>"
    }
  ]
}
[/NEWS_CARD]

- After the [NEWS_CARD] block, provide a brief 2-3 sentence market sentiment summary.
- Mention key takeaways and how the news might impact investors.
- Be concise and data-driven.
- Use the actual news data provided — do NOT make up articles."""

PORTFOLIO_COACH_PROMPT = """You are FinScope's Portfolio Coach. You help users build conservative and moderate investment portfolios.

IMPORTANT RULE:
If the user asks "Should I invest?", "How to invest?", or requests portfolio advice but HAS NOT specified their financial goals, risk tolerance, and time horizon, do NOT write a large wall of text advising them.
Instead, you MUST use the interactive form widget by outputting EXACTLY this text:
[PORTFOLIO_FORM]

When the user fills out the form in their UI, they will automatically reply with their Risk Tolerance, Time Horizon, and Goal. 
THEN, you must provide a compact, concise allocation table using Markdown. Keep text extremely brief."""


# ─── Node Functions ──────────────────────────────────────────────────────────

def classify_intent(state: FinScopeState) -> dict:
    logger.info("--- FINSCOPE: CLASSIFY INTENT ---")
    doc_text = state.get("document_text", "").strip()
    messages = state["messages"]
    last_msg = messages[-1].content if messages else ""
    last_msg_lower = last_msg.lower() if isinstance(last_msg, str) else str(last_msg).lower()

    if "video" in last_msg_lower or "youtube" in last_msg_lower:
        return {"intent": "education"}

    # Fast-path for news queries
    news_keywords = ["news", "headline", "latest", "breaking", "updates", "what's happening", "whats happening"]
    if any(kw in last_msg_lower for kw in news_keywords):
        return {"intent": "news"}

    if doc_text and any(kw in last_msg_lower for kw in ["document", "startup", "company", "analyze", "this"]):
        return {"intent": "document"}

    llm = _get_llm(temperature=0.0, max_tokens=20)
    try:
        response = llm.invoke([
            SystemMessage(content=INTENT_CLASSIFIER_PROMPT),
            HumanMessage(content=str(last_msg)),
        ])
        intent = response.content.strip().lower().replace('"', '').replace("'", "")
        if intent not in {"education", "document", "market", "strategy", "news"}:
            intent = "education"
    except Exception:
        intent = "education"

    logger.info(f"Intent classified: {intent}")
    return {"intent": intent}


async def financial_educator(state: FinScopeState) -> dict:
    logger.info("--- SUBAGENT: FINANCIAL EDUCATOR ---")
    messages = state["messages"]
    last_msg = messages[-1].content if messages else ""
    last_msg_lower = last_msg.lower() if isinstance(last_msg, str) else str(last_msg).lower()
    
    # Manually search YouTube if requested
    yt_results = ""
    if "video" in last_msg_lower or "youtube" in last_msg_lower:
        logger.info(f"User requested video. Querying YouTube for: {last_msg}")
        yt_results = custom_yt_search.invoke(last_msg)
        yt_context = f"\n\n=== YOUTUBE VIDEO RESULTS ===\n{yt_results}\n==========================="
    else:
        yt_context = ""
    
    system = FINANCIAL_EDUCATOR_PROMPT + yt_context
    llm = _get_llm(temperature=0.4, max_tokens=1800)
    response = llm.invoke([SystemMessage(content=system)] + list(messages))
    
    return {"messages": [AIMessage(content=response.content)]}


def document_analyzer(state: FinScopeState) -> dict:
    logger.info("--- SUBAGENT: DOCUMENT ANALYZER ---")
    llm = _get_llm(temperature=0.2, max_tokens=2500)
    messages = state["messages"]
    doc_text = state.get("document_text", "")
    
    if doc_text:
        system = DOCUMENT_ANALYZER_PROMPT + f"\n\n=== DOCUMENT DATA ===\n{doc_text[:8000]}"
    else:
        system = DOCUMENT_ANALYZER_PROMPT + "\n\nNo document has been uploaded yet."

    response = llm.invoke([SystemMessage(content=system)] + list(messages))
    return {"messages": [AIMessage(content=response.content)]}


def market_researcher(state: FinScopeState) -> dict:
    logger.info("--- SUBAGENT: MARKET RESEARCHER ---")
    llm = _get_llm(temperature=0.3, max_tokens=2000)
    response = llm.invoke([SystemMessage(content=MARKET_RESEARCHER_PROMPT)] + list(state["messages"]))
    return {"messages": [AIMessage(content=response.content)]}


def portfolio_coach(state: FinScopeState) -> dict:
    logger.info("--- SUBAGENT: PORTFOLIO COACH ---")
    llm = _get_llm(temperature=0.3, max_tokens=2000)
    response = llm.invoke([SystemMessage(content=PORTFOLIO_COACH_PROMPT)] + list(state["messages"]))
    return {"messages": [AIMessage(content=response.content)]}


def news_reporter(state: FinScopeState) -> dict:
    logger.info("--- SUBAGENT: NEWS REPORTER ---")
    messages = state["messages"]
    last_msg = messages[-1].content if messages else ""
    last_msg_str = last_msg if isinstance(last_msg, str) else str(last_msg)

    # Resolve symbol from user query
    symbol = _resolve_symbol(last_msg_str)
    logger.info(f"Fetching news for symbol: {symbol}")

    # Fetch live news
    news = _fetch_stock_news(symbol, limit=6)
    if news:
        news_context = "\n\n=== LIVE NEWS DATA ==="
        for item in news:
            news_context += (
                f"\n📰 Title: {item.get('article_title', 'N/A')}"
                f"\n   Source: {item.get('source', 'N/A')}"
                f"\n   Time: {item.get('post_time_utc', 'N/A')}"
                f"\n   URL: {item.get('article_url', '')}"
                f"\n   Photo: {item.get('article_photo_url', '')}"
                f"\n   Snippet: {item.get('snippet', '')[:300]}"
                f"\n---"
            )
        news_context += "\n=== END NEWS DATA ==="
    else:
        news_context = "\n\nNo live news data available. Use your knowledge to provide general market context."

    system = NEWS_REPORTER_PROMPT + news_context
    llm = _get_llm(temperature=0.3, max_tokens=2500)
    response = llm.invoke([SystemMessage(content=system)] + list(messages))
    return {"messages": [AIMessage(content=response.content)]}


def route_to_subagent(state: FinScopeState) -> str:
    return {
        "education": "financial_educator",
        "document":  "document_analyzer",
        "market":    "market_researcher",
        "strategy":  "portfolio_coach",
        "news":      "news_reporter",
    }.get(state.get("intent", "education"), "financial_educator")


def build_finscope_graph():
    wf = StateGraph(FinScopeState)

    wf.add_node("classify_intent",    classify_intent)
    wf.add_node("financial_educator", financial_educator)
    wf.add_node("document_analyzer",  document_analyzer)
    wf.add_node("market_researcher",  market_researcher)
    wf.add_node("portfolio_coach",    portfolio_coach)
    wf.add_node("news_reporter",      news_reporter)

    wf.add_edge(START, "classify_intent")
    wf.add_conditional_edges(
        "classify_intent",
        route_to_subagent,
        {
            "financial_educator": "financial_educator",
            "document_analyzer":  "document_analyzer",
            "market_researcher":  "market_researcher",
            "portfolio_coach":    "portfolio_coach",
            "news_reporter":      "news_reporter",
        },
    )

    wf.add_edge("financial_educator", END)
    wf.add_edge("document_analyzer",  END)
    wf.add_edge("market_researcher",  END)
    wf.add_edge("portfolio_coach",    END)
    wf.add_edge("news_reporter",      END)

    return wf.compile()


async def run_finscope_chat(
    question: str,
    user_profile: str = "beginner",
    document_text: str = "",
    session_id: str = "",
) -> Dict[str, str]:
    
    if not document_text and session_id:
        document_text = get_session_document(session_id)

    graph = build_finscope_graph()
    initial_state = {
        "messages":      [HumanMessage(content=question)],
        "intent":        "",
        "document_text": document_text,
        "user_profile":  user_profile,
    }

    result = await graph.ainvoke(initial_state, {"recursion_limit": 10})
    
    final_message = result["messages"][-1]
    content = final_message.content if isinstance(final_message.content, str) else str(final_message.content)
    intent = result.get("intent", "education")

    agent_map = {
        "education": "Financial Educator",
        "document":  "Document Analyzer",
        "market":    "Market Researcher",
        "strategy":  "Portfolio Coach",
        "news":      "News Reporter",
    }

    return {
        "answer": content,
        "intent": intent,
        "agent": agent_map.get(intent, "Financial Educator"),
    }


FINSCOPE_TOPICS = []
FINSCOPE_GLOSSARY = []
