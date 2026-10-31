# Gimini XAUUSD manual chart review

Open the service root URL to review a TradingView screenshot or a written setup
in Khmer. This mode works without a TradingView webhook subscription.

1. Sign in using the Gemini API key configured on this service, or its private
   `TRADINGVIEW_WEBHOOK_TOKEN`. Enter credentials only on your service's HTTPS
   page; never put them in GitHub, chat, a screenshot, or a query string.
2. Select a PNG/JPG/WebP chart (up to 5 MB), timeframe, proposed direction, and
   chart time. Add a question or context. A written description of at least
   20 characters can be used instead of an image.
3. Click the Gemini review button. The page shows technical consistency,
   Khmer reasons, risks, and missing information. `WAIT` means more evidence
   is needed; `SETUP_CONSISTENT` is not an order to execute a trade.

The image and supplied context are sent to Google Gemini only when submitted.
Uploads are processed in memory and released after review; they are not saved
as service files. The last 20 manual results are temporary and disappear on
restart. The eight-hour login cookie is signed, HttpOnly, SameSite=Strict and
Secure over HTTPS. The browser does not store the submitted API key. Requests
require the same origin, authenticated access, and a 20-second submission gap.

## Render configuration

Deploy the included `render.yaml`, using the existing Free service:

- Runtime: Python 3, standard library only
- Build: `python -m unittest discover -s tests -v`
- Start: `python -u gemini_review_server.py`
- Health: `/healthz` (`v13-khmer`, `configured: true` when a key is present)
- `GEMINI_API_KEY`: set privately in Render
- `GEMINI_MODEL`: `gemini-3.5-flash-lite`
- `TRADINGVIEW_WEBHOOK_TOKEN`: generated private token, at least 32 characters

Ship `manual.html`, `manual_review.py`, `gemini_review_server.py`, and
`tradingview_gemini_bridge.py` together. Never run the separate Telegram bot
as part of this service. No paid plan is required by this manual workflow.

Free services can sleep when idle; the first visit may take time to open.
Gemini API quota and billing are separate from Render's Free plan.

## Optional TradingView webhook mode

The existing V11 Pine file and protected webhook are retained. TradingView
Basic blocked webhook alerts during setup, so no automatic alert is enabled.
For an eligible account, create an alert for **alert() function calls only**:

- Webhook: `https://SERVICE.onrender.com/api/tradingview/TOKEN`
- Private review dashboard: `https://SERVICE.onrender.com/review/TOKEN`

Keep these token-bearing URLs private. Recreate an alert after changing Pine
code or inputs. Incoming events are queued before calling Gemini. Webhook
history uses ephemeral SQLite and can disappear on redeploy; Free cold starts
are unsuitable for dependable low-latency alerts.

The service never places orders or changes Pine backtests. No improvement in
strategy win rate is claimed, and AI output is not a measured win probability.

## Validation

Every reason, risk, and missing-information item must contain Khmer prose.
Thai characters and other foreign-script letters are rejected before displaying
the review. Gemini regenerates once from the original evidence using short
Khmer sentences. If it fails again, the page shows a Khmer error instead of
mixed-language text. ASCII technical labels such as BUY, SELL and EMA20 remain
allowed. Script validation does not guarantee perfect Khmer grammar.

Run `python -m unittest discover -s tests -v`. Tests cover authentication,
origin checks, sessions, input validation, multimodal payload construction,
queueing, failed-review handling, and the existing webhook behavior. Mocked
test results are fixtures, not live Gemini predictions.

Documentation: [Render Free](https://render.com/docs/free),
[Gemini image input](https://ai.google.dev/gemini-api/docs/image-understanding).
