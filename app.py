import logging
import os
import time
from threading import Thread

from dotenv import load_dotenv
from flask import Flask, Response, request
from twilio.rest import Client
from twilio.twiml.voice_response import VoiceResponse

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = Flask(__name__)

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID", "")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN", "")
TWILIO_PHONE_NUMBER = os.getenv("TWILIO_PHONE_NUMBER", "")
FORWARD_TO_NUMBER = os.getenv("FORWARD_TO_NUMBER", "")
MISSED_CALL_SMS_MESSAGE = os.getenv(
    "MISSED_CALL_SMS_MESSAGE",
    "Hey, sorry we missed your call. How can we help?",
)

# Caller -> epoch timestamp when we last sent them a missed-call SMS.
recent_sms_by_caller: dict[str, float] = {}
client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


def _twiml_response(xml: str) -> Response:
    return Response(xml, mimetype="text/xml")


def _send_sms(to: str, body: str) -> None:
    logger.info("Sending SMS to %s", to)
    message = client.messages.create(
        to=to,
        from_=TWILIO_PHONE_NUMBER,
        body=body,
    )
    logger.info("Twilio message SID: %s", message.sid)


def schedule_missed_call_sms(caller: str, delay_seconds: int) -> None:
    def _worker() -> None:
        time.sleep(delay_seconds)
        try:
            _send_sms(caller, MISSED_CALL_SMS_MESSAGE)
            recent_sms_by_caller[caller] = time.time()
        except Exception:
            logger.exception("Failed to send missed call SMS")

    Thread(target=_worker, daemon=True).start()


@app.route("/")
def health() -> str:
    return "ok"


@app.route("/voice", methods=["POST"])
def voice() -> Response:
    caller = (request.form.get("From") or "").strip()
    forward_to_number = FORWARD_TO_NUMBER.strip()

    logger.info("Incoming call from %s", caller)

    resp = VoiceResponse()

    # Forward the call to the business number.
    # When the forwarded call ends, Twilio will request /voice/status
    # and include DialCallStatus.
    dial = resp.dial(action="/voice/status", method="POST")
    dial.number(forward_to_number)

    return _twiml_response(str(resp))


@app.route("/voice/status", methods=["POST"])
def voice_status() -> Response:
    dial_status = (request.form.get("DialCallStatus") or "").strip().lower()
    caller = (request.form.get("From") or "").strip()
    logger.info("Dial status=%s caller=%s", dial_status, caller)

    if dial_status in {"no-answer", "busy", "failed"}:
        # Duplicate protection (in-memory).
        last_sent = recent_sms_by_caller.get(caller, 0)
        if time.time() - last_sent < 10 * 60:
            logger.info("Skipping SMS for %s (duplicate window)", caller)
        else:
            schedule_missed_call_sms(caller=caller, delay_seconds=25)

    return _twiml_response("<Response></Response>")


@app.route("/sms", methods=["POST"])
def sms_reply() -> Response:
    from_number = (request.form.get("From") or "").strip()
    body = (request.form.get("Body") or "").strip()
    logger.info("Inbound SMS from %s: %s", from_number, body)

    forward_to_number = FORWARD_TO_NUMBER.strip()
    if forward_to_number:
        try:
            _send_sms(forward_to_number, f"New lead from {from_number}: {body}")
        except Exception:
            logger.exception("Failed to forward inbound SMS")

    return _twiml_response("<Response></Response>")


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 5000)))
