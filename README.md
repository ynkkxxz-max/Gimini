# Free standalone Gemini review service

Use `gemini_review_server.py` together with `tradingview_gemini_bridge.py`.
Both files use Python's standard library only. The standalone server never
imports the Telegram bot and never executes trades.

Render configuration:

- Runtime: Python 3
- Instance type: Free
- Build command: `python -m py_compile gemini_review_server.py tradingview_gemini_bridge.py`
- Start command: `python -u gemini_review_server.py`
- Health check: `/healthz`
- Environment: `GEMINI_API_KEY`, `GEMINI_MODEL` and `TRADINGVIEW_WEBHOOK_TOKEN`
- Use a random token of at least 32 characters. Keep it and the key private.

TradingView V11: create a strategy alert for **alert() function calls only**.
Set its webhook to `https://SERVICE.onrender.com/api/tradingview/TOKEN`.
Read Gemini's Khmer reviews at `https://SERVICE.onrender.com/review/TOKEN`.
An authenticated GET to the webhook URL returns machine-readable reviews.

TradingView requires 2FA for webhook alerts and plan restrictions may apply.
Creating an alert saves a snapshot, so recreate it after a Pine script or
input change. The service queues and acknowledges valid events before the
Gemini API call. It does not send the API key to TradingView.

Render Free services sleep when idle. Their cold start may exceed TradingView's
three-second webhook timeout, so a Free service is not reliable low-latency
trading infrastructure. No paid upgrade is required or authorized by this setup.
Review history uses ephemeral SQLite and may be lost on redeploy.

Gemini reviews are not part of Pine backtests. A model opinion is not a
measured win probability; no improvement to the strategy's win rate is claimed.

Sources:
- https://render.com/docs/free
- https://render.com/docs/web-services
- https://www.tradingview.com/support/solutions/43000529348-how-to-configure-webhook-alerts/
