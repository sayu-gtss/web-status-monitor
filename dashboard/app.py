import os
import sys
import json
import time
import subprocess
from pathlib import Path
from flask import Flask, jsonify, request, render_template, Response, stream_with_context, session

# ---------------------------------------------------------------------------
# Paths — project root is one level above this file (dashboard/)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from storage.sqlite_logger import SQLiteLogger
ENV_FILE = PROJECT_ROOT / ".env"
STATE_FILE = PROJECT_ROOT / "storage" / "monitor_state.json"
LATENCY_FILE = PROJECT_ROOT / "storage" / "latency_history.json"
MONITOR_SCRIPT = PROJECT_ROOT / "monitor.py"
PID_FILE = PROJECT_ROOT / "storage" / "monitor.pid"
LOG_FILE = PROJECT_ROOT / "storage" / "monitor.log"

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "webguard-superadmin-secret-key-2026")


# ---------------------------------------------------------------------------
# Authentication Middleware & Endpoints
# ---------------------------------------------------------------------------

@app.before_request
def check_authentication():
    # Public static files & login API endpoints do not require session auth
    public_paths = ["/static/", "/api/auth/login", "/api/auth/logout"]
    if any(request.path.startswith(p) for p in public_paths):
        return None
    # For API endpoints, check session
    if "user" not in session:
        if request.path.startswith("/api/"):
            return jsonify({"error": "Unauthorized. Please log in.", "authenticated": False}), 401
    return None

@app.route("/api/auth/login", methods=["POST"])
def auth_login():
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    sqlite_logger = SQLiteLogger()
    user = sqlite_logger.verify_user(username, password)
    if user:
        session["user"] = user
        return jsonify({"success": True, "user": user})
    return jsonify({"error": "Invalid username or password"}), 401

@app.route("/api/auth/logout", methods=["POST"])
def auth_logout():
    session.clear()
    return jsonify({"success": True})

@app.route("/api/auth/me", methods=["GET"])
def auth_me():
    user = session.get("user")
    if user:
        return jsonify({"authenticated": True, "user": user})
    return jsonify({"authenticated": False}), 401

@app.route("/api/auth/change-password", methods=["POST"])
def auth_change_password():
    user = session.get("user")
    if not user:
        return jsonify({"error": "Unauthorized. Please log in."}), 401
    data = request.json or {}
    curr_pwd = data.get("current_password", "").strip()
    new_pwd = data.get("new_password", "").strip()

    if not curr_pwd or not new_pwd:
        return jsonify({"error": "Current password and new password are required"}), 400

    sqlite_logger = SQLiteLogger()
    success, msg = sqlite_logger.change_password(user["username"], curr_pwd, new_pwd)
    if success:
        return jsonify({"success": True, "message": msg})
    return jsonify({"error": msg}), 400

# ---------------------------------------------------------------------------
# User Management Endpoints (Superadmin Restricted)
# ---------------------------------------------------------------------------

@app.route("/api/users", methods=["GET"])
def list_users():
    user = session.get("user")
    if not user or user.get("role") != "superadmin":
        return jsonify({"error": "Access denied. Superadmin privileges required."}), 403
    sqlite_logger = SQLiteLogger()
    users = sqlite_logger.get_all_users()
    return jsonify({"users": users})

@app.route("/api/users", methods=["POST"])
def create_new_user():
    user = session.get("user")
    if not user or user.get("role") != "superadmin":
        return jsonify({"error": "Access denied. Superadmin privileges required."}), 403
    data = request.json or {}
    username = data.get("username", "").strip()
    password = data.get("password", "").strip()
    role = data.get("role", "admin").strip()
    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400
    sqlite_logger = SQLiteLogger()
    success, msg = sqlite_logger.create_user(username, password, role)
    if success:
        return jsonify({"success": True, "message": msg})
    return jsonify({"error": msg}), 400

@app.route("/api/users/<username>", methods=["DELETE"])
def delete_existing_user(username):
    user = session.get("user")
    if not user or user.get("role") != "superadmin":
        return jsonify({"error": "Access denied. Superadmin privileges required."}), 403
    sqlite_logger = SQLiteLogger()
    success, msg = sqlite_logger.delete_user(username)
    if success:
        return jsonify({"success": True, "message": msg})
    return jsonify({"error": msg}), 400


# ---------------------------------------------------------------------------
# .env helpers
# ---------------------------------------------------------------------------

def read_env() -> dict:
    """Parse .env file into a plain dict, skipping comments and blank lines."""
    env: dict = {}
    if not ENV_FILE.exists():
        return env
    with open(ENV_FILE, "r", encoding="utf-8") as fh:
        for line in fh:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            if "=" not in stripped:
                continue
            key, _, value = stripped.partition("=")
            env[key.strip()] = value.strip()
    return env


def write_env(updates: dict) -> None:
    """
    Write key/value pairs into .env, preserving existing comments and order.
    Keys not yet present in the file are appended at the bottom.
    """
    lines: list[str] = []
    if ENV_FILE.exists():
        with open(ENV_FILE, "r", encoding="utf-8") as fh:
            lines = fh.readlines()

    updated_keys: set[str] = set()
    new_lines: list[str] = []

    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            key = stripped.split("=", 1)[0].strip()
            if key in updates:
                new_lines.append(f"{key}={updates[key]}\n")
                updated_keys.add(key)
                continue
        new_lines.append(line)

    # Append keys that did not exist in the file yet
    for key, value in updates.items():
        if key not in updated_keys:
            new_lines.append(f"{key}={value}\n")

    with open(ENV_FILE, "w", encoding="utf-8") as fh:
        fh.writelines(new_lines)

    # Update os.environ in memory so subprocesses inherit updated configuration
    for key, value in updates.items():
        os.environ[key] = str(value)


# ---------------------------------------------------------------------------
# Routes — pages
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# Routes — config API
# ---------------------------------------------------------------------------

@app.route("/api/config", methods=["GET"])
def get_config():
    """Return the current .env values as JSON (all keys, including secrets)."""
    return jsonify(read_env())


@app.route("/api/config", methods=["POST"])
def update_config():
    """Persist one or more key/value pairs back to the .env file."""
    data = request.json
    if not isinstance(data, dict) or not data:
        return jsonify({"error": "Expected a JSON object with key/value pairs"}), 400
    write_env(data)
    return jsonify({"success": True})


# ---------------------------------------------------------------------------
# Routes — status API
# ---------------------------------------------------------------------------

@app.route("/api/status", methods=["GET"])
def get_status():
    """Return the current monitor_state.json as JSON, filtered to active monitored URLs, with SQLite DB fallback."""
    env = read_env()
    urls_str = env.get("WEBSITES_TO_MONITOR", "")
    active_urls = [u.strip() for u in urls_str.split(",") if u.strip()]

    state = {}
    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as fh:
            try:
                state = json.load(fh)
            except Exception:
                state = {}

    filtered_state = {}
    from storage.sqlite_logger import SQLiteLogger
    sqlite_logger = SQLiteLogger()

    for url in active_urls:
        if url in state:
            filtered_state[url] = state[url]
        else:
            # Fallback to SQLite database for recently logged check results
            recent_logs = sqlite_logger.get_recent_logs(limit=1, website_url=url)
            if recent_logs and len(recent_logs) > 0:
                last_log = recent_logs[0]
                status_str = "200 OK" if last_log.get("status_code") == 200 else str(last_log.get("status_desc") or "Error")
                filtered_state[url] = {
                    "status": status_str,
                    "last_check": last_log.get("timestamp"),
                    "down_since": None,
                    "consecutive_failures": 0,
                    "alerted": False
                }
            else:
                filtered_state[url] = {
                    "status": "Checking...",
                    "last_check": "Pending initial check",
                    "down_since": None,
                    "consecutive_failures": 0,
                    "alerted": False
                }
    return jsonify(filtered_state)


@app.route("/api/latency", methods=["GET"])
def get_latency():
    """Return the current latency_history.json as JSON, filtered to active monitored URLs."""
    env = read_env()
    urls_str = env.get("WEBSITES_TO_MONITOR", "")
    active_urls = {u.strip() for u in urls_str.split(",") if u.strip()}

    if LATENCY_FILE.exists():
        with open(LATENCY_FILE, "r", encoding="utf-8") as fh:
            try:
                history = json.load(fh)
            except Exception:
                history = {}
            filtered_history = {url: data for url, data in history.items() if url in active_urls}
            return jsonify(filtered_history)
    return jsonify({})


@app.route("/api/db-logs", methods=["GET"])
def get_db_logs():
    """Return recent check logs from SQLite database."""
    limit = request.args.get("limit", default=2000, type=int)
    website_url = request.args.get("url", default=None, type=str)
    from storage.sqlite_logger import SQLiteLogger
    logger = SQLiteLogger()
    logs = logger.get_recent_logs(limit=limit, website_url=website_url)
    return jsonify({"logs": logs})


# ---------------------------------------------------------------------------
# Routes — URL management API
# ---------------------------------------------------------------------------

@app.route("/api/urls", methods=["GET"])
def get_urls():
    env = read_env()
    urls_str = env.get("WEBSITES_TO_MONITOR", "")
    urls = [u.strip() for u in urls_str.split(",") if u.strip()]
    return jsonify(urls)


@app.route("/api/urls", methods=["POST"])
def add_url():
    data = request.json or {}
    url = data.get("url", "").strip()
    if not url:
        return jsonify({"error": "url is required"}), 400

    env = read_env()
    urls_str = env.get("WEBSITES_TO_MONITOR", "")
    urls = [u.strip() for u in urls_str.split(",") if u.strip()]

    if url in urls:
        return jsonify({"error": "URL is already being monitored"}), 409

    urls.append(url)
    write_env({"WEBSITES_TO_MONITOR": ",".join(urls)})
    return jsonify({"success": True, "urls": urls})


@app.route("/api/urls", methods=["DELETE"])
def remove_url():
    data = request.json or {}
    url = data.get("url", "").strip()

    env = read_env()
    urls_str = env.get("WEBSITES_TO_MONITOR", "")
    urls = [u.strip() for u in urls_str.split(",") if u.strip()]

    if url not in urls:
        return jsonify({"error": "URL not found"}), 404

    urls = [u for u in urls if u != url]
    write_env({"WEBSITES_TO_MONITOR": ",".join(urls)})

    # Clean up the state file as well so removed URLs don't linger
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as fh:
                state = json.load(fh)
            if url in state:
                del state[url]
                with open(STATE_FILE, "w", encoding="utf-8") as fh:
                    json.dump(state, fh, indent=2)
        except Exception as e:
            print(f"Error cleaning up state file for {url}: {e}")

    return jsonify({"success": True, "urls": urls})


# ---------------------------------------------------------------------------
# Routes — run check (Server-Sent Events stream)
# ---------------------------------------------------------------------------

@app.route("/api/run-check", methods=["POST"])
def run_check():
    """
    Spawns monitor.py --once as a subprocess and streams its stdout back
    to the client line-by-line using Server-Sent Events.
    """
    def generate():
        try:
            env_vars = dict(os.environ)
            env_vars.update(read_env())
            process = subprocess.Popen(
                [sys.executable, "-u", str(MONITOR_SCRIPT), "--once"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(PROJECT_ROOT),
                env=env_vars,
            )
            for line in process.stdout:
                yield f"data: {line.rstrip()}\n\n"
            process.wait()
            yield f"data: ✅ Check complete — exit code {process.returncode}\n\n"
            yield "data: __DONE__\n\n"
        except Exception as exc:
            yield f"data: ❌ Error: {exc}\n\n"
            yield "data: __DONE__\n\n"

    return Response(
        stream_with_context(generate()),
        content_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


# ---------------------------------------------------------------------------
# Routes — monitor daemon controls
# ---------------------------------------------------------------------------

def is_daemon_running() -> tuple[bool, int or None]:
    if not PID_FILE.exists():
        return False, None
    try:
        with open(PID_FILE, "r", encoding="utf-8") as f:
            pid = int(f.read().strip())
    except Exception:
        try:
            PID_FILE.unlink()
        except Exception:
            pass
        return False, None

    # Check if PID is active
    if os.name == "nt":
        try:
            output = subprocess.check_output(f'tasklist /FI "PID eq {pid}"', shell=True, text=True)
            if str(pid) in output:
                return True, pid
        except Exception:
            pass
    else:
        try:
            os.kill(pid, 0)
            return True, pid
        except OSError:
            pass

    # Clean up stale file
    try:
        PID_FILE.unlink()
    except Exception:
        pass
    return False, None


@app.route("/api/daemon", methods=["GET"])
def get_daemon_status():
    running, pid = is_daemon_running()
    return jsonify({"running": running, "pid": pid})


@app.route("/api/daemon/start", methods=["POST"])
def start_daemon():
    running, pid = is_daemon_running()
    if running:
        return jsonify({"success": True, "message": "Daemon already running", "pid": pid})

    try:
        # Spawn daemon process and capture startup output for diagnostics.
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        log_fh = open(LOG_FILE, "a", encoding="utf-8")

        env_vars = dict(os.environ)
        env_vars.update(read_env())
        start_kwargs = {
            "cwd": str(PROJECT_ROOT),
            "stdout": log_fh,
            "stderr": subprocess.STDOUT,
            "text": True,
            "env": env_vars,
        }
        if os.name == 'nt':
            creationflags = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
            start_kwargs["creationflags"] = creationflags

        process = subprocess.Popen([sys.executable, str(MONITOR_SCRIPT)], **start_kwargs)

        # Save PID
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(process.pid))

        # Give the monitor a moment to fail fast if it cannot start.
        time.sleep(1)
        if process.poll() is not None:
            message = f"Monitor process exited immediately with code {process.returncode}. See {LOG_FILE} for details."
            try:
                if PID_FILE.exists():
                    PID_FILE.unlink()
            except Exception:
                pass
            return jsonify({"error": message}), 500

        return jsonify({"success": True, "pid": process.pid, "log_file": str(LOG_FILE)})
    except Exception as e:
        return jsonify({"error": f"Failed to start daemon: {e}"}), 500


@app.route("/api/daemon/stop", methods=["POST"])
def stop_daemon():
    running, pid = is_daemon_running()
    if not running:
        return jsonify({"success": True, "message": "Daemon is not running"})

    try:
        if os.name == "nt":
            subprocess.run(["taskkill", "/F", "/T", "/PID", str(pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            os.kill(pid, 15)  # SIGTERM

        if PID_FILE.exists():
            PID_FILE.unlink()

        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"error": f"Failed to stop daemon: {e}"}), 500


# ---------------------------------------------------------------------------
# Database Logs Export Endpoint
# ---------------------------------------------------------------------------

@app.route("/api/db-logs/export", methods=["GET"])
def export_db_logs():
    fmt = request.args.get("format", default="csv", type=str).lower()
    limit = request.args.get("limit", default=10000, type=int)
    try:
        from storage.sqlite_logger import SQLiteLogger
        sqlite_logger = SQLiteLogger()
        logs = sqlite_logger.get_recent_logs(limit=limit)

        if fmt == "json":
            return Response(
                json.dumps(logs, indent=2),
                mimetype="application/json",
                headers={"Content-Disposition": "attachment;filename=monitor_logs.json"}
            )
        else:
            import csv
            import io
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["ID", "Timestamp", "Website URL", "Domain", "Status Code", "Status Description", "Response Time (ms)", "Speed Rating", "Notification Sent"])
            for row in logs:
                writer.writerow([
                    row.get("id"),
                    row.get("timestamp"),
                    row.get("website_url"),
                    row.get("domain"),
                    row.get("status_code"),
                    row.get("status_desc"),
                    row.get("response_time_ms"),
                    row.get("speed_rating"),
                    "Yes" if row.get("notification_sent") else "No"
                ])
            return Response(
                output.getvalue(),
                mimetype="text/csv",
                headers={"Content-Disposition": "attachment;filename=monitor_logs.csv"}
            )
    except Exception as e:
        return jsonify({"error": f"Failed to export logs: {e}"}), 500


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"[Dashboard] Serving from project root: {PROJECT_ROOT}")
    print("[Dashboard] Open http://localhost:5000 in your browser.")
    app.run(debug=False, port=5000, host="0.0.0.0")
