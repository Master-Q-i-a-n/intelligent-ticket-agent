import unittest
from unittest.mock import AsyncMock, patch

from workOrderAI.agent.agent_tools import fetch_similar_cases, get_tools
from workOrderAI.app.service.case_memory_service import CaseMemoryService
from workOrderAI.app.service.suggest_service import SuggestService


class CaseMemoryServiceTests(unittest.TestCase):
    def test_plain_text_removes_html(self):
        service = CaseMemoryService.__new__(CaseMemoryService)

        self.assertEqual(service._plain_text("<p>已处理&nbsp;完成</p>"), "已处理 完成")

    def test_search_filters_low_similarity_matches(self):
        service = CaseMemoryService.__new__(CaseMemoryService)

        class _DummyVectorStore:
            def similarity_search_with_relevance_scores(self, _query, k):
                from langchain_core.documents import Document

                return [
                    (
                        Document(
                            page_content="case",
                            metadata={
                                "ticket_id": "fb-low",
                                "ticket_code": "FB-LOW",
                                "title": "低相关案例",
                            },
                        ),
                        0.2,
                    )
                ]

        service.vector_store = _DummyVectorStore()

        import asyncio

        result = asyncio.run(service.search_similar_cases("完全不相关的问题"))
        self.assertEqual(result, [])


class SimilarCaseToolTests(unittest.IsolatedAsyncioTestCase):
    async def test_fetch_similar_cases_serializes_results(self):
        with patch(
            "workOrderAI.agent.agent_tools.CaseMemoryService.search_similar_cases",
            AsyncMock(
                return_value=[
                    {
                        "ticket_id": "fb-1",
                        "ticket_code": "FB-001",
                        "title": "导出失败",
                        "final_reply": "请稍后重试",
                        "similarity_score": 0.92,
                    }
                ]
            ),
        ):
            result = await fetch_similar_cases.ainvoke({"query": "导出任务失败"})

        self.assertIn('"ticket_id": "fb-1"', result)
        self.assertIn('"similarity_score": 0.92', result)

    def test_public_tools_include_similar_case_tool(self):
        tool_names = [tool.name for tool in get_tools()]
        self.assertIn("fetch_similar_cases", tool_names)


class SuggestServiceTests(unittest.TestCase):
    def test_extract_case_sources_from_tool_trace(self):
        service = SuggestService.__new__(SuggestService)

        sources = service._extract_case_sources(
            [
                {
                    "name": "fetch_similar_cases",
                    "args": {"query": "导出失败"},
                    "output": """
                    [
                      {
                        "ticket_id": "fb-1",
                        "ticket_code": "FB-001",
                        "title": "导出失败",
                        "final_reply": "请稍后重试",
                        "similarity_score": 0.92
                      }
                    ]
                    """,
                }
            ]
        )

        self.assertEqual(len(sources), 1)
        self.assertEqual(sources[0].ticket_id, "fb-1")
        self.assertEqual(sources[0].ticket_code, "FB-001")
        self.assertEqual(sources[0].similarity_score, 0.92)

    def test_merge_case_sources_deduplicates_prefetched_and_tool_cases(self):
        service = SuggestService.__new__(SuggestService)

        prefetched = service._build_case_sources(
            [
                {
                    "ticket_id": "fb-1",
                    "ticket_code": "FB-001",
                    "title": "导出失败",
                    "final_reply": "请稍后重试",
                    "similarity_score": 0.92,
                }
            ]
        )
        tool_sources = service._extract_case_sources(
            [
                {
                    "name": "fetch_similar_cases",
                    "output": """
                    [
                      {
                        "ticket_id": "fb-1",
                        "ticket_code": "FB-001",
                        "title": "导出失败",
                        "final_reply": "请稍后重试",
                        "similarity_score": 0.92
                      },
                      {
                        "ticket_id": "fb-2",
                        "ticket_code": "FB-002",
                        "title": "连接失败",
                        "final_reply": "请重连网络",
                        "similarity_score": 0.88
                      }
                    ]
                    """,
                }
            ]
        )

        merged = service._merge_case_sources(prefetched, tool_sources)

        self.assertEqual([item.ticket_id for item in merged], ["fb-1", "fb-2"])


class SuggestServiceAsyncTests(unittest.IsolatedAsyncioTestCase):
    async def test_prefetched_cases_are_injected_and_returned_without_tool_call(self):
        service = SuggestService.__new__(SuggestService)

        class _DummyGraph:
            def __init__(self):
                self.work_order = None

            async def run(self, work_order):
                self.work_order = work_order
                return {
                    "final_reply": "建议回复",
                    "case_memories": [
                        {
                            "ticket_id": "fb-1",
                            "ticket_code": "FB-001",
                            "title": "保养",
                            "final_reply": "定期清理主刷",
                            "similarity_score": 0.95,
                        }
                    ],
                    "rag_sources": [],
                }

        service.graph = _DummyGraph()
        work_order = type(
            "_WorkOrder",
            (),
            {
                "title": "保养",
                "description": "如何保养",
                "owner_username": "1001",
                "history": [],
            },
        )()

        result = await service.get_suggestion_result(work_order)

        self.assertEqual(result.suggested_reply, "建议回复")
        self.assertEqual(len(result.source_templates), 1)
        self.assertEqual(result.source_templates[0].ticket_id, "fb-1")
        self.assertEqual(service.graph.work_order, work_order)

    async def test_graph_without_cases_returns_suggestion(self):
        service = SuggestService.__new__(SuggestService)

        class _DummyGraph:
            async def run(self, _work_order):
                return {"final_reply": "建议回复", "case_memories": [], "rag_sources": []}

        service.graph = _DummyGraph()
        work_order = type(
            "_WorkOrder",
            (),
            {
                "title": "保养",
                "description": "如何保养",
                "owner_username": "1001",
                "history": [],
            },
        )()

        result = await service.get_suggestion_result(work_order)

        self.assertEqual(result.suggested_reply, "建议回复")
        self.assertEqual(result.source_templates, [])


if __name__ == "__main__":
    unittest.main()
