import unittest

from workOrderAI.evals.datasets import TASK_FILES, load_dataset


class DatasetTests(unittest.TestCase):
    def test_all_core_datasets_load(self):
        for task in TASK_FILES:
            cases = load_dataset(task)
            self.assertGreater(len(cases), 0)


if __name__ == "__main__":
    unittest.main()
