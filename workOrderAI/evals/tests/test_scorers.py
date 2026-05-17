import unittest

from workOrderAI.evals.scorers import (
    combine_knowledge_content_scores,
    score_answer_contains,
    score_classification,
    score_knowledge_content_judge,
    score_knowledge_sources,
    score_priority,
    score_reply_evidence_alignment,
    score_required_facts,
    score_tool_usage,
)


class ScorerTests(unittest.TestCase):
    def test_score_classification(self):
        result = score_classification(
            {"problem_type": "技术故障", "priority": "高", "user_sentiment": "愤怒"},
            {"problem_type": "技术故障", "priority": "高", "user_sentiment": "愤怒"},
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["score"], 1.0)

    def test_score_priority_rewards_nearer_miss(self):
        self.assertGreater(score_priority("中", "低"), score_priority("高", "低"))
        self.assertEqual(score_priority("低", "低"), 1.0)
        self.assertEqual(score_priority("紧急", "低"), 0.0)

    def test_score_tool_usage(self):
        result = score_tool_usage(
            [{"name": "get_time_now"}, {"name": "rag_summarize"}],
            ["get_time_now", "rag_summarize"],
            ["fetch_external_data"],
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["tool_call_count"], 2)

    def test_score_required_facts(self):
        result = score_required_facts(
            "用户在 2025年12月 有记录。",
            {"required_facts": ["2025-12"], "must_not_contain": ["2023-12"]},
        )
        self.assertTrue(result["passed"])

    def test_score_required_facts_accepts_synonym_groups(self):
        result = score_required_facts(
            "2024年1月的使用记录未找到。",
            {
                "required_facts": [],
                "required_fact_groups": [["未查到", "未找到", "没有查到", "没有找到"]],
            },
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["missing_fact_groups"], [])

    def test_score_reply_evidence_alignment_accepts_tool_backed_month_and_weather(self):
        result = score_reply_evidence_alignment(
            "2025年12月记录显示，当前温度21.5°C，湿度76%，风速11.6公里/小时。",
            [
                {
                    "name": "fetch_external_data",
                    "output": '[{"时间":"2025-12"}]',
                },
                {
                    "name": "get_current_weather",
                    "output": "无锡 weather: temperature 21.5C, humidity 76%, wind speed 11.6km/h",
                },
            ],
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["supported_months"], ["2025-12"])
        self.assertEqual(result["unsupported_months"], [])
        self.assertEqual(
            result["supported_weather_facts"],
            ["11.6公里/小时", "21.5°C", "76%"],
        )

    def test_score_reply_evidence_alignment_flags_unsupported_structured_facts(self):
        result = score_reply_evidence_alignment(
            "2025年12月记录显示，当前温度18°C。",
            [{"name": "fetch_external_data", "output": '[{"时间":"2025-12"}]'}],
        )
        self.assertFalse(result["passed"])
        self.assertEqual(result["unsupported_weather_facts"], ["18°C"])

    def test_score_knowledge_sources(self):
        result = score_knowledge_sources(
            [{"title": "维护保养指南"}],
            {"expected_sources": ["维护保养"]},
        )
        self.assertTrue(result["passed"])

    def test_score_knowledge_sources_passes_when_one_expected_source_matches(self):
        result = score_knowledge_sources(
            [{"title": "维护保养指南"}],
            {"expected_sources": ["维护保养", "扫拖一体机器人100问"]},
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["matched_sources"], ["维护保养"])
        self.assertEqual(result["missing_sources"], ["扫拖一体机器人100问"])

    def test_score_knowledge_sources_refusal_allows_returned_candidates(self):
        result = score_knowledge_sources(
            [{"title": "选购指南"}],
            {"expected_sources": [], "should_refuse": True},
        )
        self.assertTrue(result["passed"])
        self.assertEqual(result["returned_sources_on_refusal"], [{"title": "选购指南"}])

    def test_score_answer_contains_refusal(self):
        result = score_answer_contains(
            "没有相关信息。",
            {"answer_contains": ["没有相关信息"], "should_refuse": True},
        )
        self.assertTrue(result["passed"])

    def test_score_answer_contains_refusal_accepts_semantic_phrase(self):
        result = score_answer_contains(
            "参考资料中没有提供关于公司老板的信息。",
            {"answer_contains": ["没有相关信息"], "should_refuse": True},
        )
        self.assertTrue(result["passed"])
        self.assertTrue(result["refusal_ok"])

    def test_combine_knowledge_content_scores_accepts_judge_refusal(self):
        rule_score = score_answer_contains(
            "资料不足，无法回答。",
            {"answer_contains": ["没有相关信息"], "should_refuse": True},
        )
        judge_score = score_knowledge_content_judge(
            {"is_refusal": True},
            {"should_refuse": True},
        )
        result = combine_knowledge_content_scores(
            rule_score,
            judge_score,
            {"answer_contains": ["没有相关信息"], "should_refuse": True},
        )
        self.assertTrue(result["passed"])
        self.assertTrue(result["refusal_ok"])


if __name__ == "__main__":
    unittest.main()
