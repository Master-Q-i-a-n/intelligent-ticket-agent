import asyncio
import hashlib
import html
import json
import re
import uuid
from datetime import datetime

from langchain_core.documents import Document

from workOrderAI.app.model.database import get_db_connection
from workOrderAI.app.model.request import CaseMemoryUpsertRequest
from workOrderAI.models.factory import embed_model, reranker_model
from workOrderAI.utils.config import config
from workOrderAI.utils.logger_handler import logger
from workOrderAI.utils.vector_store import MilvusLiteVectorStore


class CaseMemoryService:
    """Persists case metadata in MySQL and indexes problem-only vectors in Milvus."""

    COLLECTION_NAME = "case_memory_collection"

    def __init__(self, reranker=None):
        self.vector_store = None
        self.reranker = reranker or reranker_model

    def _get_vector_store(self):
        if self.vector_store is None:
            self.vector_store = MilvusLiteVectorStore(
                collection_name=config["vector_store"].get("case_memory_collection_name", self.COLLECTION_NAME),
                embedding_function=embed_model,
            )
        return self.vector_store

    async def sync_case(self, request: CaseMemoryUpsertRequest, ticket_memory: dict | None = None) -> dict | None:
        self._ensure_table()
        status = str(request.status or "").strip().upper()
        final_reply = self._plain_text(request.final_reply)
        if status not in {"SOLVED", "CLOSED"} or not final_reply:
            await self.deactivate_case(request.ticket_id, status)
            return None

        memory = ticket_memory or {}
        now = self._now()
        existing = self._find_by_ticket_id(request.ticket_id)
        case_id = existing["id"] if existing else "case-" + uuid.uuid4().hex[:12]
        vector_id = existing["vector_id"] if existing else case_id
        problem_text = self._build_problem_text(request.title, request.description)
        problem_summary = self._plain_text(memory.get("summary")) or problem_text
        confirmed_facts = list(memory.get("confirmed_facts") or [])
        resolution_steps = list(memory.get("attempted_steps") or [])
        category = self._plain_text(request.category)

        row = {
            "id": case_id,
            "ticket_id": request.ticket_id,
            "ticket_code": request.ticket_code,
            "title": self._plain_text(request.title),
            "problem_text": problem_text,
            "problem_summary": problem_summary,
            "confirmed_facts_json": json.dumps(confirmed_facts, ensure_ascii=False),
            "resolution_steps_json": json.dumps(resolution_steps, ensure_ascii=False),
            "resolution_result": status,
            "final_reply": final_reply,
            "category": category,
            "status": status,
            "quality_score": 0.8,
            "active": 1,
            "memory_version": int(existing.get("memory_version") or 0) + 1 if existing else 1,
            "embedding_model": str(config["model"].get("embedding_model") or ""),
            "vector_id": vector_id,
            "vector_sync_status": "PENDING",
            "solved_at": now,
            "created_at": str(existing.get("created_at") or now) if existing else now,
            "updated_at": now,
        }
        self._upsert_row(row)

        document = self._to_vector_document(row)
        try:
            vector_store = self._get_vector_store()
            await asyncio.to_thread(vector_store.delete, ids=[vector_id])
            await asyncio.to_thread(vector_store.add_documents, [document], ids=[vector_id])
            self._mark_vector_status(request.ticket_id, "SYNCED")
            row["vector_sync_status"] = "SYNCED"
        except Exception as exc:
            logger.error("[case-memory] vector sync pending ticket_id=%s error=%s", request.ticket_id, exc, exc_info=True)

        logger.info("[case-memory] synced ticket_id=%s active=1 vector_status=%s", request.ticket_id, row["vector_sync_status"])
        return row

    async def upsert_case(self, request: CaseMemoryUpsertRequest) -> dict | None:
        """兼容旧调用方；新代码应使用 sync_case 表达状态同步语义。"""
        return await self.sync_case(request)

    async def deactivate_case(self, ticket_id: str, status: str = "") -> None:
        existing = self._find_by_ticket_id(ticket_id)
        if not existing:
            return
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "update wo_case_memory set active=0, status=%s, vector_sync_status='PENDING', updated_at=%s where ticket_id=%s",
                    (status or "INACTIVE", self._now(), ticket_id),
                )
            conn.commit()
        finally:
            conn.close()

        try:
            await asyncio.to_thread(self._get_vector_store().delete, ids=[existing["vector_id"]])
            self._mark_vector_status(ticket_id, "SYNCED")
        except Exception as exc:
            logger.error("[case-memory] deactivate vector pending ticket_id=%s error=%s", ticket_id, exc, exc_info=True)

    async def delete_case(self, ticket_id: str) -> None:
        existing = self._find_by_ticket_id(ticket_id)
        if existing:
            try:
                await asyncio.to_thread(self._get_vector_store().delete, ids=[existing["vector_id"]])
            except Exception as exc:
                logger.warning("[case-memory] delete vector failed ticket_id=%s error=%s", ticket_id, exc)
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("delete from wo_case_memory where ticket_id=%s", (ticket_id,))
            conn.commit()
        finally:
            conn.close()

    async def search_similar_cases(self, query: str, limit: int | None = None, category: str = "") -> list[dict]:
        normalized_query = self._plain_text(query)
        if not normalized_query:
            return []

        memory_config = config.get("memory", {})
        candidate_limit = int(memory_config.get("case_candidate_limit", 8))
        selected_limit = int(limit or memory_config.get("case_limit", 2))
        min_score = float(config["vector_store"].get("case_memory_min_score", 0.45))
        try:
            matches = await asyncio.to_thread(
                self._get_vector_store().similarity_search_with_relevance_scores,
                normalized_query,
                candidate_limit,
            )
        except Exception as exc:
            logger.error("[case-memory] search failed: %s", exc, exc_info=True)
            return []

        candidates = []
        score_by_ticket = {}
        for document, score in matches:
            ticket_id = str((document.metadata or {}).get("ticket_id") or "").strip()
            numeric_score = float(score)
            if ticket_id and numeric_score >= min_score and ticket_id not in score_by_ticket:
                document.metadata = dict(document.metadata or {})
                document.metadata["similarity_score"] = numeric_score
                candidates.append(document)
                score_by_ticket[ticket_id] = numeric_score
        if not candidates:
            return []

        active_rows = self._active_rows(list(score_by_ticket), category)
        row_by_ticket = {str(row["ticket_id"]): row for row in active_rows}
        candidates = [doc for doc in candidates if str(doc.metadata.get("ticket_id")) in row_by_ticket]
        try:
            reranked = list(await self.reranker.acompress_documents(candidates, normalized_query))[:selected_limit]
        except Exception as exc:
            logger.warning("[case-memory] rerank failed, use vector order: %s", exc)
            reranked = candidates[:selected_limit]

        cases = []
        for document in reranked:
            ticket_id = str(document.metadata.get("ticket_id") or "")
            row = row_by_ticket.get(ticket_id)
            if not row:
                continue
            cases.append(
                {
                    "ticket_id": ticket_id,
                    "ticket_code": str(row.get("ticket_code") or ""),
                    "title": str(row.get("title") or ""),
                    "final_reply": str(row.get("final_reply") or ""),
                    "resolution_steps": self._json_list(row.get("resolution_steps_json")),
                    "similarity_score": round(float(score_by_ticket.get(ticket_id, 0.0)), 4),
                }
            )
        logger.info(
            "[case-memory] retrieval query_hash=%s category=%s candidates=%s active=%s selected=%s",
            hashlib.sha256(normalized_query.encode("utf-8")).hexdigest()[:12],
            category or "*",
            len(matches),
            len(candidates),
            len(cases),
        )
        return cases

    async def rebuild_vectors(self) -> dict:
        self._ensure_table()
        rows = self._all_rows()
        vector_store = self._get_vector_store()
        ids = [str(row.get("vector_id") or "") for row in rows if row.get("vector_id")]
        if ids:
            await asyncio.to_thread(vector_store.delete, ids=ids)

        active_rows = [row for row in rows if int(row.get("active") or 0) == 1]
        if active_rows:
            documents = [self._to_vector_document(row) for row in active_rows]
            active_ids = [str(row["vector_id"]) for row in active_rows]
            await asyncio.to_thread(vector_store.add_documents, documents, ids=active_ids)

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("update wo_case_memory set vector_sync_status='SYNCED', updated_at=%s", (self._now(),))
            conn.commit()
        finally:
            conn.close()
        return {"total": len(rows), "active": len(active_rows)}

    def _to_vector_document(self, row: dict) -> Document:
        content = self._build_vector_content(
            str(row.get("title") or ""),
            str(row.get("problem_summary") or row.get("problem_text") or ""),
            self._json_list(row.get("confirmed_facts_json")),
            str(row.get("category") or ""),
        )
        return Document(
            page_content=content,
            metadata={
                "case_id": str(row.get("id") or ""),
                "ticket_id": str(row.get("ticket_id") or ""),
                "ticket_code": str(row.get("ticket_code") or ""),
                "title": str(row.get("title") or ""),
                "category": str(row.get("category") or ""),
                "active": bool(row.get("active")),
            },
        )

    def _build_vector_content(self, title: str, problem_summary: str, confirmed_facts: list, category: str) -> str:
        parts = [f"标题：{title}", f"问题：{problem_summary}"]
        if confirmed_facts:
            parts.append("已确认现象：" + "；".join(str(item) for item in confirmed_facts))
        if category:
            parts.append(f"分类：{category}")
        return "\n".join(parts)

    def _build_problem_text(self, title: str, description: str) -> str:
        return f"{self._plain_text(title)}\n{self._plain_text(description)}".strip()

    def _upsert_row(self, row: dict) -> None:
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    insert into wo_case_memory
                    (id,ticket_id,ticket_code,title,problem_text,problem_summary,confirmed_facts_json,
                     resolution_steps_json,resolution_result,final_reply,category,status,quality_score,
                     active,memory_version,embedding_model,vector_id,vector_sync_status,solved_at,created_at,updated_at)
                    values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    on duplicate key update
                      ticket_code=values(ticket_code), title=values(title), problem_text=values(problem_text),
                      problem_summary=values(problem_summary), confirmed_facts_json=values(confirmed_facts_json),
                      resolution_steps_json=values(resolution_steps_json), resolution_result=values(resolution_result),
                      final_reply=values(final_reply), category=values(category), status=values(status),
                      quality_score=values(quality_score), active=values(active), memory_version=values(memory_version),
                      embedding_model=values(embedding_model), vector_id=values(vector_id),
                      vector_sync_status=values(vector_sync_status), solved_at=values(solved_at), updated_at=values(updated_at)
                    """,
                    tuple(row[key] for key in [
                        "id", "ticket_id", "ticket_code", "title", "problem_text", "problem_summary",
                        "confirmed_facts_json", "resolution_steps_json", "resolution_result", "final_reply",
                        "category", "status", "quality_score", "active", "memory_version", "embedding_model",
                        "vector_id", "vector_sync_status", "solved_at", "created_at", "updated_at",
                    ]),
                )
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _active_rows(self, ticket_ids: list[str], category: str) -> list[dict]:
        if not ticket_ids:
            return []
        placeholders = ",".join(["%s"] * len(ticket_ids))
        sql = f"select * from wo_case_memory where active=1 and ticket_id in ({placeholders})"
        args = list(ticket_ids)
        if category:
            sql += " and (category=%s or category='')"
            args.append(category)
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, tuple(args))
                return list(cursor.fetchall() or [])
        finally:
            conn.close()

    def _all_rows(self) -> list[dict]:
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("select * from wo_case_memory order by created_at")
                return list(cursor.fetchall() or [])
        finally:
            conn.close()

    def _find_by_ticket_id(self, ticket_id: str):
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("select * from wo_case_memory where ticket_id=%s", (ticket_id,))
                return cursor.fetchone()
        finally:
            conn.close()

    def _mark_vector_status(self, ticket_id: str, status: str) -> None:
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "update wo_case_memory set vector_sync_status=%s, updated_at=%s where ticket_id=%s",
                    (status, self._now(), ticket_id),
                )
            conn.commit()
        finally:
            conn.close()

    def _ensure_table(self) -> None:
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    create table if not exists wo_case_memory (
                      id varchar(36) primary key, ticket_id varchar(36) not null unique,
                      ticket_code varchar(32) not null, title varchar(200) not null,
                      problem_text text not null, final_reply text not null, status varchar(32) not null,
                      vector_id varchar(36) not null unique, created_at varchar(19) not null, updated_at varchar(19) not null
                    )
                    """
                )
                cursor.execute("show columns from wo_case_memory")
                columns = {row["Field"] for row in cursor.fetchall()}
                additions = {
                    "problem_summary": "text",
                    "confirmed_facts_json": "text",
                    "resolution_steps_json": "text",
                    "resolution_result": "varchar(64) not null default ''",
                    "category": "varchar(64) not null default ''",
                    "quality_score": "double not null default 0.8",
                    "active": "tinyint not null default 1",
                    "memory_version": "int not null default 1",
                    "embedding_model": "varchar(128) not null default ''",
                    "vector_sync_status": "varchar(32) not null default 'PENDING'",
                    "solved_at": "varchar(19) not null default ''",
                }
                for name, definition in additions.items():
                    if name not in columns:
                        cursor.execute(f"alter table wo_case_memory add column {name} {definition}")
                cursor.execute("update wo_case_memory set problem_summary=problem_text where problem_summary is null or problem_summary='' ")
                cursor.execute("update wo_case_memory set confirmed_facts_json='[]' where confirmed_facts_json is null")
                cursor.execute("update wo_case_memory set resolution_steps_json='[]' where resolution_steps_json is null")
            conn.commit()
        finally:
            conn.close()

    def _plain_text(self, value: object) -> str:
        text = html.unescape(str(value or ""))
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()

    def _json_list(self, value: object) -> list:
        if isinstance(value, list):
            return value
        try:
            parsed = json.loads(str(value or "[]"))
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []

    def _now(self) -> str:
        return datetime.now().strftime("%Y-%m-%d %H:%M:%S")
