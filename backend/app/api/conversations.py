"""Conversation history stored in MongoDB Atlas.

Sending a message reuses the existing /chat workflow.
"""

from fastapi import APIRouter, BackgroundTasks, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.chat import ChatRequest, chat as run_chat
from app.chat_history.store import ConversationStoreError, MongoConversationStore

router = APIRouter()

_store: MongoConversationStore | None = None


class RenameRequest(BaseModel):
    title: str = Field(min_length=1, max_length=120)


class SendMessageRequest(BaseModel):
    message: str = Field(min_length=1, max_length=20000)


def set_conversation_store(store: MongoConversationStore | None) -> None:
    global _store
    _store = store


def get_conversation_store() -> MongoConversationStore:
    global _store
    if _store is None:
        try:
            _store = MongoConversationStore.from_env()
        except ConversationStoreError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    return _store


@router.get("")
def list_conversations():
    return get_conversation_store().list_conversations()


@router.post("", status_code=201)
def create_conversation():
    return get_conversation_store().create_conversation()


@router.get("/{conversation_id}")
def get_conversation(conversation_id: str):
    conversation = get_conversation_store().get_conversation(conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.patch("/{conversation_id}")
def rename_conversation(conversation_id: str, request: RenameRequest):
    conversation = get_conversation_store().rename_conversation(
        conversation_id,
        request.title.strip(),
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation


@router.delete("/{conversation_id}", status_code=204)
def delete_conversation(conversation_id: str):
    deleted = get_conversation_store().delete_conversation(conversation_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="Conversation not found")


@router.post("/{conversation_id}/messages")
def send_message(
    conversation_id: str,
    request: SendMessageRequest,
    background_tasks: BackgroundTasks,
):
    store = get_conversation_store()
    existing = store.get_conversation(conversation_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Conversation not found")

    history = [
        {"role": message["role"], "content": message["content"]}
        for message in existing["messages"]
    ]
    response = run_chat(
        ChatRequest(
            message=request.message,
            conversation_id=conversation_id,
            history=history,
        ),
        background_tasks,
    )
    if isinstance(response, JSONResponse):
        return response

    details = response.details.model_dump() if response.details is not None else None
    conversation = store.append_turn(
        conversation_id,
        request.message,
        response.message,
        details,
        response.request_id,
    )
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return {
        "request_id": response.request_id,
        "status": response.status,
        "conversation": conversation,
    }
