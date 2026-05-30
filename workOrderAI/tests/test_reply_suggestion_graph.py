import unittest

from langchain_core.messages import AIMessage

from workOrderAI.agent.agent_context import record_tool_call, reset_tool_trace, start_tool_trace
from workOrderAI.app.model.request import ReplySuggestRequest
from workOrderAI.app.service.reply_suggestion_graph import ReplySuggestionGraph


class DummyRouterModel:
    def __init__(self, content: str | Exception):
        self.content = content

    async def ainvoke(self, _prompt):
        if isinstance(self.content, Exception):
            raise self.content
        return AIMessage(content=self.content)


class ReplySuggestionGraphRouteTests(unittest.TestCase):
    def test_rule_fallback_user_record_route_requires_record_or_current_user_context(self):
        graph = ReplySuggestionGraph.__new__(ReplySuggestionGraph)

        self.assertEqual(graph._classify_route_by_rules("我去年12月有什么使用记录"), "USER_RECORD")
        self.assertEqual(graph._classify_route_by_rules("我的耗材还剩多久"), "USER_RECORD")
        self.assertEqual(graph._classify_route_by_rules("耗材怎么更换"), "DIRECT_KNOWLEDGE")

    def test_rule_fallback_fault_and_out_of_scope_routes(self):
        graph = ReplySuggestionGraph.__new__(ReplySuggestionGraph)

        self.assertEqual(graph._classify_route_by_rules("机器人不出水怎么办"), "FAULT_DIAGNOSIS")
        self.assertEqual(graph._classify_route_by_rules("老板，我的机器人坏了"), "FAULT_DIAGNOSIS")
        self.assertEqual(graph._classify_route_by_rules("你们公司老板是谁"), "OUT_OF_SCOPE")

    def test_route_to_branch_keeps_valid_routes(self):
        graph = ReplySuggestionGraph.__new__(ReplySuggestionGraph)

        self.assertEqual(graph.route_to_branch({"route": "USER_RECORD"}), "USER_RECORD")
        self.assertEqual(graph.route_to_branch({"route": "BAD_ROUTE"}), "DIRECT_KNOWLEDGE")


class ReplySuggestionGraphSemanticRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_router_model_can_override_keyword_fallback(self):
        graph = ReplySuggestionGraph.__new__(ReplySuggestionGraph)
        graph.router_model = DummyRouterModel(
            '{"route":"FAULT_DIAGNOSIS","confidence":0.92,"reason":"用户称呼老板，但实际在问机器人故障"}'
        )

        route = await graph._classify_route("老板，我的机器人坏了")

        self.assertEqual(route, "FAULT_DIAGNOSIS")

    async def test_router_model_low_confidence_uses_rule_fallback(self):
        graph = ReplySuggestionGraph.__new__(ReplySuggestionGraph)
        graph.router_model = DummyRouterModel(
            '{"route":"DIRECT_KNOWLEDGE","confidence":0.3,"reason":"不确定"}'
        )

        route = await graph._classify_route("机器人不出水怎么办")

        self.assertEqual(route, "FAULT_DIAGNOSIS")

    async def test_router_model_invalid_json_uses_rule_fallback(self):
        graph = ReplySuggestionGraph.__new__(ReplySuggestionGraph)
        graph.router_model = DummyRouterModel("not json")

        route = await graph._classify_route("我去年12月有什么使用记录")

        self.assertEqual(route, "USER_RECORD")

    async def test_router_model_exception_uses_rule_fallback(self):
        graph = ReplySuggestionGraph.__new__(ReplySuggestionGraph)
        graph.router_model = DummyRouterModel(RuntimeError("boom"))

        route = await graph._classify_route("耗材怎么更换")

        self.assertEqual(route, "DIRECT_KNOWLEDGE")


class ReplySuggestionGraphSelfCheckTests(unittest.IsolatedAsyncioTestCase):
    def _request(self) -> ReplySuggestRequest:
        return ReplySuggestRequest(
            id="fb-1",
            title="查询记录",
            description="我2024年1月有什么使用记录？",
            owner_username="1001",
            history=[],
        )

    async def test_groundedness_blocks_fabricated_records_when_no_records_found(self):
        graph = ReplySuggestionGraph.__new__(ReplySuggestionGraph)
        graph._format_trusted_evidence = lambda _state: '{"found": false, "records": [], "message": "no records found"}'
        state = {
            "work_order": self._request(),
            "route": "USER_RECORD",
            "draft_reply": "您在2024年1月清扫30次，滤网剩余10%。",
            "retry_count": 0,
        }

        result = await ReplySuggestionGraph.self_check(graph, state)

        self.assertEqual(result["check_result"]["status"], "REVISE")
        self.assertIn("groundedness", result["check_result"]["failed_dimensions"])

    def test_groundedness_rules_do_not_treat_branch_result_as_no_records_evidence(self):
        graph = ReplySuggestionGraph.__new__(ReplySuggestionGraph)
        graph._format_trusted_evidence = lambda _state: "工具 fetch_current_user_records 返回：滤网剩余15%"
        state = {
            "work_order": self._request(),
            "route": "DIRECT_KNOWLEDGE",
            "branch_result": "未查到记录。",
        }

        issues = graph._check_groundedness("您好，建议您按记录关注滤网状态。", state)

        self.assertEqual(issues, [])

    async def test_groundedness_model_blocks_unsupported_facts(self):
        graph = ReplySuggestionGraph.__new__(ReplySuggestionGraph)
        graph.router_model = DummyRouterModel(
            '{"supported":false,"unsupported_facts":["滤网剩余10%"],"reason":"证据中只支持滤网剩余15%"}'
        )
        graph._format_trusted_evidence = lambda _state: "工具 fetch_current_user_records 返回：滤网剩余15%，主刷剩余35天"
        state = {
            "work_order": self._request(),
            "route": "USER_RECORD",
            "draft_reply": "已查询记录，滤网剩余10%，建议您及时关注耗材。",
            "retry_count": 0,
        }

        result = await ReplySuggestionGraph.self_check(graph, state)

        self.assertEqual(result["check_result"]["status"], "REVISE")
        self.assertIn("groundedness", result["check_result"]["failed_dimensions"])
        self.assertIn("滤网剩余10%", "；".join(result["check_result"]["issues"]))

    async def test_groundedness_model_checks_branch_result_against_trusted_evidence(self):
        graph = ReplySuggestionGraph.__new__(ReplySuggestionGraph)
        graph.router_model = DummyRouterModel(
            '{"supported":false,"unsupported_facts":["分支结果中的滤网剩余10%"],"reason":"可信证据中只支持滤网剩余15%"}'
        )
        graph._format_trusted_evidence = lambda _state: "工具 fetch_current_user_records 返回：滤网剩余15%，主刷剩余35天"
        state = {
            "work_order": self._request(),
            "route": "USER_RECORD",
            "branch_result": "用户记录显示滤网剩余10%。",
            "draft_reply": "已查询记录，滤网剩余10%，建议您及时关注耗材。",
            "retry_count": 0,
        }

        result = await ReplySuggestionGraph.self_check(graph, state)

        self.assertEqual(result["check_result"]["status"], "REVISE")
        self.assertIn("groundedness", result["check_result"]["failed_dimensions"])
        issue_text = "；".join(result["check_result"]["issues"])
        self.assertIn("分支结果中的滤网剩余10%", issue_text)
        self.assertIn("可信证据中只支持滤网剩余15%", issue_text)

    def test_trusted_evidence_excludes_branch_result_and_keeps_sources(self):
        graph = ReplySuggestionGraph.__new__(ReplySuggestionGraph)
        token = start_tool_trace()
        try:
            record_tool_call("fetch_current_user_records", {"month": "2025-12"}, "滤网剩余15%")
            state = {
                "branch_result": "滤网剩余10%",
                "case_memories": [{"ticket_code": "C-1", "title": "保养案例", "final_reply": "建议清理滤网"}],
                "rag_sources": [{"title": "维护保养", "score": 0.9}],
            }

            evidence = graph._format_trusted_evidence(state)
        finally:
            reset_tool_trace(token)

        self.assertIn("滤网剩余15%", evidence)
        self.assertIn("保养案例", evidence)
        self.assertIn("维护保养", evidence)
        self.assertNotIn("滤网剩余10%", evidence)

    async def test_groundedness_model_supported_allows_reply(self):
        graph = ReplySuggestionGraph.__new__(ReplySuggestionGraph)
        graph.router_model = DummyRouterModel('{"supported":true,"unsupported_facts":[],"reason":"事实均有证据"}')
        graph._format_trusted_evidence = lambda _state: "知识库摘要：建议每周清理滤网并定期检查主刷。"
        state = {
            "work_order": ReplySuggestRequest(
                id="fb-knowledge",
                title="保养咨询",
                description="扫地机器人怎么保养？",
                owner_username="1001",
                history=[],
            ),
            "route": "DIRECT_KNOWLEDGE",
            "draft_reply": "您好，建议您每周清理滤网，并定期检查主刷。",
            "retry_count": 0,
        }

        result = await ReplySuggestionGraph.self_check(graph, state)

        self.assertEqual(result["check_result"]["status"], "PASS")

    async def test_groundedness_model_invalid_json_does_not_block(self):
        graph = ReplySuggestionGraph.__new__(ReplySuggestionGraph)
        graph.router_model = DummyRouterModel("not-json")
        graph._format_trusted_evidence = lambda _state: "知识库摘要：建议定期保养。"
        state = {
            "work_order": ReplySuggestRequest(
                id="fb-knowledge",
                title="保养咨询",
                description="扫地机器人怎么保养？",
                owner_username="1001",
                history=[],
            ),
            "route": "DIRECT_KNOWLEDGE",
            "draft_reply": "您好，建议您按照说明定期保养。",
            "retry_count": 0,
        }

        result = await ReplySuggestionGraph.self_check(graph, state)

        self.assertEqual(result["check_result"]["status"], "PASS")

    async def test_groundedness_model_exception_does_not_block(self):
        graph = ReplySuggestionGraph.__new__(ReplySuggestionGraph)
        graph.router_model = DummyRouterModel(RuntimeError("boom"))
        graph._format_trusted_evidence = lambda _state: "知识库摘要：建议定期保养。"
        state = {
            "work_order": ReplySuggestRequest(
                id="fb-knowledge",
                title="保养咨询",
                description="扫地机器人怎么保养？",
                owner_username="1001",
                history=[],
            ),
            "route": "DIRECT_KNOWLEDGE",
            "draft_reply": "您好，建议您按照说明定期保养。",
            "retry_count": 0,
        }

        result = await ReplySuggestionGraph.self_check(graph, state)

        self.assertEqual(result["check_result"]["status"], "PASS")

    async def test_privacy_issue_escalates(self):
        graph = ReplySuggestionGraph.__new__(ReplySuggestionGraph)
        graph._format_evidence = lambda _state: "工具返回正常"
        state = {
            "work_order": self._request(),
            "route": "DIRECT_KNOWLEDGE",
            "draft_reply": "已查询 owner_username=1001，内部工单ID为 fb-1。",
            "retry_count": 0,
        }

        result = await ReplySuggestionGraph.self_check(graph, state)

        self.assertEqual(result["check_result"]["status"], "ESCALATE")
        self.assertIn("privacy", result["check_result"]["failed_dimensions"])

    async def test_completeness_requires_record_query_result(self):
        graph = ReplySuggestionGraph.__new__(ReplySuggestionGraph)
        graph._format_trusted_evidence = lambda _state: "有工具证据"
        state = {
            "work_order": self._request(),
            "route": "USER_RECORD",
            "draft_reply": "您好，建议您保持设备清洁。",
            "retry_count": 0,
        }

        result = await ReplySuggestionGraph.self_check(graph, state)

        self.assertEqual(result["check_result"]["status"], "REVISE")
        self.assertIn("completeness", result["check_result"]["failed_dimensions"])

    async def test_out_of_scope_reply_does_not_require_advice(self):
        graph = ReplySuggestionGraph.__new__(ReplySuggestionGraph)
        graph._format_evidence = lambda _state: ""
        state = {
            "work_order": ReplySuggestRequest(
                id="fb-2",
                title="公司老板",
                description="你们公司老板是谁？",
                owner_username="1001",
                history=[],
            ),
            "route": "OUT_OF_SCOPE",
            "draft_reply": "您好，当前问题超出了现有扫地机器人知识库和工单处理范围，建议联系人工客服确认。",
            "retry_count": 0,
        }

        result = await ReplySuggestionGraph.self_check(graph, state)

        self.assertEqual(result["check_result"]["status"], "PASS")

    async def test_clarify_reply_does_not_require_final_solution(self):
        graph = ReplySuggestionGraph.__new__(ReplySuggestionGraph)
        graph._format_evidence = lambda _state: ""
        state = {
            "work_order": ReplySuggestRequest(
                id="fb-3",
                title="坏了",
                description="不好用",
                owner_username="1001",
                history=[],
            ),
            "route": "CLARIFY",
            "draft_reply": "您好，请您补充设备型号、具体异常现象、出现时间，以及是否有截图或报错提示。",
            "retry_count": 0,
        }

        result = await ReplySuggestionGraph.self_check(graph, state)

        self.assertEqual(result["check_result"]["status"], "PASS")

    async def test_fault_route_requires_steps_or_clarifying_question(self):
        graph = ReplySuggestionGraph.__new__(ReplySuggestionGraph)
        graph._format_evidence = lambda _state: "知识库摘要"
        state = {
            "work_order": ReplySuggestRequest(
                id="fb-4",
                title="机器人故障",
                description="机器人不出水怎么办？",
                owner_username="1001",
                history=[],
            ),
            "route": "FAULT_DIAGNOSIS",
            "draft_reply": "您好，我们会继续处理。",
            "retry_count": 0,
        }

        result = await ReplySuggestionGraph.self_check(graph, state)

        self.assertEqual(result["check_result"]["status"], "REVISE")
        self.assertIn("completeness", result["check_result"]["failed_dimensions"])

    def test_after_self_check_retries_once_then_fallback(self):
        graph = ReplySuggestionGraph.__new__(ReplySuggestionGraph)

        self.assertEqual(
            graph.after_self_check({"check_result": {"status": "REVISE"}, "retry_count": 0}),
            "retry",
        )
        self.assertEqual(
            graph.after_self_check({"check_result": {"status": "REVISE"}, "retry_count": 1}),
            "fallback",
        )
        self.assertEqual(
            graph.after_self_check({"check_result": {"status": "PASS"}, "retry_count": 0}),
            "end",
        )


if __name__ == "__main__":
    unittest.main()
