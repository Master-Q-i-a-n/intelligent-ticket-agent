import unittest
from unittest.mock import MagicMock, patch

from workOrderAI.agent.agent_tools import fetch_external_data


class FetchExternalDataTests(unittest.TestCase):
    @patch("workOrderAI.agent.agent_tools.get_db_connection")
    def test_fetch_external_data_returns_explicit_empty_payload(self, get_db_connection):
        cursor = MagicMock()
        cursor.fetchall.return_value = []
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        get_db_connection.return_value = conn

        result = fetch_external_data.invoke({"user_id": "9999", "month": "2024-01"})

        self.assertIn('"found": false', result.lower())
        self.assertIn('"records": []', result)
        self.assertIn('"message": "no records found"', result)


if __name__ == "__main__":
    unittest.main()
