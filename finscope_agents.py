"""
FinScope — multi-subagent financial advisory system (LangGraph).

    START → classify_intent ─┬→ financial_educator  (explains concepts + YouTube videos)
                             ├→ document_analyzer   ([FLASHCARD] + [COMPETITOR_CHART] + RAG Q&A)
                             ├→ market_researcher   (live web research with sources)
                             ├→ portfolio_coach     ([PORTFOLIO_FORM] → allocation table)
                             └→ news_reporter       ([NEWS_CARD] with sentiment)
                                         → END

Each chat session keeps its history and uploaded document, so follow-up questions work.
"""

import asyncio
import json
import logging
import re
import time
from datetime import datetime
from typing import Annotated, Any, Dict, List, Optional, Sequence, TypedDict

import httpx
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages

from aura import store, vector_store
from aura.config import RAPIDAPI_KEY
from aura.llm import ainvoke_json, get_llm
from aura.search import format_results, news_search, web_search

logger = logging.getLogger("aura.finscope")

AGENT_NAMES = {
    "education": "Financial Educator",
    "document":  "Document Analyzer",
    "market":    "Market Researcher",
    "strategy":  "Portfolio Coach",
    "news":      "News Reporter",
}

_HISTORY_TURNS = 8


# ─── Session memory ───────────────────────────────────────────────────────────

def _session(session_id: str) -> Dict[str, Any]:
    return store.finscope_sessions.setdefault(
        session_id or "anonymous",
        {"history": [], "document_name": "", "document_text": "", "created_at": datetime.utcnow().isoformat() + "Z"},
    )


def _session_collection(session_id: str) -> str:
    return f"session_{session_id}"


def store_session_document(session_id: str, document_name: str, document_text: str, chunks: List[Dict[str, Any]]) -> None:
    session = _session(session_id)
    session.update({"document_name": document_name, "document_text": document_text[:60000]})
    try:
        vector_store.reset(_session_collection(session_id))
        vector_store.add_texts(
            _session_collection(session_id),
            [c["text"] for c in chunks],
            [c["metadata"] for c in chunks],
        )
    except Exception as e:
        logger.warning(f"FinScope ▸ Could not index document for RAG ({e}); using raw text")
    store.save()


def _strip_widgets(text: str) -> str:
    text = re.sub(r"\[(COMPETITOR_CHART|NEWS_CARD)\][\s\S]*?\[/\1\]", "[chart data omitted]", text)
    return text.replace("[PORTFOLIO_FORM]", "").strip()[:2500]


def _history_messages(session: Dict[str, Any]) -> List[BaseMessage]:
    messages: List[BaseMessage] = []
    for turn in session["history"][-_HISTORY_TURNS:]:
        content = _strip_widgets(turn["content"])
        messages.append(HumanMessage(content=content) if turn["role"] == "user" else AIMessage(content=content))
    return messages


# ─── External data helpers ────────────────────────────────────────────────────

_SYMBOL_MAP = {
    "apple": "AAPL:NASDAQ", "google": "GOOGL:NASDAQ", "alphabet": "GOOGL:NASDAQ",
    "microsoft": "MSFT:NASDAQ", "amazon": "AMZN:NASDAQ", "tesla": "TSLA:NASDAQ",
    "meta": "META:NASDAQ", "facebook": "META:NASDAQ", "nvidia": "NVDA:NASDAQ",
    "netflix": "NFLX:NASDAQ", "reliance": "RELIANCE:NSE", "tcs": "TCS:NSE",
    "infosys": "INFY:NSE", "wipro": "WIPRO:NSE", "hdfc": "HDFCBANK:NSE",
    "icici": "ICICIBANK:NSE", "sbi": "SBIN:NSE", "zomato": "ZOMATO:NSE",
    "paytm": "PAYTM:NSE", "tata motors": "TATAMOTORS:NSE", "bitcoin": "BTC-USD",
}

_news_cache: Dict[str, Any] = {}
_NEWS_TTL = 300


def fetch_stock_news(symbol_or_query: str, limit: int = 6) -> List[Dict[str, Any]]:
    """Live news in RapidAPI's shape. Uses RapidAPI when keyed, DuckDuckGo News otherwise."""
    key = f"{symbol_or_query}:{limit}"
    cached = _news_cache.get(key)
    if cached and time.time() - cached[0] < _NEWS_TTL:
        return cached[1]

    news: List[Dict[str, Any]] = []
    if RAPIDAPI_KEY and ":" in symbol_or_query:
        try:
            resp = httpx.get(
                "https://real-time-finance-data.p.rapidapi.com/stock-news",
                headers={"X-RapidAPI-Key": RAPIDAPI_KEY, "X-RapidAPI-Host": "real-time-finance-data.p.rapidapi.com"},
                params={"symbol": symbol_or_query, "language": "en"},
                timeout=10,
            )
            resp.raise_for_status()
            news = resp.json().get("data", {}).get("news", [])[:limit]
        except Exception as e:
            logger.warning(f"RapidAPI news failed for {symbol_or_query}: {e}")
    if not news:
        query = symbol_or_query.split(":")[0]
        news = news_search(f"{query} stock market news", max_results=limit)
    _news_cache[key] = (time.time(), news)
    return news


def _youtube_videos(query: str, limit: int = 3) -> List[Dict[str, str]]:
    """YouTube videos for a topic: DuckDuckGo video search first, direct YouTube search as fallback."""
    videos: List[Dict[str, str]] = []
    try:
        from ddgs import DDGS

        for hit in DDGS(timeout=10).videos(query, max_results=limit * 3):
            match = re.search(r"youtube\.com/watch\?v=([A-Za-z0-9_-]{6,})", hit.get("content", ""))
            if match and len(videos) < limit:
                videos.append({"title": hit.get("title", "Video"), "id": match.group(1)})
    except Exception as e:
        logger.warning(f"FinScope ▸ DuckDuckGo video search failed: {e}")
    if videos:
        return videos
    for hit in web_search(f"{query} site:youtube.com", max_results=limit * 3):
        match = re.search(r"youtube\.com/watch\?v=([A-Za-z0-9_-]{6,})", hit.get("url", ""))
        if match and len(videos) < limit:
            videos.append({"title": re.sub(r"\s*-\s*YouTube$", "", hit.get("title") or "Video"), "id": match.group(1)})
    if videos:
        return videos
    try:
        from youtube_search import YoutubeSearch

        data = json.loads(YoutubeSearch(query, max_results=limit).to_json())
    except Exception as e:
        logger.warning(f"FinScope ▸ YouTube search failed: {e}")
        return []
    for video in data.get("videos", []):
        match = re.search(r"v=([A-Za-z0-9_-]{6,})", video.get("url_suffix", ""))
        if match:
            videos.append({"title": video.get("title", "Video"), "id": match.group(1)})
    return videos


# ─── State ────────────────────────────────────────────────────────────────────

class FinScopeState(TypedDict):
    messages:      Annotated[Sequence[BaseMessage], add_messages]
    question:      str
    intent:        str
    session_id:    str
    user_profile:  str
    analyze_document: bool


def _profile_note(state: FinScopeState) -> str:
    return (
        f"The user describes themselves as a '{state.get('user_profile') or 'beginner'}' investor. "
        "Match your depth to that. Use GitHub markdown. Never promise returns; you are an "
        "educational assistant, not a licensed advisor."
    )


# ─── Intent classifier ────────────────────────────────────────────────────────

_INTENT_PROMPT = """Classify the user's latest message into exactly one intent for a finance assistant.

- "education": explain a concept, term or how something works; asks for videos or tutorials
- "document": about an uploaded document, pitch deck or "this company/startup" when a document exists
- "market": market trends, sectors, specific stocks or funds, market size, comparisons, current data
- "strategy": personal investing plan, portfolio allocation, risk, retirement, "should I invest"
- "news": latest news, headlines, what happened today, updates about a company or market

Use the conversation for context (a short follow-up usually keeps the previous intent).
Reply as JSON: {"intent": "<education|document|market|strategy|news>", "reason": "<short>"}"""


async def classify_intent(state: FinScopeState) -> dict:
    question = state["question"]
    lower = question.lower()
    session = _session(state["session_id"])
    has_doc = bool(session.get("document_text"))

    if state.get("analyze_document"):
        intent, reason = "document", "document upload"
    elif re.search(r"\b(video|videos|youtube|tutorial)\b", lower):
        intent, reason = "education", "asked for videos"
    elif re.search(r"risk tolerance is .+ time horizon is", lower):
        intent, reason = "strategy", "portfolio form submitted"
    elif re.search(r"\b(news|headlines?|breaking|latest update|what'?s happening)\b", lower):
        intent, reason = "news", "news keywords"
    elif has_doc and re.search(r"\b(document|deck|pitch|this (startup|company|report|file|pdf))\b", lower):
        intent, reason = "document", "refers to uploaded document"
    else:
        try:
            result = await ainvoke_json(
                _INTENT_PROMPT,
                f"Document uploaded in this chat: {'yes — ' + session['document_name'] if has_doc else 'no'}\n"
                f"Latest message: {question}",
                max_tokens=120,
                history=_history_messages(session)[-4:],
            )
            intent = str(result.get("intent", "")).lower()
            reason = result.get("reason", "")
        except Exception as e:
            logger.warning(f"FinScope ▸ Intent classifier failed ({e}); defaulting to education")
            intent, reason = "education", "classifier fallback"
        if intent not in AGENT_NAMES:
            intent = "education"
    logger.info(f"FinScope ▸ Intent '{intent}' → {AGENT_NAMES[intent]} ({reason})")
    return {"intent": intent}


def route_to_subagent(state: FinScopeState) -> str:
    return {
        "education": "financial_educator",
        "document":  "document_analyzer",
        "market":    "market_researcher",
        "strategy":  "portfolio_coach",
        "news":      "news_reporter",
    }.get(state.get("intent", "education"), "financial_educator")


async def _chat(system: str, state: FinScopeState, temperature: float = 0.3, max_tokens: int = 1800) -> str:
    llm = get_llm(temperature=temperature, max_tokens=max_tokens)
    response = await llm.ainvoke([SystemMessage(content=system)] + list(state["messages"]))
    return str(response.content).strip()


# ─── Subagents ────────────────────────────────────────────────────────────────

_VIDEO_REQUEST = re.compile(
    r"\b(can you |please )?(show|give|find|send|share|suggest|recommend)?( me)?( a| some| any)?"
    r"( good)?( youtube)? (videos?|tutorials?)( on| about| for| explaining)?( it| this| that)?\b",
    re.IGNORECASE,
)


def _video_topic(question: str) -> str:
    topic = _VIDEO_REQUEST.sub(" ", question)
    topic = re.sub(r"\b(what is|what are|explain|tell me about|how does|how do)\b", " ", topic, flags=re.IGNORECASE)
    topic = re.sub(r"[?.!,]+", " ", topic)
    topic = re.sub(r"^\s*(a|an|the)\s+|\s+(with|on|about|for|using)\s*$", " ", topic.strip(), flags=re.IGNORECASE)
    return " ".join(topic.split())[:80] or question[:80]


async def financial_educator(state: FinScopeState) -> dict:
    logger.info("FinScope ▸ Financial Educator is preparing an explanation")
    topic = _video_topic(state["question"])
    videos = await asyncio.to_thread(_youtube_videos, f"{topic} explained", 3)
    if videos:
        logger.info(f"FinScope ▸ Found {len(videos)} YouTube videos for '{topic}'")
        video_note = "Relevant YouTube videos are attached below your answer; you may point to them."
    else:
        video_note = "No videos could be fetched right now; do not mention videos or links."
    system = (
        "You are FinScope's Financial Educator. Teach investing and startup-finance concepts "
        "clearly: start with a one-line definition, then explain with a concrete example (use ₹ or $), "
        "then list 2-3 key takeaways. Keep it under 300 words. Do not include any links. "
        f"{video_note} " + _profile_note(state)
    )
    answer = await _chat(system, state, temperature=0.4)
    if videos:
        answer += "\n\n" + "\n".join(
            f"- {v['title'].replace(':', ' -')}: https://www.youtube.com/watch?v={v['id']}" for v in videos
        )
    return {"messages": [AIMessage(content=answer)]}


_FLASHCARD_SYSTEM = """Read the document and return JSON:
{"title": "<company/startup name>", "highlight": "<single most important takeaway, one sentence>",
 "verdict": "<Positive|Neutral|Warning>", "team": "<key people, comma separated, or 'Not specified'>",
 "key_metrics": "<most important metric e.g. '$1.2M ARR' or 'Pre-revenue'>",
 "what_it_does": "<one sentence>"}
Use only facts from the document."""

_COMPETITOR_SYSTEM = """You compare a company with its three closest real competitors. Return JSON:
{"company": "<name>", "competitors": ["<c1>", "<c2>", "<c3>"],
 "metrics": {
   "marketShare":  {"company": <0-100>, "competitors": [<n>, <n>, <n>]},
   "accuracy":     {"company": <0-100 product quality score>, "competitors": [<n>, <n>, <n>]},
   "growthRate":   {"company": <YoY growth %, 0-100>, "competitors": [<n>, <n>, <n>]},
   "fundingM":     {"company": <total funding USD millions>, "competitors": [<n>, <n>, <n>]},
   "customerBase": {"company": <approx customers>, "competitors": [<n>, <n>, <n>]}},
 "strengths": ["<5-8 words>", "<5-8 words>", "<5-8 words>"],
 "weaknesses": ["<5-8 words>", "<5-8 words>"]}
Use well-known real competitors in the same industry and realistic public figures; use the
document's own claims for the company. All metric values must be plain numbers."""


def _clean_competitors(data: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    try:
        competitors = [str(c) for c in data.get("competitors", [])][:3]
        if not competitors:
            return None
        metrics = {}
        for key in ("marketShare", "accuracy", "growthRate", "fundingM", "customerBase"):
            raw = (data.get("metrics") or {}).get(key) or {}
            values = [float(x) for x in (raw.get("competitors") or [])][: len(competitors)]
            values += [0.0] * (len(competitors) - len(values))
            metrics[key] = {"company": float(raw.get("company") or 0), "competitors": values}
        return {
            "company": str(data.get("company") or "Company"),
            "competitors": competitors,
            "metrics": metrics,
            "strengths": [str(s) for s in data.get("strengths", [])][:3],
            "weaknesses": [str(w) for w in data.get("weaknesses", [])][:3],
        }
    except (TypeError, ValueError):
        return None


async def document_analyzer(state: FinScopeState) -> dict:
    session = _session(state["session_id"])
    doc_text = session.get("document_text", "")
    if not doc_text:
        logger.info("FinScope ▸ Document Analyzer: no document in this chat")
        return {"messages": [AIMessage(content=(
            "I don't have a document for this chat yet. Attach a pitch deck, annual report or "
            "term sheet with the 📎 button and I'll break it down for you."
        ))]}

    if not state.get("analyze_document"):
        logger.info("FinScope ▸ Document Analyzer: retrieving relevant passages for follow-up question")
        try:
            hits = await asyncio.to_thread(vector_store.search, _session_collection(state["session_id"]), state["question"], 6)
            context = "\n\n---\n\n".join(h["text"] for h in hits) or doc_text[:8000]
        except Exception:
            context = doc_text[:8000]
        system = (
            f"You are FinScope's Document Analyzer. Answer using the document '{session['document_name']}'. "
            "Quote figures exactly, say clearly when the document does not contain the answer, and flag red "
            f"flags. {_profile_note(state)}\n\n=== RELEVANT DOCUMENT PASSAGES ===\n{context}"
        )
        return {"messages": [AIMessage(content=await _chat(system, state, temperature=0.2))]}

    logger.info(f"FinScope ▸ Document Analyzer: full analysis of '{session['document_name']}'")
    excerpt = doc_text[:14000]
    user_ask = state["question"]
    focus = (
        f"The user uploaded it with this request — answer it directly first: \"{user_ask}\". "
        if not user_ask.lower().startswith("analyze this document") else ""
    )
    analysis_system = (
        "You are FinScope's Document Analyzer, explaining a financial or startup document to a "
        f"non-expert investor. {focus}Then write sections: **What the company does**, **Key numbers** "
        "(a markdown table of the most important metrics with a one-line meaning each), **Strengths**, "
        "**Red flags & open questions**, **Bottom line**. Be specific and quote the document. "
        + _profile_note(state)
    )
    flashcard, competitors, narrative = await asyncio.gather(
        ainvoke_json(_FLASHCARD_SYSTEM, excerpt[:9000], max_tokens=500),
        ainvoke_json(_COMPETITOR_SYSTEM, excerpt[:6000], max_tokens=900),
        get_llm(temperature=0.2, max_tokens=2200).ainvoke(
            [SystemMessage(content=analysis_system), HumanMessage(content=f"DOCUMENT:\n{excerpt}")]
        ),
        return_exceptions=True,
    )

    parts: List[str] = []
    if isinstance(flashcard, dict):
        parts.append(
            "[FLASHCARD]\n"
            f"Title: {flashcard.get('title', 'Startup Analysis')}\n"
            f"Highlight: {flashcard.get('highlight', '')}\n"
            f"Verdict: {flashcard.get('verdict', 'Neutral')}\n"
            f"Team: {flashcard.get('team', 'Not specified')}\n"
            f"KeyMetrics: {flashcard.get('key_metrics', 'Not specified')}\n"
            f"What It Does: {flashcard.get('what_it_does', 'Not specified')}\n"
            "[/FLASHCARD]"
        )
    else:
        logger.warning(f"FinScope ▸ Flashcard generation failed: {flashcard}")
    chart = _clean_competitors(competitors) if isinstance(competitors, dict) else None
    if chart:
        logger.info(f"FinScope ▸ Competitor map: {chart['company']} vs {', '.join(chart['competitors'])}")
        parts.append(f"[COMPETITOR_CHART]\n{json.dumps(chart)}\n[/COMPETITOR_CHART]")
    parts.append(str(narrative.content).strip() if not isinstance(narrative, Exception) else
                 "I extracted the document but could not complete the written analysis. Ask me a question about it.")
    return {"messages": [AIMessage(content="\n\n".join(parts))]}


async def market_researcher(state: FinScopeState) -> dict:
    logger.info("FinScope ▸ Market Researcher is planning web research")
    try:
        plan = await ainvoke_json(
            'Write 2 focused web search queries to research the user\'s market question with current data. '
            'Reply as JSON {"queries": ["...", "..."]}.',
            state["question"],
            max_tokens=150,
            history=_history_messages(_session(state["session_id"]))[-2:],
        )
        queries = [str(q) for q in plan.get("queries", [])][:2] or [state["question"]]
    except Exception:
        queries = [state["question"]]
    results = await asyncio.gather(*(asyncio.to_thread(web_search, q, 5) for q in queries))
    research = "\n\n".join(format_results(r, q) for r, q in zip(results, queries))
    sources = {r["url"]: r["title"] for batch in results for r in batch if r.get("url")}
    logger.info(f"FinScope ▸ Market Researcher gathered {len(sources)} sources")
    system = (
        "You are FinScope's Market Researcher. Give a data-driven answer: lead with the direct answer, "
        "then key figures (size, growth, leaders) in a short markdown table where useful, then trends and "
        "what it means for an investor. Cite sources inline as [1], [2] matching the research list. "
        f"If data is missing, say so. {_profile_note(state)}\n\n=== WEB RESEARCH ===\n{research}"
    )
    answer = await _chat(system, state, temperature=0.3, max_tokens=2000)
    if sources:
        answer += "\n\n**Sources**\n" + "\n".join(
            f"{i}. [{title or url}]({url})" for i, (url, title) in enumerate(list(sources.items())[:6], start=1)
        )
    return {"messages": [AIMessage(content=answer)]}


_RISK_RE = re.compile(r"\b(conservative|moderate|aggressive|low[- ]risk|high[- ]risk|medium[- ]risk|risk tolerance)\b", re.I)
_HORIZON_RE = re.compile(r"(\d+\s*\+?\s*(yrs?|years?)|time horizon|long[- ]term|short[- ]term|retire)", re.I)


async def portfolio_coach(state: FinScopeState) -> dict:
    session = _session(state["session_id"])
    recent_user = " ".join(t["content"] for t in session["history"][-4:] if t["role"] == "user") + " " + state["question"]
    if not (_RISK_RE.search(recent_user) and _HORIZON_RE.search(recent_user)):
        logger.info("FinScope ▸ Portfolio Coach needs risk tolerance and horizon — showing form")
        return {"messages": [AIMessage(content=(
            "To suggest an allocation I need three things: your risk tolerance, your time horizon and "
            "your goal. Fill this in and I'll build it.\n\n[PORTFOLIO_FORM]"
        ))]}
    logger.info("FinScope ▸ Portfolio Coach is building an allocation")
    system = (
        "You are FinScope's Portfolio Coach. Using the user's risk tolerance, time horizon and goal, give: "
        "(1) a markdown table with columns Asset class | Allocation % | Example instruments | Why, summing to "
        "100%; (2) three short rules for rebalancing and risk; (3) one line on how much, if any, belongs in "
        "early-stage startups or DAO investments. Keep the text brief. Include a one-line reminder that this "
        f"is educational, not personalised advice. {_profile_note(state)}"
    )
    return {"messages": [AIMessage(content=await _chat(system, state, temperature=0.2))]}


async def news_reporter(state: FinScopeState) -> dict:
    question = state["question"]
    lower = question.lower()
    symbol = next((sym for name, sym in _SYMBOL_MAP.items() if name in lower), "")
    topic = ""
    if not symbol:
        try:
            target = await ainvoke_json(
                'Extract what the user wants news about. Reply as JSON {"topic": "<company, sector or market>", '
                '"symbol": "<TICKER:EXCHANGE if a listed company, e.g. AAPL:NASDAQ or TCS:NSE, else empty>"}',
                question,
                max_tokens=80,
            )
            symbol = str(target.get("symbol") or "")
            topic = str(target.get("topic") or "")
        except Exception:
            pass
    lookup = symbol or topic or "stock market"
    logger.info(f"FinScope ▸ News Reporter fetching live news for '{lookup}'")
    articles = await asyncio.to_thread(fetch_stock_news, lookup, 6)

    if not articles:
        logger.info("FinScope ▸ No live articles found")
        system = (
            "You are FinScope's News Reporter. No live articles could be fetched right now. Say so in one line, "
            f"then give brief general context on the topic from your knowledge. {_profile_note(state)}"
        )
        return {"messages": [AIMessage(content=await _chat(system, state))]}

    listing = "\n".join(
        f"{i}. {a.get('article_title', '')} — {a.get('source', '')}: {str(a.get('snippet', ''))[:220]}"
        for i, a in enumerate(articles, start=1)
    )
    try:
        judged = await ainvoke_json(
            'Classify investor sentiment for each numbered headline, in order. Then write "summary": 2-3 '
            'sentences of markdown on the overall picture and what it means for investors — do not list or '
            'number the headlines. Reply as JSON {"sentiments": ["positive"|"negative"|"neutral", ...], '
            '"summary": "<markdown>"}',
            f"Topic: {lookup}\n{listing}",
            max_tokens=700,
        )
    except Exception as e:
        logger.warning(f"FinScope ▸ Sentiment pass failed: {e}")
        judged = {}
    sentiments = judged.get("sentiments") or []
    card = {
        "symbol": (symbol.split(":")[0] if symbol else (topic or "MARKETS")).upper()[:24],
        "articles": [
            {
                "title": a.get("article_title", ""),
                "source": a.get("source", ""),
                "time": a.get("post_time_utc", ""),
                "snippet": str(a.get("snippet", ""))[:260],
                "sentiment": (sentiments[i] if i < len(sentiments) else "neutral").lower(),
                "url": a.get("article_url", ""),
                "photo": a.get("article_photo_url", ""),
            }
            for i, a in enumerate(articles)
        ],
    }
    summary = judged.get("summary") or "Here are the latest headlines."
    logger.info(f"FinScope ▸ News Reporter built {len(card['articles'])} news cards")
    return {"messages": [AIMessage(content=f"[NEWS_CARD]\n{json.dumps(card)}\n[/NEWS_CARD]\n\n{summary}")]}


# ─── Graph ────────────────────────────────────────────────────────────────────

def build_finscope_graph():
    wf = StateGraph(FinScopeState)
    wf.add_node("classify_intent",    classify_intent)
    wf.add_node("financial_educator", financial_educator)
    wf.add_node("document_analyzer",  document_analyzer)
    wf.add_node("market_researcher",  market_researcher)
    wf.add_node("portfolio_coach",    portfolio_coach)
    wf.add_node("news_reporter",      news_reporter)

    wf.add_edge(START, "classify_intent")
    wf.add_conditional_edges("classify_intent", route_to_subagent, {
        "financial_educator": "financial_educator",
        "document_analyzer":  "document_analyzer",
        "market_researcher":  "market_researcher",
        "portfolio_coach":    "portfolio_coach",
        "news_reporter":      "news_reporter",
    })
    for node in ("financial_educator", "document_analyzer", "market_researcher", "portfolio_coach", "news_reporter"):
        wf.add_edge(node, END)
    return wf.compile()


_graph = build_finscope_graph()


async def run_finscope_chat(
    question: str,
    session_id: str,
    user_profile: str = "beginner",
    analyze_document: bool = False,
) -> Dict[str, str]:
    session = _session(session_id)
    state: FinScopeState = {
        "messages": _history_messages(session) + [HumanMessage(content=question)],
        "question": question,
        "intent": "",
        "session_id": session_id or "anonymous",
        "user_profile": user_profile,
        "analyze_document": analyze_document,
    }
    started = time.time()
    result = await _graph.ainvoke(state, {"recursion_limit": 10})
    answer = str(result["messages"][-1].content)
    intent = result.get("intent", "education")
    agent = AGENT_NAMES.get(intent, "Financial Educator")

    now = datetime.utcnow().isoformat() + "Z"
    session["history"].append({"role": "user", "content": question, "at": now})
    session["history"].append({"role": "assistant", "content": answer, "agent": agent, "at": now})
    session["history"] = session["history"][-40:]
    session["updated_at"] = now
    store.save()
    logger.info(f"FinScope ▸ {agent} answered in {time.time() - started:.1f}s")
    return {"answer": answer, "intent": intent, "agent": agent}
