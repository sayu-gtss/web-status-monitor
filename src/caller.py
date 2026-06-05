import os
from twilio.rest import Client
from dotenv import load_dotenv

# Load env variables in case caller is imported or run standalone
load_dotenv()

def make_voice_call(website_url, status_desc):
    """
    Triggers an automated phone call using Twilio.
    Uses custom voice record if TWILIO_PLAY_URL is set,
    otherwise uses dynamic Text-to-Speech to read the status.
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN")
    from_number = os.getenv("TWILIO_FROM_NUMBER")
    to_number = os.getenv("TWILIO_TO_NUMBER")
    voice_url = os.getenv("TWILIO_PLAY_URL")
    
    if not all([account_sid, auth_token, from_number, to_number]):
        print("[Caller] Missing Twilio configuration. Phone call not triggered.")
        return False

    try:
        client = Client(account_sid, auth_token)
        
        # Build TwiML response
        if voice_url and voice_url.strip():
            # Play a custom audio recording
            twiml_content = f"<Response><Play>{voice_url.strip()}</Play></Response>"
        else:
            # Dynamic text-to-speech with pauses for dramatic clarity
            twiml_content = (
                "<Response>"
                "<Say voice='alice' language='en-US'>Alert. Alert. Alert.</Say>"
                "<Pause length='1'/>"
                "<Say voice='alice' language='en-US'>Your website is down and requires immediate attention.</Say>"
                "<Pause length='1'/>"
                f"<Say voice='alice' language='en-US'>Website: {website_url}.</Say>"
                "<Pause length='1'/>"
                f"<Say voice='alice' language='en-US'>Current status: {status_desc}.</Say>"
                "<Pause length='1'/>"
                "<Say voice='alice' language='en-US'>This is a high priority alert. Please check your server immediately.</Say>"
                "<Pause length='2'/>"
                "<Say voice='alice' language='en-US'>Repeating the alert.</Say>"
                "<Pause length='1'/>"
                f"<Say voice='alice' language='en-US'>Website {website_url} is down. Status: {status_desc}. Please take immediate action.</Say>"
                "</Response>"
            )
            
        call = client.calls.create(
            to=to_number,
            from_=from_number,
            twiml=twiml_content
        )
        print(f"[Caller] Phone call triggered successfully! Call SID: {call.sid}")
        return True
    except Exception as e:
        print(f"[Caller] Error making voice call: {e}")
        return False

if __name__ == "__main__":
    # Test script standalone execution
    print("[Caller] Running Twilio voice call standalone test...")
    make_voice_call("http://127.0.0.1:8080/live", "HTTP Status 404")
