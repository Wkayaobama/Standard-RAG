"""RAG chat endpoint.

Pipeline per request: retrieve top-k chunks → assemble system prompt with
chunk context → call Claude via `claude_examples.chat_once`. Stateless:
conversation history, if any, is supplied by the caller.
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from app.claude_examples import chat_once
from app.retrieval import top_k

router = APIRouter(prefix="/api", tags=["chat"])


class ChatMessage(BaseModel):
    role: str
    content: str


class ChatRequest(BaseModel):
    question: str
    history: list[ChatMessage] = []
    top_k: int = 6


class Citation(BaseModel):
    pdf_id: str
    section_path: str


class ChatResponse(BaseModel):
    answer: str
    citations: list[Citation]


SYSTEM_TEMPLATE = (
    "You answer questions strictly from the provided document excerpts. "
    "Cite the excerpt(s) you used by their section path. If the excerpts "
    "do not contain the answer, say so plainly — do not guess.\n\n"
    "Excerpts:\n{context}"
)


def _format_context(chunks) -> str:
    if not chunks:
        return "(no relevant excerpts found)"
    blocks = []
    for i, c in enumerate(chunks, 1):
        blocks.append(
            f"[{i}] pdf_id={c.pdf_id} section={c.section_path}\n{c.content}"
        )
    return "\n\n".join(blocks)


@router.post("/chat", response_model=ChatResponse)
async def chat(request: Request, body: ChatRequest):
    if not body.question.strip():
        raise HTTPException(status_code=400, detail="Empty question.")

    db = request.app.state.db
    chunks = await top_k(db, body.question, k=body.top_k)
    context = _format_context(chunks)

    history_dicts = [{"role": m.role, "content": m.content} for m in body.history]

    answer = await chat_once(
        user_message=body.question,
        system_prompt=SYSTEM_TEMPLATE.format(context=context),
        history=history_dicts,
    )

    citations = [
        Citation(pdf_id=c.pdf_id, section_path=c.section_path) for c in chunks
    ]
    return ChatResponse(answer=answer, citations=citations)
