"""Startup evaluation: a self-correcting LangGraph research loop.

    START → analyst ─(tool calls)→ tools ─(grade: enough?)→ generate → END
               ↑                              │ no
               └──────────── rewrite ←────────┘   (max 2 rewrites)

The analyst plans research and calls tools (web market search, retrieval over the
startup's own documents). A grader checks whether the evidence is sufficient; if not
the query is rewritten. Generate writes the 11-section report as structured JSON so
scores and chart data come from the analysis itself.
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from typing import Annotated, Any, Callable, Dict, List, Literal, Optional, Sequence, TypedDict

from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode, tools_condition

from aura import vector_store
from aura.config import CHAT_MODEL
from aura.llm import get_llm, invoke_json
from aura.mca import consistency_flags
from aura.search import format_results, web_search

logger = logging.getLogger("aura.evaluation")

MAX_REWRITES = 2

SECTION_TITLES = {
    "executive_summary":      "Executive Summary",
    "problem_solution":       "Problem & Solution",
    "market_opportunity":     "Market Opportunity",
    "competitive_landscape":  "Competitive Landscape",
    "business_model":         "Business Model",
    "team_assessment":        "Team Assessment",
    "traction_milestones":    "Traction & Milestones",
    "compliance_governance":  "Compliance & Governance",
    "risks_challenges":       "Risks & Challenges",
    "investment_thesis":      "Investment Thesis",
    "recommendation":         "Recommendation",
}

SCORE_DIMENSIONS = {
    "product":        "Product Strength",
    "market":         "Market Size",
    "team":           "Team Quality",
    "business_model": "Business Model",
    "moat":           "Moat",
    "execution_risk": "Execution Risk (10 = low risk)",
    "traction":       "Traction",
}

RECOMMENDATIONS = ("Strong Buy", "Buy", "Hold", "Pass")


def collection_name(startup_id: str) -> str:
    return f"startup_{startup_id.replace('-', '')}"


class AnalysisState(TypedDict):
    messages:      Annotated[Sequence[BaseMessage], add_messages]
    startup_id:    str
    rewrite_count: int
    result:        Dict[str, Any]


def _profile_block(startup: Dict[str, Any]) -> str:
    v = startup.get("verification") or {}
    if v.get("mca_verified"):
        mca = (
            f"MCA VERIFIED — CIN {v.get('cin')}, status {v.get('company_status')}, "
            f"registered as {v.get('company_name')}, directors: {', '.join(v.get('directors', [])) or 'none listed'}"
        )
    elif v.get("cin"):
        mca = f"MCA CHECK FAILED — CIN {v.get('cin')}, status {v.get('company_status')}"
    else:
        mca = "MCA NOT VERIFIED — no CIN supplied"
    flags = consistency_flags(startup)
    return (
        f"Name: {startup.get('name', 'N/A')}\n"
        f"Domain: {startup.get('domain', 'N/A')}\n"
        f"Description: {startup.get('description', 'N/A')}\n"
        f"Team: {startup.get('team', 'N/A')}\n"
        f"Stage: {startup.get('stage') or 'N/A'} | Funding ask: {startup.get('funding_required') or 'N/A'}\n"
        f"Additional info: {startup.get('extras') or 'N/A'}\n"
        f"Compliance: {mca}\n"
        f"Compliance flags: {', '.join(flags) if flags else 'none'}"
    )


def document_context(startup: Dict[str, Any], query: str, k: int = 6) -> str:
    """Top-k chunks from the startup's documents, falling back to raw extracted text."""
    try:
        hits = vector_store.search(collection_name(startup["startup_id"]), query, k=k)
        if hits:
            return "\n\n---\n\n".join(h["text"] for h in hits)
    except Exception as e:
        logger.warning(f"Vector retrieval failed, using in-memory text: {e}")
    text = startup.get("extracted_text", "")
    return text[:3000] if text else "No documents uploaded for this startup."


def build_analysis_workflow(
    startup: Dict[str, Any],
    progress: Callable[[str], None] = lambda stage: None,
):
    sources: List[Dict[str, str]] = []

    @tool
    def search_market_data(query: str) -> str:
        """Search the web for market size, growth rate, competitors, funding rounds, regulation and industry trends."""
        results = web_search(query, max_results=5)
        sources.extend(r for r in results if r.get("url"))
        return format_results(results, query)

    @tool
    def retrieve_startup_documents(query: str) -> str:
        """Search the startup's own uploaded pitch deck and documents for facts (traction, revenue, team, product)."""
        return document_context(startup, query, k=5)

    tools = [search_market_data, retrieve_startup_documents]
    tool_node = ToolNode(tools)

    def analyst_agent(state: AnalysisState) -> dict:
        progress("Analyst agent is planning research")
        logger.info(f"Evaluation ▸ Analyst agent planning research for '{startup.get('name')}'")
        system = f"""You are a senior venture capital analyst preparing due diligence on a startup.

STARTUP PROFILE
{_profile_block(startup)}

EXCERPTS FROM THE STARTUP'S DOCUMENTS
{document_context(startup, f"{startup.get('name')} product traction revenue team business model", k=6)}

Plan your research, then call tools. Call search_market_data 2 to 4 times with focused queries
covering: (1) market size and growth rate for this domain, (2) main competitors and their funding,
(3) recent industry trends, investment activity or regulation. Call retrieve_startup_documents if
you need specific facts from the pitch deck. Make all the tool calls you need in this turn."""
        llm = get_llm(temperature=0.2, max_tokens=1500).bind_tools(tools)
        try:
            response = llm.invoke([SystemMessage(content=system)] + list(state["messages"]))
            calls = getattr(response, "tool_calls", None) or []
            if calls:
                logger.info("Evaluation ▸ Analyst requested " + "; ".join(
                    f"{c['name']}({c['args'].get('query', '')})" for c in calls))
            return {"messages": [response]}
        except Exception as e:
            logger.warning(f"Evaluation ▸ Analyst tool binding failed ({e}); continuing to report")
            return {"messages": [AIMessage(content="Tool call failed; writing report from profile and documents.")]}

    def safe_tool_node(state: AnalysisState) -> dict:
        progress("Researching the market and reading documents")
        try:
            return tool_node.invoke(state)
        except Exception as e:
            logger.warning(f"Evaluation ▸ Tool execution error (continuing): {e}")
            last_ai = next((m for m in reversed(state["messages"]) if isinstance(m, AIMessage)), None)
            calls = getattr(last_ai, "tool_calls", None) or []
            return {"messages": [
                ToolMessage(
                    content=f"[Tool failed: {e}] Use pre-trained knowledge and mark figures as estimates.",
                    tool_call_id=c.get("id", "fallback"),
                    name=c.get("name", "unknown_tool"),
                )
                for c in calls
            ]}

    def grade_relevance(state: AnalysisState) -> Literal["generate", "rewrite"]:
        if state.get("rewrite_count", 0) >= MAX_REWRITES:
            logger.info("Evaluation ▸ Grader: rewrite limit reached, generating report")
            return "generate"
        recent: List[str] = []
        for msg in reversed(state["messages"]):
            if isinstance(msg, ToolMessage):
                recent.append(str(msg.content)[:1500])
            elif recent:
                break
        evidence = "\n\n".join(recent)[:5000]
        progress("Grading research quality")
        try:
            verdict = invoke_json(
                'You grade research for a startup due-diligence report. Reply as JSON '
                '{"sufficient": true|false, "missing": "<what is missing>"}. Research is sufficient '
                "when it gives at least an approximate market size or growth figure AND names "
                "some competitors or industry context.",
                f"Startup domain: {startup.get('domain')}\n\nResearch gathered:\n{evidence}",
                max_tokens=200,
            )
            sufficient = bool(verdict.get("sufficient"))
            logger.info(
                f"Evaluation ▸ Grader: research {'sufficient' if sufficient else 'insufficient'}"
                + ("" if sufficient else f" — missing {verdict.get('missing', 'detail')}")
            )
            return "generate" if sufficient else "rewrite"
        except Exception as e:
            logger.warning(f"Evaluation ▸ Grader failed ({e}); generating report")
            return "generate"

    def rewrite_query(state: AnalysisState) -> dict:
        count = state.get("rewrite_count", 0) + 1
        progress(f"Refining research query (rewrite {count} of {MAX_REWRITES})")
        original = state["messages"][0].content if state["messages"] else ""
        llm = get_llm(temperature=0.3, max_tokens=300)
        try:
            new_query = llm.invoke([HumanMessage(content=(
                "The research below did not give enough market data for a startup evaluation.\n"
                f"Startup: {startup.get('name')} ({startup.get('domain')}): {startup.get('description')}\n"
                f"Original request: {original}\n\n"
                "Write one sharper research instruction naming the exact market, geography and "
                "competitor set to search for. Reply with the instruction only."
            ))]).content
        except Exception:
            new_query = f"Find the market size, CAGR and top competitors for {startup.get('domain')} startups"
        logger.info(f"Evaluation ▸ Rewrite {count}: {str(new_query)[:160]}")
        return {"messages": [HumanMessage(content=str(new_query))], "rewrite_count": count}

    def generate_analysis(state: AnalysisState) -> dict:
        progress("Scoring the startup and sizing the market")
        logger.info("Evaluation ▸ Scoring and market sizing")
        research = [str(m.content) for m in state["messages"] if isinstance(m, ToolMessage)]
        research_text = "\n\n---\n\n".join(research[-10:])[:14000] or "No external research was retrieved."
        docs = document_context(startup, "revenue customers traction team product pricing competitors", k=8)
        year = datetime.utcnow().year
        evidence = (
            f"STARTUP PROFILE\n{_profile_block(startup)}\n\n"
            f"STARTUP DOCUMENTS\n{docs[:7000]}\n\n"
            f"MARKET RESEARCH\n{research_text}"
        )
        scoring_schema = {
            "overall_score": "number 0-10, one decimal",
            "recommendation_label": "one of: Strong Buy, Buy, Hold, Pass",
            "category_scores": {k: "number 0-10" for k in SCORE_DIMENSIONS},
            "market_sizing": {
                "tam_usd_b": "number, total addressable market in USD billions",
                "sam_usd_b": "number, serviceable addressable market in USD billions",
                "som_usd_b": "number, serviceable obtainable market in USD billions",
                "current_market_usd_b": f"number, size of the core market in {year} in USD billions",
                "cagr_pct": "number, expected annual growth rate in percent",
                "basis": "one sentence on where the figures come from",
            },
            "projected_revenue": [{"year": "int", "revenue_musd": "number, USD millions"}],
        }
        scores = invoke_json(
            "You are a senior venture capital analyst scoring a startup. Be critical but fair; prefer figures "
            "from the research and documents. Convert other currencies to USD (1 USD ≈ 83 INR). "
            f"projected_revenue lists 5 consecutive years starting {year}, grounded in current revenue. "
            f"Return JSON matching this shape:\n{scoring_schema}",
            evidence, temperature=0.1, max_tokens=900,
        )

        progress("Writing the 11-section investor report")
        logger.info("Evaluation ▸ Writing the 11-section report (two writers in parallel)")
        keys = list(SECTION_TITLES)
        verdict = (
            f"Your verdict (already decided — keep the text consistent with it): overall {scores.get('overall_score')}/10, "
            f"{scores.get('recommendation_label')}, category scores {scores.get('category_scores')}, "
            f"market sizing {scores.get('market_sizing')}, projected revenue {scores.get('projected_revenue')}."
        )

        def write_sections(section_keys: List[str]) -> Dict[str, Any]:
            shape = {k: f"markdown for '{SECTION_TITLES[k]}'" for k in section_keys}
            return invoke_json(
                "You are a senior venture capital analyst writing part of an investor-facing startup evaluation. "
                "Each value is GitHub markdown: 2-4 short paragraphs or bullet lists, specific numbers, no top-level "
                "headings. Cite figures from the research and say when a figure is an estimate. "
                "The recommendation section starts with the recommendation label in bold. The compliance_governance "
                "section discusses the MCA status and compliance flags. "
                f"{verdict}\nReturn JSON with exactly these keys: {shape}",
                evidence, temperature=0.25, max_tokens=4000,
            )

        with ThreadPoolExecutor(max_workers=2) as pool:
            parts = list(pool.map(write_sections, [keys[:6], keys[6:]]))
        result = {**scores, "sections": {**parts[0], **parts[1]}}
        return {"result": result, "messages": [AIMessage(content="Report generated.")]}

    wf = StateGraph(AnalysisState)
    wf.add_node("analyst", analyst_agent)
    wf.add_node("tools", safe_tool_node)
    wf.add_node("rewrite", rewrite_query)
    wf.add_node("generate", generate_analysis)

    wf.add_edge(START, "analyst")
    wf.add_conditional_edges("analyst", tools_condition, {"tools": "tools", END: "generate"})
    wf.add_conditional_edges("tools", grade_relevance, {"generate": "generate", "rewrite": "rewrite"})
    wf.add_edge("rewrite", "analyst")
    wf.add_edge("generate", END)

    return wf.compile(), sources


def _num(value: Any, default: float = 0.0, lo: Optional[float] = None, hi: Optional[float] = None) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        n = default
    if lo is not None:
        n = max(lo, n)
    if hi is not None:
        n = min(hi, n)
    return n


def _normalise(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Validate model output and fill any gaps so charts and UI always have data."""
    scores_raw = raw.get("category_scores") or {}
    category_scores = {k: round(_num(scores_raw.get(k), 5.0, 0, 10), 1) for k in SCORE_DIMENSIONS}
    mean = sum(category_scores.values()) / len(category_scores)
    overall = round(_num(raw.get("overall_score"), mean, 0, 10), 1)

    label = str(raw.get("recommendation_label") or "").strip().title()
    if label not in RECOMMENDATIONS:
        label = "Strong Buy" if overall >= 8 else "Buy" if overall >= 6.5 else "Hold" if overall >= 5 else "Pass"

    m = raw.get("market_sizing") or {}
    tam = _num(m.get("tam_usd_b"), 10, 0)
    sam = _num(m.get("sam_usd_b"), tam * 0.3, 0, tam or None)
    som = _num(m.get("som_usd_b"), sam * 0.1, 0, sam or None)
    current = _num(m.get("current_market_usd_b"), sam or tam, 0)
    cagr = _num(m.get("cagr_pct"), 12, -50, 150)
    base_year = datetime.utcnow().year
    trend = [
        {"year": y, "size_usd_b": round(current * (1 + cagr / 100) ** (y - base_year), 2)}
        for y in range(base_year - 4, base_year + 5)
    ]

    revenue = []
    for row in raw.get("projected_revenue") or []:
        try:
            revenue.append({"year": int(row.get("year")), "revenue_musd": round(_num(row.get("revenue_musd"), 0, 0), 2)})
        except (TypeError, ValueError, AttributeError):
            continue
    revenue = sorted(revenue, key=lambda r: r["year"])[:5]

    sections_raw = raw.get("sections") or {}
    sections = {
        key: str(sections_raw.get(key) or f"_{title} was not generated for this report._").strip()
        for key, title in SECTION_TITLES.items()
    }

    return {
        "overall_score": overall,
        "recommendation_label": label,
        "category_scores": category_scores,
        "market_sizing": {
            "tam_usd_b": round(tam, 2), "sam_usd_b": round(sam, 2), "som_usd_b": round(som, 3),
            "current_market_usd_b": round(current, 2), "cagr_pct": round(cagr, 1),
            "basis": str(m.get("basis") or "Analyst estimate from market research."),
            "trend": trend,
        },
        "projected_revenue": revenue,
        "sections": sections,
    }


def report_markdown(analysis: Dict[str, Any]) -> str:
    return "\n\n".join(
        f"## {i}. {title}\n\n{analysis['sections'].get(key, '')}"
        for i, (key, title) in enumerate(SECTION_TITLES.items(), start=1)
    )


def run_evaluation(startup: Dict[str, Any], progress: Callable[[str], None] = lambda s: None) -> Dict[str, Any]:
    """Run the full workflow for one startup. Blocking; call from a worker thread."""
    workflow, sources = build_analysis_workflow(startup, progress)
    initial: AnalysisState = {
        "messages": [HumanMessage(content=(
            f"Complete an investment evaluation of {startup.get('name')} in {startup.get('domain')}. "
            "Research market size, growth, competitors, trends and regulation."
        ))],
        "startup_id": startup["startup_id"],
        "rewrite_count": 0,
        "result": {},
    }
    final = workflow.invoke(initial, {"recursion_limit": 15})
    analysis = _normalise(final.get("result") or {})

    unique_sources, seen = [], set()
    for s in sources:
        if s["url"] not in seen:
            seen.add(s["url"])
            unique_sources.append({"title": s["title"], "url": s["url"]})

    analysis.update({
        "sources": unique_sources[:12],
        "rewrites": final.get("rewrite_count", 0),
        "compliance_flags": consistency_flags(startup),
        "generated_at": datetime.utcnow().isoformat() + "Z",
        "model": CHAT_MODEL,
    })
    analysis["report_markdown"] = report_markdown(analysis)
    logger.info(
        f"Evaluation ▸ Done: {startup.get('name')} scored {analysis['overall_score']}/10 "
        f"({analysis['recommendation_label']}), {len(analysis['sources'])} sources, {analysis['rewrites']} rewrites"
    )
    return analysis


def to_frontend(analysis: Dict[str, Any]) -> Dict[str, Any]:
    """Shape the analysis for the dashboard (keeps the camelCase keys the UI already reads)."""
    s, cs = analysis["sections"], analysis["category_scores"]
    return {
        "score": analysis["overall_score"],
        "recommendationLabel": analysis["recommendation_label"],
        "executiveSummary": s["executive_summary"],
        "marketAnalysis": s["market_opportunity"],
        "teamAssessment": s["team_assessment"],
        "riskFactors": s["risks_challenges"],
        "recommendation": s["recommendation"],
        "categoryScores": {
            "team": cs["team"], "market": cs["market"], "product": cs["product"],
            "traction": cs["traction"], "risk": cs["execution_risk"],
            "businessModel": cs["business_model"], "moat": cs["moat"],
        },
        "projectedRevenue": [{"year": r["year"], "revenue": r["revenue_musd"]} for r in analysis["projected_revenue"]],
        "marketSizing": analysis["market_sizing"],
        "sections": [
            {"key": k, "title": t, "content": s[k]} for k, t in SECTION_TITLES.items()
        ],
        "sources": analysis.get("sources", []),
        "complianceFlags": analysis.get("compliance_flags", []),
        "generatedAt": analysis.get("generated_at"),
        "model": analysis.get("model"),
    }
