"""Saved AI chats: every conversation is kept (like the chat history in Claude), in the data folder."""
from __future__ import annotations

import re
import time
import uuid

from ..core.errors import AppError

MAX_CHATS, MAX_MSGS, MAX_TEXT = 200, 80, 8000


def _check_chats(d) -> None:
    if not isinstance(d, dict) or not all(isinstance(x, dict) for x in d.get("items", [])):
        raise ValueError("chats.json has the wrong shape")


class ChatsMixin:
    def _chats_path(self):
        return self._need_store().root / "chats.json"

    def _chats_data(self) -> dict:
        data = self._need_store().read_json(self._chats_path(), {}, check=_check_chats) or {}
        data.setdefault("items", [])
        return data

    def chats_list(self) -> dict:
        items = sorted(self._chats_data()["items"], key=lambda c: c.get("updated", 0), reverse=True)
        return {"items": [{"id": c["id"], "title": c.get("title", ""), "updated": c.get("updated", 0)} for c in items]}

    def chat_get(self, chat_id: str) -> dict:
        c = next((x for x in self._chats_data()["items"] if x["id"] == chat_id), None)
        if not c:
            raise AppError("not_found", "That chat is not there any more.", status=404)
        return c

    def chat_save(self, chat_id: str, b: dict) -> dict:
        """Create or update one chat. An empty id makes a new one."""
        if chat_id and not re.fullmatch(r"[a-z0-9]{6,20}", chat_id):
            raise AppError("bad_id")
        msgs = []
        for m in (b.get("messages") or [])[-MAX_MSGS:]:
            if isinstance(m, dict) and str(m.get("content", "")).strip():
                msgs.append({"role": "assistant" if m.get("role") == "assistant" else "user",
                             "content": str(m["content"])[:MAX_TEXT], **({"error": True} if m.get("error") else {})})
        data = self._chats_data()
        c = next((x for x in data["items"] if x["id"] == chat_id), None) if chat_id else None
        if not c:
            c = {"id": chat_id or uuid.uuid4().hex[:10], "title": ""}
            data["items"].append(c)
        first = next((m["content"] for m in msgs if m["role"] == "user"), "")
        c.update(messages=msgs, grade_id=str(b.get("grade_id", ""))[:60], updated=int(time.time()),
                 title=str(b.get("title") or c.get("title") or " ".join(first.split())[:48]))
        data["items"] = sorted(data["items"], key=lambda x: x.get("updated", 0), reverse=True)[:MAX_CHATS]
        self._need_store().write_json(self._chats_path(), data)
        return {"id": c["id"], "title": c["title"], "updated": c["updated"]}

    def chat_delete(self, chat_id: str) -> dict:
        data = self._chats_data()
        data["items"] = [x for x in data["items"] if x["id"] != chat_id]
        self._need_store().write_json(self._chats_path(), data)
        return self.chats_list()
