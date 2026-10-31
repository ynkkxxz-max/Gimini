import copy
import io
import json
import os
import unittest
from unittest.mock import patch

import manual_review as manual
import tradingview_gemini_bridge as bridge


VALID = {'verdict': 'WAIT', 'reason_km': 'ទិសដៅមិនស្របគ្នា។ សូមរង់ចាំទៀនបិទ។',
         'risks_km': ['តម្លៃអាចត្រឡប់ឡើងវិញ។'],
         'missing_data': ['ត្រូវការទិសដៅពីក្រាហ្វ 4H និងកម្រិត EMA20។']}


def response(review):
    return io.BytesIO(json.dumps({'candidates': [{'finishReason': 'STOP',
        'content': {'parts': [{'text': json.dumps(review, ensure_ascii=False)}]}}]}).encode())


class KhmerOutputTests(unittest.TestCase):
    def test_language_repair_cannot_change_signal_evidence_or_history(self):
        from signal_review import MANUAL_SCHEMA
        original = dict(VALID, reason_km=VALID['reason_km'] + ' ลง',
                        setup={'direction': 'SELL', 'entry_confirmed': False},
                        historical={'visible': True, 'closed_trades': 5, 'reported_win_rate': 20})
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}), patch.object(
                bridge.urllib.request, 'urlopen', side_effect=[response(original), response(VALID)]) as send:
            result = bridge.generate_review([{'text': 'synthetic'}], 'Review evidence only.', response_schema=MANUAL_SCHEMA)
        self.assertEqual(result['setup'], original['setup'])
        self.assertEqual(result['historical'], original['historical'])
        editing = json.loads(send.call_args_list[1].args[0].data)
        self.assertNotIn('historical', editing['generationConfig']['responseSchema']['required'])

    def test_checks_every_prose_field_for_thai_characters(self):
        for field in ('reason_km', 'risks_km', 'missing_data'):
            with self.subTest(field=field):
                mixed = copy.deepcopy(VALID)
                if field == 'reason_km':
                    mixed[field] += ' ทิศทาง'
                else:
                    mixed[field][0] += ' ทิศทาง'
                self.assertFalse(bridge.is_khmer_review(mixed))
        self.assertTrue(bridge.is_khmer_review(VALID))

    def test_repairs_draft_as_text_without_reanalysing_the_image(self):
        mixed = dict(VALID, reason_km=VALID['reason_km'] + ' ลง')
        parts = [{'text': 'Synthetic test context, not live prices'},
                 {'inlineData': {'mimeType': 'image/png', 'data': 'original-test-image'}}]
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}), patch.object(
                bridge.urllib.request, 'urlopen', side_effect=[response(mixed), response(VALID)]) as send:
            result = bridge.generate_review(parts, 'Review only the supplied evidence.')
        self.assertEqual(result['reason_km'], VALID['reason_km'])
        self.assertEqual(send.call_count, 2)
        first = json.loads(send.call_args_list[0].args[0].data)
        second = json.loads(send.call_args_list[1].args[0].data)
        self.assertEqual(first['contents'][0]['parts'], parts)
        self.assertNotIn('inlineData', json.dumps(second))
        self.assertNotIn('original-test-image', json.dumps(second))
        draft = json.loads(second['contents'][0]['parts'][0]['text'].split('\n', 1)[1])
        self.assertEqual(draft, mixed)
        self.assertIn('ZERO Thai', second['systemInstruction']['parts'][0]['text'])
        self.assertEqual(second['generationConfig']['responseSchema']['properties']['verdict']['enum'], ['WAIT'])

    def test_repeated_language_failure_is_not_presented_as_a_review(self):
        mixed = dict(VALID, missing_data=['រង់ចាំ ข้อมูล'])
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}), patch.object(
                bridge.urllib.request, 'urlopen', side_effect=[response(mixed), response(mixed), response(mixed)]) as send:
            with self.assertRaisesRegex(RuntimeError, '^gemini_language_mismatch$'):
                bridge.generate_review([{'text': 'synthetic'}], 'Review evidence only.')
        self.assertEqual(send.call_count, 3)

    def test_repair_cannot_upgrade_the_verdict(self):
        mixed = dict(VALID, reason_km=VALID['reason_km'] + ' ลง')
        upgraded = dict(VALID, verdict='SETUP_CONSISTENT')
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}), patch.object(
                bridge.urllib.request, 'urlopen', side_effect=[response(mixed), response(upgraded), response(VALID)]) as send:
            result = bridge.generate_review([{'text': 'synthetic'}], 'Review evidence only.')
        self.assertEqual(send.call_count, 3)
        self.assertEqual(result['verdict'], 'WAIT')

    def test_repair_preserves_numbers_labels_and_list_items(self):
        original = dict(VALID, reason_km='តម្លៃ XAUUSD នៅ 3900.50 ក្រោម EMA20។')
        corrupt = dict(original, reason_km=original['reason_km'] + ' د')
        changed_number = dict(original, reason_km='តម្លៃ XAUUSD នៅ 3910.50 ក្រោម EMA20។')
        changed_label = dict(original, reason_km='តម្លៃ XAUUSD នៅ 3900.50 ក្រោម EMA50។')
        changed_items = dict(original, risks_km=[])
        for edited in (changed_number, changed_label, changed_items):
            with self.subTest(edited=edited), patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}), patch.object(
                    bridge.urllib.request, 'urlopen', side_effect=[response(corrupt), response(edited), response(original)]) as send:
                result = bridge.generate_review([{'text': 'synthetic'}], 'Review evidence only.')
                self.assertEqual(result['reason_km'], original['reason_km'])
                self.assertEqual(send.call_count, 3)

    def test_repair_keeps_numbered_items_in_their_original_order(self):
        original = dict(VALID, risks_km=['តម្លៃ 3900 ក្រោម EMA20។', 'តម្លៃ 3950 ក្រោម EMA50។'])
        swapped = dict(original, risks_km=list(reversed(original['risks_km'])))
        self.assertFalse(bridge.same_review_facts(original, swapped))
        localized = dict(original, risks_km=['តម្លៃ ៣៩០០ ក្រោម EMA20។', 'តម្លៃ ៣៩៥០ ក្រោម EMA50។'])
        self.assertTrue(bridge.same_review_facts(original, localized))

    def test_valid_reviews_need_no_editing_request(self):
        with patch.dict(os.environ, {'GEMINI_API_KEY': 'test-key'}), patch.object(
                bridge.urllib.request, 'urlopen', side_effect=[response(VALID)]) as send:
            self.assertEqual(bridge.generate_review([{'text': 'synthetic'}], 'Review evidence only.')['reason_km'], VALID['reason_km'])
        self.assertEqual(send.call_count, 1)

    def test_english_only_missing_information_requires_khmer_translation(self):
        english = dict(VALID, missing_data=['Economic calendar'])
        self.assertFalse(bridge.is_khmer_review(english))

    def test_rejects_other_foreign_letters_embedded_inside_khmer_words(self):
        for character in ('ל', 'ລ', 'я', 'ก', '๕', '฿', 'ฯ', '๛', '\u05b0'):
            with self.subTest(character=character):
                mixed = dict(VALID, risks_km=['តម្លៃហ' + character + 'ាក់ចុះ។'])
                self.assertFalse(bridge.is_khmer_review(mixed))

    def test_valid_khmer_punctuation_numbers_and_technical_labels(self):
        valid = dict(VALID, reason_km='តម្លៃ XAUUSD នៅក្រោម EMA20 លើក្រាហ្វ 15m។\nសូមរង់ចាំទៀនបិទ។',
                     risks_km=['តម្លៃអាចត្រឡប់ពី ៣៨៩០.៥០ ទៅ 3900.50។'])
        self.assertTrue(bridge.is_khmer_review(valid))

    def test_language_failure_reaches_the_user_as_a_safe_error(self):
        def unavailable(_data):
            raise RuntimeError('gemini_language_mismatch')
        jobs = manual.ManualJobs(unavailable)
        status, job = jobs.submit({'context': 'Synthetic QA example with insufficient market data.'})
        self.assertEqual(status, 202)
        jobs.jobs.join()
        result = jobs.get(job['id'])
        self.assertEqual(result['status'], 'failed')
        self.assertEqual(result['review']['error'], 'gemini_language_mismatch')
        self.assertEqual(result['review']['verdict'], 'WAIT')
        self.assertNotIn('reason_km', result['review'])


if __name__ == '__main__':
    unittest.main()
