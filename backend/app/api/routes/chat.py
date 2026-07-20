import json
import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.orchestrator import Orchestrator
from app.api.deps import get_current_user, get_db
from app.core.events import hub
from app.core.tracing import end_trace, start_trace
from app.models import Conversation, Message, UsageEvent, User
from app.schemas import ChatIn, ChatOut, ConversationOut, MessageOut


def _record_usage(db: Session, user: User, prompt: str, answer: str, kind: str = "chat") -> None:
    """Metering for the Admin usage view — token counts estimated at ~4 chars/token."""
    try:
        from app.core.config import settings

        db.add(UsageEvent(user_id=user.id, kind=kind, model=settings.OPENAI_MODEL,
                          prompt_tokens=max(1, len(prompt) // 4), completion_tokens=max(1, len(answer) // 4)))
        db.commit()
    except Exception:  # noqa: BLE001 — metering must never break chat
        db.rollback()

router = APIRouter(prefix="/chat", tags=["chat"])


@router.get("/conversations", response_model=list[ConversationOut])
def conversations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return db.scalars(
        select(Conversation).where(Conversation.user_id == user.id).order_by(Conversation.updated_at.desc())
    ).all()


@router.get("/conversations/{conv_id}/messages", response_model=list[MessageOut])
def messages(conv_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conv = db.get(Conversation, conv_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(404, "Conversation not found")
    return db.scalars(select(Message).where(Message.conversation_id == conv_id).order_by(Message.created_at)).all()


@router.delete("/conversations/{conv_id}", status_code=204)
def delete_conversation(conv_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    conv = db.get(Conversation, conv_id)
    if conv is None or conv.user_id != user.id:
        raise HTTPException(404, "Conversation not found")
    db.delete(conv)
    db.commit()


@router.post("", response_model=ChatOut)
def send(body: ChatIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Route a message through the multi-agent orchestrator and persist the exchange."""
    text = body.message.strip()
    if not text:
        raise HTTPException(422, "Empty message")

    conv = db.get(Conversation, body.conversation_id) if body.conversation_id else None
    if conv is not None and conv.user_id != user.id:
        raise HTTPException(404, "Conversation not found")
    if conv is None:
        conv = Conversation(user_id=user.id, title=text[:60])
        db.add(conv)
        db.commit()
        db.refresh(conv)

    db.add(Message(conversation_id=conv.id, role="user", content=text))
    db.commit()

    start_trace(text, user=user.email, kind="chat")
    try:
        result = Orchestrator(db, user).handle(text, force_agent=body.agent, thread_id=conv.id)
        end_trace("ok")
    except Exception:
        end_trace("error")
        raise
    _record_usage(db, user, text, result.answer)

    reply = Message(
        conversation_id=conv.id,
        role="assistant",
        content=result.answer,
        agent=result.agent,
        citations=result.citations_json,
        confidence=result.confidence,
    )
    db.add(reply)
    db.commit()
    db.refresh(reply)

    # realtime: other windows/users following this conversation see it instantly
    hub.publish("chat.message", conversation_id=conv.id, user=user.full_name,
                agent=result.agent, preview=result.answer[:160], confidence=result.confidence)

    return ChatOut(
        conversation_id=conv.id,
        message=MessageOut.model_validate(reply),
        plan=result.plan,
        retrieved=result.citations,
    )


@router.post("/stream")
def send_stream(body: ChatIn, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Streaming variant of POST /chat — Server-Sent Events.

    Events: meta (plan/citations/confidence, sent first) → delta (text chunks,
    progressive delivery) → done. The exchange is fully persisted before
    streaming starts, so an aborted client never loses the message.
    """
    text = body.message.strip()
    if not text:
        raise HTTPException(422, "Empty message")

    conv = db.get(Conversation, body.conversation_id) if body.conversation_id else None
    if conv is not None and conv.user_id != user.id:
        raise HTTPException(404, "Conversation not found")
    if conv is None:
        conv = Conversation(user_id=user.id, title=text[:60])
        db.add(conv)
        db.commit()
        db.refresh(conv)

    db.add(Message(conversation_id=conv.id, role="user", content=text))
    db.commit()

    start_trace(text, user=user.email, kind="chat")
    try:
        result = Orchestrator(db, user).handle(text, force_agent=body.agent, thread_id=conv.id)
        end_trace("ok")
    except Exception:
        end_trace("error")
        raise

    _record_usage(db, user, text, result.answer)
    reply = Message(
        conversation_id=conv.id, role="assistant", content=result.answer,
        agent=result.agent, citations=result.citations_json, confidence=result.confidence,
    )
    db.add(reply)
    db.commit()

    hub.publish("chat.message", conversation_id=conv.id, user=user.full_name,
                agent=result.agent, preview=result.answer[:160], confidence=result.confidence)

    answer = result.answer
    meta = {
        "type": "meta", "conversation_id": conv.id, "agent": result.agent,
        "plan": result.plan, "confidence": result.confidence,
        "citations": [c.model_dump() for c in result.citations],
    }

    def gen():
        yield f"data: {json.dumps(meta)}\n\n"
        step = max(6, len(answer) // 120)  # ~120 chunks regardless of length
        for i in range(0, len(answer), step):
            yield f"data: {json.dumps({'type': 'delta', 'text': answer[i:i + step]})}\n\n"
            time.sleep(0.012)
        yield 'data: {"type": "done"}\n\n'

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})
