"""Standalone Gemini review service. No bot imports and no order execution."""
import hmac
import html
import json
import os
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from tradingview_gemini_bridge import api_key, get_bridge, handle_tradingview, webhook_token
from manual_review import handle_manual, manual_page


def dashboard():
    rows = []
    for item in get_bridge().recent():
        snapshot, review = item['snapshot'], item['review'] or {}
        verdict = review.get('verdict', item['status'])
        missing = review.get('missing_data', [])
        reason = review.get('reason_km', review.get('error', 'កំពុងរង់ចាំ Gemini។'))
        details = '<br>'.join(html.escape(str(x)) for x in review.get('risks_km', []) + missing)
        closed_at = datetime.fromtimestamp(snapshot['closed_at'] / 1000, timezone(timedelta(hours=7))).strftime('%Y-%m-%d %H:%M')
        rows.append('<tr><td>{}</td><td>{}<br>{}</td><td>{}</td><td>{}</td><td>{}</td></tr>'.format(
            closed_at, html.escape(snapshot['event']),
            html.escape(snapshot['side']), html.escape(str(snapshot['trigger'])),
            html.escape(verdict), html.escape(reason) + ('<p>' + details + '</p>' if details else '')))
    return '''<!doctype html><html lang="km"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>XAUUSD · Gemini setup review</title><style>
body{font:16px/1.7 system-ui,sans-serif;margin:0;background:#101722;color:#e7edf4}main{max-width:1140px;margin:40px auto;padding:24px}
h1{font-size:28px}p{color:#adb9c8}a{color:#7cc8ff}table{border-collapse:collapse;width:100%;background:#182333}th,td{padding:14px;text-align:left;border-bottom:1px solid #344154;vertical-align:top}th{color:#dfc075}td p{font-size:14px} .overflow{overflow:auto}button{padding:10px 18px;border:0;border-radius:8px;background:#e1b75c;color:#17202d;font-weight:700}
</style><main><h1>XAUUSD · Gemini setup review</h1>
<p>PREP = ត្រៀមមុនចូល។ SETUP_CONSISTENT = ទិន្នន័យបច្ចេកទេសស្របគ្នា។ WAIT = រង់ចាំ។</p>
<p>ការពិនិត្យនេះមិនបញ្ជាទិញ/លក់ និងមិនកែ backtest ក្នុង TradingView ទេ។ មិនមានភាគរយឈ្នះដែលបានផ្ទៀងផ្ទាត់សម្រាប់ AI ទេ។</p>
<button onclick="location.reload()">ផ្ទុកលទ្ធផលថ្មី</button><p>សញ្ញាថ្មីបំផុត 30។ ពេលវេលាទៀនគិតជា UTC+7។</p>
<div class="overflow"><table><thead><tr><th>ទៀនបិទ</th><th>សញ្ញា</th><th>Trigger</th><th>លទ្ធផល</th><th>ការពន្យល់ និងទិន្នន័យដែលខ្វះ</th></tr></thead><tbody>''' + (''.join(rows) or '<tr><td colspan="5">មិនទាន់បានទទួលសញ្ញាពី TradingView។</td></tr>') + '</tbody></table></div></main></html>'


class ReviewHandler(BaseHTTPRequestHandler):
    def setup(self):
        super().setup()
        self.connection.settimeout(10)

    def do_GET(self):
        if self.path in ('/', '/manual'):
            body = manual_page()
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Frame-Options', 'DENY')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; img-src 'self' blob: data:; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)
            return
        if handle_manual(self):
            return
        token = webhook_token()
        if self.path.startswith('/review/'):
            if not token or not hmac.compare_digest(self.path.encode(), ('/review/' + token).encode()):
                self.send_error(403)
                return
            body = dashboard().encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.send_header('Content-Length', str(len(body)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Referrer-Policy', 'no-referrer')
            self.send_header('X-Frame-Options', 'DENY')
            self.end_headers()
            self.wfile.write(body)
            return
        if handle_tradingview(self):
            return
        if self.path != '/healthz':
            self.send_error(404)
            return
        body = json.dumps({'service': 'XAUUSD Gemini setup review', 'version': 'v14-khmer-repair',
                           'configured': bool(api_key()), 'places_orders': False}).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_HEAD(self):
        self.send_response(200 if self.path in ('/', '/manual', '/healthz') else 404)
        self.end_headers()

    def do_POST(self):
        if handle_manual(self):
            return
        if not handle_tradingview(self):
            self.send_error(404)

    def log_message(self, *_args):
        pass  # Private endpoint tokens and payloads never appear in access logs.


if __name__ == '__main__':
    address = (os.getenv('BIND_HOST', '0.0.0.0'), int(os.getenv('PORT', '10000')))
    print('Gemini review service listening; credentials remain server-side.', flush=True)
    ThreadingHTTPServer(address, ReviewHandler).serve_forever()
