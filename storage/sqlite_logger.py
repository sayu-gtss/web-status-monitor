import os
import sqlite3
from datetime import datetime
from urllib.parse import urlparse
from dotenv import load_dotenv

load_dotenv()

DEFAULT_DB_PATH = os.path.join("storage", "monitor_logs.db")

class SQLiteLogger:
    def __init__(self, db_path=None):
        self.db_path = db_path or os.getenv("SQLITE_DB_PATH", DEFAULT_DB_PATH)
        # Ensure parent directory exists
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
            
        self.init_db()

    def _get_connection(self):
        """Creates and returns a connection to the SQLite database."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn

    def init_db(self):
        """Initializes the SQLite database tables and indexes if they do not exist."""
        try:
            from werkzeug.security import generate_password_hash
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS check_logs (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        timestamp TEXT NOT NULL,
                        website_url TEXT NOT NULL,
                        domain TEXT NOT NULL,
                        status_code INTEGER,
                        status_desc TEXT,
                        response_time_ms REAL,
                        speed_rating TEXT,
                        notification_sent INTEGER NOT NULL
                    )
                """)
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_domain ON check_logs(domain)")
                cursor.execute("CREATE INDEX IF NOT EXISTS idx_logs_timestamp ON check_logs(timestamp)")

                # Create users table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        password_hash TEXT NOT NULL,
                        role TEXT NOT NULL DEFAULT 'admin',
                        created_at TEXT NOT NULL
                    )
                """)
                
                # Seed default superadmin if not present
                cursor.execute("SELECT id FROM users WHERE username = ?", ("superadmin",))
                if not cursor.fetchone():
                    default_hash = generate_password_hash("WebGuardSuper")
                    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    cursor.execute("""
                        INSERT INTO users (username, password_hash, role, created_at)
                        VALUES (?, ?, ?, ?)
                    """, ("superadmin", default_hash, "superadmin", now_str))
                    print("[SQLiteLogger] Seeded default superadmin account (username: superadmin).")

                conn.commit()
            print(f"[SQLiteLogger] Initialized database at '{self.db_path}'.")
            return True
        except Exception as e:
            print(f"[SQLiteLogger] Database initialization error: {e}")
            return False

    def _extract_domain(self, url):
        """Extracts domain/path from URL for grouping."""
        try:
            parsed = urlparse(url)
            domain = parsed.hostname or url
            path = parsed.path.strip('/')
            if path:
                return f"{domain}/{path}"
            return domain
        except Exception:
            return "unknown"

    def cleanup_old_logs(self, retention_days=None):
        """Deletes database check logs older than the specified retention days."""
        if retention_days is None:
            ret_val = os.getenv("RETENTION_DAYS", "30")
            try:
                retention_days = int(ret_val)
            except ValueError:
                retention_days = 30

        if retention_days <= 0:
            return 0  # 0 or negative means retain forever

        try:
            from datetime import timedelta
            cutoff_date = (datetime.now() - timedelta(days=retention_days)).strftime("%Y-%m-%d %H:%M:%S")
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM check_logs WHERE timestamp < ?", (cutoff_date,))
                deleted_count = cursor.rowcount
                conn.commit()
            if deleted_count > 0:
                print(f"[SQLiteLogger] Cleaned up {deleted_count} logs older than {retention_days} days (before {cutoff_date}).")
            return deleted_count
        except Exception as e:
            print(f"[SQLiteLogger] Log cleanup error: {e}")
            return 0

    def log(self, website_url, status_code, status_desc, response_time_ms, speed_rating, notification_sent):
        """Logs a website heartbeat check result to the SQLite database."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        domain = self._extract_domain(website_url)
        notification_val = 1 if notification_sent else 0
        resp_time = float(response_time_ms) if response_time_ms is not None else None

        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO check_logs 
                    (timestamp, website_url, domain, status_code, status_desc, response_time_ms, speed_rating, notification_sent)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (timestamp, website_url, domain, int(status_code), str(status_desc), resp_time, str(speed_rating), notification_val))
                conn.commit()
            print(f"[SQLiteLogger] Logged check to DB [{domain}]: {website_url} (Status: {status_code})")
            
            # Auto cleanup logs older than retention period
            self.cleanup_old_logs()

            # Optional Google Sheets Fallback
            if os.getenv("GOOGLE_SHEET_ID"):
                try:
                    from storage.sheet_logger import SheetLogger
                    sheet_logger = SheetLogger()
                    if sheet_logger.spreadsheet:
                        sheet_logger.log(website_url, status_code, status_desc, response_time_ms, speed_rating, notification_sent)
                except Exception as ex:
                    print(f"[SQLiteLogger] Google Sheets fallback logging error: {ex}")
                    
            return True
        except Exception as e:
            print(f"[SQLiteLogger] Failed to log check to SQLite database: {e}")
            return False

    def get_recent_logs(self, limit=100, website_url=None):
        """Retrieves recent log entries from the database."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                if website_url:
                    cursor.execute("""
                        SELECT * FROM check_logs WHERE website_url = ? ORDER BY id DESC LIMIT ?
                    """, (website_url, limit))
                else:
                    cursor.execute("""
                        SELECT * FROM check_logs ORDER BY id DESC LIMIT ?
                    """, (limit,))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            print(f"[SQLiteLogger] Failed to fetch logs: {e}")
            return []

    def get_latency_history(self, website_url, limit=50):
        """Retrieves response time history for a specific website URL."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT timestamp, response_time_ms as latency_ms, status_desc as status 
                    FROM check_logs 
                    WHERE website_url = ? AND response_time_ms IS NOT NULL
                    ORDER BY id DESC LIMIT ?
                """, (website_url, limit))
                rows = cursor.fetchall()
                return [dict(row) for row in reversed(rows)]
        except Exception as e:
            print(f"[SQLiteLogger] Failed to fetch latency history: {e}")
            return []

    # ---------------------------------------------------------------------------
    # User Management Methods
    # ---------------------------------------------------------------------------

    def get_user(self, username):
        """Retrieves a user by username."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except Exception as e:
            print(f"[SQLiteLogger] Error getting user {username}: {e}")
            return None

    def verify_user(self, username, password):
        """Verifies username and password. Returns user dict if valid, else None."""
        from werkzeug.security import check_password_hash
        user = self.get_user(username)
        if not user:
            return None
        if check_password_hash(user["password_hash"], password):
            return {"id": user["id"], "username": user["username"], "role": user["role"], "created_at": user["created_at"]}
        return None

    def create_user(self, username, password, role="admin"):
        """Creates a new user account."""
        from werkzeug.security import generate_password_hash
        try:
            password_hash = generate_password_hash(password)
            created_at = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT INTO users (username, password_hash, role, created_at)
                    VALUES (?, ?, ?, ?)
                """, (username, password_hash, role, created_at))
                conn.commit()
            print(f"[SQLiteLogger] Created user '{username}' with role '{role}'.")
            return True, "User created successfully"
        except sqlite3.IntegrityError:
            return False, f"Username '{username}' already exists"
        except Exception as e:
            return False, f"Error creating user: {e}"

    def get_all_users(self):
        """Returns list of all registered user accounts (without password hashes)."""
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT id, username, role, created_at FROM users ORDER BY id ASC")
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except Exception as e:
            print(f"[SQLiteLogger] Error fetching all users: {e}")
            return []

    def delete_user(self, username):
        """Deletes a user account. Cannot delete primary superadmin."""
        if username == "superadmin":
            return False, "Cannot delete primary superadmin account"
        try:
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM users WHERE username = ?", (username,))
                conn.commit()
                if cursor.rowcount > 0:
                    return True, f"User '{username}' deleted"
                return False, f"User '{username}' not found"
        except Exception as e:
            return False, f"Error deleting user: {e}"

    def change_password(self, username, current_password, new_password):
        """Changes the password for an existing user account."""
        from werkzeug.security import check_password_hash, generate_password_hash
        user = self.get_user(username)
        if not user:
            return False, "User not found"
        if not check_password_hash(user["password_hash"], current_password):
            return False, "Current password is incorrect"
        
        try:
            new_hash = generate_password_hash(new_password)
            with self._get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("UPDATE users SET password_hash = ? WHERE username = ?", (new_hash, username))
                conn.commit()
            print(f"[SQLiteLogger] Changed password for user '{username}'.")
            return True, "Password updated successfully"
        except Exception as e:
            return False, f"Error updating password: {e}"
