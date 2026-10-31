"""Screenshot setup screening and historical statistics, never a win forecast."""
import math

from tradingview_gemini_bridge import SCHEMA

DEFAULT_MIN_WIN_RATE = 80
DEFAULT_MIN_TRADES = 100
MIN_REWARD_RISK = 1.5


def number_schema(kind='NUMBER'):
    return {'type': kind, 'nullable': True}


SETUP_PROPERTIES = {
    'direction': {'type': 'STRING', 'enum': ['BUY', 'SELL', 'MIXED', 'UNKNOWN']},
    'chart_readable': {'type': 'BOOLEAN'},
    'trend_aligned': {'type': 'BOOLEAN'},
    'entry_confirmed': {'type': 'BOOLEAN'},
    'chart_time_known': {'type': 'BOOLEAN'},
    'entry_price': number_schema(),
    'stop_loss': number_schema(),
    'take_profit': number_schema(),
}
HISTORY_PROPERTIES = {
    'visible': {'type': 'BOOLEAN'},
    'closed_trades': number_schema('INTEGER'),
    'winning_trades': number_schema('INTEGER'),
    'reported_win_rate': number_schema(),
    'profit_factor': number_schema(),
}
MANUAL_SCHEMA = {
    **SCHEMA,
    'properties': {**SCHEMA['properties'],
        'setup': {'type': 'OBJECT', 'properties': SETUP_PROPERTIES, 'required': list(SETUP_PROPERTIES)},
        'historical': {'type': 'OBJECT', 'properties': HISTORY_PROPERTIES, 'required': list(HISTORY_PROPERTIES)}},
    'required': [*SCHEMA['required'], 'setup', 'historical'],
}
SIGNAL_RULES = '''
Also extract structured screenshot evidence into setup and historical.
These are observations, never an invented trade plan or a future win probability.
For setup.direction use the visible technical direction, even if the user's proposed
direction conflicts. MIXED means conflicting directions; UNKNOWN means unreadable.
Set booleans true ONLY when directly supported by clear visible chart evidence.
trend_aligned requires the chart and visible higher-timeframe trends to agree.
entry_confirmed requires a visible confirmed entry trigger on a completed candle.
BIAS, WATCH, PREP, ARMED, an old Last order, or a candle still forming are NOT entry
confirmation. A WAIT banner overrides those preparatory labels.
chart_time_known requires a readable full date and time with timezone, or user-supplied
chart date/time. Do not mistake a historical crosshair time for the latest candle time.
Only extract entry_price, stop_loss and take_profit explicitly displayed for the SAME
current setup. Historical trades, axis ticks and indicator values are not entry/SL/TP.
Use null for missing prices; never calculate or invent levels from the chart image.
Historical data must come ONLY from a clearly visible Strategy Tester/report/stats
panel in the image. Never use performance claims from user context or infer a high
win rate from trend strength. A WIN percentage is reported_win_rate; it is NOT a count.
closed_trades and winning_trades must be counts of CLOSED trades, not WATCH/PREP
markers. Use null for unreadable/missing values, not zero. profit_factor is the visible
historical PF number. If no readable historical report exists, visible=false and all
historical numbers=null. Keep historical percentages numeric in historical only;
do not write percentages in prose. Never state the next signal's win probability.
'''


def finite_number(value, minimum=0, maximum=1000000):
    return type(value) in (int, float) and math.isfinite(value) and minimum <= value <= maximum


def historical_stats(raw, has_image):
    empty = {'available': False, 'win_rate': None, 'closed_trades': None,
             'winning_trades': None, 'profit_factor': None, 'source': 'screenshot', 'method': None}
    if not has_image or not isinstance(raw, dict) or raw.get('visible') is not True:
        return empty
    count, wins, reported, pf = (raw.get(k) for k in
        ('closed_trades', 'winning_trades', 'reported_win_rate', 'profit_factor'))
    if type(count) is not int or not 0 < count <= 1000000:
        return empty
    if wins is not None and (type(wins) is not int or not 0 <= wins <= count):
        return empty
    if reported is not None and not finite_number(reported, maximum=100):
        return empty
    rate = 100 * wins / count if wins is not None else reported
    if rate is None or (wins is not None and reported is not None and abs(rate - reported) > 0.11):
        return empty
    if wins is None and abs(100 * round(rate * count / 100) / count - rate) > 0.11:
        return empty
    return {**empty, 'available': True, 'win_rate': rate, 'closed_trades': count,
            'winning_trades': wins, 'profit_factor': pf if finite_number(pf) else None,
            'method': 'counts' if wins is not None else 'reported'}


def screen_signal(review, data):
    raw = review.get('setup')
    setup = raw if isinstance(raw, dict) else {}
    side = setup.get('direction', 'UNKNOWN')
    has_image = bool(data.get('image'))
    history = historical_stats(review.get('historical'), has_image)
    minimum_rate = data.get('min_win_rate', DEFAULT_MIN_WIN_RATE)
    minimum_trades = data.get('min_closed_trades', DEFAULT_MIN_TRADES)
    proposed = data.get('proposed_direction', 'UNDECIDED')
    entry, stop, target = (setup.get(k) for k in ('entry_price', 'stop_loss', 'take_profit'))
    valid_levels = all(finite_number(value, minimum=0.000001) for value in (entry, stop, target))
    ordered = valid_levels and ((side == 'BUY' and stop < entry < target) or
                                (side == 'SELL' and target < entry < stop))
    rr = abs(target - entry) / abs(entry - stop) if ordered else None
    checks = [
        ('image', 'រូបក្រាហ្វច្បាស់លាស់', has_image and setup.get('chart_readable') is True),
        ('trend', 'ទិសដៅក្រាហ្វ និងពេលវេលាធំស្របគ្នា', side in ('BUY', 'SELL') and setup.get('trend_aligned') is True),
        ('entry', 'មានសញ្ញាចូលដែលបានបញ្ជាក់ក្រោយទៀនបិទ', setup.get('entry_confirmed') is True),
        ('time', 'មានពេលវេលារូបក្រាហ្វច្បាស់លាស់', setup.get('chart_time_known') is True),
        ('levels', 'មានតម្លៃចូល SL និង TP សម្រាប់ setup ដូចគ្នា', bool(ordered)),
        ('reward_risk', 'សមាមាត្រគោលដៅធៀបហានិភ័យយ៉ាងតិច 1.5', rr is not None and rr >= MIN_REWARD_RISK),
        ('history', 'អត្រាឈ្នះប្រវត្តិឆ្លងតម្រង ' + str(minimum_rate) + '%', history['available'] and history['win_rate'] >= minimum_rate),
        ('sample', 'ប្រតិបត្តិការបិទយ៉ាងតិច ' + str(minimum_trades), history['available'] and history['closed_trades'] >= minimum_trades),
        ('profit_factor', 'Profit factor លើស 1', history['profit_factor'] is not None and history['profit_factor'] > 1),
        ('review', 'លទ្ធផលវិភាគស្របគ្នា', review.get('verdict') == 'SETUP_CONSISTENT'),
        ('proposed', 'ស្របនឹងទិសដៅដែលអ្នកជ្រើស', proposed == 'UNDECIDED' or side == proposed),
    ]
    action = side if all(passed for _, _, passed in checks) else 'WAIT'
    return {'signal': action, 'bias': side if side in ('BUY', 'SELL', 'MIXED') else 'UNKNOWN',
            'basis': 'screenshot', 'win_probability': None,
            'entry_price': entry if action != 'WAIT' else None,
            'stop_loss': stop if action != 'WAIT' else None,
            'take_profit': target if action != 'WAIT' else None,
            'reward_risk': round(rr, 2) if rr is not None else None,
            'checks': [{'key': key, 'label_km': label, 'passed': bool(passed)} for key, label, passed in checks],
            'historical_stats': history, 'filters': {'min_win_rate': minimum_rate, 'min_closed_trades': minimum_trades}}
