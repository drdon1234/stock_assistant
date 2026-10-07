"""在独立子进程中执行一次回测：从标准输入读取 JSON 请求，按行向标准输出写 JSON 消息。

消息：{"type": "progress", "progress": 0.42, "date": "..."} / {"type": "result", "result": {...}} /
{"type": "error", "message": "...", "traceback": [...], "logs": [...]}。
策略里的 print 与日志进入结果的 logs；进程的标准输出另作他用，避免策略代码打乱消息。
"""
import io
import json
import os
import sys
import traceback

import numpy as np


class StrategyFailure(Exception):
    def __init__(self, message, trace, logs):
        super().__init__(message)
        self.message, self.trace, self.logs = message, trace, logs


def _json_default(value):
    if isinstance(value, np.generic):
        return value.item()
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    return str(value)


def _user_trace(exc, code):
    """只保留策略代码中的调用栈，附上对应的源码行。"""
    lines = code.splitlines()
    out = []
    for frame in traceback.extract_tb(exc.__traceback__):
        if frame.filename == '<strategy>':
            text = lines[frame.lineno - 1].strip() if frame.lineno and frame.lineno <= len(lines) else ''
            out.append({'line': frame.lineno, 'function': frame.name, 'code': text})
    return out


def run_strategy(code, start, end, capital, benchmark='000300.XSHG', progress=None):
    """执行策略并返回结果；策略出错时抛出 StrategyFailure（含出错行与已有日志）。"""
    from instock.quant import engine, jqapi, store

    bt = None
    try:
        bt = engine.Backtest(store.Panel(), store.load_securities(), store.load_members(), store.load_trade_days(),
                             start, end, capital, benchmark, progress)
        ns = jqapi.Api(bt).namespace()
        jqapi.install_modules(ns)
        ns['__name__'] = 'strategy'
        exec(compile(code, '<strategy>', 'exec'), ns)  # noqa: S102  策略代码在沙箱进程中执行
        return bt.run(ns)
    except Exception as e:
        if isinstance(e, (engine.NotSupported, engine.StrategyError)):
            message = str(e)
        else:
            message = f'{type(e).__name__}: {e}'
        raise StrategyFailure(message, _user_trace(e, code), bt.logs if bt else []) from e


def main():
    proto = os.fdopen(os.dup(1), 'w', encoding='utf-8')
    devnull = os.open(os.devnull, os.O_WRONLY)
    os.dup2(devnull, 1)  # 策略或第三方库直接写标准输出时丢弃
    sys.stdout = io.StringIO()

    def send(message):
        proto.write(json.dumps(message, ensure_ascii=False, default=_json_default) + '\n')
        proto.flush()

    request = json.loads(sys.stdin.read())
    try:
        result = run_strategy(request['code'], request['start'], request['end'], request['capital'],
                              request.get('benchmark') or '000300.XSHG',
                              lambda p, day: send({'type': 'progress', 'progress': round(p, 4),
                                                   'date': day.isoformat()}))
        send({'type': 'result', 'result': result})
    except StrategyFailure as e:
        send({'type': 'error', 'message': e.message, 'traceback': e.trace, 'logs': e.logs[-500:]})
    except Exception as e:  # 引擎自身的错误
        send({'type': 'error', 'message': f'{type(e).__name__}: {e}', 'traceback': [], 'logs': []})


if __name__ == '__main__':
    main()
