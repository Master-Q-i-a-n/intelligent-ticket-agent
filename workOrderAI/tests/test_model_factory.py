import unittest

from langchain_community.chat_models.tongyi import ChatTongyi

from workOrderAI.models.factory import ChatModelFactory, judge_model, router_model


class ModelFactoryTests(unittest.TestCase):
    def test_chat_model_factory_keeps_chat_tongyi(self):
        model = ChatModelFactory(model_name="qwen3-max").generator()
        self.assertIsInstance(model, ChatTongyi)

    def test_judge_model_uses_chat_tongyi(self):
        self.assertIsInstance(judge_model, ChatTongyi)
        self.assertEqual(judge_model.model_name, "qwen3-next-80b-a3b-instruct")

    def test_router_model_uses_chat_tongyi(self):
        self.assertIsInstance(router_model, ChatTongyi)
        self.assertEqual(router_model.model_name, "qwen3-32b")
        self.assertEqual(router_model.model_kwargs.get("enable_thinking"), False)


if __name__ == "__main__":
    unittest.main()
