import unittest
from unittest.mock import patch

from langchain_core.messages import AIMessage

from workOrderAI.evals import judges


class JudgeTests(unittest.TestCase):
    @patch("workOrderAI.evals.judges.judge_model")
    def test_invoke_json_renders_prompt_and_parses_response(self, judge_model):
        judge_model.invoke.return_value = AIMessage(content='{"is_refusal": true, "reason": "ok"}')

        result = judges.judge_refusal("who", "no info")

        self.assertEqual(result, {"is_refusal": True, "reason": "ok"})
        self.assertIn("Question: who", judge_model.invoke.call_args.args[0])
        self.assertIn("Answer: no info", judge_model.invoke.call_args.args[0])

    @patch("workOrderAI.evals.judges.judge_model")
    def test_invoke_json_raises_clear_error_for_invalid_json(self, judge_model):
        judge_model.invoke.return_value = "not-json"

        with self.assertRaisesRegex(ValueError, "judge model returned invalid JSON"):
            judges.judge_refusal("who", "no info")

    @patch("workOrderAI.evals.judges.judge_model")
    def test_invoke_json_raises_clear_error_for_request_failure(self, judge_model):
        judge_model.invoke.side_effect = RuntimeError("boom")

        with self.assertRaisesRegex(RuntimeError, "judge model request failed"):
            judges.judge_refusal("who", "no info")


if __name__ == "__main__":
    unittest.main()
