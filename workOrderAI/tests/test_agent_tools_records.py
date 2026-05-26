import unittest
from unittest.mock import MagicMock, patch

from workOrderAI.agent.agent_context import reset_current_username, set_current_username
from workOrderAI.agent.agent_tools import fetch_current_user_records, fetch_external_data


class FetchExternalDataTests(unittest.TestCase):
    @patch("workOrderAI.agent.agent_tools.get_db_connection")
    def test_fetch_current_user_records_queries_specific_month(self, get_db_connection):
        token = set_current_username("1001")
        cursor = MagicMock()
        cursor.fetchall.return_value = [
            {
                "record_month": "2025-12",
                "feature": "65sqm apartment",
                "clean_efficiency": "coverage:90%",
                "consumable": "filter:10%",
                "comparison": "better than 85% same-size users",
            }
        ]
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        get_db_connection.return_value = conn

        try:
            result = fetch_current_user_records.invoke({"month": "2025-12"})
        finally:
            reset_current_username(token)

        self.assertIn("2025-12", result)
        self.assertIn("filter:10%", result)
        cursor.execute.assert_called_once()
        self.assertEqual(cursor.execute.call_args.args[1], ("1001", "2025-12"))

    @patch("workOrderAI.agent.agent_tools.get_db_connection")
    def test_fetch_current_user_records_queries_all_when_month_empty(self, get_db_connection):
        token = set_current_username("1001")
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        get_db_connection.return_value = conn

        try:
            result = fetch_current_user_records.invoke({"month": ""})
        finally:
            reset_current_username(token)

        self.assertIn('"found": false', result.lower())
        self.assertIn('"records": []', result)
        cursor.execute.assert_called_once()
        self.assertEqual(cursor.execute.call_args.args[1], ("1001",))

    @patch("workOrderAI.agent.agent_tools.get_db_connection")
    def test_fetch_current_user_records_blocks_missing_username_context(self, get_db_connection):
        result = fetch_current_user_records.invoke({"month": "2025-12"})

        self.assertEqual(result, "")
        get_db_connection.assert_not_called()

    @patch("workOrderAI.agent.agent_tools.get_db_connection")
    def test_fetch_external_data_returns_explicit_empty_payload(self, get_db_connection):
        token = set_current_username("9999")
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        get_db_connection.return_value = conn

        try:
            result = fetch_external_data.invoke({"user_id": "9999", "month": "2024-01"})
        finally:
            reset_current_username(token)

        self.assertIn('"found": false', result.lower())
        self.assertIn('"records": []', result)
        self.assertIn('"message": "no records found"', result)

    @patch("workOrderAI.agent.agent_tools.get_db_connection")
    def test_fetch_external_data_blocks_cross_user_query(self, get_db_connection):
        token = set_current_username("1001")
        try:
            result = fetch_external_data.invoke({"user_id": "1002", "month": "2025-12"})
        finally:
            reset_current_username(token)

        self.assertEqual(result, "")
        get_db_connection.assert_not_called()

    @patch("workOrderAI.agent.agent_tools.get_db_connection")
    def test_fetch_external_data_blocks_missing_username_context(self, get_db_connection):
        result = fetch_external_data.invoke({"user_id": "1001", "month": "2025-12"})

        self.assertEqual(result, "")
        get_db_connection.assert_not_called()


if __name__ == "__main__":
    unittest.main()
