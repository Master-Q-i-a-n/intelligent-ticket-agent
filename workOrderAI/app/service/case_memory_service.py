import asyncio
import html
import re
import uuid
from datetime import datetime

from langchain_core.documents import Document

from workOrderAI.app.model.database import get_db_connection
from workOrderAI.app.model.request import CaseMemoryUpsertRequest
from workOrderAI.models.factory import embed_model
from workOrderAI.utils.config import config
from workOrderAI.utils.logger_handler import logger
from workOrderAI.utils.vector_store import MilvusLiteVectorStore


class CaseMemoryService:
    """负责历史案例的元数据存储、向量写入和相似案例检索。"""

    COLLECTION_NAME = "case_memory_collection"

    def __init__(self):
        self.vector_store = None

    def _get_vector_store(self):
        if getattr(self, "vector_store", None) is None:
            self.vector_store = MilvusLiteVectorStore(
                collection_name=config["vector_store"].get("case_memory_collection_name", self.COLLECTION_NAME),
                embedding_function=embed_model,
            )
        return self.vector_store

    async def upsert_case(self, request: CaseMemoryUpsertRequest) -> dict | None:
        """仅把已解决/已关闭且含客服回复的工单沉淀为可检索案例。"""
        status = str(request.status or "").strip().upper()
        final_reply = self._plain_text(request.final_reply)
        if status not in {"SOLVED", "CLOSED"} or not final_reply:
            return None

        self._ensure_table()
        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        existing = self._find_by_ticket_id(request.ticket_id)
        case_id = existing["id"] if existing else "case-" + uuid.uuid4().hex[:12]
        vector_id = existing["vector_id"] if existing else case_id
        problem_text = self._build_problem_text(request.title, request.description)

        document = Document(
            page_content=self._build_vector_content(problem_text, final_reply),
            metadata={
                "case_id": case_id,
                "ticket_id": request.ticket_id,
                "ticket_code": request.ticket_code,
                "title": request.title,
                "final_reply": final_reply,
                "status": status,
            },
        )
        vector_store = self._get_vector_store()
        await asyncio.to_thread(vector_store.delete, ids=[vector_id])
        await asyncio.to_thread(vector_store.add_documents, [document], ids=[vector_id])

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                if existing:
                    cursor.execute(
                        """
                        update wo_case_memory
                        set ticket_code = %s, title = %s, problem_text = %s, final_reply = %s,
                            status = %s, vector_id = %s, updated_at = %s
                        where ticket_id = %s
                        """,
                        (
                            request.ticket_code,
                            request.title,
                            problem_text,
                            final_reply,
                            status,
                            vector_id,
                            now,
                            request.ticket_id,
                        ),
                    )
                else:
                    cursor.execute(
                        """
                        insert into wo_case_memory
                        (id, ticket_id, ticket_code, title, problem_text, final_reply, status, vector_id, created_at, updated_at)
                        values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        """,
                        (
                            case_id,
                            request.ticket_id,
                            request.ticket_code,
                            request.title,
                            problem_text,
                            final_reply,
                            status,
                            vector_id,
                            now,
                            now,
                        ),
                    )
            conn.commit()
        except Exception:
            await asyncio.to_thread(vector_store.delete, ids=[vector_id])
            raise
        finally:
            conn.close()

        logger.info("[case-memory] stored case ticket_id=%s, case_id=%s", request.ticket_id, case_id)
        return {
            "id": case_id,
            "ticket_id": request.ticket_id,
            "ticket_code": request.ticket_code,
            "title": request.title,
            "final_reply": final_reply,
            "status": status,
        }

    async def search_similar_cases(self, query: str, limit: int = 3) -> list[dict]:
        """按问题语义检索历史案例，返回给 Agent 复用处理经验。"""
        normalized_query = self._plain_text(query)
        if not normalized_query:
            return []

        try:
            vector_store = self._get_vector_store()
            matches = await asyncio.to_thread(
                vector_store.similarity_search_with_relevance_scores,
                normalized_query,
                k=limit,
            )
        except Exception as exc:
            logger.error("[case-memory] similar case search failed: %s", exc, exc_info=True)
            return []

        cases = []
        seen = set()
        min_score = float(config["vector_store"].get("case_memory_min_score", 0.45))
        for document, score in matches:
            metadata = document.metadata or {}
            ticket_id = str(metadata.get("ticket_id") or "").strip()
            numeric_score = float(score)
            if not ticket_id or ticket_id in seen or numeric_score < min_score:
                continue
            seen.add(ticket_id)
            cases.append(
                {
                    "ticket_id": ticket_id,
                    "ticket_code": str(metadata.get("ticket_code") or ""),
                    "title": str(metadata.get("title") or ""),
                    "final_reply": str(metadata.get("final_reply") or ""),
                    "similarity_score": round(numeric_score, 4),
                }
            )
        return cases

    def _ensure_table(self):
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    create table if not exists wo_case_memory (
                      id varchar(36) primary key,
                      ticket_id varchar(36) not null unique,
                      ticket_code varchar(32) not null,
                      title varchar(200) not null,
                      problem_text text not null,
                      final_reply text not null,
                      status varchar(32) not null,
                      vector_id varchar(36) not null unique,
                      created_at varchar(19) not null,
                      updated_at varchar(19) not null
                    )
                    """
                )
            conn.commit()
        finally:
            conn.close()

    def _find_by_ticket_id(self, ticket_id: str):
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "select id, vector_id from wo_case_memory where ticket_id = %s",
                    (ticket_id,),
                )
                return cursor.fetchone()
        finally:
            conn.close()

    def _build_problem_text(self, title: str, description: str) -> str:
        title_text = self._plain_text(title)
        description_text = self._plain_text(description)
        return f"{title_text}\n{description_text}".strip()

    def _build_vector_content(self, problem_text: str, final_reply: str) -> str:
        return f"问题：{problem_text}\n最终回复：{final_reply}"

    def _plain_text(self, value: str | None) -> str:
        text = html.unescape(str(value or ""))
        text = re.sub(r"<[^>]+>", " ", text)
        return re.sub(r"\s+", " ", text).strip()
