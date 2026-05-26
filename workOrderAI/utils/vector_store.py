import asyncio
import os
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any

import aiofiles
from aiofiles import os as aio_os
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda
from langchain_community.retrievers import BM25Retriever
from langchain_classic.retrievers import EnsembleRetriever
from pymilvus import DataType, MilvusClient

from workOrderAI.models.factory import embed_model
from workOrderAI.utils.config import config
from workOrderAI.utils.file_handler import (
    get_file_md5_hex,
    markdown_loader,
    pdf_loader,
    ppt_loader,
    txt_loader,
    word_loader,
)
from workOrderAI.utils.file_handler import listdir_allowed_type
from workOrderAI.utils.logger_handler import logger
from workOrderAI.utils.path_tool import get_abs_path
from workOrderAI.utils.text_spliter import AsyncTextSplitter


class MilvusLiteVectorStore:
    """Small adapter that keeps the vector-store methods used by the app."""

    PRIMARY_FIELD = "id"
    TEXT_FIELD = "text"
    VECTOR_FIELD = "vector"
    METADATA_FIELD = "metadata"

    def __init__(self, collection_name: str, embedding_function, uri: str | None = None):
        self.collection_name = collection_name
        self.embedding_function = embedding_function
        self.uri = self._normalize_uri(uri or config["vector_store"].get("milvus_uri", "data/milvus_lite.db"))
        self.metric_type = config["vector_store"].get("milvus_metric_type", "COSINE")
        try:
            self.client = MilvusClient(uri=self.uri)
        except Exception as exc:
            message = str(exc)
            if "milvus-lite is required" in message or "milvus_lite" in message:
                raise RuntimeError(
                    "Milvus Lite local file mode requires the milvus-lite package. "
                    "Install it in the Agent environment with: pip install \"pymilvus[milvus_lite]\""
                ) from exc
            raise

    def _normalize_uri(self, uri: str) -> str:
        uri = str(uri or "").strip()
        if uri.startswith(("http://", "https://", "tcp://")):
            return uri

        path = Path(uri if os.path.isabs(uri) else get_abs_path(uri))
        path.parent.mkdir(parents=True, exist_ok=True)
        return path.as_posix()

    def _has_collection(self) -> bool:
        return bool(self.client.has_collection(self.collection_name))

    def _ensure_collection(self, vector_dim: int) -> None:
        if self._has_collection():
            return

        schema = MilvusClient.create_schema(auto_id=False, enable_dynamic_field=True)
        schema.add_field(
            field_name=self.PRIMARY_FIELD,
            datatype=DataType.VARCHAR,
            is_primary=True,
            max_length=512,
        )
        schema.add_field(
            field_name=self.TEXT_FIELD,
            datatype=DataType.VARCHAR,
            max_length=65535,
        )
        schema.add_field(
            field_name=self.VECTOR_FIELD,
            datatype=DataType.FLOAT_VECTOR,
            dim=vector_dim,
        )
        schema.add_field(field_name=self.METADATA_FIELD, datatype=DataType.JSON)

        index_params = MilvusClient.prepare_index_params()
        index_params.add_index(
            field_name=self.VECTOR_FIELD,
            index_type="AUTOINDEX",
            metric_type=self.metric_type,
        )
        self.client.create_collection(
            collection_name=self.collection_name,
            schema=schema,
            index_params=index_params,
        )

    def _ensure_collection_loaded(self) -> None:
        if not self._has_collection():
            return

        try:
            state = self.client.get_load_state(collection_name=self.collection_name)
            state_text = str(state.get("state", "")).lower() if isinstance(state, dict) else str(state).lower()
            if "loaded" in state_text:
                return
        except Exception as exc:
            logger.debug("[vector-store] failed to read load state for %s: %s", self.collection_name, exc)

        self.client.load_collection(collection_name=self.collection_name)

    def add_documents(self, documents: list[Document], ids: list[str] | None = None, **_: Any) -> list[str]:
        if not documents:
            return []

        texts = [str(doc.page_content or "") for doc in documents]
        embeddings = self.embedding_function.embed_documents(texts)
        if not embeddings:
            return []

        self._ensure_collection(len(embeddings[0]))

        if ids is None:
            ids = [uuid.uuid4().hex for _ in documents]

        rows = []
        for doc_id, doc, vector in zip(ids, documents, embeddings):
            metadata = self._clean_metadata(doc.metadata or {})
            row = {
                self.PRIMARY_FIELD: str(doc_id),
                self.TEXT_FIELD: str(doc.page_content or ""),
                self.VECTOR_FIELD: vector,
                self.METADATA_FIELD: metadata,
            }
            # Keep common filter keys as dynamic scalar fields so deletes can use simple expr filters.
            for key in ("document_id", "user_id", "case_id", "ticket_id"):
                value = metadata.get(key)
                if value not in (None, ""):
                    row[key] = str(value)
            rows.append(row)

        self.client.upsert(collection_name=self.collection_name, data=rows)
        return [str(item) for item in ids]

    def delete(self, ids: list[str] | None = None, expr: str | None = None, **_: Any):
        if not self._has_collection():
            return {"delete_count": 0}
        if ids:
            return self.client.delete(collection_name=self.collection_name, ids=[str(item) for item in ids])
        if expr:
            return self.client.delete(collection_name=self.collection_name, filter=expr)
        return {"delete_count": 0}

    def close(self) -> None:
        self.client.close()

    def similarity_search_with_relevance_scores(self, query: str, k: int = 4, **_: Any) -> list[tuple[Document, float]]:
        if not self._has_collection():
            return []

        self._ensure_collection_loaded()
        query_vector = self.embedding_function.embed_query(str(query or ""))
        results = self.client.search(
            collection_name=self.collection_name,
            data=[query_vector],
            limit=k,
            output_fields=[self.TEXT_FIELD, self.METADATA_FIELD],
            search_params={"metric_type": self.metric_type},
        )

        matches = []
        for hit in results[0] if results else []:
            entity = hit.get("entity") or {}
            metadata = entity.get(self.METADATA_FIELD) or {}
            if not isinstance(metadata, dict):
                metadata = {}
            vector_id = hit.get("id") or hit.get(self.PRIMARY_FIELD)
            if vector_id:
                metadata.setdefault("vector_id", str(vector_id))
            text = entity.get(self.TEXT_FIELD) or ""
            raw_score = float(hit.get("distance", hit.get("score", 0.0)) or 0.0)
            score = self._to_relevance_score(raw_score)
            matches.append((Document(page_content=text, metadata=metadata), score))
        return matches

    def _to_relevance_score(self, raw_score: float) -> float:
        if self.metric_type.upper() == "COSINE":
            return max(0.0, min(1.0, 1.0 - raw_score))
        return raw_score

    def similarity_search(self, query: str, k: int = 4, **kwargs: Any) -> list[Document]:
        return [document for document, _ in self.similarity_search_with_relevance_scores(query, k=k, **kwargs)]

    def as_retriever(self, search_type: str = "similarity", search_kwargs: dict | None = None):
        search_kwargs = search_kwargs or {}
        k = int(search_kwargs.get("k", config["vector_store"]["k"]))

        def invoke(query: str) -> list[Document]:
            return self._documents_with_scores(query, k=k)

        async def ainvoke(query: str) -> list[Document]:
            return await asyncio.to_thread(self._documents_with_scores, query, k)

        return RunnableLambda(invoke, afunc=ainvoke)

    def _documents_with_scores(self, query: str, k: int = 4) -> list[Document]:
        documents = []
        for document, score in self.similarity_search_with_relevance_scores(query, k=k):
            document.metadata = dict(document.metadata or {})
            document.metadata["relevance_score"] = score
            documents.append(document)
        return documents

    def _clean_metadata(self, metadata: dict) -> dict:
        clean = {}
        for key, value in metadata.items():
            if value is None:
                clean[str(key)] = ""
            elif isinstance(value, (str, int, float, bool)):
                clean[str(key)] = value
            else:
                clean[str(key)] = str(value)
        return clean


class VectorStoreService:
    _cached_vector_retriever = None
    _cached_bm25_retriever = None
    _retriever_cache_initialized = False
    _retriever_cache_lock = asyncio.Lock()

    def __init__(self):
        provider = config["vector_store"].get("provider", "milvus_lite")
        if provider != "milvus_lite":
            raise ValueError(f"Unsupported vector_store provider: {provider}")

        self.vectors_store = MilvusLiteVectorStore(
            collection_name=config["vector_store"]["collection_name"],
            embedding_function=embed_model,
        )
        self.spliter = AsyncTextSplitter(
            chunk_size=config["vector_store"]["chunk_size"],
            chunk_overlap=config["vector_store"]["chunk_overlap"],
            separators=config["vector_store"]["separators"],
            embedding_model=embed_model,
        )

    async def get_bm25_retriever(self) -> BM25Retriever:
        _, bm25_retriever = await self._get_cached_base_retrievers()
        return bm25_retriever

    async def _list_knowledge_file_paths(self) -> list[str]:
        return await listdir_allowed_type(
            config["vector_store"]["data_path"],
            tuple(config["vector_store"]["allow_knowledge_file_types"]),
            tuple(config["vector_store"].get("knowledge_exclude_paths", [])),
        )

    async def _build_bm25_retriever(self) -> BM25Retriever | None:
        allowed_file_path = await self._list_knowledge_file_paths()

        all_docs = []
        for file_path in allowed_file_path:
            documents = await self.get_file_document(file_path)
            if documents:
                split_docs = await self.spliter.split_documents(documents)
                all_docs.extend(split_docs)

        if not all_docs:
            return None

        return BM25Retriever.from_documents(
            documents=all_docs,
            k=self._retriever_k(),
        )

    async def _get_cached_base_retrievers(self):
        cls = type(self)
        if cls._retriever_cache_initialized:
            return cls._cached_vector_retriever, cls._cached_bm25_retriever

        async with cls._retriever_cache_lock:
            if not cls._retriever_cache_initialized:
                started_at = time.perf_counter()
                cls._cached_vector_retriever = self.vectors_store.as_retriever(
                    search_type="similarity",
                    search_kwargs={"k": self._retriever_k()},
                )
                cls._cached_bm25_retriever = await self._build_bm25_retriever()
                cls._retriever_cache_initialized = True
                elapsed = time.perf_counter() - started_at
                logger.info(
                    "[retriever-cache] base retrievers ready, elapsed: %.2fs, bm25=%s",
                    elapsed,
                    "yes" if cls._cached_bm25_retriever else "no",
                )
        return cls._cached_vector_retriever, cls._cached_bm25_retriever

    def _retriever_k(self) -> int:
        return int(config["vector_store"].get("rerank_candidate_k") or config["vector_store"]["k"])

    @classmethod
    async def invalidate_retriever_cache(cls):
        async with cls._retriever_cache_lock:
            cls._cached_vector_retriever = None
            cls._cached_bm25_retriever = None
            cls._retriever_cache_initialized = False
        logger.info("[retriever-cache] invalidated")

    async def get_retriever(self, query: str = None):
        vector_retriever, bm25_retriever = await self._get_cached_base_retrievers()
        if bm25_retriever:
            return EnsembleRetriever(
                retrievers=[vector_retriever, bm25_retriever],
                weights=await self.get_dynamic_weights(query),
            )
        return vector_retriever

    async def similarity_search_with_relevance_scores(self, query: str, k: int | None = None):
        return await asyncio.to_thread(
            self.vectors_store.similarity_search_with_relevance_scores,
            query,
            k or config["vector_store"]["k"],
        )

    @staticmethod
    async def get_dynamic_weights(query: str = None):
        default_vector_weight = 0.5
        default_bm25_weight = 0.5

        if not query:
            return [default_vector_weight, default_bm25_weight]

        query_length = len(query)
        query_words = len(query.split())
        has_chinese = any("\u4e00" <= char <= "\u9fff" for char in query)

        if query_length > 50:
            vector_weight = 0.7
            bm25_weight = 0.3
        elif query_length < 20:
            if has_chinese:
                vector_weight = 0.7
                bm25_weight = 0.3
            else:
                vector_weight = 0.3
                bm25_weight = 0.7
        else:
            vector_weight = default_vector_weight
            bm25_weight = default_bm25_weight

        if query_words > 0 and not (query_length < 20 and has_chinese):
            word_density = query_words / query_length
            if word_density > 0.1:
                bm25_weight = min(bm25_weight + 0.1, 0.7)
                vector_weight = max(vector_weight - 0.1, 0.3)

        return [vector_weight, bm25_weight]

    async def check_md5_hex(self, md5_for_check: str) -> bool:
        md5_path = get_abs_path(config["vector_store"]["md5_hex_store"])
        md5_dir = os.path.dirname(md5_path)
        if not await aio_os.path.exists(md5_dir):
            await aio_os.makedirs(md5_dir, exist_ok=True)
        if not await aio_os.path.exists(md5_path):
            async with aiofiles.open(md5_path, "w", encoding="utf-8"):
                pass
            return False

        async with aiofiles.open(md5_path, "r", encoding="utf-8") as f:
            async for line in f:
                if line.strip() == md5_for_check:
                    return True
        return False

    async def save_md5_hex(self, md5_hex: str):
        md5_path = get_abs_path(config["vector_store"]["md5_hex_store"])
        md5_dir = os.path.dirname(md5_path)
        if not await aio_os.path.exists(md5_dir):
            await aio_os.makedirs(md5_dir, exist_ok=True)
        async with aiofiles.open(md5_path, "a", encoding="utf-8") as f:
            await f.write(md5_hex + "\n")

    async def delete_user_documents(self, user_id: str):
        await self._delete_by_metadata({"user_id": user_id})
        logger.info("[vector-store] deleted all documents for user_id=%s", user_id)

    async def delete_document(self, document_id: str):
        await self._delete_by_metadata({"document_id": document_id})
        logger.info("[vector-store] deleted document chunks for document_id=%s", document_id)

    async def _delete_by_metadata(self, where: dict):
        expr = self._build_filter_expr(where)
        if expr:
            await asyncio.to_thread(self.vectors_store.delete, expr=expr)

    def _build_filter_expr(self, where: dict) -> str:
        parts = []
        for key, value in where.items():
            key = str(key or "").strip()
            if not key:
                continue
            parts.append(f'{key} == "{self._escape_expr_value(value)}"')
        return " and ".join(parts)

    def _escape_expr_value(self, value: object) -> str:
        return str(value or "").replace("\\", "\\\\").replace('"', '\\"')

    async def get_file_document(self, read_path: str) -> list[Document]:
        if read_path.endswith(".txt"):
            return await txt_loader(read_path)
        if read_path.endswith(".pdf"):
            return await pdf_loader(read_path)
        if read_path.endswith(".md"):
            return await markdown_loader(read_path)
        if read_path.endswith(".pptx"):
            return await ppt_loader(read_path)
        if read_path.endswith(".docx"):
            return await word_loader(read_path)
        return []

    async def get_document(self, files: list = None, user_id: str = None):
        file_paths = []
        if files:
            for file in files:
                temp_file = await asyncio.to_thread(
                    tempfile.NamedTemporaryFile,
                    delete=False,
                    suffix=os.path.splitext(file.filename)[1],
                )
                content = await file.read()
                await asyncio.to_thread(temp_file.write, content)
                await asyncio.to_thread(temp_file.close)
                file_paths.append(temp_file.name)
        else:
            file_paths = await self._list_knowledge_file_paths()

        for file_path in file_paths:
            md5_hex = await get_file_md5_hex(file_path)
            if await self.check_md5_hex(md5_hex):
                logger.info("[vector-store] md5 exists, skip file=%s", file_path)
                if files:
                    self._safe_unlink(file_path)
                continue

            try:
                documents = await self.get_file_document(file_path)
                if not documents:
                    logger.error("[vector-store] file content is empty, skip file=%s", file_path)
                    if files:
                        self._safe_unlink(file_path)
                    continue

                split_documents = await self.spliter.split_documents(documents)
                if not split_documents:
                    logger.error("[vector-store] split content is empty, skip file=%s", file_path)
                    if files:
                        self._safe_unlink(file_path)
                    continue

                if user_id:
                    for doc in split_documents:
                        doc.metadata["user_id"] = user_id

                ids = self._build_chunk_ids(md5_hex, split_documents)
                await asyncio.to_thread(self.vectors_store.add_documents, split_documents, ids=ids)
                await self.save_md5_hex(md5_hex)
                logger.info("[vector-store] file ingested, file=%s, chunks=%s", file_path, len(split_documents))

                if files:
                    self._safe_unlink(file_path)
            except Exception as exc:
                logger.error("[vector-store] failed to process file=%s: %s", file_path, exc, exc_info=True)
                if files:
                    self._safe_unlink(file_path)

    async def ingest_file(self, file_path: str, metadata: dict | None = None) -> int:
        documents = await self.get_file_document(file_path)
        if not documents:
            return 0

        split_documents = await self.spliter.split_documents(documents)
        if not split_documents:
            return 0

        extra_metadata = metadata or {}
        for doc in split_documents:
            doc.metadata.update(extra_metadata)

        document_key = str(extra_metadata.get("document_id") or await get_file_md5_hex(file_path))
        ids = self._build_chunk_ids(document_key, split_documents)
        await asyncio.to_thread(self.vectors_store.add_documents, split_documents, ids=ids)
        return len(split_documents)

    def _build_chunk_ids(self, key: str, documents: list[Document]) -> list[str]:
        safe_key = "".join(char if char.isalnum() or char in "-_" else "-" for char in str(key or uuid.uuid4().hex))
        return [f"doc-{safe_key}-{index}" for index, _ in enumerate(documents)]

    def _safe_unlink(self, file_path: str) -> None:
        try:
            os.unlink(file_path)
        except OSError:
            pass


if __name__ == "__main__":
    async def main():
        store = VectorStoreService()
        await store.get_document()
        retriever = await store.get_retriever()
        results = await retriever.ainvoke("robot maintenance")
        print(f"retrieved: {len(results)}")
        for result in results:
            print(result)

    asyncio.run(main())
