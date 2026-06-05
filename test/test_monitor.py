import os
import unittest
from unittest.mock import patch, MagicMock
from datetime import datetime

# Add root folder to sys.path so we can import local modules
import sys
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import monitor
from src import notifier
from storage.sheet_logger import SheetLogger

class TestMonitor(unittest.TestCase):
    
    @patch('requests.get')
    def test_check_website_success(self, mock_get):
        # Setup mock response
        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_get.return_value = mock_response
        
        status_code, status_desc, is_up, error_msg = monitor.check_website("https://example.com", 5)
        
        self.assertEqual(status_code, 200)
        self.assertEqual(status_desc, "200 OK")
        self.assertTrue(is_up)
        self.assertEqual(error_msg, "")
        mock_get.assert_called_once()

    @patch('requests.get')
    def test_check_website_fail_500(self, mock_get):
        mock_response = MagicMock()
        mock_response.status_code = 500
        mock_get.return_value = mock_response
        
        status_code, status_desc, is_up, error_msg = monitor.check_website("https://example.com", 5)
        
        self.assertEqual(status_code, 500)
        self.assertEqual(status_desc, "HTTP Status 500")
        self.assertFalse(is_up)
        self.assertIn("response code 500", error_msg)

    @patch('requests.get')
    def test_check_website_timeout(self, mock_get):
        import requests
        mock_get.side_effect = requests.exceptions.Timeout()
        
        status_code, status_desc, is_up, error_msg = monitor.check_website("https://example.com", 5)
        
        self.assertEqual(status_code, 0)
        self.assertEqual(status_desc, "Timeout")
        self.assertFalse(is_up)
        self.assertIn("Request timed out", error_msg)

    @patch('requests.get')
    def test_check_website_connection_error(self, mock_get):
        import requests
        mock_get.side_effect = requests.exceptions.ConnectionError()
        
        status_code, status_desc, is_up, error_msg = monitor.check_website("https://example.com", 5)
        
        self.assertEqual(status_code, 0)
        self.assertEqual(status_desc, "Connection Error")
        self.assertFalse(is_up)
        self.assertIn("Failed to connect", error_msg)

    @patch('src.notifier.send_email')
    def test_send_downtime_alert(self, mock_send_email):
        mock_send_email.return_value = True
        
        success = notifier.send_downtime_alert("https://example.com", 500, "Internal Server Error")
        
        self.assertTrue(success)
        mock_send_email.assert_called_once()
        args, kwargs = mock_send_email.call_args
        self.assertIn("🚨 ALERT: Website Down", args[0])
        self.assertIn("https://example.com", args[0])
        self.assertIn("500", args[1])
        self.assertIn("Internal Server Error", args[1])

    @patch('src.notifier.send_email')
    def test_send_recovery_alert(self, mock_send_email):
        mock_send_email.return_value = True
        
        success = notifier.send_recovery_alert("https://example.com", "1m 30s")
        
        self.assertTrue(success)
        mock_send_email.assert_called_once()
        args, kwargs = mock_send_email.call_args
        self.assertIn("✅ RECOVERED: Website Up", args[0])
        self.assertIn("https://example.com", args[0])
        self.assertIn("1m 30s", args[1])

    @patch('monitor.load_state')
    @patch('monitor.save_state')
    @patch('monitor.check_website')
    @patch('monitor.send_downtime_alert')
    @patch('monitor.send_recovery_alert')
    @patch('storage.sheet_logger.SheetLogger.log')
    @patch.dict(os.environ, {"WEBSITES_TO_MONITOR": "https://test.com"})
    def test_run_checks_transitions(self, mock_log, mock_send_recovery, mock_send_downtime, mock_check, mock_save, mock_load):
        # Initialize a mock SheetLogger that does not connect to anything
        logger_mock = MagicMock(spec=SheetLogger)
        
        # 1. Test transition: UNKNOWN -> DOWN (alerts)
        mock_load.return_value = {}
        mock_check.return_value = (500, "HTTP Status 500", False, "Failed")
        mock_send_downtime.return_value = True
        
        monitor.run_checks(logger_mock)
        
        mock_send_downtime.assert_called_once_with("https://test.com", 500, "Failed")
        mock_send_recovery.assert_not_called()
        mock_save.assert_called_once()
        
        # Check that saved state marks it as DOWN
        saved_state = mock_save.call_args[0][0]
        self.assertEqual(saved_state["https://test.com"]["status"], "DOWN")
        
        # Reset mocks
        mock_send_downtime.reset_mock()
        mock_send_recovery.reset_mock()
        mock_save.reset_mock()
        
        # 2. Test transition: DOWN -> DOWN (no new alert)
        mock_load.return_value = {
            "https://test.com": {
                "status": "DOWN",
                "last_check": "2026-06-05 12:00:00",
                "down_since": "2026-06-05 12:00:00"
            }
        }
        monitor.run_checks(logger_mock)
        mock_send_downtime.assert_not_called()
        mock_send_recovery.assert_not_called()
        
        # Reset mocks
        mock_send_downtime.reset_mock()
        mock_send_recovery.reset_mock()
        mock_save.reset_mock()
        
        # 3. Test transition: DOWN -> UP (alerts recovery)
        mock_load.return_value = {
            "https://test.com": {
                "status": "DOWN",
                "last_check": "2026-06-05 12:00:00",
                "down_since": "2026-06-05 12:00:00"
            }
        }
        mock_check.return_value = (200, "200 OK", True, "")
        mock_send_recovery.return_value = True
        
        monitor.run_checks(logger_mock)
        mock_send_downtime.assert_not_called()
        mock_send_recovery.assert_called_once()
        
        # Check that saved state marks it as UP
        saved_state = mock_save.call_args[0][0]
        self.assertEqual(saved_state["https://test.com"]["status"], "UP")
        self.assertIsNone(saved_state["https://test.com"]["down_since"])

if __name__ == '__main__':
    unittest.main()
