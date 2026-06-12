import os
import sys
import json
import subprocess
from pathlib import Path
from flask import Flask, jsonify, request, render_template, Response, stream_with_context

# ---------------------------------------------------------------------------
# Paths — project root is one level above this file (dashboard/)
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).parent.parent
ENV_FILE = PROJECT_ROOT / ".env"
STATE_FILE = PROJECT_ROOT / "storage" / "monitor_state.json"
LATENCY_FILE = PROJECT_ROOT / "storage" / "latency_history.json"
MONITOR_SCRIPT = PROJECT_ROOT / "monitor.py"
PID_FILE = PROJECT_ROOT / "storage" / "monitor.pid"

app = Flask(__name__)


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
    """Return the current monitor_state.json as JSON, filtered to active monitored URLs."""
    env = read_env()
    urls_str = env.get("WEBSITES_TO_MONITOR", "")
    active_urls = {u.strip() for u in urls_str.split(",") if u.strip()}

    if STATE_FILE.exists():
        with open(STATE_FILE, "r", encoding="utf-8") as fh:
            try:
                state = json.load(fh)
            except Exception:
                state = {}
            filtered_state = {url: data for url, data in state.items() if url in active_urls}
            return jsonify(filtered_state)
    return jsonify({})


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
            process = subprocess.Popen(
                [sys.executable, str(MONITOR_SCRIPT), "--once"],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                cwd=str(PROJECT_ROOT),
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
        # Spawn daemon process
        process = subprocess.Popen(
            [sys.executable, str(MONITOR_SCRIPT)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            cwd=str(PROJECT_ROOT),
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0
        )
        
        # Save PID
        with open(PID_FILE, "w", encoding="utf-8") as f:
            f.write(str(process.pid))
            
        return jsonify({"success": True, "pid": process.pid})
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
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"[Dashboard] Serving from project root: {PROJECT_ROOT}")
    print("[Dashboard] Open http://localhost:5000 in your browser.")
    app.run(debug=False, port=5000, host="0.0.0.0")
