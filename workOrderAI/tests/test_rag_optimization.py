import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import AsyncMock, patch

from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda

from workOrderAI.app.service.rag_service import (
    HYDE_MAX_TOKENS,
    KNOWLEDGE_NO_ANSWER_SUMMARY,
    RagService,
)
from workOrderAI.utils.prompt_builder import QUESTION_HYDE_PROMPT, STATEMENT_HYDE_PROMPT
from workOrderAI.utils.file_handler import listdir_allowed_type
from workOrderAI.utils.vector_store import MilvusLiteVectorStore, VectorStoreService


class _DummyVectorStore:
    def __init__(self):
        self.as_retriever_calls = 0

    def as_retriever(self, **_kwargs):
        self.as_retriever_calls += 1
        return "vector"


class VectorStoreCacheTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        await VectorStoreService.invalidate_retriever_cache()

    async def test_base_retrievers_are_built_once(self):
        service = VectorStoreService.__new__(VectorStoreService)
        service.vectors_store = _DummyVectorStore()
        service._build_bm25_retriever = AsyncMock(return_value="bm25")

        first = await service._get_cached_base_retrievers()
        second = await service._get_cached_base_retrievers()

        self.assertEqual(first, ("vector", "bm25"))
        self.assertEqual(second, ("vector", "bm25"))
        self.assertEqual(service.vectors_store.as_retriever_calls, 1)
        service._build_bm25_retriever.assert_awaited_once()

    async def test_invalidate_retriever_cache_clears_cached_retrievers(self):
        VectorStoreService._cached_vector_retriever = "vector"
        VectorStoreService._cached_bm25_retriever = "bm25"
        VectorStoreService._retriever_cache_initialized = True

        await VectorStoreService.invalidate_retriever_cache()

        self.assertIsNone(VectorStoreService._cached_vector_retriever)
        self.assertIsNone(VectorStoreService._cached_bm25_retriever)
        self.assertFalse(VectorStoreService._retriever_cache_initialized)


class KnowledgeFileSelectionTests(unittest.IsolatedAsyncioTestCase):
    async def test_listdir_allowed_type_skips_excluded_paths(self):
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            root.joinpath("knowledge.txt").write_text("knowledge", encoding="utf-8")
            root.joinpath("knowledge_docs").mkdir()
            root.joinpath("knowledge_docs", "uploaded.txt").write_text("uploaded", encoding="utf-8")
            root.joinpath("external").mkdir()
            root.joinpath("external", "records.txt").write_text("records", encoding="utf-8")
            root.joinpath("md5_hex_store").mkdir()
            root.joinpath("md5_hex_store", "md5_hex_store.txt").write_text("hash", encoding="utf-8")

            files = await listdir_allowed_type(
                str(root),
                ("txt",),
                (str(root / "external"), str(root / "md5_hex_store")),
            )

            self.assertEqual(
                {Path(file_path).name for file_path in files},
                {"knowledge.txt", "uploaded.txt"},
            )


class DynamicWeightTests(unittest.IsolatedAsyncioTestCase):
    async def test_short_chinese_query_prefers_vector_search(self):
        self.assertEqual(
            await VectorStoreService.get_dynamic_weights("扫地机器人如何保养"),
            [0.7, 0.3],
        )

    async def test_short_english_query_still_prefers_bm25(self):
        self.assertEqual(
            await VectorStoreService.get_dynamic_weights("brush"),
            [0.3, 0.7],
        )

    async def test_long_chinese_query_keeps_existing_vector_bias(self):
        query = "扫地机器人长期使用后应该如何维护主刷边刷滤网拖布和水箱以保持清洁效果稳定" * 2
        self.assertEqual(
            await VectorStoreService.get_dynamic_weights(query),
            [0.7, 0.3],
        )


class MilvusLiteVectorStoreTests(unittest.TestCase):
    def test_search_loads_released_collection_before_query(self):
        class _FakeEmbeddings:
            def embed_query(self, _query):
                return [0.1, 0.2, 0.3]

        class _FakeMilvusClient:
            def __init__(self):
                self.load_calls = []
                self.search_called = False

            def has_collection(self, _collection_name):
                return True

            def get_load_state(self, collection_name):
                return {"state": "LoadStateReleased", "collection_name": collection_name}

            def load_collection(self, collection_name):
                self.load_calls.append(collection_name)

            def search(self, **_kwargs):
                self.search_called = True
                return [[]]

        store = MilvusLiteVectorStore.__new__(MilvusLiteVectorStore)
        store.collection_name = "rag_collection"
        store.embedding_function = _FakeEmbeddings()
        store.metric_type = "COSINE"
        store.client = _FakeMilvusClient()

        result = store.similarity_search_with_relevance_scores("query")

        self.assertEqual(result, [])
        self.assertEqual(store.client.load_calls, ["rag_collection"])
        self.assertTrue(store.client.search_called)


class RagLightPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_retrieve_direct_documents_respects_limit(self):
        service = RagService.__new__(RagService)

        class _DummyRetriever:
            async def ainvoke(self, _query):
                return [
                    Document(page_content="doc-1"),
                    Document(page_content="doc-2"),
                    Document(page_content="doc-3"),
                ]

        class _DummyVectorStoreService:
            async def get_retriever(self, _query):
                return _DummyRetriever()

        service.vector_store = _DummyVectorStoreService()

        documents = await RagService.retrieve_direct_documents(service, "query", limit=2)

        self.assertEqual([doc.page_content for doc in documents], ["doc-1", "doc-2"])

    async def test_rag_summary_for_suggestion_uses_reranked_documents(self):
        service = RagService.__new__(RagService)
        service.retrieve_direct_reranked_matches = AsyncMock(
            return_value=[
                (
                    Document(
                        page_content="doc-1",
                        metadata={"document_id": "doc-1-id", "title": "Doc 1", "vector_id": "chunk-1"},
                    ),
                    0.91,
                ),
                (
                    Document(
                        page_content="doc-2",
                        metadata={"document_id": "doc-2-id", "title": "Doc 2", "vector_id": "chunk-2"},
                    ),
                    0.82,
                ),
                (
                    Document(
                        page_content="doc-3",
                        metadata={"document_id": "doc-3-id", "title": "Doc 3", "vector_id": "chunk-3"},
                    ),
                    0.73,
                ),
            ]
        )

        class _DummyChain:
            def __init__(self):
                self.payload = None

            async def ainvoke(self, payload):
                self.payload = payload
                return "summary"

        service.chain = _DummyChain()

        result = await RagService.rag_summary_for_suggestion(service, "query")

        self.assertEqual(result["summary"], "summary")
        self.assertEqual(result["sources"][0]["document_id"], "doc-1-id")
        self.assertEqual(result["sources"][0]["chunk_id"], "chunk-1")
        self.assertEqual(result["sources"][0]["score"], 0.91)
        service.retrieve_direct_reranked_matches.assert_awaited_once_with("query")
        self.assertIn("doc-1", service.chain.payload["context"])
        self.assertIn("doc-2", service.chain.payload["context"])
        self.assertIn("doc-3", service.chain.payload["context"])

    async def test_retrieve_direct_reranked_matches_fetches_five_and_keeps_three(self):
        service = RagService.__new__(RagService)
        documents = [
            Document(page_content=f"doc-{index}", metadata={"vector_id": f"chunk-{index}"})
            for index in range(1, 6)
        ]
        service.retrieve_direct_document_matches = AsyncMock(
            return_value=[
                (documents[0], 0.1),
                (documents[1], 0.2),
                (documents[2], 0.3),
                (documents[3], 0.4),
                (documents[4], 0.5),
            ]
        )
        reranked = [
            Document(page_content="doc-5", metadata={"vector_id": "chunk-5", "relevance_score": 0.93}),
            Document(page_content="doc-3", metadata={"vector_id": "chunk-3", "relevance_score": 0.88}),
            Document(page_content="doc-1", metadata={"vector_id": "chunk-1"}),
        ]
        service.rerank_documents = AsyncMock(return_value=reranked)

        matches = await RagService.retrieve_direct_reranked_matches(service, "query")

        service.retrieve_direct_document_matches.assert_awaited_once_with("query", limit=5)
        service.rerank_documents.assert_awaited_once_with("query", documents, 3, "[RAG-light]")
        self.assertEqual([doc.page_content for doc, _ in matches], ["doc-5", "doc-3", "doc-1"])
        self.assertEqual([score for _, score in matches], [0.93, 0.88, 0.1])

    async def test_rerank_documents_uses_reranker_and_top_k(self):
        service = RagService.__new__(RagService)
        documents = [Document(page_content=f"doc-{index}") for index in range(1, 6)]

        class _DummyReranker:
            def __init__(self):
                self.query = None
                self.documents = None

            async def acompress_documents(self, docs, query):
                self.documents = docs
                self.query = query
                return [docs[4], docs[2], docs[0], docs[1], docs[3]]

        service.reranker_model = _DummyReranker()

        result = await RagService.rerank_documents(service, "query", documents, top_k=3)

        self.assertEqual([doc.page_content for doc in result], ["doc-5", "doc-3", "doc-1"])
        self.assertEqual(service.reranker_model.query, "query")
        self.assertEqual(service.reranker_model.documents, documents)

    async def test_rerank_documents_falls_back_to_original_order_on_error(self):
        service = RagService.__new__(RagService)
        documents = [Document(page_content=f"doc-{index}") for index in range(1, 6)]

        class _FailingReranker:
            async def acompress_documents(self, _docs, _query):
                raise RuntimeError("rerank failed")

        service.reranker_model = _FailingReranker()

        result = await RagService.rerank_documents(service, "query", documents, top_k=3)

        self.assertEqual([doc.page_content for doc in result], ["doc-1", "doc-2", "doc-3"])

    async def test_retrieve_document_reranks_hybrid_candidates(self):
        service = RagService.__new__(RagService)
        documents = [Document(page_content=f"doc-{index}") for index in range(1, 6)]

        class _DummyRetriever:
            async def ainvoke(self, _query):
                return documents

        class _DummyVectorStoreService:
            async def get_retriever(self, _query):
                return _DummyRetriever()

        service.vector_store = _DummyVectorStoreService()
        service.rerank_documents = AsyncMock(return_value=[documents[2], documents[1], documents[0]])

        result = await RagService.retrieve_document(service, "query")

        service.rerank_documents.assert_awaited_once_with("query", documents, 3, "[RAG]")
        self.assertEqual([doc.page_content for doc in result], ["doc-3", "doc-2", "doc-1"])

    async def test_chitchat_invalid_returns_knowledge_refusal(self):
        service = RagService.__new__(RagService)
        service.hyde_pre = AsyncMock(return_value="Chitchat_Invalid")

        result = await RagService.get_documents_and_summary(service, "who is the boss")

        self.assertEqual(result["summary"], KNOWLEDGE_NO_ANSWER_SUMMARY)
        self.assertEqual(result["documents"], [])
        self.assertEqual(result["source_documents"], [])


class HydePromptTests(unittest.TestCase):
    def test_hyde_prompts_are_short_retrieval_expansions(self):
        self.assertIn("60字以内", QUESTION_HYDE_PROMPT)
        self.assertIn("60字以内", STATEMENT_HYDE_PROMPT)
        self.assertNotIn("专业且详细", QUESTION_HYDE_PROMPT)
        self.assertNotIn("写一段诊断和排查指南", STATEMENT_HYDE_PROMPT)

    @patch("workOrderAI.app.service.rag_service.VectorStoreService")
    @patch("workOrderAI.app.service.rag_service.chat_model", new=RunnableLambda(lambda _input: "ok"))
    def test_hyde_model_limits_output_tokens(self, _vector_store_service):
        service = RagService()
        self.assertEqual(service.hyde_model.kwargs["max_tokens"], HYDE_MAX_TOKENS)


if __name__ == "__main__":
    unittest.main()
