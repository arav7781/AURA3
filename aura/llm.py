"""Chat and embedding clients for the OpenAI-compatible LLM gateway."""

import json
import logging
import re
import time
from typing import Any, Dict, List, Optional

import httpx
from langchain_core.messages import BaseMessage, HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI

from aura.config import CHAT_MODEL, EMBEDDING_MODEL, LLM_API_KEY, LLM_BASE_URL

logger = logging.getLogger("aura.llm")

_EMBED_BATCH = 64


def get_llm(temperature: float = 0.2, max_tokens: int = 2048, json_mode: bool = False) -> ChatOpenAI:
    kwargs: Dict[str, Any] = {}
    if json_mode:
        kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    return ChatOpenAI(
        base_url=LLM_BASE_URL,
        api_key=LLM_API_KEY,
        model=CHAT_MODEL,
        temperature=temperature,
        max_tokens=max_tokens,
        timeout=240,
        max_retries=1,
        **kwargs,
    )


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
    temperature: float = 0.1,
    max_tokens: int = 2048,
    history: Optional[List[BaseMessage]] = None,
) -> Any:
    llm = get_llm(temperature=temperature, max_tokens=max_tokens, json_mode=True)
    messages: List[BaseMessage] = [SystemMessage(content=system)]
    messages += history or []
    messages.append(HumanMessage(content=user))
    response = await llm.ainvoke(messages)
    return parse_json(str(response.content))


def invoke_json(system: str, user: str, temperature: float = 0.1, max_tokens: int = 2048) -> Any:
    llm = get_llm(temperature=temperature, max_tokens=max_tokens, json_mode=True)
    response = llm.invoke([SystemMessage(content=system), HumanMessage(content=user)])
    return parse_json(str(response.content))


def embed(texts: List[str]) -> List[List[float]]:
    """Embed texts through the gateway's /embeddings endpoint, in batches."""
    vectors: List[List[float]] = []
    with httpx.Client(timeout=120.0) as client:
        for start in range(0, len(texts), _EMBED_BATCH):
            batch = [t if t.strip() else " " for t in texts[start : start + _EMBED_BATCH]]
            for attempt in range(3):
                try:
                    resp = client.post(
                        f"{LLM_BASE_URL}/embeddings",
                        headers={"Authorization": f"Bearer {LLM_API_KEY}"},
                        json={"model": EMBEDDING_MODEL, "input": batch},
                    )
                    resp.raise_for_status()
                    data = sorted(resp.json()["data"], key=lambda item: item.get("index", 0))
                    vectors.extend(item["embedding"] for item in data)
                    break
                except Exception as e:
                    if attempt == 2:
                        raise
                    logger.warning(f"Embedding batch failed (attempt {attempt + 1}): {e}")
                    time.sleep(1.5 * (attempt + 1))
    return vectors
