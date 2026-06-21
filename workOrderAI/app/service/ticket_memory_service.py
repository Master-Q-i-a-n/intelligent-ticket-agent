import hashlib
import json
import re
from datetime import datetime

from workOrderAI.app.model.database import get_db_connection
from workOrderAI.app.model.request import ReplyMessage, ReplySuggestRequest
from workOrderAI.models.factory import router_model
from workOrderAI.utils.config import config
from workOrderAI.utils.logger_handler import logger


EMPTY_TICKET_MEMORY = {
    "summary": "",
    "confirmed_facts": [],
    "attempted_steps": [],
    "unresolved": [],
    "history_cursor": "",
    "version": 0,
}


class TicketMemoryService:
    """Maintains compact, ticket-scoped working memory derived from reply history."""

    def __init__(self, model=None):
        self.model = model or router_model

    async def refresh(self, work_order: ReplySuggestRequest) -> dict:
        if not config.get("memory", {}).get("enabled", True):
            return self._with_recent_messages(dict(EMPTY_TICKET_MEMORY), work_order.history)

        try:
            self._ensure_table()
            existing = self.get_memory(work_order.id)
        except Exception as exc:
            logger.warning("[ticket-memory] load failed ticket_id=%s error=%s", work_order.id, exc)
            return self._with_recent_messages(dict(EMPTY_TICKET_MEMORY), work_order.history)

        new_messages, next_cursor = self._new_messages(work_order.history, existing.get("history_cursor", ""))
        if not new_messages:
            return self._with_recent_messages(existing, work_order.history)

        prompt = self._build_extract_prompt(work_order, existing, new_messages)
        try:
            result = await self.model.ainvoke(prompt)
            payload = self._parse_json_object(getattr(result, "content", result))
            memory = self._normalize_memory(payload, existing)
            memory["history_cursor"] = next_cursor
            memory["version"] = int(existing.get("version") or 0) + 1
            self._save(work_order.id, memory, int(existing.get("version") or 0))
            logger.info(
                "[ticket-memory] refreshed ticket_id=%s new_messages=%s version=%s",
                work_order.id,
                len(new_messages),
                memory["version"],
            )
            return self._with_recent_messages(memory, work_order.history)
        except Exception as exc:
            logger.warning("[ticket-memory] refresh degraded ticket_id=%s error=%s", work_order.id, exc)
            return self._with_recent_messages(existing, work_order.history)

    def get_memory(self, ticket_id: str) -> dict:
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    select history_cursor, summary, confirmed_facts_json, attempted_steps_json,
                           unresolved_json, version, updated_at
                    from wo_ticket_memory where ticket_id = %s
                    """,
                    (ticket_id,),
                )
                row = cursor.fetchone()
        finally:
            conn.close()

        if not row:
            return dict(EMPTY_TICKET_MEMORY)
        return {
            "summary": str(row.get("summary") or ""),
            "confirmed_facts": self._json_list(row.get("confirmed_facts_json")),
            "attempted_steps": self._json_list(row.get("attempted_steps_json")),
            "unresolved": self._json_list(row.get("unresolved_json")),
            "history_cursor": str(row.get("history_cursor") or ""),
            "version": int(row.get("version") or 0),
            "updated_at": str(row.get("updated_at") or ""),
        }

    def delete(self, ticket_id: str) -> None:
        self._ensure_table()
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("delete from wo_ticket_memory where ticket_id = %s", (ticket_id,))
            conn.commit()
        finally:
            conn.close()

    def _new_messages(self, history: list[ReplyMessage], current_cursor: str) -> tuple[list[ReplyMessage], str]:
        messages = list(history or [])
        next_cursor = self._history_cursor(messages)
        if not messages or current_cursor == next_cursor:
            return [], next_cursor

        if current_cursor and not current_cursor.startswith("hash:"):
            for index, message in enumerate(messages):
                if str(message.id or "") == current_cursor:
                    return messages[index + 1 :], next_cursor
        return messages, next_cursor

    def _history_cursor(self, history: list[ReplyMessage]) -> str:
        if history and history[-1].id:
            return str(history[-1].id)
        serialized = json.dumps(
            [
                {
                    "role": message.role,
                    "content": message.content,
                    "created_at": message.created_at,
                }
                for message in history or []
            ],
            ensure_ascii=False,
            sort_keys=True,
        )
        return "hash:" + hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:32]

    def _build_extract_prompt(self, work_order: ReplySuggestRequest, existing: dict, messages: list[ReplyMessage]) -> str:
        new_history = "\n".join(f"{item.role}：{item.content}" for item in messages if item.content.strip())
        return f"""你是工单工作记忆整理器。请基于已有记忆和新增真实对话，输出更新后的完整工作记忆。

规则：
1. 只记录对话明确支持的事实，不推测设备型号、原因或用户偏好。
2. attempted_steps 中每项格式为 {{"action":"操作","result":"结果","status":"SUCCESS|FAILED|UNKNOWN"}}。
3. 用户明确表示无效、仍未解决时标记 FAILED；明确恢复正常时标记 SUCCESS；否则 UNKNOWN。
4. 合并重复事实和重复步骤，summary 控制在200字以内。
5. unresolved 只保留仍需确认或尚未解决的问题。
6. 只输出严格 JSON。

工单标题：{work_order.title}
工单描述：{work_order.description}

已有记忆：
{json.dumps(existing, ensure_ascii=False)}

新增对话：
{new_history or "无"}

输出格式：
{{"summary":"","confirmed_facts":[],"attempted_steps":[],"unresolved":[]}}"""

    def _normalize_memory(self, payload: dict, existing: dict) -> dict:
        summary = str(payload.get("summary") or existing.get("summary") or "").strip()[:200]
        facts = self._dedupe_strings(payload.get("confirmed_facts", existing.get("confirmed_facts", [])))
        unresolved = self._dedupe_strings(payload.get("unresolved", existing.get("unresolved", [])))
        attempted_steps = []
        seen_actions = set()
        for item in payload.get("attempted_steps", existing.get("attempted_steps", [])) or []:
            if not isinstance(item, dict):
                continue
            action = str(item.get("action") or "").strip()
            if not action or action in seen_actions:
                continue
            seen_actions.add(action)
            status = str(item.get("status") or "UNKNOWN").strip().upper()
            attempted_steps.append(
                {
                    "action": action,
                    "result": str(item.get("result") or "").strip(),
                    "status": status if status in {"SUCCESS", "FAILED", "UNKNOWN"} else "UNKNOWN",
                }
            )
        return {
            "summary": summary,
            "confirmed_facts": facts,
            "attempted_steps": attempted_steps,
            "unresolved": unresolved,
        }

    def _with_recent_messages(self, memory: dict, history: list[ReplyMessage]) -> dict:
        limit = int(config.get("memory", {}).get("recent_message_limit", 4))
        result = dict(memory)
        result["recent_messages"] = [
            {"id": item.id or "", "role": item.role, "content": item.content, "created_at": item.created_at or ""}
            for item in (history or [])[-limit:]
            if str(item.content or "").strip()
        ]
        return result

    def _save(self, ticket_id: str, memory: dict, previous_version: int) -> None:
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                if previous_version > 0:
                    cursor.execute(
                        """
                        update wo_ticket_memory
                        set history_cursor=%s, summary=%s, confirmed_facts_json=%s,
                            attempted_steps_json=%s, unresolved_json=%s, version=%s, updated_at=%s
                        where ticket_id=%s and version=%s
                        """,
                        (
                            memory["history_cursor"],
                            memory["summary"],
                            json.dumps(memory["confirmed_facts"], ensure_ascii=False),
                            json.dumps(memory["attempted_steps"], ensure_ascii=False),
                            json.dumps(memory["unresolved"], ensure_ascii=False),
                            memory["version"],
                            now,
                            ticket_id,
                            previous_version,
                        ),
                    )
                    if cursor.rowcount == 0:
                        raise RuntimeError("ticket memory version conflict")
                else:
                    cursor.execute(
                        """
                        insert into wo_ticket_memory
                        (ticket_id, history_cursor, summary, confirmed_facts_json, attempted_steps_json,
                         unresolved_json, version, created_at, updated_at)
                        values (%s,%s,%s,%s,%s,%s,%s,%s,%s)
                        """,
                        (
                            ticket_id,
                            memory["history_cursor"],
                            memory["summary"],
                            json.dumps(memory["confirmed_facts"], ensure_ascii=False),
                            json.dumps(memory["attempted_steps"], ensure_ascii=False),
                            json.dumps(memory["unresolved"], ensure_ascii=False),
                            memory["version"],
                            now,
                            now,
                        ),
                    )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _ensure_table(self) -> None:
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    create table if not exists wo_ticket_memory (
                      ticket_id varchar(36) primary key,
                      history_cursor varchar(128) not null default '',
                      summary text not null,
                      confirmed_facts_json text not null,
                      attempted_steps_json text not null,
                      unresolved_json text not null,
                      version int not null default 1,
                      created_at varchar(19) not null,
                      updated_at varchar(19) not null
                    )
                    """
                )
            conn.commit()
        finally:
            conn.close()

    def _parse_json_object(self, content: object) -> dict:
        text = str(content or "")
        try:
            value = json.loads(text)
        except json.JSONDecodeError:
            match = re.search(r"\{[\s\S]*\}", text)
            if not match:
                return {}
            try:
                value = json.loads(match.group(0))
            except json.JSONDecodeError:
                return {}
        return value if isinstance(value, dict) else {}

    def _json_list(self, value: object) -> list:
        try:
            parsed = json.loads(str(value or "[]"))
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []

    def _dedupe_strings(self, values: object) -> list[str]:
        if not isinstance(values, list):
            return []
        result = []
        seen = set()
        for value in values:
            normalized = str(value or "").strip()
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
        return result
