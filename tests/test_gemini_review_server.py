import http.client
import json
import os
import threading
import unittest
from unittest.mock import patch

import gemini_review_server as server


class StandaloneServerTests(unittest.TestCase):
    def setUp(self):
        self.httpd = server.ThreadingHTTPServer(('127.0.0.1', 0), server.ReviewHandler)
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=2)

    def request(self, path):
        connection = http.client.HTTPConnection('127.0.0.1', self.httpd.server_port, timeout=2)
        try:
            connection.request('GET', path)
            response = connection.getresponse()
            return response.status, response.read()
        finally:
            connection.close()

    def test_public_health_and_not_found(self):
        status, body = self.request('/healthz')
        self.assertEqual(status, 200)
        self.assertFalse(json.loads(body)['places_orders'])
        self.assertEqual(self.request('/missing')[0], 404)

    def test_dashboard_requires_private_token(self):
        with patch.dict(os.environ, {'TRADINGVIEW_WEBHOOK_TOKEN': 'x'*40}):
            self.assertEqual(self.request('/review/wrong')[0], 403)

    def test_dashboard_escapes_model_text(self):
        class FakeBridge:
            def recent(self):
                return [dict(snapshot=dict(closed_at=1793376000000, event='PREP', side='SELL', trigger=4000),
                             status='reviewed', review=dict(verdict='WAIT', reason_km='<script>alert(1)</script>',
                                                          risks_km=[], missing_data=[]))]
        with patch.dict(os.environ, {'TRADINGVIEW_WEBHOOK_TOKEN': 'x'*40}), patch.object(server, 'get_bridge', return_value=FakeBridge()):
            status, body = self.request('/review/' + 'x'*40)
            self.assertEqual(status, 200)
            self.assertNotIn(b'<script>', body)
            self.assertIn(b'&lt;script&gt;', body)


if __name__ == '__main__':
    unittest.main()
