import base64
import http.client
import json
import os
import time
import unittest
from unittest.mock import patch

import manual_review as manual
import gemini_review_server as server
from tests import test_gemini_review_server as http_tests


def entry():
    return {'timeframe': '15m', 'direction': 'SELL', 'context': 'Synthetic test: price below EMA20 and EMA50; higher timeframe data not supplied.', 'price': 4000}


class ManualInputTests(unittest.TestCase):
    def test_requires_chart_or_useful_context(self):
        with self.assertRaisesRegex(ValueError, 'chart_or_context_required'):
            manual.valid_manual_input({'context': 'short'})

    def test_rejects_invalid_price_and_mismatched_image(self):
        with self.assertRaisesRegex(ValueError, 'invalid_price'):
            manual.valid_manual_input(dict(entry(), price=float('nan')))
        with self.assertRaisesRegex(ValueError, 'invalid_image'):
            manual.valid_manual_input(dict(entry(), image={'mime': 'image/jpeg', 'data': base64.b64encode(b'not-an-image').decode()}))

    def test_png_input_and_multimodal_request(self):
        image = {'mime': 'image/png', 'data': base64.b64encode(b'\x89PNG\r\n\x1a\nexample').decode()}
        data = manual.valid_manual_input(dict(entry(), image=image))
        with patch.object(manual, 'generate_review', return_value={'verdict': 'WAIT'}) as generate:
            manual.analyze_manual(data)
        parts = generate.call_args.args[0]
        self.assertEqual(parts[1]['inlineData']['mimeType'], 'image/png')
        self.assertNotIn('data', json.loads(parts[0]['text'].split('Supplied data: ')[1]))

    def test_expired_and_tampered_session_are_rejected(self):
        class Handler:
            headers = {}
        handler = Handler()
        with patch.dict(os.environ, {'TRADINGVIEW_WEBHOOK_TOKEN': 'x'*40}):
            valid = manual.new_session()
            handler.headers = {'Cookie': manual.COOKIE + '=' + valid}
            self.assertTrue(manual.authenticated(handler))
            handler.headers = {'Cookie': manual.COOKIE + '=' + valid[:-1] + ('b' if valid[-1] != 'b' else 'a')}
            self.assertFalse(manual.authenticated(handler))
            with patch.object(manual.time, 'time', return_value=time.time() + 40000):
                handler.headers = {'Cookie': manual.COOKIE + '=' + valid}
                self.assertFalse(manual.authenticated(handler))

    def test_failure_is_wait_and_screenshot_is_not_retained(self):
        jobs = manual.ManualJobs(lambda data: (_ for _ in ()).throw(RuntimeError('gemini_http_403')))
        status, response = jobs.submit(entry())
        self.assertEqual(status, 202)
        jobs.jobs.join()
        result = jobs.get(response['id'])
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['review']['verdict'], 'WAIT')
        self.assertNotIn('image', result)
        self.assertIsNone(result['review']['win_probability'])


class ManualHttpTests(unittest.TestCase):
    setUp = http_tests.StandaloneServerTests.setUp
    tearDown = http_tests.StandaloneServerTests.tearDown
    request = http_tests.StandaloneServerTests.request
    def post(self, path, payload, cookie='', origin=True):
        host = '127.0.0.1:' + str(self.httpd.server_port)
        headers = {'Content-Type': 'application/json', 'Cookie': cookie}
        if origin:
            headers['Origin'] = 'http://' + host
        connection = http.client.HTTPConnection('127.0.0.1', self.httpd.server_port, timeout=2)
        try:
            connection.request('POST', path, json.dumps(payload), headers)
            response = connection.getresponse()
            return response.status, json.loads(response.read()), response.getheader('Set-Cookie')
        finally:
            connection.close()

    def get_authenticated(self, path, cookie):
        connection = http.client.HTTPConnection('127.0.0.1', self.httpd.server_port, timeout=2)
        try:
            connection.request('GET', path, headers={'Cookie': cookie})
            response = connection.getresponse()
            return response.status, json.loads(response.read())
        finally:
            connection.close()

    def test_public_form_contains_no_server_secret(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'private-provider-key'}):
            status, body = self.request('/')
            self.assertEqual(status, 200)
            self.assertIn(b'analysisForm', body)
            self.assertNotIn(b'private-provider-key', body)

    def test_login_authentication_origin_and_manual_workflow(self):
        result = {'ai_status': 'reviewed', 'verdict': 'WAIT', 'reason_km': 'ត្រូវការទិន្នន័យបន្ថែម។', 'risks_km': [], 'missing_data': ['Higher timeframe'], 'win_probability': None}
        jobs = manual.ManualJobs(lambda data: result)
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'private-provider-key', 'TRADINGVIEW_WEBHOOK_TOKEN': 'x'*40}), patch.object(manual, 'manual_jobs', return_value=jobs):
            self.assertEqual(self.post('/api/manual', entry())[0], 401)
            self.assertEqual(self.post('/api/session', {'credential': 'x'*40}, origin=False)[0], 403)
            self.assertEqual(self.post('/api/session', {'credential': 'wrong'})[0], 401)
            code, response, cookie = self.post('/api/session', {'credential': 'x'*40})
            self.assertEqual(code, 200)
            self.assertIn('HttpOnly', cookie)
            self.assertIn('SameSite=Strict', cookie)
            self.assertNotIn('private-provider-key', cookie)
            cookie = cookie.split(';')[0]
            code, accepted, _ = self.post('/api/manual', entry(), cookie)
            self.assertEqual(code, 202)
            jobs.jobs.join()
            code, reviewed = self.get_authenticated('/api/manual/' + accepted['id'], cookie)
            self.assertEqual(code, 200)
            self.assertEqual(reviewed['review']['reason_km'], result['reason_km'])
            self.assertEqual(self.post('/api/manual', entry(), cookie)[0], 429)


if __name__ == '__main__':
    unittest.main()
