import copy
import io
import json
import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

import tradingview_gemini_bridge as bridge


def snapshot():
    return dict(schema='gold-setup-v1', event='PREP', side='SELL', ticker='OANDA:XAUUSD',
                timeframe='15', closed_at=int(time.time()*1000), open=4003, high=4005,
                low=3997, price=3999, atr=8, adx=30, ema20=4002, ema50=4010,
                ema200=4040, trigger=3996, bias15=-1, bias60=-1, bias240=-1,
                stop_atr=1.5, reward_risk=2)


class FakeHandler:
    command = 'POST'

    def __init__(self, payload, token):
        body = json.dumps(payload).encode()
        self.path = '/api/tradingview/' + token
        self.headers = {'Content-Length': str(len(body)), 'Content-Type': 'application/json'}
        self.rfile = io.BytesIO(body)
        self.wfile = io.BytesIO()

    def send_response(self, status):
        self.status = status

    def send_header(self, *args):
        pass

    def end_headers(self):
        pass


class BridgeTests(unittest.TestCase):
    def test_rejects_invalid_and_future_inputs(self):
        for field, value in [('price', float('nan')), ('atr', 0), ('bias240', True),
                             ('ticker', 'OANDA:BTCUSD'), ('closed_at', int((time.time()+3600)*1000)),
                             ('closed_at', int((time.time()-3600)*1000)), ('trigger', 4001)]:
            with self.subTest(field=field, value=value):
                data = snapshot()
                data[field] = value
                with self.assertRaises(ValueError):
                    bridge.validate_snapshot(data)

    def test_duplicate_delivery_and_payload_conflict(self):
        with tempfile.TemporaryDirectory() as directory:
            review = bridge.ReviewBridge(Path(directory)/'test.sqlite3')
            data = snapshot()
            self.assertEqual(review.submit(data)[0], 202)
            self.assertEqual(review.submit(data)[0], 200)
            changed = copy.deepcopy(data)
            changed['atr'] = 10
            self.assertEqual(review.submit(changed)[0], 409)
            self.assertEqual(review.jobs.qsize(), 1)

    def test_failure_is_wait_and_never_an_approval(self):
        def failure(data):
            raise RuntimeError('gemini_http_429')
        with tempfile.TemporaryDirectory() as directory:
            review = bridge.ReviewBridge(Path(directory)/'test.sqlite3', failure)
            data = snapshot()
            _, response = review.submit(data)
            review.process_one(response['id'], data)
            result = review.recent()[0]
            self.assertEqual(result['status'], 'failed')
            self.assertEqual(result['review']['verdict'], 'WAIT')
            self.assertIsNone(result['review']['win_probability'])
            self.assertFalse(result['review']['places_orders'])

    def test_auth_and_ack_before_review(self):
        with tempfile.TemporaryDirectory() as directory, patch.dict(os.environ, {'TRADINGVIEW_WEBHOOK_TOKEN': 'a'*40}):
            review = bridge.ReviewBridge(Path(directory)/'test.sqlite3', lambda d: self.fail('synchronous AI call'))
            bad = FakeHandler(snapshot(), 'incorrect')
            bridge.handle_tradingview(bad)
            self.assertEqual(bad.status, 403)
            good = FakeHandler(snapshot(), 'a'*40)
            with patch.object(bridge, 'get_bridge', return_value=review):
                bridge.handle_tradingview(good)
            self.assertEqual(good.status, 202)
            self.assertEqual(json.loads(good.wfile.getvalue())['status'], 'queued')

    def test_gemini_schema_and_model_output_validation(self):
        valid = dict(verdict='SETUP_CONSISTENT', reason_km='ទិសដៅស្របគ្នា។',
                     risks_km=['ការប្រែប្រួលតម្លៃ។'], missing_data=['Economic calendar'])
        def response(value):
            return io.BytesIO(json.dumps({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': json.dumps(value)}]}}]}).encode())
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key', 'GEMINI_MODEL': 'gemini-flash-latest'}):
            with patch.object(bridge.urllib.request, 'urlopen', return_value=response(valid)) as request:
                result = bridge.review_with_gemini(snapshot())
                self.assertFalse(result['affects_pine_backtest'])
                self.assertEqual(result['ai_status'], 'reviewed')
                self.assertNotIn('test-key', request.call_args.args[0].full_url)
            invalid = dict(valid, reason_km='Win chance 99%')
            with patch.object(bridge.urllib.request, 'urlopen', return_value=response(invalid)):
                with self.assertRaisesRegex(RuntimeError, 'invalid_response'):
                    bridge.review_with_gemini(snapshot())

    def test_restart_recovers_queued_review(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)/'test.sqlite3'
            first = bridge.ReviewBridge(path)
            first.submit(snapshot())
            restarted = bridge.ReviewBridge(path)
            self.assertEqual(restarted.jobs.qsize(), 1)


if __name__ == '__main__':
    unittest.main()
