import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from dotenv import load_dotenv

# Load env variables in case notifier is imported or run standalone
load_dotenv()

def send_email(subject, body, to_email=None, in_reply_to=None, references=None):
    """
    Sends an email using standard SMTP.
    Supports standard TLS (port 587) and SSL (port 465).
    Returns (success_bool, message_id)
    """
    smtp_server = os.getenv("SMTP_SERVER")
    smtp_port = os.getenv("SMTP_PORT")
    smtp_username = os.getenv("SMTP_USERNAME")
    smtp_password = os.getenv("SMTP_PASSWORD")
    receiver_email = to_email or os.getenv("NOTIFICATION_RECEIVER")
    
    if not all([smtp_server, smtp_port, smtp_username, smtp_password, receiver_email]):
        print("[Notifier] Missing SMTP configuration in environment. Email not sent.")
        return False, None
        
    try:
        port = int(smtp_port)
    except ValueError:
        print(f"[Notifier] Invalid SMTP_PORT: {smtp_port}. Port must be an integer.")
        return False, None

    # Create message container
    msg = MIMEMultipart()
    msg['From'] = smtp_username
    msg['To'] = receiver_email
    
    if in_reply_to:
        msg['In-Reply-To'] = in_reply_to
        msg['References'] = references or in_reply_to
        if not subject.lower().startswith("re:"):
            msg['Subject'] = f"Re: {subject}"
        else:
            msg['Subject'] = subject
    else:
        msg['Subject'] = subject
    
    # Generate unique Message-ID
    import email.utils
    domain = 'localhost'
    if smtp_server and '.' in smtp_server:
        parts = smtp_server.split('.')
        if len(parts) >= 2:
            domain = '.'.join(parts[-2:])
    msg_id = email.utils.make_msgid(domain=domain)
    msg['Message-ID'] = msg_id
    
    msg.attach(MIMEText(body, 'plain'))
    
    try:
        if port == 465:
            # SSL Connection
            server = smtplib.SMTP_SSL(smtp_server, port, timeout=10)
        else:
            # TLS Connection (port 587 etc.)
            server = smtplib.SMTP(smtp_server, port, timeout=10)
            server.ehlo()
            server.starttls()
            server.ehlo()
            
        server.login(smtp_username, smtp_password)
        server.sendmail(smtp_username, receiver_email, msg.as_string())
        server.quit()
        print(f"[Notifier] Alert email successfully sent to {receiver_email} with Message-ID: {msg_id}")
        return True, msg_id
    except Exception as e:
        print(f"[Notifier] Error sending email: {e}")
        return False, None

def send_downtime_alert(website_url, status_code, error_message, to_email=None):
    """
    Formulate and send a HIGH alert downtime email.
    Returns (success_bool, message_id)
    """
    subject = f"[HIGH ALERT] 🚨 Website Down - {website_url}"
    body = (
        f"Hello,\n\n"
        f"This is an automated HIGH SEVERITY alert notification.\n"
        f"The website monitored has failed its availability check.\n\n"
        f"Details:\n"
        f"-----------------------------------------\n"
        f"URL:          {website_url}\n"
        f"Status Code:  {status_code}\n"
        f"Error/Reason: {error_message}\n"
        f"-----------------------------------------\n\n"
        f"Please check the server status as soon as possible.\n"
    )
    return send_email(subject, body, to_email=to_email)

def send_slow_alert(website_url, latency_ms, to_email=None):
    """
    Formulate and send a MEDIUM alert slow response email.
    Returns (success_bool, message_id)
    """
    subject = f"[MEDIUM ALERT] ⚠️ Website Slow - {website_url}"
    body = (
        f"Hello,\n\n"
        f"This is an automated MEDIUM SEVERITY alert notification.\n"
        f"The website monitored is responding extremely slowly.\n\n"
        f"Details:\n"
        f"-----------------------------------------\n"
        f"URL:          {website_url}\n"
        f"Latency:      {latency_ms:.1f} ms\n"
        f"State:        SLOW\n"
        f"-----------------------------------------\n\n"
        f"Please investigate performance issues.\n"
    )
    return send_email(subject, body, to_email=to_email)

def send_recovery_alert(website_url, downtime_duration_str=None, to_email=None, in_reply_to=None, references=None, subject_to_reply=None):
    """
    Formulate and send a recovery alert email.
    Returns (success_bool, message_id)
    """
    subject = subject_to_reply or f"✅ RECOVERED: Website Up - {website_url}"
    duration_info = f" (Downtime duration: {downtime_duration_str})" if downtime_duration_str else ""
    body = (
        f"Hello,\n\n"
        f"Good news! The website has recovered and is now answering successfully.\n\n"
        f"Details:\n"
        f"-----------------------------------------\n"
        f"URL:          {website_url}\n"
        f"Status Code:  200 OK\n"
        f"State:        ONLINE\n"
        f"Duration:     {duration_info if duration_info else 'N/A'}\n"
        f"-----------------------------------------\n\n"
        f"Monitoring has resumed standard heartbeat checks.\n"
    )
    return send_email(subject, body, to_email=to_email, in_reply_to=in_reply_to, references=references)
