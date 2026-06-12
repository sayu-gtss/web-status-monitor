import os
import sys
import time
import json
import argparse
from datetime import datetime
import requests
from dotenv import load_dotenv
import schedule

from src.notifier import send_downtime_alert, send_recovery_alert, send_slow_alert
from src.caller import make_voice_call
from storage.sheet_logger import SheetLogger

# Load configurations
load_dotenv()

STATE_FILE = "storage/monitor_state.json"
LATENCY_FILE = "storage/latency_history.json"

def load_state():
    """Load the last known status of monitored websites from a JSON file."""
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[Monitor] Error loading state file: {e}. Starting fresh.")
    return {}

def save_state(state):
    """Save the current status of monitored websites to a JSON file."""
    try:
        with open(STATE_FILE, 'w', encoding='utf-8') as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[Monitor] Error saving state file: {e}")

def log_latency(url, latency_ms, status_desc):
    """Log check response time to a rolling window of 50 logs per URL."""
    history = {}
    if os.path.exists(LATENCY_FILE):
        try:
            with open(LATENCY_FILE, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except Exception:
            pass

    if url not in history:
        history[url] = []

    history[url].append({
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "latency_ms": latency_ms,
        "status": status_desc
    })

    # Keep only the last 10000 entries
    history[url] = history[url][-10000:]

    try:
        with open(LATENCY_FILE, 'w', encoding='utf-8') as f:
            json.dump(history, f, indent=2)
    except Exception as e:
        print(f"[Monitor] Error saving latency history: {e}")

def check_website(url, timeout):
    """
    Checks the status of a website.
    Returns (status_code, status_description, is_up, error_message).
    """
    # Use a standard browser User-Agent so we don't get blocked by WAFs/firewalls
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        # We perform a GET request with redirect following (timeout is disabled as requested)
        response = requests.get(url, headers=headers, timeout=None, allow_redirects=True)
        status_code = response.status_code
        latency_ms = response.elapsed.total_seconds() * 1000
        
        # Check if the response status is 200 (user specifies other than 200 is down)
        if status_code == 200:
            return status_code, "200 OK", True, "", latency_ms
        else:
            return status_code, f"HTTP Status {status_code}", False, f"Server returned response code {status_code}", latency_ms
            
    except requests.exceptions.Timeout:
        return 0, "Timeout", False, f"Request timed out after {timeout} seconds", None
    except requests.exceptions.ConnectionError:
        return 0, "Connection Error", False, "Failed to connect to the server (DNS issue or server down)", None
    except requests.exceptions.RequestException as e:
        return 0, "Error", False, f"An exception occurred: {str(e)}", None

def run_checks(logger):
    """Runs a single round of checks for all configured websites."""
    websites_str = os.getenv("WEBSITES_TO_MONITOR", "")
    if not websites_str:
        print("[Monitor] No websites configured in WEBSITES_TO_MONITOR. Please check your .env file.")
        return
        
    websites = [w.strip() for w in websites_str.split(",") if w.strip()]
    timeout_val = os.getenv("REQUEST_TIMEOUT_SECONDS", "5")
    try:
        timeout = int(timeout_val)
    except ValueError:
        timeout = 5
        print(f"[Monitor] Invalid REQUEST_TIMEOUT_SECONDS: {timeout_val}. Defaulting to 5 seconds.")
        
    slow_threshold_val = os.getenv("SLOW_THRESHOLD_SECONDS", "1.5")
    try:
        slow_threshold = float(slow_threshold_val)
    except ValueError:
        slow_threshold = 1.5
    
    state = load_state()
    current_time = datetime.now()
    
    print(f"\n--- Starting Status Check at {current_time.strftime('%Y-%m-%d %H:%M:%S')} ---")
    
    for url in websites:
        status_code, status_desc, is_up, error_msg, latency_ms = check_website(url, timeout)
        
        # Determine speed rating
        speed_rating = "Normal"
        if latency_ms is None:
            speed_rating = "Timeout/Error"
        elif latency_ms > (slow_threshold * 1000):
            speed_rating = "Slow"
        
        # Determine detailed current status
        if is_up:
            if speed_rating == "Slow":
                current_status = "SLOW"
            else:
                current_status = "200 OK"
        else:
            current_status = status_desc  # e.g., "HTTP Status 404", "HTTP Status 500", "Timeout", etc.

        # Get previous state
        prev_data = state.get(url, {
            "status": "UNKNOWN", 
            "down_since": None,
            "last_alert_msg_id": None,
            "last_alert_subject": None
        })
        prev_status = prev_data.get("status", "UNKNOWN")
        prev_down_since = prev_data.get("down_since")
        last_alert_msg_id = prev_data.get("last_alert_msg_id")
        last_alert_subject = prev_data.get("last_alert_subject")
        
        notification_sent = False
        status_changed = (current_status != prev_status)
        
        if status_changed:
            if current_status == "200 OK":
                # Recovered from SLOW or a DOWN state
                if prev_status not in ["UNKNOWN", "200 OK"]:
                    downtime_duration_str = None
                    if prev_down_since:
                        try:
                            down_time = datetime.strptime(prev_down_since, "%Y-%m-%d %H:%M:%S")
                            duration = current_time - down_time
                            
                            # Format duration into human readable string
                            seconds = int(duration.total_seconds())
                            hours, remainder = divmod(seconds, 3600)
                            minutes, seconds = divmod(remainder, 60)
                            
                            parts = []
                            if hours > 0:
                                parts.append(f"{hours}h")
                            if minutes > 0 or hours > 0:
                                parts.append(f"{minutes}m")
                            parts.append(f"{seconds}s")
                            downtime_duration_str = " ".join(parts)
                        except Exception as ex:
                            print(f"[Monitor] Error parsing down_since timestamp '{prev_down_since}': {ex}")
                    
                    print(f"[Monitor] {url} is BACK ONLINE/NORMAL! Sending recovery alert...")
                    success, msg_id = send_recovery_alert(
                        website_url=url, 
                        downtime_duration_str=downtime_duration_str,
                        to_email="sayusahas@gmail.com",
                        in_reply_to=last_alert_msg_id,
                        references=last_alert_msg_id,
                        subject_to_reply=last_alert_subject
                    )
                    notification_sent = success
                else:
                    print(f"[Monitor] {url} is UP (200 OK)")
                
                # Clear alert context on recovery
                last_alert_msg_id = None
                last_alert_subject = None
                down_since_str = None
                
            elif current_status == "SLOW":
                print(f"[Monitor] {url} is SLOW! Sending MEDIUM alert notification...")
                success, msg_id = send_slow_alert(url, latency_ms, to_email="sayusahas@gmail.com")
                notification_sent = success
                if success:
                    last_alert_msg_id = msg_id
                    last_alert_subject = f"[MEDIUM ALERT] ⚠️ Website Slow - {url}"
                down_since_str = prev_down_since or current_time.strftime("%Y-%m-%d %H:%M:%S")
                
            else:
                # Downtime (e.g. 404, 500, Timeout, Connection Error)
                print(f"[Monitor] {url} went DOWN/Changed state! Sending HIGH alert notification... (Reason: {status_desc})")
                success, msg_id = send_downtime_alert(url, status_code if status_code != 0 else status_desc, error_msg, to_email="sayusahas@gmail.com")
                notification_sent = success
                if success:
                    last_alert_msg_id = msg_id
                    last_alert_subject = f"[HIGH ALERT] 🚨 Website Down - {url}"
                down_since_str = prev_down_since or current_time.strftime("%Y-%m-%d %H:%M:%S")
                
                # Trigger phone call on ANY status change to a non-200 state
                # (e.g. 200→404, 404→500, SLOW→500, UNKNOWN→404 all trigger a call)
                print(f"[Monitor] {url} changed to a non-200 state ({current_status}). Triggering voice call...")
                make_voice_call(url, current_status)
        else:
            print(f"[Monitor] {url} remains {current_status}. No alert email sent.")
            down_since_str = prev_down_since
            
        # Save state
        state[url] = {
            "status": current_status,
            "last_check": current_time.strftime("%Y-%m-%d %H:%M:%S"),
            "down_since": down_since_str,
            "last_alert_msg_id": last_alert_msg_id,
            "last_alert_subject": last_alert_subject
        }
            
        # Log to Sheets/CSV
        logger.log(url, status_code, status_desc, latency_ms, speed_rating, notification_sent)
        
        # Log to local rolling history file for dashboard charts
        log_latency(url, latency_ms, status_desc)
        
    save_state(state)
    print(f"--- Finished Status Check ---")

def main():
    parser = argparse.ArgumentParser(description="Website Heartbeat Monitor")
    parser.add_argument("--once", action="store_true", help="Run once and exit (useful for scheduling tools like Windows Task Scheduler)")
    args = parser.parse_args()
    
    # Initialize Google Sheets / CSV fallback logger
    logger = SheetLogger()
    
    if args.once:
        run_checks(logger)
        sys.exit(0)
        
    # Daemon loop mode — supports seconds or minutes
    interval_seconds_val = os.getenv("CHECK_INTERVAL_SECONDS")
    interval_minutes_val = os.getenv("CHECK_INTERVAL_MINUTES")
    
    if interval_seconds_val:
        try:
            interval_sec = int(interval_seconds_val)
        except ValueError:
            interval_sec = 60
            print(f"[Monitor] Invalid CHECK_INTERVAL_SECONDS: {interval_seconds_val}. Defaulting to 60 seconds.")
        if interval_sec <= 0:
            interval_sec = 60
        print(f"[Monitor] Starting Website Monitor daemon. Pulse frequency: every {interval_sec} seconds.")
        schedule.every(interval_sec).seconds.do(run_checks, logger=logger)
    else:
        try:
            interval_min = int(interval_minutes_val) if interval_minutes_val else 10
        except ValueError:
            interval_min = 10
            print(f"[Monitor] Invalid CHECK_INTERVAL_MINUTES: {interval_minutes_val}. Defaulting to 10 minutes.")
        if interval_min <= 0:
            interval_min = 10
        print(f"[Monitor] Starting Website Monitor daemon. Pulse frequency: every {interval_min} minutes.")
        schedule.every(interval_min).minutes.do(run_checks, logger=logger)
    
    # Run once at boot
    run_checks(logger)
    
    try:
        while True:
            schedule.run_pending()
            time.sleep(1)
    except KeyboardInterrupt:
        print("[Monitor] Stopping Website Monitor daemon. Goodbye!")

if __name__ == "__main__":
    main()
