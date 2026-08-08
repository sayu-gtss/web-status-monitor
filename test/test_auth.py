import os
import unittest
import tempfile
import json
from storage.sqlite_logger import SQLiteLogger
from dashboard.app import app

class TestUserAuth(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.db_path = os.path.join(self.temp_dir, "test_auth.db")
        os.environ["SQLITE_DB_PATH"] = self.db_path
        self.logger = SQLiteLogger(db_path=self.db_path)
        app.config['TESTING'] = True
        app.config['SECRET_KEY'] = 'test-secret'
        self.client = app.test_client()

    def tearDown(self):
        if "SQLITE_DB_PATH" in os.environ:
            del os.environ["SQLITE_DB_PATH"]

    def test_superadmin_seeding_and_verification(self):
        # Verify default superadmin seeded
        user = self.logger.get_user("superadmin")
        self.assertIsNotNone(user)
        self.assertEqual(user["role"], "superadmin")

        # Test password verification
        verified = self.logger.verify_user("superadmin", "WebGuardSuper")
        self.assertIsNotNone(verified)
        self.assertEqual(verified["username"], "superadmin")

        # Test wrong password
        invalid = self.logger.verify_user("superadmin", "WrongPassword")
        self.assertIsNone(invalid)

    def test_user_crud_operations(self):
        # Create new user
        success, msg = self.logger.create_user("admin1", "Pass1234", role="admin")
        self.assertTrue(success)

        # Retrieve user list
        users = self.logger.get_all_users()
        usernames = [u["username"] for u in users]
        self.assertIn("superadmin", usernames)
        self.assertIn("admin1", usernames)

        # Attempt to delete primary superadmin (should fail)
        del_super, del_msg = self.logger.delete_user("superadmin")
        self.assertFalse(del_super)

        # Delete admin1 (should succeed)
        del_admin, del_msg = self.logger.delete_user("admin1")
        self.assertTrue(del_admin)

    def test_flask_auth_api_endpoints(self):
        # Login with wrong credentials
        res = self.client.post('/api/auth/login', json={'username': 'superadmin', 'password': 'WrongPassword'})
        self.assertEqual(res.status_code, 401)

        # Login with superadmin credentials
        res = self.client.post('/api/auth/login', json={'username': 'superadmin', 'password': 'WebGuardSuper'})
        self.assertEqual(res.status_code, 200)
        data = res.get_json()
        self.assertTrue(data['success'])
        self.assertEqual(data['user']['username'], 'superadmin')

        # Check /api/auth/me
        res_me = self.client.get('/api/auth/me')
        self.assertEqual(res_me.status_code, 200)
        self.assertTrue(res_me.get_json()['authenticated'])

        # Create new user via API
        res_create = self.client.post('/api/users', json={'username': 'apiuser', 'password': 'ApiPassword123', 'role': 'admin'})
        self.assertEqual(res_create.status_code, 200)

        # List users via API
        res_list = self.client.get('/api/users')
        self.assertEqual(res_list.status_code, 200)
        users = res_list.get_json()['users']
        self.assertTrue(any(u['username'] == 'apiuser' for u in users))

        # Logout
        res_logout = self.client.post('/api/auth/logout')
        self.assertEqual(res_logout.status_code, 200)

    def test_change_password(self):
        # Login superadmin
        self.client.post('/api/auth/login', json={'username': 'superadmin', 'password': 'WebGuardSuper'})
        
        # Test wrong current password
        res = self.client.post('/api/auth/change-password', json={'current_password': 'Wrong', 'new_password': 'NewSuperPass123'})
        self.assertEqual(res.status_code, 400)

        # Test valid password change
        res_ok = self.client.post('/api/auth/change-password', json={'current_password': 'WebGuardSuper', 'new_password': 'NewSuperPass123'})
        self.assertEqual(res_ok.status_code, 200)

        # Re-verify login with new password
        self.client.post('/api/auth/logout')
        res_login_new = self.client.post('/api/auth/login', json={'username': 'superadmin', 'password': 'NewSuperPass123'})
        self.assertEqual(res_login_new.status_code, 200)

        # Reset password back to WebGuardSuper for other tests
        self.client.post('/api/auth/change-password', json={'current_password': 'NewSuperPass123', 'new_password': 'WebGuardSuper'})
        self.client.post('/api/auth/logout')

if __name__ == '__main__':
    unittest.main()
