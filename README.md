# 🌐 WebPulse Monitor

> **Real-time website uptime monitoring with automated email alerts and phone call notifications.**

WebPulse Monitor continuously checks your websites for downtime, slow responses, and unexpected HTTP status codes. When something goes wrong, it immediately notifies you via a **HIGH/MEDIUM priority email** and triggers an **automated phone call** — so you never miss a critical outage.

---

## ✨ Features

- 🔍 **Multi-URL Monitoring** — Watch multiple websites simultaneously from a single config
- 📊 **Status Detection** — Detects HTTP errors (404, 500, etc.), timeouts, and connection failures
- 🐢 **Slow Response Detection** — Flags responses that exceed a configurable latency threshold
- 📧 **Smart Email Alerts** — HIGH alerts for downtime, MEDIUM alerts for slow responses
- 🧵 **Email Threading** — Recovery emails are sent in the same thread as the original alert
- 🔕 **No Duplicate Alerts** — Alerts only fire when the status *changes*, not on every check
- 📞 **Phone Call Alerts** — Automated voice calls via Twilio when a site goes down
- 📋 **Google Sheets Logging** — Every check is logged to a Google Sheet for history tracking
- 💾 **CSV Fallback** — Logs to a local CSV if Google Sheets is unavailable
- ⚙️ **Configurable Intervals** — Check every N seconds or N minutes via `.env`

---

## 📁 Project Structure

```
WebPulse-Monitor/
├── monitor.py              # Main daemon — runs all checks on a schedule
├── requirements.txt        # Python dependencies
├── .env                    # Your private config (never commit this!)
├── .env.example            # Template for environment variables
├── src/
│   ├── notifier.py         # Email alert logic (SMTP + threading)
│   └── caller.py           # Twilio voice call logic
├── storage/
│   ├── sheet_logger.py     # Google Sheets / CSV logging
│   └── monitor_state.json  # Persisted state between runs (auto-generated)
└── test/
    ├── test_monitor.py     # Unit tests
    └── test-server/        # Local test server to simulate 200/404/500 responses
```

---

## 🚀 Quick Start

### 1. Clone the repository

```bash
git clone https://github.com/YOUR_USERNAME/webpulse-monitor.git
cd webpulse-monitor
```

### 2. Install dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` with your settings (see [Configuration](#%EF%B8%8F-configuration) below).

### 4. Run the monitor

```bash
python monitor.py
```

Or run once (useful for cron/Task Scheduler):

```bash
python monitor.py --once
```

---

## ⚙️ Configuration

Copy `.env.example` to `.env` and fill in your values:

```env
# Comma-separated list of URLs to monitor
WEBSITES_TO_MONITOR=https://your-site.com,https://your-other-site.com

# Check frequency
CHECK_INTERVAL_SECONDS=60      # Use seconds (takes priority)
# CHECK_INTERVAL_MINUTES=10    # Or use minutes

# Request settings
REQUEST_TIMEOUT_SECONDS=10     # Seconds before a request is considered timed out
SLOW_THRESHOLD_SECONDS=1.5     # Seconds above which a response is flagged as "slow"

# --- Email Alerts (Gmail SMTP) ---
SMTP_SERVER=smtp.gmail.com
SMTP_PORT=587
SMTP_USERNAME=your-sender@gmail.com
SMTP_PASSWORD=your-gmail-app-password   # Use a Gmail App Password, not your real password
NOTIFICATION_RECEIVER=your-receiver@gmail.com

# --- Google Sheets Logging (optional) ---
GOOGLE_SHEET_ID=your-google-sheet-id
GOOGLE_CREDS_FILE=storage/credentials.json

# --- Twilio Phone Calls (optional) ---
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your-auth-token
TWILIO_FROM_NUMBER=+1234567890      # Your Twilio phone number
TWILIO_TO_NUMBER=+0987654321        # Number to call when site goes down
TWILIO_PLAY_URL=                    # Optional: URL to a custom audio file to play
```

---

## 📧 Email Alert Types

| Situation | Alert Level | Subject Example |
|-----------|-------------|-----------------|
| Site returns non-200 (404, 500, etc.) | 🔴 **HIGH** | `[HIGH ALERT] 🚨 Website Down - https://example.com` |
| Site responds but is slow | 🟡 **MEDIUM** | `[MEDIUM ALERT] ⚠️ Website Slow - https://example.com` |
| Site recovers to 200 OK | 🟢 **Recovery** | `Re: [HIGH ALERT] 🚨 Website Down - https://example.com` |

> Recovery emails are **threaded** under the original alert email for easy tracking.

---

## 📞 Phone Call Alerts

When a website transitions from **UP → DOWN**, an automated phone call is placed to `TWILIO_TO_NUMBER` using Twilio's Voice API. The call reads:

> *"Alert. Alert. Alert. Your website is down and requires immediate attention. Website: [URL]. Current status: [HTTP Status]. This is a high priority alert. Please check your server immediately..."*

### Gmail App Password Setup

1. Go to your Google Account → **Security** → **2-Step Verification** (must be enabled)
2. At the bottom, click **App Passwords**
3. Generate a password for "Mail" → copy the 16-character code into `SMTP_PASSWORD`

### Twilio Setup

1. Sign up at [twilio.com](https://www.twilio.com) and get a free phone number
2. Add your credentials to `.env`
3. **Trial accounts:** You must [verify your personal phone number](https://www.twilio.com/console/phone-numbers/verified) in the Twilio console before calls can reach it. A brief trial disclaimer will also play before your message.

---

## 📊 Google Sheets Logging

Each monitoring check is logged with:
- Timestamp
- URL checked
- HTTP status code & description
- Response latency (ms)
- Speed rating (Normal / Slow / Timeout)
- Whether a notification was sent

### Setup

1. Create a Google Cloud project and enable the **Google Sheets API** and **Google Drive API**
2. Create a **Service Account**, download the JSON key, and save it as `storage/credentials.json`
3. Share your Google Sheet with the service account email (give it **Editor** access)
4. Paste the Sheet ID into `GOOGLE_SHEET_ID` in your `.env`

If credentials are missing or invalid, the monitor automatically falls back to logging in a local **CSV file** (`storage/monitor_log.csv`).

---

## 🧪 Testing

### Run the test server

Simulates a controllable web server with buttons to trigger 200, 404, and 500 responses:

```bash
python test/test-server/server.py
```

Then open `http://127.0.0.1:8080` in your browser.

### Run unit tests

```bash
python -m pytest test/test_monitor.py -v
```

---

## 📦 Dependencies

| Package | Purpose |
|---------|---------|
| `requests` | HTTP checks |
| `schedule` | Polling interval management |
| `python-dotenv` | Environment variable loading |
| `gspread` | Google Sheets API client |
| `google-auth` | Google API authentication |
| `twilio` | Voice call alerts |

---

## 🛡️ Security Notes

- **Never commit `.env`** — it contains your SMTP password and Twilio credentials
- Use Gmail **App Passwords**, not your real Google password
- The `.gitignore` excludes `.env`, `storage/credentials.json`, and state files automatically

---

## 📜 License

MIT License — free to use, modify, and distribute.
