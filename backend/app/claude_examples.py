"""Standalone Anthropic cookbook — chat, streaming, vision, tools, JSON.

Single-provider, single-mode: direct calls to `api.anthropic.com` using
`ANTHROPIC_API_KEY`. No proxy branch, no system-prompt rewriting, no
outbound telemetry.
"""
from __future__ import annotations

import json
from typing import Any, AsyncIterator, Optional

from anthropic import AsyncAnthropic

from app.config import settings


_client: Optional[AsyncAnthropic] = None


def get_client() -> AsyncAnthropic:
    """Lazily construct a shared AsyncAnthropic client.

    Raises `RuntimeError` if `ANTHROPIC_API_KEY` is not configured.
    """
    global _client
    if _client is None:
        if not settings.anthropic_api_key.strip():
            raise RuntimeError(
                "ANTHROPIC_API_KEY is not set. Put it in .env (copy from "
                ".env.example) and restart the backend."
            )
        _client = AsyncAnthropic(api_key=settings.anthropic_api_key)
    return _client


async def chat_once(
    *,
    user_message: str,
    system_prompt: Optional[str] = None,
    history: Optional[list[dict]] = None,
    model: Optional[str] = None,
    max_tokens: int = 1024,
) -> str:
    """Single-turn chat with optional prior history. Returns plain text."""
    client = get_client()
    messages = list(history or [])
    messages.append({"role": "user", "content": user_message})

    kwargs: dict[str, Any] = {
        "model": model or settings.ai_model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system_prompt:
        kwargs["system"] = system_prompt

    resp = await client.messages.create(**kwargs)
    return "".join(b.text for b in resp.content if b.type == "text")


async def stream_chat(
    *,
    user_message: str,
    system_prompt: Optional[str] = None,
    history: Optional[list[dict]] = None,
    model: Optional[str] = None,
    max_tokens: int = 1024,
) -> AsyncIterator[str]:
    """Yield text chunks as Claude generates them."""
    client = get_client()
    messages = list(history or [])
    messages.append({"role": "user", "content": user_message})

    kwargs: dict[str, Any] = {
        "model": model or settings.ai_model,
        "max_tokens": max_tokens,
        "messages": messages,
    }
    if system_prompt:
        kwargs["system"] = system_prompt

    async with client.messages.stream(**kwargs) as stream:
        async for text in stream.text_stream:
            yield text


async def chat_with_image(
    *,
    user_message: str,
    image_base64: Optional[str] = None,
    image_url: Optional[str] = None,
    image_media_type: str = "image/jpeg",
    model: Optional[str] = None,
    max_tokens: int = 1024,
) -> str:
    client = get_client()
    if image_base64:
        image_block: dict = {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": image_media_type,
                "data": image_base64,
            },
        }
    elif image_url:
        image_block = {
            "type": "image",
            "source": {"type": "url", "url": image_url},
        }
    else:
        raise ValueError("Provide either image_base64 or image_url")

    resp = await client.messages.create(
        model=model or settings.ai_model,
        max_tokens=max_tokens,
        messages=[
            {
                "role": "user",
                "content": [image_block, {"type": "text", "text": user_message}],
            }
        ],
    )
    return "".join(b.text for b in resp.content if b.type == "text")


async def chat_with_tools(
    *,
    user_message: str,
    tools: list[dict],
    tool_handler,
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 1024,
    max_rounds: int = 5,
) -> str:
    client = get_client()
    messages: list[dict] = [{"role": "user", "content": user_message}]

    for _ in range(max_rounds):
        kwargs: dict[str, Any] = {
            "model": model or settings.ai_model,
            "max_tokens": max_tokens,
            "tools": tools,
            "messages": messages,
        }
        if system_prompt:
            kwargs["system"] = system_prompt

        resp = await client.messages.create(**kwargs)
        messages.append({"role": "assistant", "content": resp.content})

        if resp.stop_reason != "tool_use":
            return "".join(b.text for b in resp.content if b.type == "text")

        tool_results = []
        for block in resp.content:
            if block.type != "tool_use":
                continue
            try:
                result = await tool_handler(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result if isinstance(result, str) else json.dumps(result),
                })
            except Exception as e:
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": f"Error: {e}",
                    "is_error": True,
                })

        messages.append({"role": "user", "content": tool_results})

    return "Tool loop hit max rounds without completing."


async def extract_structured(
    *,
    user_message: str,
    schema: dict,
    schema_name: str = "extracted_data",
    schema_description: str = "Extracted structured data",
    system_prompt: Optional[str] = None,
    model: Optional[str] = None,
    max_tokens: int = 1024,
) -> dict:
    client = get_client()
    tool = {
        "name": schema_name,
        "description": schema_description,
        "input_schema": schema,
    }

    kwargs: dict[str, Any] = {
        "model": model or settings.ai_model,
        "max_tokens": max_tokens,
        "tools": [tool],
        "tool_choice": {"type": "tool", "name": schema_name},
        "messages": [{"role": "user", "content": user_message}],
    }
    if system_prompt:
        kwargs["system"] = system_prompt

    resp = await client.messages.create(**kwargs)
    for block in resp.content:
        if block.type == "tool_use" and block.name == schema_name:
            return block.input

    raise RuntimeError("Claude did not return structured output")


# Error handling cheat-sheet:
#   from anthropic import APIError, RateLimitError, AuthenticationError
#   - AuthenticationError (401) -> bad/missing ANTHROPIC_API_KEY — fail fast.
#   - RateLimitError (429) -> SDK retries twice by default; custom UX optional.
#   - APIError (5xx) -> upstream issue — retry.
#   - APIConnectionError -> network — retry.
