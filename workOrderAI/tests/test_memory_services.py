import unittest
from unittest.mock import patch

from workOrderAI.agent.agent_context import reset_current_username, set_current_username
from workOrderAI.agent.agent_tools import fetch_current_user_profile
from workOrderAI.app.model.request import ReplyMessage
from workOrderAI.app.service.case_memory_service import CaseMemoryService
from workOrderAI.app.service.ticket_memory_service import TicketMemoryService
from workOrderAI.app.service.user_memory_service import UserMemoryService


class TicketMemoryServiceTests(unittest.TestCase):
    def test_incremental_messages_start_after_saved_reply(self):
        service = TicketMemoryService.__new__(TicketMemoryService)
        history = [
            ReplyMessage(id="rep-1", role="user", content="机器不出水"),
            ReplyMessage(id="rep-2", role="service", content="请检查水箱"),
            ReplyMessage(id="rep-3", role="user", content="检查后仍然无效"),
        ]

        messages, cursor = service._new_messages(history, "rep-2")

        self.assertEqual([item.id for item in messages], ["rep-3"])
        self.assertEqual(cursor, "rep-3")

    def test_recent_message_window_keeps_last_four(self):
        service = TicketMemoryService.__new__(TicketMemoryService)
        history = [ReplyMessage(id=f"rep-{index}", role="user", content=str(index)) for index in range(6)]

        result = service._with_recent_messages({}, history)

        self.assertEqual([item["id"] for item in result["recent_messages"]], ["rep-2", "rep-3", "rep-4", "rep-5"])

    def test_normalization_keeps_failed_step_status(self):
        service = TicketMemoryService.__new__(TicketMemoryService)

        result = service._normalize_memory(
            {
                "summary": "水箱检查后仍不出水",
                "confirmed_facts": ["水箱有水"],
                "attempted_steps": [{"action": "重新安装水箱", "result": "仍不出水", "status": "FAILED"}],
                "unresolved": ["是否有泵声"],
            },
            {},
        )

        self.assertEqual(result["attempted_steps"][0]["status"], "FAILED")


class CaseMemoryVectorTests(unittest.TestCase):
    def test_vector_content_contains_problem_facts_but_not_final_reply(self):
        service = CaseMemoryService.__new__(CaseMemoryService)
        row = {
            "id": "case-1",
            "ticket_id": "fb-1",
            "ticket_code": "FB-001",
            "title": "机器人不出水",
            "problem_summary": "清扫时不出水",
            "confirmed_facts_json": '["水箱有水"]',
            "category": "技术故障",
            "final_reply": "请更换水泵",
            "active": 1,
        }

        document = service._to_vector_document(row)

        self.assertIn("清扫时不出水", document.page_content)
        self.assertIn("水箱有水", document.page_content)
        self.assertNotIn("请更换水泵", document.page_content)


class UserMemoryServiceTests(unittest.TestCase):
    def test_feature_parser_only_emits_whitelisted_profile_keys(self):
        service = UserMemoryService.__new__(UserMemoryService)

        candidates = service._profile_candidates_from_feature("80㎡木地板，有1只猫，滤网剩余10%")

        self.assertEqual({item["memory_key"] for item in candidates}, {"home_size", "floor_type", "pet"})

    @patch("workOrderAI.agent.agent_tools.UserMemoryService.list_active")
    def test_profile_tool_reads_only_context_user(self, list_active):
        list_active.return_value = [
            {"memory_key": "floor_type", "memory_value": "木地板", "source_type": "EXPLICIT_USER"}
        ]
        token = set_current_username("user-1")
        try:
            result = fetch_current_user_profile.invoke({})
        finally:
            reset_current_username(token)

        self.assertIn("木地板", result)
        list_active.assert_called_once_with("user-1")

    @patch("workOrderAI.agent.agent_tools.UserMemoryService.list_active")
    def test_profile_tool_blocks_empty_context(self, list_active):
        result = fetch_current_user_profile.invoke({})

        self.assertEqual(result, "")
        list_active.assert_not_called()


if __name__ == "__main__":
    unittest.main()
