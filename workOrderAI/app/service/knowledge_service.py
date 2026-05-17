import base64
import hashlib
import os
import uuid
from datetime import datetime
from pathlib import Path

import aiofiles

from workOrderAI.app.model.database import get_db_connection
from workOrderAI.app.service.rag_service import RagService
from workOrderAI.utils.config import config
from workOrderAI.utils.path_tool import get_abs_path
from workOrderAI.utils.vector_store import VectorStoreService


class KnowledgeService:
    def __init__(self):
        self.vector_store = VectorStoreService()
        self.allowed_types = set(config["vector_store"]["allow_knowledge_file_types"])

    async def answer(self, question: str) -> dict:
        return await RagService().rag_qa(question)

    def list_documents(self) -> dict:
        self._ensure_table()
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    select id, title, file_name, file_ext, file_size, created_by, status, created_at
                    from wo_knowledge_document
                    order by created_at desc
                    """
                )
                rows = cursor.fetchall()
        finally:
            conn.close()

        return {"total": len(rows), "items": rows}

    async def upload_document(self, file_name: str, content_base64: str, created_by: str) -> dict:
        self._ensure_table()
        safe_file_name = self._sanitize_filename(file_name)
        ext = self._extract_extension(safe_file_name)
        if ext not in self.allowed_types:
            raise ValueError("unsupported knowledge file type")

        try:
            content = base64.b64decode(content_base64, validate=True)
        except Exception as exc:
            raise ValueError("invalid file content") from exc
        if not content:
            raise ValueError("file is empty")

        content_md5 = hashlib.md5(content).hexdigest()
        existing = self._find_by_md5(content_md5)
        if existing:
            raise ValueError("knowledge file already exists")

        document_id = "kb-" + uuid.uuid4().hex[:12]
        storage_rel_path = f"data/knowledge_docs/{document_id}__{safe_file_name}"
        storage_abs_path = Path(get_abs_path(storage_rel_path))
        storage_abs_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiofiles.open(storage_abs_path, "wb") as file:
            await file.write(content)

        chunk_count = await self.vector_store.ingest_file(
            str(storage_abs_path),
            {
                "document_id": document_id,
                "title": Path(safe_file_name).stem,
                "file_name": safe_file_name,
            },
        )
        if chunk_count <= 0:
            storage_abs_path.unlink(missing_ok=True)
            raise ValueError("knowledge file has no readable content")

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    insert into wo_knowledge_document
                    (id, title, file_name, file_ext, file_size, content_md5, storage_path, created_by, status, created_at, updated_at)
                    values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """,
                    (
                        document_id,
                        Path(safe_file_name).stem,
                        safe_file_name,
                        ext,
                        len(content),
                        content_md5,
                        storage_rel_path,
                        created_by,
                        "active",
                        now,
                        now,
                    ),
                )
            conn.commit()
        except Exception:
            await self.vector_store.delete_document(document_id)
            storage_abs_path.unlink(missing_ok=True)
            raise
        finally:
            conn.close()

        await self.vector_store.invalidate_retriever_cache()
        return {
            "id": document_id,
            "title": Path(safe_file_name).stem,
            "file_name": safe_file_name,
            "file_ext": ext,
            "file_size": len(content),
            "created_by": created_by,
            "status": "active",
            "created_at": now,
        }

    async def delete_document(self, document_id: str) -> bool:
        self._ensure_table()
        document = self._find_by_id(document_id)
        if not document:
            return False

        await self.vector_store.delete_document(document_id)
        storage_path = Path(get_abs_path(document["storage_path"]))
        storage_path.unlink(missing_ok=True)

        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute("delete from wo_knowledge_document where id = %s", (document_id,))
            conn.commit()
        finally:
            conn.close()
        await self.vector_store.invalidate_retriever_cache()
        return True

    def _ensure_table(self):
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    create table if not exists wo_knowledge_document (
                      id varchar(36) primary key,
                      title varchar(255) not null,
                      file_name varchar(255) not null,
                      file_ext varchar(32) not null,
                      file_size bigint not null,
                      content_md5 varchar(32) not null unique,
                      storage_path varchar(500) not null,
                      created_by varchar(64) not null,
                      status varchar(32) not null,
                      created_at varchar(19) not null,
                      updated_at varchar(19) not null
                    )
                    """
                )
            conn.commit()
        finally:
            conn.close()

    def _find_by_md5(self, content_md5: str):
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "select id from wo_knowledge_document where content_md5 = %s",
                    (content_md5,),
                )
                return cursor.fetchone()
        finally:
            conn.close()

    def _find_by_id(self, document_id: str):
        conn = get_db_connection()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    "select id, storage_path from wo_knowledge_document where id = %s",
                    (document_id,),
                )
                return cursor.fetchone()
        finally:
            conn.close()

    def _sanitize_filename(self, file_name: str) -> str:
        normalized = os.path.basename(str(file_name or "").strip()).replace("\\", "_").replace("/", "_")
        return normalized or "knowledge.txt"

    def _extract_extension(self, file_name: str) -> str:
        suffix = Path(file_name).suffix.lower().lstrip(".")
        return suffix
