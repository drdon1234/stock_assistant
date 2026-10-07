import datetime

import pandas as pd
import pytest

from instock import history

from conftest import make_bars


def _spot(day, close, pre_close, after_close=True):
    df = pd.DataFrame([{'date': day, 'code': '000001', 'open_price': pre_close, 'high_price': close * 1.01,
                        'low_price': pre_close * 0.99, 'new_price': close, 'pre_close_price': pre_close,
                        'volume': 1000.0, 'deal_amount': 1e6, 'turnoverrate': 0.5}])
    hour = 16 if after_close else 11
    df.attrs['fetched_at'] = datetime.datetime.combine(day, datetime.time(hour))
    return df


@pytest.fixture
def cached(calendar):
    df = make_bars([10.0] * 500, start=datetime.date(2024, 1, 1))
    df.attrs['start'] = datetime.date(2023, 1, 1)
    history._save('000001', df)
    last = df['date'].iloc[-1].date()
    return df, last, calendar


def test_append_from_closing_spot(cached, monkeypatch):
    df, last, cal = cached
    monkeypatch.setattr(history, 'refresh', lambda *a, **k: pytest.fail('不应重新抓取'))
    day = [d for d in cal.between(last, last + datetime.timedelta(days=7)) if d > last][0]
    history.ensure(['000001'], day, _spot(day, 10.5, 10.0))
    saved = history.load('000001')
    assert len(saved) == len(df) + 1
    assert saved['date'].iloc[-1].date() == day
    assert saved['volume'].iloc[-1] == 1000.0 * 100  # 手 -> 股
    assert saved.attrs['start'] == datetime.date(2023, 1, 1)


@pytest.mark.parametrize('pre_close, after_close', [(9.5, True), (10.0, False)])
def test_refetch_on_ex_rights_or_intraday_spot(cached, monkeypatch, pre_close, after_close):
    _, last, cal = cached
    calls = []
    monkeypatch.setattr(history, 'refresh', lambda code, as_of: calls.append(code))
    day = [d for d in cal.between(last, last + datetime.timedelta(days=7)) if d > last][0]
    history.ensure(['000001'], day, _spot(day, 10.5, pre_close, after_close))
    assert calls == ['000001']


def test_new_listing_is_covered_by_fetch_start(cached, monkeypatch):
    df, last, _ = cached
    young = df.tail(30).reset_index(drop=True)
    young.attrs['start'] = last - datetime.timedelta(days=1000)
    history._save('000002', young)
    monkeypatch.setattr(history, 'refresh', lambda *a, **k: pytest.fail('次新股不应反复重抓'))
    history.ensure(['000002'], last, earliest=last - datetime.timedelta(days=20))
