import unittest

from workOrderAI.evals.reporting import build_summary


class ReportingTests(unittest.TestCase):
    def test_build_summary_for_all_tasks(self):
        summary = build_summary(
            {
                "classification": [
                    {
                        "passed": True,
                        "score": 1.0,
                        "latency_seconds": 1.0,
                        "rule_score": {
                            "field_scores": {
                                "problem_type": True,
                                "priority": True,
                                "user_sentiment": True,
                            }
                        },
                    }
                ],
                "reply_suggestion": [
                    {
                        "passed": False,
                        "score": 0.5,
                        "latency_seconds": 2.0,
                        "tool_score": {"tool_call_count": 2, "passed": False},
                    }
                ],
                "knowledge_qa": [
                    {
                        "passed": True,
                        "score": 1.0,
                        "latency_seconds": 3.0,
                        "expected": {"should_refuse": True},
                        "source_score": {"score": 1.0},
                        "content_score": {"refusal_ok": True},
                        "returned_sources_on_refusal": [{"title": "选购指南"}],
                    },
                    {
                        "passed": True,
                        "score": 0.8,
                        "latency_seconds": 2.0,
                        "expected": {"should_refuse": False},
                        "source_score": {"score": 0.5},
                        "content_score": {"refusal_ok": True},
                    },
                ],
                "reply_suggestion_error": [
                    {
                        "passed": False,
                        "score": 0.0,
                        "latency_seconds": 0.2,
                        "error": "network down",
                    }
                ],
            }
        )
        self.assertEqual(summary["overall"]["case_count"], 5)
        self.assertEqual(summary["overall"]["passed_count"], 3)
        self.assertEqual(summary["tasks"]["classification"]["field_accuracy"]["problem_type"], 1.0)
        self.assertEqual(summary["tasks"]["reply_suggestion"]["average_tool_calls"], 2.0)
        self.assertEqual(summary["tasks"]["knowledge_qa"]["source_hit_rate"], 0.75)
        self.assertEqual(summary["tasks"]["knowledge_qa"]["refusal_case_count"], 1)
        self.assertEqual(summary["tasks"]["knowledge_qa"]["refusal_pass_rate"], 1.0)
        self.assertEqual(summary["tasks"]["knowledge_qa"]["refusal_with_returned_sources_count"], 1)
        self.assertEqual(summary["tasks"]["reply_suggestion_error"]["error_count"], 1)


if __name__ == "__main__":
    unittest.main()
