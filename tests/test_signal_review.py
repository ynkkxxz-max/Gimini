"""Synthetic fixtures exercise screening, not a measured trading strategy."""
import copy
import unittest

import manual_review as manual
from signal_review import historical_stats, screen_signal


def fixture():
    return {'verdict': 'SETUP_CONSISTENT', 'setup': {
        'direction': 'BUY', 'chart_readable': True, 'trend_aligned': True,
        'entry_confirmed': True, 'chart_time_known': True,
        'entry_price': 100, 'stop_loss': 99, 'take_profit': 102},
        'historical': {'visible': True, 'closed_trades': 500, 'winning_trades': 400,
                       'reported_win_rate': 80, 'profit_factor': 1.5}}


def data():
    return {'image': {'mime': 'image/png', 'data': 'synthetic'}, 'proposed_direction': 'UNDECIDED',
            'min_win_rate': 80, 'min_closed_trades': 100}


class SignalTests(unittest.TestCase):
    def test_buy_requires_all_conditions_and_never_a_win_forecast(self):
        result = screen_signal(fixture(), data())
        self.assertEqual(result['signal'], 'BUY')
        self.assertEqual(result['historical_stats']['win_rate'], 80)
        self.assertIsNone(result['win_probability'])
        self.assertTrue(all(item['passed'] for item in result['checks']))
        self.assertEqual(result['reward_risk'], 2)

    def test_sell_level_order_and_proposed_direction(self):
        review = fixture()
        review['setup'].update(direction='SELL', stop_loss=101, take_profit=98)
        self.assertEqual(screen_signal(review, data())['signal'], 'SELL')
        self.assertEqual(screen_signal(review, dict(data(), proposed_direction='BUY'))['signal'], 'WAIT')

    def test_unconfirmed_prep_or_wait_bias_cannot_become_entry(self):
        for field in ('chart_readable', 'trend_aligned', 'entry_confirmed', 'chart_time_known'):
            with self.subTest(field=field):
                review = fixture()
                review['setup'][field] = False
                self.assertEqual(screen_signal(review, data())['signal'], 'WAIT')
        review = dict(fixture(), verdict='WAIT')
        self.assertEqual(screen_signal(review, data())['signal'], 'WAIT')
        self.assertEqual(screen_signal(fixture(), dict(data(), image=None))['signal'], 'WAIT')

    def test_eighty_percent_filter_sample_and_profit_factor(self):
        for change in ({'winning_trades': 399, 'reported_win_rate': None},
                       {'closed_trades': 5, 'winning_trades': 4}, {'profit_factor': 0.9},
                       {'profit_factor': None}, {'visible': False}):
            with self.subTest(change=change):
                review = fixture()
                review['historical'].update(change)
                result = screen_signal(review, data())
                self.assertEqual(result['signal'], 'WAIT')
                self.assertIsNone(result['entry_price'])
        review = fixture()
        review['historical'].update(closed_trades=100000, winning_trades=79999, reported_win_rate=None)
        self.assertEqual(screen_signal(review, data())['signal'], 'WAIT')

    def test_missing_bad_or_low_reward_levels_are_wait(self):
        for change in ({'stop_loss': None}, {'stop_loss': 101}, {'take_profit': 100},
                       {'entry_price': True}, {'take_profit': float('nan')},
                       {'take_profit': 101}, {'direction': 'MIXED'}):
            with self.subTest(change=change):
                review = fixture()
                review['setup'].update(change)
                self.assertEqual(screen_signal(review, data())['signal'], 'WAIT')

    def test_reported_history_has_provenance_and_no_fabricated_wins(self):
        raw = dict(fixture()['historical'], winning_trades=None)
        result = historical_stats(raw, True)
        self.assertTrue(result['available'])
        self.assertIsNone(result['winning_trades'])
        self.assertEqual(result['method'], 'reported')
        self.assertEqual(result['source'], 'screenshot')
        self.assertFalse(historical_stats(raw, False)['available'])

    def test_inconsistent_or_impossible_history_is_not_displayed(self):
        for change in ({'closed_trades': 0}, {'closed_trades': True}, {'winning_trades': 501},
                       {'reported_win_rate': 90}, {'reported_win_rate': float('inf')},
                       {'closed_trades': 3, 'winning_trades': None, 'reported_win_rate': 80}):
            with self.subTest(change=change):
                raw = dict(fixture()['historical'], **change)
                result = historical_stats(raw, True)
                self.assertFalse(result['available'])
                self.assertIsNone(result['win_rate'])

    def test_signal_filter_input_validation_and_defaults(self):
        clean = manual.valid_manual_input({'context': 'Synthetic context only with no chart attached.'})
        self.assertEqual(clean['min_win_rate'], 80)
        self.assertEqual(clean['min_closed_trades'], 100)
        for change in ({'min_win_rate': True}, {'min_win_rate': float('nan')},
                       {'min_win_rate': 101}, {'min_closed_trades': 0}, {'min_closed_trades': 1.5}):
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, 'invalid_input'):
                manual.valid_manual_input(dict({'context': 'Synthetic context for validation only.'}, **change))

    def test_malformed_extraction_fails_closed(self):
        for review in ({}, {'setup': None, 'historical': []}, {'setup': {'direction': 'BUY'}}):
            result = screen_signal(copy.deepcopy(review), data())
            self.assertEqual(result['signal'], 'WAIT')
            self.assertIsNone(result['win_probability'])


if __name__ == '__main__':
    unittest.main()
