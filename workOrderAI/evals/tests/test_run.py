import unittest
from unittest.mock import patch

from workOrderAI.evals.run import run_langsmith_from_results


class RunTests(unittest.TestCase):
    @patch("workOrderAI.evals.langsmith_adapter.run_experiment_from_results")
    def test_run_langsmith_from_results_replays_each_task(self, run_experiment_from_results):
        results_by_task = {
            "classification": [{"id": "cls-1"}],
            "knowledge_qa": [{"id": "qa-1"}],
        }

        run_langsmith_from_results(
            results_by_task,
            skip_judge=True,
            experiment_prefix="workorder-agent",
        )

        self.assertEqual(run_experiment_from_results.call_count, 2)
        run_experiment_from_results.assert_any_call(
            "classification",
            [{"id": "cls-1"}],
            skip_judge=True,
            experiment_prefix="workorder-agent",
        )
        run_experiment_from_results.assert_any_call(
            "knowledge_qa",
            [{"id": "qa-1"}],
            skip_judge=True,
            experiment_prefix="workorder-agent",
        )


if __name__ == "__main__":
    unittest.main()
