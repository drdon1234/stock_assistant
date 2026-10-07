"""数据字典：所有数据表的列定义、中文名和前端显示格式，是建表、入库、接口元数据的唯一来源。

显示格式 fmt：code 代码，text 文本，price 价格，pct 涨跌类百分数(红涨绿跌)，percent 普通百分数，num 普通数值，int 整数，
money 金额(元)，vol 成交量(手)，share 股数(股)，date 日期，bool 是否，signal 形态信号(±100)。
"""
from dataclasses import dataclass

import sqlalchemy as sa

from instock.analysis.indicators import INDICATORS
from instock.analysis.patterns import PATTERNS


@dataclass(frozen=True)
class Col:
    name: str
    type: object
    label: str
    fmt: str
    src: str = None  # 数据源字段名（综合选股）


@dataclass(frozen=True)
class TableSpec:
    name: str
    label: str
    cols: tuple
    key: tuple = ('date', 'code')
    group: str = None  # 菜单分组，None 表示不作为通用数据表展示
    sort: tuple = None  # 默认排序 (列名, 是否降序)

    @property
    def names(self):
        return [c.name for c in self.cols]


_KINDS = {'F': (sa.Float, 'num'), 'B': (sa.BigInteger, 'num'), 'I': (sa.SmallInteger, 'int'),
          'Y': (sa.Boolean, 'bool'), 'D': (sa.Date, 'date'), 'T': (sa.DateTime, 'datetime')}


def c(name, kind, label, fmt=None, src=None):
    """kind：F 浮点，B 长整数，I 小整数，Y 布尔，D 日期，T 日期时间，Sn 长度为 n 的字符串。"""
    if kind[0] == 'S':
        return Col(name, sa.String(int(kind[1:])), label, fmt or 'text', src)
    sa_type, default_fmt = _KINDS[kind]
    return Col(name, sa_type(), label, fmt or default_fmt, src)


DATE = c('date', 'D', '日期')
CODE = c('code', 'S6', '代码', 'code')
NAME = c('name', 'S20', '名称')
PRICE = c('new_price', 'F', '最新价', 'price')
CHANGE = c('change_rate', 'F', '涨跌幅', 'pct')


def _price(name, label):
    return c(name, 'F', label, 'price')


def _pct(name, label):
    return c(name, 'F', label, 'pct')


def _percent(name, label):
    return c(name, 'F', label, 'percent')


def _money(name, label):
    return c(name, 'B', label, 'money')


USERNAME = c('username', 'S32', '账号')

USER = TableSpec('instock_user', '账号', (
    USERNAME, c('password', 'S200', '密码哈希'), c('is_admin', 'Y', '管理员'), c('created_at', 'T', '创建时间')),
    key=('username',))

# 登录凭证：token 为凭证的 SHA-256，库中不保存凭证原文
SESSION = TableSpec('instock_session', '登录凭证', (
    c('token', 'S64', '凭证哈希'), USERNAME, c('created_at', 'T', '登录时间'), c('last_used', 'T', '最近使用'),
    c('expires_at', 'T', '过期时间'), c('user_agent', 'S200', '浏览器'), c('ip', 'S64', 'IP')),
    key=('token',))

# 每个账号各自的关注列表。旧版不分账号的 cn_stock_attention 在创建第一个账号时迁移给该账号
ATTENTION = TableSpec('cn_stock_user_attention', '我的关注', (
    USERNAME, CODE, c('created_at', 'D', '关注日期')), key=('username', 'code'))
LEGACY_ATTENTION = 'cn_stock_attention'

STOCK_SPOT = TableSpec('cn_stock_spot', '每日股票数据', (
    DATE, CODE, NAME, PRICE, CHANGE, _price('ups_downs', '涨跌额'), c('volume', 'B', '成交量', 'vol'),
    _money('deal_amount', '成交额'), _percent('amplitude', '振幅'), _percent('turnoverrate', '换手率'),
    c('volume_ratio', 'F', '量比'), _price('open_price', '今开'), _price('high_price', '最高'),
    _price('low_price', '最低'), _price('pre_close_price', '昨收'), _pct('speed_increase_60', '60日涨跌幅'),
    _pct('speed_increase_all', '年初至今涨跌幅'), c('dtsyl', 'F', '市盈率(动)'), c('pe9', 'F', '市盈率(TTM)'),
    c('pe', 'F', '市盈率(静)'), c('pbnewmrq', 'F', '市净率'), c('basic_eps', 'F', '每股收益'),
    c('bvps', 'F', '每股净资产'), c('per_capital_reserve', 'F', '每股公积金'),
    c('per_unassign_profit', 'F', '每股未分配利润'), _percent('roe_weight', '加权ROE'), _percent('sale_gpr', '毛利率'),
    _percent('debt_asset_ratio', '资产负债率'), _money('total_operate_income', '营业收入'),
    _pct('toi_yoy_ratio', '营收同比'), _money('parent_netprofit', '归属净利润'),
    _pct('netprofit_yoy_ratio', '净利润同比'),
    c('total_shares', 'B', '总股本', 'share'), c('free_shares', 'B', '流通股本', 'share'),
    _money('total_market_cap', '总市值'), _money('free_cap', '流通市值'), c('industry', 'S20', '所处行业'),
    c('listing_date', 'D', '上市时间')),
    group='行情', sort=('change_rate', True))

ETF_SPOT = TableSpec('cn_etf_spot', '每日ETF数据', (
    DATE, CODE, c('name', 'S40', '名称'), PRICE, CHANGE, _price('ups_downs', '涨跌额'),
    c('volume', 'B', '成交量', 'vol'), _money('deal_amount', '成交额'), _price('open_price', '开盘价'),
    _price('high_price', '最高价'), _price('low_price', '最低价'), _price('pre_close_price', '昨收'),
    _percent('turnoverrate', '换手率'), _money('total_market_cap', '总市值'), _money('free_cap', '流通市值')),
    group='行情', sort=('deal_amount', True))

_SELECTION_FIELDS = (
    ('new_price', 'F', '最新价', 'NEW_PRICE'),
    ('change_rate', 'F', '涨跌幅', 'CHANGE_RATE'),
    ('volume_ratio', 'F', '量比', 'VOLUME_RATIO'),
    ('high_price', 'F', '最高价', 'HIGH_PRICE'),
    ('low_price', 'F', '最低价', 'LOW_PRICE'),
    ('pre_close_price', 'F', '昨收价', 'PRE_CLOSE_PRICE'),
    ('volume', 'B', '成交量', 'VOLUME'),
    ('deal_amount', 'B', '成交额', 'DEAL_AMOUNT'),
    ('turnoverrate', 'F', '换手率', 'TURNOVERRATE'),
    ('listing_date', 'D', '上市时间', 'LISTING_DATE'),
    ('industry', 'S50', '行业', 'INDUSTRY'),
    ('area', 'S50', '地区', 'AREA'),
    ('concept', 'S800', '概念', 'CONCEPT'),
    ('style', 'S255', '板块', 'STYLE'),
    ('is_hs300', 'S2', '沪300', 'IS_HS300'),
    ('is_sz50', 'S2', '上证50', 'IS_SZ50'),
    ('is_zz500', 'S2', '中证500', 'IS_ZZ500'),
    ('is_zz1000', 'S2', '中证1000', 'IS_ZZ1000'),
    ('is_cy50', 'S2', '创业板50', 'IS_CY50'),
    ('pe9', 'F', '市盈率TTM', 'PE9'),
    ('pbnewmrq', 'F', '市净率MRQ', 'PBNEWMRQ'),
    ('pettmdeducted', 'F', '市盈率TTM扣非', 'PETTMDEDUCTED'),
    ('ps9', 'F', '市销率TTM', 'PS9'),
    ('pcfjyxjl9', 'F', '市现率TTM', 'PCFJYXJL9'),
    ('predict_pe_syear', 'F', '预测市盈率今年', 'PREDICT_PE_SYEAR'),
    ('predict_pe_nyear', 'F', '预测市盈率明年', 'PREDICT_PE_NYEAR'),
    ('total_market_cap', 'B', '总市值', 'TOTAL_MARKET_CAP'),
    ('free_cap', 'B', '流通市值', 'FREE_CAP'),
    ('dtsyl', 'F', '动态市盈率', 'DTSYL'),
    ('ycpeg', 'F', '预测PEG', 'YCPEG'),
    ('enterprise_value_multiple', 'F', '企业价值倍数', 'ENTERPRISE_VALUE_MULTIPLE'),
    ('basic_eps', 'F', '每股收益', 'BASIC_EPS'),
    ('bvps', 'F', '每股净资产', 'BVPS'),
    ('per_netcash_operate', 'F', '每股经营现金流', 'PER_NETCASH_OPERATE'),
    ('per_fcfe', 'F', '每股自由现金流', 'PER_FCFE'),
    ('per_capital_reserve', 'F', '每股资本公积', 'PER_CAPITAL_RESERVE'),
    ('per_unassign_profit', 'F', '每股未分配利润', 'PER_UNASSIGN_PROFIT'),
    ('per_surplus_reserve', 'F', '每股盈余公积', 'PER_SURPLUS_RESERVE'),
    ('per_retained_earning', 'F', '每股留存收益', 'PER_RETAINED_EARNING'),
    ('parent_netprofit', 'B', '归属净利润', 'PARENT_NETPROFIT'),
    ('deduct_netprofit', 'B', '扣非净利润', 'DEDUCT_NETPROFIT'),
    ('total_operate_income', 'B', '营业总收入', 'TOTAL_OPERATE_INCOME'),
    ('roe_weight', 'F', '净资产收益率ROE', 'ROE_WEIGHT'),
    ('jroa', 'F', '总资产净利率ROA', 'JROA'),
    ('roic', 'F', '投入资本回报率ROIC', 'ROIC'),
    ('zxgxl', 'F', '最新股息率', 'ZXGXL'),
    ('sale_gpr', 'F', '毛利率', 'SALE_GPR'),
    ('sale_npr', 'F', '净利率', 'SALE_NPR'),
    ('netprofit_yoy_ratio', 'F', '净利润增长率', 'NETPROFIT_YOY_RATIO'),
    ('deduct_netprofit_growthrate', 'F', '扣非净利润增长率', 'DEDUCT_NETPROFIT_GROWTHRATE'),
    ('toi_yoy_ratio', 'F', '营收增长率', 'TOI_YOY_RATIO'),
    ('netprofit_growthrate_3y', 'F', '净利润3年复合增长率', 'NETPROFIT_GROWTHRATE_3Y'),
    ('income_growthrate_3y', 'F', '营收3年复合增长率', 'INCOME_GROWTHRATE_3Y'),
    ('predict_netprofit_ratio', 'F', '预测净利润同比增长', 'PREDICT_NETPROFIT_RATIO'),
    ('predict_income_ratio', 'F', '预测营收同比增长', 'PREDICT_INCOME_RATIO'),
    ('basiceps_yoy_ratio', 'F', '每股收益同比增长率', 'BASICEPS_YOY_RATIO'),
    ('total_profit_growthrate', 'F', '利润总额同比增长率', 'TOTAL_PROFIT_GROWTHRATE'),
    ('operate_profit_growthrate', 'F', '营业利润同比增长率', 'OPERATE_PROFIT_GROWTHRATE'),
    ('debt_asset_ratio', 'F', '资产负债率', 'DEBT_ASSET_RATIO'),
    ('equity_ratio', 'F', '产权比率', 'EQUITY_RATIO'),
    ('equity_multiplier', 'F', '权益乘数', 'EQUITY_MULTIPLIER'),
    ('current_ratio', 'F', '流动比率', 'CURRENT_RATIO'),
    ('speed_ratio', 'F', '速动比率', 'SPEED_RATIO'),
    ('total_shares', 'B', '总股本', 'TOTAL_SHARES'),
    ('free_shares', 'B', '流通股本', 'FREE_SHARES'),
    ('holder_newest', 'B', '最新股东户数', 'HOLDER_NEWEST'),
    ('holder_ratio', 'F', '股东户数增长率', 'HOLDER_RATIO'),
    ('hold_amount', 'F', '户均持股金额', 'HOLD_AMOUNT'),
    ('avg_hold_num', 'F', '户均持股数量', 'AVG_HOLD_NUM'),
    ('holdnum_growthrate_3q', 'F', '户均持股数季度增长率', 'HOLDNUM_GROWTHRATE_3Q'),
    ('holdnum_growthrate_hy', 'F', '户均持股数半年增长率', 'HOLDNUM_GROWTHRATE_HY'),
    ('hold_ratio_count', 'F', '十大股东持股比例合计', 'HOLD_RATIO_COUNT'),
    ('free_hold_ratio', 'F', '十大流通股东比例合计', 'FREE_HOLD_RATIO'),
    ('macd_golden_fork', 'Y', 'MACD金叉日线', 'MACD_GOLDEN_FORK'),
    ('macd_golden_forkz', 'Y', 'MACD金叉周线', 'MACD_GOLDEN_FORKZ'),
    ('macd_golden_forky', 'Y', 'MACD金叉月线', 'MACD_GOLDEN_FORKY'),
    ('kdj_golden_fork', 'Y', 'KDJ金叉日线', 'KDJ_GOLDEN_FORK'),
    ('kdj_golden_forkz', 'Y', 'KDJ金叉周线', 'KDJ_GOLDEN_FORKZ'),
    ('kdj_golden_forky', 'Y', 'KDJ金叉月线', 'KDJ_GOLDEN_FORKY'),
    ('break_through', 'Y', '放量突破', 'BREAK_THROUGH'),
    ('low_funds_inflow', 'Y', '低位资金净流入', 'LOW_FUNDS_INFLOW'),
    ('high_funds_outflow', 'Y', '高位资金净流出', 'HIGH_FUNDS_OUTFLOW'),
    ('breakup_ma_5days', 'Y', '向上突破均线5日', 'BREAKUP_MA_5DAYS'),
    ('breakup_ma_10days', 'Y', '向上突破均线10日', 'BREAKUP_MA_10DAYS'),
    ('breakup_ma_20days', 'Y', '向上突破均线20日', 'BREAKUP_MA_20DAYS'),
    ('breakup_ma_30days', 'Y', '向上突破均线30日', 'BREAKUP_MA_30DAYS'),
    ('breakup_ma_60days', 'Y', '向上突破均线60日', 'BREAKUP_MA_60DAYS'),
    ('long_avg_array', 'Y', '均线多头排列', 'LONG_AVG_ARRAY'),
    ('short_avg_array', 'Y', '均线空头排列', 'SHORT_AVG_ARRAY'),
    ('upper_large_volume', 'Y', '连涨放量', 'UPPER_LARGE_VOLUME'),
    ('down_narrow_volume', 'Y', '下跌无量', 'DOWN_NARROW_VOLUME'),
    ('one_dayang_line', 'Y', '一根大阳线', 'ONE_DAYANG_LINE'),
    ('two_dayang_lines', 'Y', '两根大阳线', 'TWO_DAYANG_LINES'),
    ('rise_sun', 'Y', '旭日东升', 'RISE_SUN'),
    ('power_fulgun', 'Y', '强势多方炮', 'POWER_FULGUN'),
    ('restore_justice', 'Y', '拨云见日', 'RESTORE_JUSTICE'),
    ('down_7days', 'Y', '七仙女下凡(七连阴)', 'DOWN_7DAYS'),
    ('upper_8days', 'Y', '八仙过海(八连阳)', 'UPPER_8DAYS'),
    ('upper_9days', 'Y', '九阳神功(九连阳)', 'UPPER_9DAYS'),
    ('upper_4days', 'Y', '四串阳', 'UPPER_4DAYS'),
    ('heaven_rule', 'Y', '天量法则', 'HEAVEN_RULE'),
    ('upside_volume', 'Y', '放量上攻', 'UPSIDE_VOLUME'),
    ('bearish_engulfing', 'Y', '穿头破脚', 'BEARISH_ENGULFING'),
    ('reversing_hammer', 'Y', '倒转锤头', 'REVERSING_HAMMER'),
    ('shooting_star', 'Y', '射击之星', 'SHOOTING_STAR'),
    ('evening_star', 'Y', '黄昏之星', 'EVENING_STAR'),
    ('first_dawn', 'Y', '曙光初现', 'FIRST_DAWN'),
    ('pregnant', 'Y', '身怀六甲', 'PREGNANT'),
    ('black_cloud_tops', 'Y', '乌云盖顶', 'BLACK_CLOUD_TOPS'),
    ('morning_star', 'Y', '早晨之星', 'MORNING_STAR'),
    ('narrow_finish', 'Y', '窄幅整理', 'NARROW_FINISH'),
    ('limited_lift_f6m', 'Y', '限售解禁未来半年', 'LIMITED_LIFT_F6M'),
    ('limited_lift_f1y', 'Y', '限售解禁未来1年', 'LIMITED_LIFT_F1Y'),
    ('limited_lift_6m', 'Y', '限售解禁近半年', 'LIMITED_LIFT_6M'),
    ('limited_lift_1y', 'Y', '限售解禁近1年', 'LIMITED_LIFT_1Y'),
    ('directional_seo_1m', 'Y', '定向增发近1个月', 'DIRECTIONAL_SEO_1M'),
    ('directional_seo_3m', 'Y', '定向增发近3个月', 'DIRECTIONAL_SEO_3M'),
    ('directional_seo_6m', 'Y', '定向增发近6个月', 'DIRECTIONAL_SEO_6M'),
    ('directional_seo_1y', 'Y', '定向增发近1年', 'DIRECTIONAL_SEO_1Y'),
    ('recapitalize_1m', 'Y', '资产重组近1个月', 'RECAPITALIZE_1M'),
    ('recapitalize_3m', 'Y', '资产重组近3个月', 'RECAPITALIZE_3M'),
    ('recapitalize_6m', 'Y', '资产重组近6个月', 'RECAPITALIZE_6M'),
    ('recapitalize_1y', 'Y', '资产重组近1年', 'RECAPITALIZE_1Y'),
    ('equity_pledge_1m', 'Y', '股权质押近1个月', 'EQUITY_PLEDGE_1M'),
    ('equity_pledge_3m', 'Y', '股权质押近3个月', 'EQUITY_PLEDGE_3M'),
    ('equity_pledge_6m', 'Y', '股权质押近6个月', 'EQUITY_PLEDGE_6M'),
    ('equity_pledge_1y', 'Y', '股权质押近1年', 'EQUITY_PLEDGE_1Y'),
    ('pledge_ratio', 'F', '质押比例', 'PLEDGE_RATIO'),
    ('goodwill_scale', 'B', '商誉规模', 'GOODWILL_SCALE'),
    ('goodwill_assets_ratro', 'F', '商誉占净资产比例', 'GOODWILL_ASSETS_RATRO'),
    ('predict_type', 'S10', '业绩预告', 'PREDICT_TYPE'),
    ('par_dividend_pretax', 'F', '每股股利税前', 'PAR_DIVIDEND_PRETAX'),
    ('par_dividend', 'F', '每股红股', 'PAR_DIVIDEND'),
    ('par_it_equity', 'F', '每股转增股本', 'PAR_IT_EQUITY'),
    ('holder_change_3m', 'F', '近3月股东增减比例', 'HOLDER_CHANGE_3M'),
    ('executive_change_3m', 'F', '近3月高管增减比例', 'EXECUTIVE_CHANGE_3M'),
    ('org_survey_3m', 'I', '近3月机构调研', 'ORG_SURVEY_3M'),
    ('org_rating', 'S10', '机构评级', 'ORG_RATING'),
    ('allcorp_num', 'I', '机构持股家数合计', 'ALLCORP_NUM'),
    ('allcorp_fund_num', 'I', '基金持股家数', 'ALLCORP_FUND_NUM'),
    ('allcorp_qs_num', 'I', '券商持股家数', 'ALLCORP_QS_NUM'),
    ('allcorp_qfii_num', 'I', 'QFII持股家数', 'ALLCORP_QFII_NUM'),
    ('allcorp_bx_num', 'I', '保险公司持股家数', 'ALLCORP_BX_NUM'),
    ('allcorp_sb_num', 'I', '社保持股家数', 'ALLCORP_SB_NUM'),
    ('allcorp_xt_num', 'I', '信托公司持股家数', 'ALLCORP_XT_NUM'),
    ('allcorp_ratio', 'F', '机构持股比例合计', 'ALLCORP_RATIO'),
    ('allcorp_fund_ratio', 'F', '基金持股比例', 'ALLCORP_FUND_RATIO'),
    ('allcorp_qs_ratio', 'F', '券商持股比例', 'ALLCORP_QS_RATIO'),
    ('allcorp_qfii_ratio', 'F', 'QFII持股比例', 'ALLCORP_QFII_RATIO'),
    ('allcorp_bx_ratio', 'F', '保险公司持股比例', 'ALLCORP_BX_RATIO'),
    ('allcorp_sb_ratio', 'F', '社保持股比例', 'ALLCORP_SB_RATIO'),
    ('allcorp_xt_ratio', 'F', '信托公司持股比例', 'ALLCORP_XT_RATIO'),
    ('popularity_rank', 'I', '股吧人气排名', 'POPULARITY_RANK'),
    ('rank_change', 'I', '人气排名变化', 'RANK_CHANGE'),
    ('upp_days', 'I', '人气排名连涨', 'UPP_DAYS'),
    ('down_days', 'I', '人气排名连跌', 'DOWN_DAYS'),
    ('new_high', 'I', '人气排名创新高', 'NEW_HIGH'),
    ('new_down', 'I', '人气排名创新低', 'NEW_DOWN'),
    ('newfans_ratio', 'F', '新晋粉丝占比', 'NEWFANS_RATIO'),
    ('bigfans_ratio', 'F', '铁杆粉丝占比', 'BIGFANS_RATIO'),
    ('concern_rank_7days', 'I', '7日关注排名', 'CONCERN_RANK_7DAYS'),
    ('browse_rank', 'I', '今日浏览排名', 'BROWSE_RANK'),
    ('amplitude', 'F', '振幅', 'AMPLITUDE'),
    ('is_issue_break', 'Y', '破发股票', 'IS_ISSUE_BREAK'),
    ('is_bps_break', 'Y', '破净股票', 'IS_BPS_BREAK'),
    ('now_newhigh', 'Y', '今日创历史新高', 'NOW_NEWHIGH'),
    ('now_newlow', 'Y', '今日创历史新低', 'NOW_NEWLOW'),
    ('high_recent_3days', 'Y', '近期创历史新高近3日', 'HIGH_RECENT_3DAYS'),
    ('high_recent_5days', 'Y', '近期创历史新高近5日', 'HIGH_RECENT_5DAYS'),
    ('high_recent_10days', 'Y', '近期创历史新高近10日', 'HIGH_RECENT_10DAYS'),
    ('high_recent_20days', 'Y', '近期创历史新高近20日', 'HIGH_RECENT_20DAYS'),
    ('high_recent_30days', 'Y', '近期创历史新高近30日', 'HIGH_RECENT_30DAYS'),
    ('low_recent_3days', 'Y', '近期创历史新低近3日', 'LOW_RECENT_3DAYS'),
    ('low_recent_5days', 'Y', '近期创历史新低近5日', 'LOW_RECENT_5DAYS'),
    ('low_recent_10days', 'Y', '近期创历史新低近10日', 'LOW_RECENT_10DAYS'),
    ('low_recent_20days', 'Y', '近期创历史新低近20日', 'LOW_RECENT_20DAYS'),
    ('low_recent_30days', 'Y', '近期创历史新低近30日', 'LOW_RECENT_30DAYS'),
    ('win_market_3days', 'Y', '近期跑赢大盘近3日', 'WIN_MARKET_3DAYS'),
    ('win_market_5days', 'Y', '近期跑赢大盘近5日', 'WIN_MARKET_5DAYS'),
    ('win_market_10days', 'Y', '近期跑赢大盘近10日', 'WIN_MARKET_10DAYS'),
    ('win_market_20days', 'Y', '近期跑赢大盘近20日', 'WIN_MARKET_20DAYS'),
    ('win_market_30days', 'Y', '近期跑赢大盘近30日', 'WIN_MARKET_30DAYS'),
    ('net_inflow', 'F', '当日净流入额', 'NET_INFLOW'),
    ('netinflow_3days', 'B', '3日主力净流入', 'NETINFLOW_3DAYS'),
    ('netinflow_5days', 'B', '5日主力净流入', 'NETINFLOW_5DAYS'),
    ('nowinterst_ratio', 'F', '当日增仓占比', 'NOWINTERST_RATIO'),
    ('nowinterst_ratio_3d', 'F', '3日增仓占比', 'NOWINTERST_RATIO_3D'),
    ('nowinterst_ratio_5d', 'F', '5日增仓占比', 'NOWINTERST_RATIO_5D'),
    ('ddx', 'F', '当日DDX', 'DDX'),
    ('ddx_3d', 'F', '3日DDX', 'DDX_3D'),
    ('ddx_5d', 'F', '5日DDX', 'DDX_5D'),
    ('ddx_red_10d', 'I', '10日内DDX飘红天数', 'DDX_RED_10D'),
    ('changerate_3days', 'F', '3日涨跌幅', 'CHANGERATE_3DAYS'),
    ('changerate_5days', 'F', '5日涨跌幅', 'CHANGERATE_5DAYS'),
    ('changerate_10days', 'F', '10日涨跌幅', 'CHANGERATE_10DAYS'),
    ('changerate_ty', 'F', '今年以来涨跌幅', 'CHANGERATE_TY'),
    ('upnday', 'I', '连涨天数', 'UPNDAY'),
    ('downnday', 'I', '连跌天数', 'DOWNNDAY'),
    ('listing_yield_year', 'F', '上市以来年化收益率', 'LISTING_YIELD_YEAR'),
    ('listing_volatility_year', 'F', '上市以来年化波动率', 'LISTING_VOLATILITY_YEAR'),
    ('mutual_netbuy_amt', 'B', '沪深股通净买入金额', 'MUTUAL_NETBUY_AMT'),
    ('hold_ratio', 'F', '沪深股通持股比例', 'HOLD_RATIO'),
)

_SELECTION_FMT = {
    'pct': {'changerate_3days', 'changerate_5days', 'changerate_10days', 'changerate_ty'},
    'percent': {'turnoverrate', 'amplitude', 'roe_weight', 'jroa', 'roic', 'zxgxl', 'sale_gpr', 'sale_npr',
                'netprofit_yoy_ratio', 'deduct_netprofit_growthrate', 'toi_yoy_ratio', 'netprofit_growthrate_3y',
                'income_growthrate_3y', 'predict_netprofit_ratio', 'predict_income_ratio', 'basiceps_yoy_ratio',
                'total_profit_growthrate', 'operate_profit_growthrate', 'debt_asset_ratio', 'holder_ratio',
                'holdnum_growthrate_3q', 'holdnum_growthrate_hy', 'hold_ratio_count', 'free_hold_ratio',
                'pledge_ratio', 'goodwill_assets_ratro', 'holder_change_3m', 'executive_change_3m',
                'allcorp_ratio', 'allcorp_fund_ratio', 'allcorp_qs_ratio', 'allcorp_qfii_ratio', 'allcorp_bx_ratio',
                'allcorp_sb_ratio', 'allcorp_xt_ratio', 'newfans_ratio', 'bigfans_ratio', 'nowinterst_ratio',
                'nowinterst_ratio_3d', 'nowinterst_ratio_5d', 'listing_yield_year', 'listing_volatility_year',
                'hold_ratio'},
    'money': {'deal_amount', 'total_market_cap', 'free_cap', 'parent_netprofit', 'deduct_netprofit',
              'total_operate_income', 'hold_amount', 'goodwill_scale', 'net_inflow', 'netinflow_3days',
              'netinflow_5days', 'mutual_netbuy_amt'},
    'share': {'total_shares', 'free_shares'},
    'price': {'high_price', 'low_price', 'pre_close_price'},
}


def _selection_col(name, kind, label, src):
    fmt = next((f for f, names in _SELECTION_FMT.items() if name in names), None)
    return c(name, kind, label, fmt, src)


SELECTION = TableSpec('cn_stock_selection', '综合选股', (
    c('date', 'D', '日期', src='MAX_TRADE_DATE'), c('code', 'S6', '代码', 'code', 'SECURITY_CODE'),
    c('name', 'S20', '名称', src='SECURITY_NAME_ABBR'), c('new_price', 'F', '最新价', 'price', 'NEW_PRICE'),
    c('change_rate', 'F', '涨跌幅', 'pct', 'CHANGE_RATE'),
    *(_selection_col(*f) for f in _SELECTION_FIELDS if f[0] not in ('new_price', 'change_rate'))),
    group='行情', sort=('change_rate', True))

_FLOW_KINDS = (('', '主力'), ('_super', '超大单'), ('_large', '大单'), ('_medium', '中单'), ('_small', '小单'))


def _flow_cols(suffix, period):
    cols = [_pct(f'change_rate{suffix}', f'{period}涨跌幅')]
    for kind, label in _FLOW_KINDS:
        cols.append(_money(f'fund_amount{kind}{suffix}', f'{period}{label}净流入'))
        cols.append(_pct(f'fund_rate{kind}{suffix}', f'{period}{label}净占比'))
    return cols


_FLOW_PERIODS = (('', '今日'), ('_3', '3日'), ('_5', '5日'), ('_10', '10日'))

FUND_FLOW = TableSpec('cn_stock_fund_flow', '个股资金流向', (
    DATE, CODE, NAME, PRICE, *(col for s, p in _FLOW_PERIODS for col in _flow_cols(s, p))),
    group='资金', sort=('fund_amount', True))


def _sector_flow(name, label):
    cols = [DATE, c('name', 'S30', '板块')]
    for suffix, period in (('', '今日'), ('_5', '5日'), ('_10', '10日')):
        cols += _flow_cols(suffix, period)
        cols.append(c(f'stock_name{suffix}', 'S20', f'{period}主力净流入最大股'))
    return TableSpec(name, label, tuple(cols), key=('date', 'name'), group='资金', sort=('fund_amount', True))


FUND_FLOW_INDUSTRY = _sector_flow('cn_stock_fund_flow_industry', '行业资金流向')
FUND_FLOW_CONCEPT = _sector_flow('cn_stock_fund_flow_concept', '概念资金流向')

BONUS = TableSpec('cn_stock_bonus', '分红配送', (
    DATE, CODE, NAME, c('plan_profile', 'S100', '分配方案'), c('convertible_total_rate', 'F', '送转总比例(每10股)'),
    c('convertible_rate', 'F', '送股比例(每10股)'), c('convertible_transfer_rate', 'F', '转股比例(每10股)'),
    c('bonusaward_rate', 'F', '现金分红(每10股)'), _percent('bonusaward_yield', '股息率'), c('basic_eps', 'F', '每股收益'),
    c('bvps', 'F', '每股净资产'), c('per_capital_reserve', 'F', '每股公积金'),
    c('per_unassign_profit', 'F', '每股未分配利润'), _pct('netprofit_yoy_ratio', '净利润同比'),
    c('total_shares', 'B', '总股本', 'share'), c('plan_date', 'D', '预案公告日'), c('record_date', 'D', '股权登记日'),
    c('ex_dividend_date', 'D', '除权除息日'), c('progress', 'S50', '方案进度'), c('report_date', 'D', '最新公告日')),
    group='事件', sort=('plan_date', True))

LHB = TableSpec('cn_stock_lhb', '龙虎榜', (
    DATE, CODE, NAME, c('interpret', 'S255', '解读'), _price('new_price', '收盘价'), CHANGE,
    _money('net_amount_buy', '龙虎榜净买额'), _money('sum_buy', '龙虎榜买入额'), _money('sum_sell', '龙虎榜卖出额'),
    _money('lhb_amount', '龙虎榜成交额'), _money('market_amount', '市场总成交额'),
    _pct('net_amount_rate', '净买额占比'), _percent('sum_rate', '成交额占比'), _percent('turnoverrate', '换手率'),
    _money('free_cap', '流通市值'), c('reason', 'S2000', '上榜原因'), _pct('ranking_after_1', '上榜后1日'),
    _pct('ranking_after_2', '上榜后2日'), _pct('ranking_after_5', '上榜后5日'), _pct('ranking_after_10', '上榜后10日')),
    group='事件', sort=('net_amount_buy', True))

BLOCKTRADE = TableSpec('cn_stock_blocktrade', '大宗交易', (
    DATE, CODE, NAME, _price('new_price', '收盘价'), CHANGE, _price('average_price', '成交均价'),
    _pct('overflow_rate', '折溢率'), c('trade_number', 'I', '成交笔数'), c('sum_volume', 'B', '成交总量', 'share'),
    _money('sum_turnover', '成交总额'), _percent('turnover_market_rate', '成交额/流通市值')),
    group='事件', sort=('sum_turnover', True))


def _chip_race(name, label, amount_label):
    return TableSpec(name, label, (
        DATE, CODE, NAME, PRICE, CHANGE, _price('pre_close_price', '昨收'), _price('open_price', '今开'),
        _money('deal_amount', amount_label), _percent('bid_rate', '抢筹幅度'), _money('bid_trust_amount', '抢筹委托金额'),
        _money('bid_deal_amount', '抢筹成交金额'), _percent('bid_ratio', '抢筹占比'), c('limitup_day', 'I', '连板天数'),
        c('limitup_board', 'I', '连板数')), group='事件', sort=('bid_trust_amount', True))


CHIP_RACE_OPEN = _chip_race('cn_stock_chip_race_open', '早盘抢筹', '开盘金额')
CHIP_RACE_END = _chip_race('cn_stock_chip_race_end', '尾盘抢筹', '收盘金额')

LIMITUP_REASON = TableSpec('cn_stock_limitup_reason', '涨停原因', (
    DATE, CODE, NAME, c('title', 'S255', '涨停原因'), c('reason', 'S2000', '详细解读'), PRICE, CHANGE,
    _price('ups_downs', '涨跌额'), _percent('turnoverrate', '换手率'), c('volume', 'B', '成交量', 'vol'),
    _money('deal_amount', '成交额'), c('dde', 'F', 'DDE净量')),
    group='事件', sort=('deal_amount', True))

INDICATOR = TableSpec('cn_stock_indicators', '技术指标', (
    DATE, CODE, NAME, _price('close', '收盘价'), *(c(k, 'F', label) for k, label in INDICATORS)),
    group='分析')

PATTERN = TableSpec('cn_stock_pattern', 'K线形态', (
    DATE, CODE, NAME, *(c(k, 'I', label, 'signal') for k, label, _ in PATTERNS)),
    group='分析')

RETURN_HORIZONS = (1, 3, 5, 10, 20, 60)

SIGNAL = TableSpec('cn_stock_signal', '策略选股', (
    DATE, c('strategy', 'S30', '策略'), CODE, NAME, _price('close', '信号日收盘价'),
    *(_pct(f'ret_{h}', f'{h}日收益') for h in RETURN_HORIZONS)),
    key=('date', 'strategy', 'code'))

# 回测基准：当日全部 A 股按同样口径（次日开盘买入）计算的等权平均收益
BENCHMARK = TableSpec('cn_market_return', '全市场基准收益', (
    DATE, c('stocks', 'I', '样本数'), *(_pct(f'ret_{h}', f'{h}日收益') for h in RETURN_HORIZONS)),
    key=('date',))

TABLES = {spec.name: spec for spec in (
    STOCK_SPOT, ETF_SPOT, SELECTION, FUND_FLOW, FUND_FLOW_INDUSTRY, FUND_FLOW_CONCEPT, LHB, BLOCKTRADE, BONUS,
    CHIP_RACE_OPEN, CHIP_RACE_END, LIMITUP_REASON, INDICATOR, PATTERN, SIGNAL, BENCHMARK, USER, SESSION, ATTENTION)}

metadata = sa.MetaData()


def _build(spec):
    columns = [sa.Column(col.name, col.type, primary_key=col.name in spec.key) for col in spec.cols]
    return sa.Table(spec.name, metadata, *columns, mysql_charset='utf8mb4', mysql_collate='utf8mb4_general_ci')


SA_TABLES = {name: _build(spec) for name, spec in TABLES.items()}
sa.Index('ix_signal_strategy_date', SA_TABLES[SIGNAL.name].c.strategy, SA_TABLES[SIGNAL.name].c.date)
sa.Index('ix_session_username', SA_TABLES[SESSION.name].c.username)
