import json
import unittest
from unittest.mock import MagicMock, patch

from workOrderAI.app.api.classify import classify_work_order
from workOrderAI.app.model.request import ClassifyRequest


CLASSIFICATION_RESULT = json.dumps(
    {
        "problem_type": "技术故障",
        "priority": "高",
        "user_sentiment": "焦虑",
        "confidence_score": 0.92,
        "analysis_reasoning": "设备无法充电",
    },
    ensure_ascii=False,
)


class ClassifyApiTests(unittest.TestCase):
    def _build_request(self, update_category: bool) -> ClassifyRequest:
        return ClassifyRequest(
            ticket_id="fb-1",
            title="充不上电",
            description="设备无法充电",
            replies=[],
            update_category=update_category,
        )

    def _build_connection(self, current_category: str):
        cursor = MagicMock()
        cursor.fetchone.return_value = {"category": current_category}
        cursor.rowcount = 1
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        return conn, cursor

    @patch("workOrderAI.app.api.classify.ClassifyService")
    @patch("workOrderAI.app.api.classify.get_db_connection")
    def test_unknown_category_is_backfilled_during_reanalysis(self, get_db_connection, classify_service_cls):
        conn, cursor = self._build_connection("UNKNOWN")
        get_db_connection.return_value = conn
        classify_service_cls.return_value.get_classification.return_value = CLASSIFICATION_RESULT

        classify_work_order(self._build_request(update_category=False))

        self.assertEqual(
            cursor.execute.call_args_list[1].args[0],
            "UPDATE wo_feedback SET category = %s, priority = %s, emotion = %s, service_group = %s WHERE id = %s",
        )
        self.assertEqual(cursor.execute.call_args_list[1].args[1][3], "TECH_SUPPORT")

    @patch("workOrderAI.app.api.classify.ClassifyService")
    @patch("workOrderAI.app.api.classify.get_db_connection")
    def test_existing_category_is_preserved_during_reanalysis(self, get_db_connection, classify_service_cls):
        conn, cursor = self._build_connection("产品咨询")
        get_db_connection.return_value = conn
        classify_service_cls.return_value.get_classification.return_value = CLASSIFICATION_RESULT

        classify_work_order(self._build_request(update_category=False))

        self.assertEqual(
            cursor.execute.call_args_list[1].args[0],
            "UPDATE wo_feedback SET priority = %s, emotion = %s WHERE id = %s",
        )


if __name__ == "__main__":
    unittest.main()
