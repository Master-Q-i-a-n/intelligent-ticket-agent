import unittest
from types import SimpleNamespace
from unittest.mock import patch

from workOrderAI.evals.langsmith_adapter import (
    _build_rule_evaluator,
    _input_key,
    _predict_from_results,
    sync_dataset,
)


class _FakeClient:
    def __init__(self, existing_ids=None):
        self.existing_ids = set(existing_ids or [])
        self.created_datasets = []
        self.created_examples = []
        self.updated_examples = []

    def read_dataset(self, dataset_name):
        return {"name": dataset_name}

    def create_dataset(self, name, description):
        self.created_datasets.append((name, description))

    def list_examples(self, dataset_name):
        return [SimpleNamespace(id=example_id) for example_id in self.existing_ids]

    def create_examples(self, dataset_name, examples):
        self.created_examples.extend(examples)

    def update_examples(self, dataset_name, updates):
        self.updated_examples.extend(updates)


class LangSmithAdapterTests(unittest.TestCase):
    @patch("workOrderAI.evals.langsmith_adapter.load_dataset")
    def test_sync_dataset_upserts_examples(self, load_dataset):
        cases = [
            {"id": "case-1", "input": {}, "expected": {}, "tags": []},
            {"id": "case-2", "input": {}, "expected": {}, "tags": []},
        ]
        load_dataset.return_value = cases

        first_client = _FakeClient()
        sync_dataset("classification", client=first_client)
        existing_ids = {example["id"] for example in first_client.created_examples}

        second_client = _FakeClient(existing_ids=existing_ids)
        sync_dataset("classification", client=second_client)

        self.assertEqual(len(first_client.created_examples), 2)
        self.assertEqual(second_client.created_examples, [])
        self.assertEqual(len(second_client.updated_examples), 2)

    @patch("workOrderAI.evals.langsmith_adapter._knowledge_content_judge_score")
    @patch("workOrderAI.evals.langsmith_adapter.judge_knowledge")
    def test_knowledge_rule_evaluator_returns_four_metrics(self, judge_knowledge, content_judge_score):
        judge_knowledge.return_value = {
            "average_score": 4.0,
            "reason": "ok",
        }
        content_judge_score.return_value = {"refusal_ok": True}
        evaluator = _build_rule_evaluator("knowledge_qa")
        run = SimpleNamespace(
            outputs={
                "answer": "参考资料中没有提供关于公司老板的信息。",
                "source_documents": [{"title": "维护保养"}],
            }
        )
        example = SimpleNamespace(
            inputs={"question": "你们公司老板是谁？"},
            outputs={
                "expected": {
                    "answer_contains": ["没有相关信息"],
                    "expected_sources": [],
                    "should_refuse": True,
                }
            },
        )

        result = evaluator(run, example)

        self.assertEqual(
            [item["key"] for item in result["results"]],
            ["source_score", "content_score", "judge_score", "overall_score"],
        )
        self.assertEqual(result["results"][0]["score"], 1.0)
        self.assertEqual(result["results"][1]["score"], 1.0)
        self.assertEqual(result["results"][2]["score"], 0.8)
        self.assertAlmostEqual(result["results"][3]["score"], (1.0 + 1.0 + 0.8) / 3)
        self.assertIn('"refusal_ok": true', result["results"][1]["comment"].lower())

    def test_predict_from_results_replays_local_actual(self):
        inputs = {"question": "如何维护滤网？"}
        expected_actual = {"answer": "定期清洁滤网。"}
        result = _predict_from_results({_input_key(inputs): expected_actual}, inputs)
        self.assertEqual(result, expected_actual)

    def test_classification_rule_evaluator_returns_three_field_metrics(self):
        evaluator = _build_rule_evaluator("classification")
        run = SimpleNamespace(
            outputs={
                "problem_type": "技术故障",
                "priority": "中",
                "user_sentiment": "愤怒",
            }
        )
        example = SimpleNamespace(
            outputs={
                "expected": {
                    "problem_type": "技术故障",
                    "priority": "低",
                    "user_sentiment": "愤怒",
                }
            }
        )

        result = evaluator(run, example)

        self.assertEqual(
            [item["key"] for item in result["results"]],
            ["problem_type_accuracy", "priority_accuracy", "user_sentiment_accuracy", "overall_score"],
        )
        self.assertEqual(result["results"][0]["score"], 1.0)
        self.assertAlmostEqual(result["results"][1]["score"], 2 / 3)
        self.assertEqual(result["results"][2]["score"], 1.0)
        self.assertAlmostEqual(result["results"][3]["score"], (1.0 + (2 / 3) + 1.0) / 3)

    @patch("workOrderAI.evals.langsmith_adapter.judge_reply")
    def test_reply_rule_evaluator_returns_five_metrics_and_passes_tool_evidence(self, judge_reply):
        judge_reply.return_value = {
            "average_score": 5.0,
            "reason": "evidence ok",
        }
        evaluator = _build_rule_evaluator("reply_suggestion")
        run = SimpleNamespace(
            outputs={
                "suggested_reply": "2025年12月有记录。",
                "tool_trace": [
                    {
                        "name": "fetch_external_data",
                        "output": '[{"时间":"2025-12"}]',
                    }
                ],
            }
        )
        example = SimpleNamespace(
            inputs={"description": "我去年12月有什么记录？"},
            outputs={
                "expected": {"required_facts": ["2025-12"]},
                "expected_tools": ["fetch_external_data"],
                "forbidden_tools": [],
            },
        )

        result = evaluator(run, example)

        self.assertEqual(
            [item["key"] for item in result["results"]],
            ["tool_score", "fact_score", "evidence_score", "judge_score", "overall_score"],
        )
        self.assertEqual(result["results"][0]["score"], 1.0)
        self.assertEqual(result["results"][1]["score"], 1.0)
        self.assertEqual(result["results"][2]["score"], 1.0)
        self.assertEqual(result["results"][3]["score"], 1.0)
        self.assertEqual(result["results"][4]["score"], 1.0)
        judge_reply.assert_called_once()
        _, _, tool_trace, evidence_score = judge_reply.call_args.args
        self.assertEqual(tool_trace, run.outputs["tool_trace"])
        self.assertEqual(evidence_score["supported_months"], ["2025-12"])


if __name__ == "__main__":
    unittest.main()
