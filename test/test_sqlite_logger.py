import os
import unittest
import tempfile
import gc
import sys

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from storage.sqlite_logger import SQLiteLogger

class TestSQLiteLogger(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_monitor_logs.db")
        self.logger = SQLiteLogger(db_path=self.db_path)

    def tearDown(self):
        del self.logger
        gc.collect()
        try:
            self.temp_dir.cleanup()
        except Exception:
            pass

    def test_init_db(self):
        self.assertTrue(os.path.exists(self.db_path))

    def test_log_and_retrieve(self):
        url = "https://example.com/api/test"
        success = self.logger.log(
            website_url=url,
            status_code=200,
            status_desc="200 OK",
            response_time_ms=145.5,
            speed_rating="Normal",
            notification_sent=False
        )
        self.assertTrue(success)

        logs = self.logger.get_recent_logs(limit=10)
        self.assertEqual(len(logs), 1)
        self.assertEqual(logs[0]["website_url"], url)
        self.assertEqual(logs[0]["status_code"], 200)
        self.assertAlmostEqual(logs[0]["response_time_ms"], 145.5)

        history = self.logger.get_latency_history(website_url=url)
        self.assertEqual(len(history), 1)
        self.assertAlmostEqual(history[0]["latency_ms"], 145.5)

if __name__ == "__main__":
    unittest.main()
