import unittest

from langchain_community.chat_models.tongyi import ChatTongyi

from workOrderAI.models.factory import ChatModelFactory, judge_model


class ModelFactoryTests(unittest.TestCase):
    def test_chat_model_factory_keeps_chat_tongyi(self):
        model = ChatModelFactory(model_name="qwen3-max").generator()
        self.assertIsInstance(model, ChatTongyi)

    def test_judge_model_uses_chat_tongyi(self):
        self.assertIsInstance(judge_model, ChatTongyi)
        self.assertEqual(judge_model.model_name, "qwen3-next-80b-a3b-instruct")


if __name__ == "__main__":
    unittest.main()
