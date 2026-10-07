import datetime

import numpy as np
import pandas as pd
import sqlalchemy as sa

from instock import db, schema
from instock.analysis.bars import Bars
from instock.analysis.backtest import forward_returns

from conftest import make_bars


def test_records_coerce_types():
    df = pd.DataFrame({
        'date': ['2026-09-30'], 'code': ['000001'], 'name': ['平安银行' * 10], 'new_price': ['11.57'],
        'volume': [1234.6], 'listing_date': [19910403], 'pe9': [np.nan], 'industry': [None],
    })
    row = db.records(schema.STOCK_SPOT, df)[0]
    assert row['date'] == datetime.date(2026, 9, 30)
    assert row['listing_date'] == datetime.date(1991, 4, 3)
    assert row['pe9'] is None and row['industry'] is None
    assert row['new_price'] == 11.57 and row['volume'] == 1235
    assert len(row['name']) == 20


def test_records_bool_and_dedup():
    df = pd.DataFrame({'date': ['2026-09-30'] * 3, 'code': ['000001', '000001', None],
                       'macd_golden_fork': ['是', '否', '是']})
    rows = db.records(schema.SELECTION, df)
    assert len(rows) == 1 and rows[0]['macd_golden_fork'] is False


def test_replace_is_idempotent():
    db.init()
    df = pd.DataFrame({'date': ['2026-09-30', '2026-09-30'], 'code': ['000001', '000002'], 'new_price': [1, 2]})
    db.replace(schema.STOCK_SPOT, df, date=datetime.date(2026, 9, 30))
    db.replace(schema.STOCK_SPOT, df, date=datetime.date(2026, 9, 30))
    assert db.scalar('SELECT COUNT(*) FROM cn_stock_spot WHERE date = :d', d=datetime.date(2026, 9, 30)) == 2


def test_init_adds_missing_columns():
    eng = db.engine()
    with eng.begin() as conn:
        conn.execute(sa.text('DROP TABLE IF EXISTS cn_market_return'))
        conn.execute(sa.text('CREATE TABLE cn_market_return (date DATE PRIMARY KEY)'))
    db.init()
    columns = {c['name'] for c in sa.inspect(eng).get_columns('cn_market_return')}
    assert {'stocks', 'ret_60'} <= columns


def test_forward_returns_enter_next_open():
    close = np.arange(10, 80, dtype=float)
    b = Bars(make_bars(close, spread=0.0))
    r = forward_returns(b, 0)
    entry = b.open[1]
    assert r['ret_1'] == round((b.close[1] / entry - 1) * 100, 4)
    assert r['ret_60'] == round((b.close[60] / entry - 1) * 100, 4)
    assert forward_returns(b, len(b) - 1)['ret_1'] is None
