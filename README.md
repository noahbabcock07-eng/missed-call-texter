# Missed Call Texter

Small Flask service for a call-forwarding SaaS MVP. It forwards inbound calls with Twilio, sends a delayed missed-call SMS when the business does not answer, and forwards inbound SMS replies to the business owner's phone.

## How it works

1. Twilio sends inbound calls to `POST /voice`.
2. The app forwards the call to `FORWARD_TO_NUMBER` with Twilio `<Dial>`.
3. After the forwarded call ends, Twilio sends `DialCallStatus` to `POST /voice/status`.
4. If the dial result is `no-answer`, `busy`, or `failed`, the app schedules a delayed SMS back to the original caller.
5. The SMS is delayed by 20-30 seconds to avoid interrupting voicemail.
6. Duplicate missed-call SMS messages are blocked for 10 minutes per caller using an in-memory dictionary.
7. If the customer replies by SMS, Twilio sends that reply to `POST /sms`, and the app forwards it to `FORWARD_TO_NUMBER`.

Default SMS:

```text
Hey, sorry we missed your call. How can we help?
```

You can override that text with `MISSED_CALL_SMS_MESSAGE`.

## MVP behavior

- Forwarding logic stays simple and uses Twilio webhooks only.
- Missed-call detection uses `DialCallStatus`, which reflects the outcome of the forwarded call leg.
- SMS sending is delayed in a background thread so the webhook can return immediately.
- Duplicate texts are blocked for 10 minutes per caller.
- Caller number, status, and timestamps are logged to the console.
- Customer SMS replies are forwarded to the business owner as `New lead from <number>: <message>`.

## Environment variables

Required:

- `TWILIO_ACCOUNT_SID`
- `TWILIO_AUTH_TOKEN`
- `TWILIO_PHONE_NUMBER`

Recommended for the missed-call flow:

- `FORWARD_TO_NUMBER` - the real phone number that should ring when a call comes in

Optional:

- `MISSED_CALL_SMS_DELAY_SECONDS` - delay before the SMS is sent; clamped to 20-30 seconds, default `25`
- `MISSED_CALL_SMS_MESSAGE` - custom auto-reply text

See `.env.example` for a copyable template.

## Run locally

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python app.py
```

The app listens on `http://localhost:5000`.

If you want to test Twilio webhooks locally, expose the app with a tunnel such as:

```bash
ngrok http 5000
```

Then set your Twilio phone number's Voice webhook to:

```text
https://your-public-url/voice
```

Use `HTTP POST`.

Set the same Twilio phone number's Messaging webhook to:

```text
https://your-public-url/sms
```

Use `HTTP POST`.

## Deploy on Render

### Option 1: Quick manual deploy

1. Push this project to GitHub.
2. In Render, create a new Web Service from the repo.
3. Use:
   - Build command: `pip install -r requirements.txt`
   - Start command: `gunicorn --bind 0.0.0.0:$PORT app:app`
4. Add these environment variables in Render:
   - `TWILIO_ACCOUNT_SID`
   - `TWILIO_AUTH_TOKEN`
   - `TWILIO_PHONE_NUMBER`
   - `FORWARD_TO_NUMBER`
   - `MISSED_CALL_SMS_DELAY_SECONDS` (optional, default `25`)
   - `MISSED_CALL_SMS_MESSAGE` (optional)
5. Deploy.
6. In the Twilio Console, set the phone number Voice webhook to:

```text
https://your-render-service.onrender.com/voice
```

7. Set the phone number Messaging webhook to:

```text
https://your-render-service.onrender.com/sms
```

### Option 2: Use `render.yaml`

This repo includes `render.yaml`, so you can also create the Render service with Blueprint deploys. You still need to set the secret environment variables in Render.

## Notes

- `TWILIO_PHONE_NUMBER` is used as the SMS sender.
- `FORWARD_TO_NUMBER` is the destination that actually rings.
- If `FORWARD_TO_NUMBER` is missing, the app will end the call instead of forwarding it.
- The duplicate-message store is in memory, so it resets if the app restarts or scales to multiple instances.
