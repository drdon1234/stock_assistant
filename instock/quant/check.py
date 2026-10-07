"""运行前静态检查聚宽策略：语法、入口函数、不支持的 API、缺少的第三方库、分钟级参数与定时时刻的近似。"""
import ast
import importlib.util

from instock.quant import engine
from instock.quant.jqapi import UNSUPPORTED, UNSUPPORTED_OBJECTS

_JQ_ONLY_MODULES = {'jqlib': '聚宽技术指标库 jqlib', 'jqfactor': '聚宽因子库 jqfactor', 'jqdatasdk': 'jqdatasdk',
                    'kuanke.wizard': '聚宽向导函数库'}
_PROVIDED = {'jqdata', 'kuanke', 'kuanke.user_space_api'}
_FREQ_ARGS = {'get_price': ('frequency', 3), 'history': ('unit', 1), 'attribute_history': ('unit', 2),
              'get_bars': ('unit', 2)}
_DAILY = {'daily', '1d', 'day', 'd'}
_MINUTE = {'1m', 'minute', '5m', '15m', '30m', '60m', '120m'}


def _literal(node):
    try:
        return ast.literal_eval(node)
    except (ValueError, TypeError, SyntaxError, MemoryError, RecursionError):
        return None


def _arg(call, name, pos):
    for kw in call.keywords:
        if kw.arg == name:
            return kw.value
    return call.args[pos] if len(call.args) > pos else None


def check(code):
    """返回 {'errors': [...], 'warnings': [...], 'notes': [...]}，每项为 {'line', 'message'}。errors 非空时不能运行。"""
    errors, warnings, notes = [], [], []
    try:
        tree = ast.parse(code, '<strategy>')
    except SyntaxError as e:
        errors.append({'line': e.lineno, 'message': f'语法错误：{e.msg}'})
        return {'errors': errors, 'warnings': warnings, 'notes': notes}
    defined = {n.name for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
    if 'initialize' not in defined:
        errors.append({'line': None, 'message': '缺少 initialize(context) 函数'})
    seen = set()

    def warn(node, message, bucket=warnings):
        key = (getattr(node, 'lineno', None), message)
        if key not in seen:
            seen.add(key)
            bucket.append({'line': getattr(node, 'lineno', None), 'message': message})

    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module or '']
            for name in names:
                top = name.split('.')[0]
                if name in _PROVIDED or top in ('jqdata',):
                    continue
                label = _JQ_ONLY_MODULES.get(name) or _JQ_ONLY_MODULES.get(top)
                if label:
                    warn(node, f'不支持 {label}，导入会失败')
                elif top and importlib.util.find_spec(top) is None:
                    warn(node, f'回测环境没有安装 {top}，导入会失败')
        elif isinstance(node, ast.Name) and node.id in UNSUPPORTED and node.id not in defined:
            warn(node, f'{node.id}：{UNSUPPORTED[node.id]}，运行到这里会报错')
        elif isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) \
                and node.value.id in UNSUPPORTED_OBJECTS and node.value.id not in defined:
            warn(node, f'{node.value.id}.{node.attr}：没有聚宽财务/扩展数据库，运行到这里会报错')
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            fn = node.func.id
            if fn in _FREQ_ARGS:
                value = _literal(_arg(node, *_FREQ_ARGS[fn]) or ast.Constant(None))
                if isinstance(value, str) and value.lower() in _MINUTE:
                    warn(node, f'{fn} 使用了 {value} 分钟线：需要服务器已同步分钟数据（没有的日期会缺失）', notes)
                elif isinstance(value, str) and value.lower() not in _DAILY:
                    warn(node, f'{fn} 使用了 {value} 周期，只支持日线与 1m/5m/15m/30m/60m/120m，运行到这里会报错')
            elif fn == 'run_daily' or fn in ('run_weekly', 'run_monthly'):
                pos = 1 if fn == 'run_daily' else 2
                value = _literal(_arg(node, 'time', pos) or ast.Constant('9:30'))
                if isinstance(value, str):
                    try:
                        minute = engine.parse_time(value)
                    except engine.StrategyError as e:
                        warn(node, str(e))
                        continue
                    if minute not in (engine.BEFORE_OPEN, engine.OPEN, engine.CLOSE, engine.AFTER_CLOSE)                             and value.strip().lower() != 'every_bar':
                        price = '开盘价' if minute < engine.NOON else '收盘价'
                        warn(node, f'{fn} 的时间 {value}：按该分钟的收盘价撮合；没有分钟数据的日期按当天{price}近似', notes)
    return {'errors': errors, 'warnings': warnings, 'notes': notes}
