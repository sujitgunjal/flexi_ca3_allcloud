"""MongoDB Atlas storage for chat conversations and messages."""

import os
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from pymongo import ASCENDING, DESCENDING, MongoClient
from pymongo.database import Database


class ConversationStoreError(RuntimeError):
    """Chat history storage is unavailable."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


class MongoConversationStore:
    """Conversations and messages stored in a MongoDB Atlas database."""

    def __init__(self, database: Database):
        self.database = database
        self.conversations = database["conversations"]
        self.messages = database["messages"]
        self.conversations.create_index([("updated_at", DESCENDING)])
        self.messages.create_index(
            [("conversation_id", ASCENDING), ("created_at", ASCENDING)]
        )

    @classmethod
    def from_env(cls) -> "MongoConversationStore":
        uri = os.getenv("MONGODB_URI", "").strip()
        if not uri:
            raise ConversationStoreError(
                "Chat history requires MongoDB Atlas. Set MONGODB_URI."
            )
        database_name = os.getenv("MONGODB_DB_NAME", "switchboard").strip() or "switchboard"
        client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        try:
            client.admin.command("ping")
        except Exception as exc:
            raise ConversationStoreError(
                "MongoDB Atlas could not be reached. Check MONGODB_URI."
            ) from exc
        return cls(client[database_name])

    def list_conversations(self) -> list[dict[str, Any]]:
        documents = self.conversations.find().sort("updated_at", DESCENDING).limit(100)
        return [self._summary(document) for document in documents]

    def create_conversation(self, title: str = "New chat") -> dict[str, Any]:
        now = _now()
        document = {
            "_id": str(uuid4()),
            "title": title,
            "title_custom": False,
            "preview": None,
            "created_at": now,
            "updated_at": now,
        }
        self.conversations.insert_one(document)
        return self._conversation(document, [])

    def get_conversation(self, conversation_id: str) -> dict[str, Any] | None:
        document = self.conversations.find_one({"_id": conversation_id})
        if document is None:
            return None
        messages = self.messages.find({"conversation_id": conversation_id}).sort(
            "created_at", ASCENDING
        )
        return self._conversation(document, list(messages))

    def rename_conversation(
        self,
        conversation_id: str,
        title: str,
        *,
        custom: bool = True,
    ) -> dict[str, Any] | None:
        result = self.conversations.update_one(
            {"_id": conversation_id},
            {
                "$set": {
                    "title": title,
                    "title_custom": custom,
                    "updated_at": _now(),
                }
            },
        )
        if result.matched_count == 0:
            return None
        return self.get_conversation(conversation_id)

    def delete_conversation(self, conversation_id: str) -> bool:
        deleted = self.conversations.delete_one({"_id": conversation_id})
        if deleted.deleted_count == 0:
            return False
        self.messages.delete_many({"conversation_id": conversation_id})
        return True

    def append_turn(
        self,
        conversation_id: str,
        user_content: str,
        assistant_content: str,
        details: dict[str, Any] | None,
        request_id: str | None,
    ) -> dict[str, Any] | None:
        document = self.conversations.find_one({"_id": conversation_id})
        if document is None:
            return None

        created_at = _now()
        self.messages.insert_many(
            [
                {
                    "_id": str(uuid4()),
                    "conversation_id": conversation_id,
                    "role": "user",
                    "content": user_content,
                    "created_at": created_at,
                    "request_id": None,
                    "details": None,
                },
                {
                    "_id": str(uuid4()),
                    "conversation_id": conversation_id,
                    "role": "assistant",
                    "content": assistant_content,
                    "created_at": created_at + timedelta(milliseconds=1),
                    "request_id": request_id,
                    "details": details,
                },
            ]
        )
        preview = assistant_content.strip().splitlines()[0][:80]
        updates: dict[str, Any] = {
            "preview": preview,
            "updated_at": _now(),
        }
        if not document.get("title_custom") and document.get("title") == "New chat":
            updates["title"] = user_content.strip().splitlines()[0][:80] or "New chat"
        self.conversations.update_one({"_id": conversation_id}, {"$set": updates})
        return self.get_conversation(conversation_id)

    def _summary(self, document: dict[str, Any]) -> dict[str, Any]:
        return {
            "id": document["_id"],
            "title": document["title"],
            "created_at": _iso(document["created_at"]),
            "updated_at": _iso(document["updated_at"]),
            "preview": document.get("preview"),
        }

    def _conversation(
        self,
        document: dict[str, Any],
        messages: list[dict[str, Any]],
    ) -> dict[str, Any]:
        summary = self._summary(document)
        summary["messages"] = [
            {
                "id": message["_id"],
                "role": message["role"],
                "content": message["content"],
                "created_at": _iso(message["created_at"]),
                "request_id": message.get("request_id"),
                "details": message.get("details"),
            }
            for message in messages
        ]
        return summary
