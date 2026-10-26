"""Chat models for the OpenAI-compatible gateway, by role.

Roles map to models from settings: ``agent`` (copilot and evaluation analyst), ``util`` (cheap helper
calls such as summaries and query rewrites) and ``judge`` (eval grading; a different model family from the
agent so it does not grade its own model's work).

Run ``uv run python -m aura.core.llm smoke`` to check the gateway end to end.
"""

import asyncio
import json
import logging
import re
import sys
from typing import Any, Literal

from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from aura.core.config import get_settings

logger = logging.getLogger("aura.llm")

Role = Literal["agent", "util", "judge"]

_semaphore: asyncio.Semaphore | None = None


def gateway_slot() -> asyncio.Semaphore:
    """Process-wide cap on concurrent gateway calls (shared by agents, evaluations and evals)."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(get_settings().llm_concurrency)
    return _semaphore


def model_name(role: Role) -> str:
    s = get_settings()
    return {"agent": s.model_agent, "util": s.model_util, "judge": s.model_judge}[role]


def chat_model(
    role: Role = "agent",
    *,
    temperature: float | None = 0.2,
    max_tokens: int = 2048,
    json_mode: bool = False,
    internal: bool = False,
    **kwargs: Any,
) -> ChatOpenAI:
    """A chat model for ``role``.

    ``internal=True`` tags the model ``nostream`` so its tokens never reach a copilot token stream
    (used for summaries, query rewrites and grading). gpt-5 models ignore temperature and count
    reasoning tokens against ``max_tokens``, so the judge gets a larger budget and no temperature.
    """
    settings = get_settings()
    settings.require_llm()
    name = model_name(role)
    params: dict[str, Any] = dict(kwargs)
    if json_mode:
        params.setdefault("model_kwargs", {})["response_format"] = {"type": "json_object"}
    if name.startswith("gpt-5"):
        temperature = None
        max_tokens = max(max_tokens, 1500)
        params.setdefault("reasoning_effort", "low")
    model = ChatOpenAI(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=name,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=settings.llm_timeout_s,
        max_retries=2,
        **params,
    )
    return model.with_config(tags=["nostream"]) if internal else model  # type: ignore[return-value]


def _strip_fences(text: str) -> str:
    text = text.strip()
    fenced = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.DOTALL)
    return fenced.group(1) if fenced else text


def parse_json(text: str) -> Any:
    """Parse model output as JSON, tolerating code fences and leading prose."""
    text = _strip_fences(text)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = min((i for i in (text.find("{"), text.find("[")) if i != -1), default=-1)
        if start == -1:
            raise
        end = max(text.rfind("}"), text.rfind("]"))
        return json.loads(text[start : end + 1])


async def ainvoke_json(
    system: str,
    user: str,
    *,
    role: Role = "agent",
    temperature: float = 0.0,
    max_tokens: int = 2048,
    history: list[BaseMessage] | None = None,
) -> Any:
    llm = chat_model(role, temperature=temperature, max_tokens=max_tokens, json_mode=True, internal=True)
    messages: list[BaseMessage] = [SystemMessage(content=system), *(history or []), HumanMessage(content=user)]
    async with gateway_slot():
        response = await llm.ainvoke(messages)
    return parse_json(str(response.content))


def invoke_json(system: str, user: str, *, role: Role = "agent", temperature: float = 0.0, max_tokens: int = 2048) -> Any:
    llm = chat_model(role, temperature=temperature, max_tokens=max_tokens, json_mode=True, internal=True)
    response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    return parse_json(str(response.content))


async def _smoke() -> int:
    from langchain_core.tools import tool

    from aura.core.embeddings import DenseEmbedder

    settings = get_settings()
    print(f"data_dir: {settings.data_dir}")
    failures = 0

    @tool
    def search_startups(query: str) -> str:
        """Search the startup catalogue."""
        return query

    @tool
    def web_search(query: str) -> str:
        """Search the web."""
        return query

    agent = chat_model("agent").bind_tools([search_startups, web_search])
    reply = await agent.ainvoke(
        "In parallel: search our catalogue for agritech startups AND search the web for 2026 India agritech "
        "funding. Call both tools now."
    )
    names = [call["name"] for call in reply.tool_calls]
    ok = len(names) >= 2
    failures += not ok
    print(f"agent ({model_name('agent')}): tool calls {names} -> {'ok' if ok else 'FAIL'}")

    verdict = await ainvoke_json(
        "Return JSON {\"supported\": true|false, \"reason\": str}.",
        "Claim: the TAM is USD 82.3M in 2025. Evidence: 'TAM — India Agriculture IoT market: USD 82.3M in 2025'.",
        role="judge",
    )
    ok = isinstance(verdict, dict) and verdict.get("supported") is True
    failures += not ok
    print(f"judge ({model_name('judge')}): {verdict} -> {'ok' if ok else 'FAIL'}")

    vectors = await DenseEmbedder().embed(["solar soil sensor", "WhatsApp crop advisory"])
    norms = [round(float((v * v).sum() ** 0.5), 4) for v in vectors]
    ok = vectors.shape == (2, settings.embed_dims) and all(abs(n - 1) < 1e-3 for n in norms)
    failures += not ok
    print(f"embeddings ({settings.embed_model}): shape {vectors.shape}, norms {norms} -> {'ok' if ok else 'FAIL'}")
    return failures


if __name__ == "__main__":
    if sys.argv[1:] == ["smoke"]:
        sys.exit(1 if asyncio.run(_smoke()) else 0)
    print("usage: python -m aura.core.llm smoke")
