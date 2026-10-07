"""回测任务：Web 服务创建任务目录，运行器进程逐个在子进程中执行，结果写回任务目录。

jobs/<id>/meta.json      任务参数（账号、名称、区间、资金、基准、创建时间），由 Web 写入
jobs/<id>/strategy.py    策略代码
jobs/<id>/status.json    状态 queued/running/done/failed/canceled、进度、错误，由运行器写入
jobs/<id>/result.json    回测结果
jobs/<id>/cancel         取消标记

沙箱模式（docker-compose 中的 instock-backtest 容器，以 root 启动）：子进程降权为 nobody，
jobs 目录仅 root 可读，子进程看不到其他任务的代码；容器本身无网络、无数据库凭证、根文件系统只读。
"""
import datetime
import json
import logging
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import threading
import time

from instock import config, tradecal
from instock.quant import check, store
from instock.sources.baostock import INDEXES

log = logging.getLogger(__name__)

MAX_CODE_BYTES = 256 * 1024
MAX_ACTIVE_PER_USER = 3
_ID = re.compile(r'^[0-9a-f]{20}$')
_HEARTBEAT_SECONDS = 30
_NOBODY = 65534


class JobError(Exception):
    """提交或操作任务时的参数错误，信息直接返回给用户。"""


def jobs_dir():
    return config.QUANT_DIR / 'jobs'


def _job_dir(job_id):
    if not _ID.match(job_id or ''):
        raise JobError('任务编号无效')
    return jobs_dir() / job_id


def _read_json(path, default=None):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (FileNotFoundError, ValueError):
        return default


def _write_json(path, data):
    tmp = path.with_name(f'{path.name}.{os.getpid()}.tmp')
    tmp.write_text(json.dumps(data, ensure_ascii=False, separators=(',', ':')), encoding='utf-8')
    os.replace(tmp, path)


# ---------- 状态 ----------

def runner_status():
    beat = _read_json(config.QUANT_DIR / 'runner.json', {})
    alive = bool(beat) and time.time() - beat.get('time', 0) < _HEARTBEAT_SECONDS
    return {'alive': alive, 'sandboxed': bool(alive and beat.get('sandboxed'))}


def data_status():
    state = store.load_state()
    return {'ready': bool(state.get('ready')) and (store.root() / 'panel' / 'codes.json').is_file(),
            'start': state.get('start'), 'end': state.get('last_date'), 'synced_at': state.get('synced_at'),
            'securities': state.get('securities'), 'minute': state.get('minute')}


def can_run(user):
    runner = runner_status()
    return runner['alive'] and (runner['sandboxed'] or user['admin'])


# ---------- Web 端：任务管理 ----------

def _parse_day(value, label):
    try:
        return datetime.date.fromisoformat(str(value))
    except ValueError:
        raise JobError(f'{label}格式应为 YYYY-MM-DD') from None


def create_job(user, data):
    """校验参数并创建任务，返回 (任务, 检查结果)。"""
    if not can_run(user):
        runner = runner_status()
        raise JobError('回测服务未运行' if not runner['alive'] else '回测服务未启用沙箱，只有管理员可以运行回测')
    status = data_status()
    if not status['ready']:
        raise JobError('回测数据尚未准备好：请管理员先运行 python -m instock quant sync')
    code = str(data.get('code') or '')
    if not code.strip():
        raise JobError('策略代码为空')
    if len(code.encode('utf-8')) > MAX_CODE_BYTES:
        raise JobError(f'策略代码不能超过 {MAX_CODE_BYTES // 1024} KB')
    result = check.check(code)
    if result['errors']:
        return None, result
    start, end = _parse_day(data.get('start'), '开始日期'), _parse_day(data.get('end'), '结束日期')
    first, last = datetime.date.fromisoformat(status['start']), datetime.date.fromisoformat(status['end'])
    if start > end:
        raise JobError('开始日期不能晚于结束日期')
    if end < first or start > last:
        raise JobError(f'回测区间须在数据范围 {first} ~ {last} 之内')
    try:
        capital = float(data.get('capital') or 1_000_000)
    except (TypeError, ValueError):
        raise JobError('初始资金应为数字') from None
    if not 1_000 <= capital <= 1e11:
        raise JobError('初始资金应在 1 千元到 1000 亿元之间')
    benchmark = str(data.get('benchmark') or '000300.XSHG')
    if benchmark not in INDEXES:
        raise JobError('不支持的基准指数')
    frequency = str(data.get('frequency') or 'day')
    if frequency not in ('day', 'minute'):
        raise JobError('回测频率只能是 day 或 minute')
    if frequency == 'minute' and not status['minute']:
        raise JobError('还没有分钟数据：请管理员先运行 python -m instock quant sync-minute')
    active = [j for j in list_jobs(user['username']) if j['status']['state'] in ('queued', 'running')]
    if len(active) >= MAX_ACTIVE_PER_USER:
        raise JobError(f'每个账号最多同时排队 {MAX_ACTIVE_PER_USER} 个回测')
    now = tradecal.now()
    job_id = f'{now:%Y%m%d%H%M%S}{secrets.token_hex(3)}'
    folder = jobs_dir() / job_id
    _ensure_jobs_dir()
    folder.mkdir(mode=0o700)
    meta = {'id': job_id, 'user': user['username'], 'name': str(data.get('name') or '未命名策略')[:60],
            'start': max(start, first).isoformat(), 'end': min(end, last).isoformat(), 'capital': capital,
            'benchmark': benchmark, 'frequency': frequency, 'created': now.isoformat(' ', 'seconds')}
    (folder / 'strategy.py').write_text(code, encoding='utf-8')
    _write_json(folder / 'meta.json', meta)
    _write_json(folder / 'status.json', {'state': 'queued'})
    return _summary(folder), result


def _summary(folder):
    meta = _read_json(folder / 'meta.json')
    if meta is None:
        return None
    status = _read_json(folder / 'status.json', {'state': 'queued'})
    return {**meta, 'status': status}


def list_jobs(username=None):
    folder = jobs_dir()
    if not folder.is_dir():
        return []
    jobs = [_summary(p) for p in folder.iterdir() if p.is_dir() and _ID.match(p.name)]
    jobs = [j for j in jobs if j and (username is None or j['user'] == username)]
    return sorted(jobs, key=lambda j: j['id'], reverse=True)


def get_job(job_id, user):
    folder = _job_dir(job_id)
    job = _summary(folder) if folder.is_dir() else None
    if job is None or (job['user'] != user['username'] and not user['admin']):
        raise JobError('任务不存在')
    job['code'] = (folder / 'strategy.py').read_text(encoding='utf-8')
    job['result'] = _read_json(folder / 'result.json')
    return job


def remove_job(job_id, user):
    """排队或运行中的任务取消，已结束的任务删除。"""
    job = get_job(job_id, user)
    folder = _job_dir(job_id)
    if job['status']['state'] in ('queued', 'running'):
        (folder / 'cancel').touch()
        return 'canceled'
    shutil.rmtree(folder, ignore_errors=True)
    return 'deleted'


# ---------- 运行器 ----------

def _sandboxed():
    return config.QUANT_SANDBOX and os.name == 'posix' and os.geteuid() == 0


def _ensure_jobs_dir():
    folder = jobs_dir()
    folder.mkdir(parents=True, exist_ok=True)
    if os.name == 'posix':
        os.chmod(folder, 0o700)


def _limits():
    """子进程启动前（降权前）设置资源上限。"""
    import resource
    mem = config.QUANT_MEMORY_MB * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_DATA, (mem, mem))
    resource.setrlimit(resource.RLIMIT_CPU, (config.QUANT_TIMEOUT + 60,) * 2)
    resource.setrlimit(resource.RLIMIT_FSIZE, (0, 0))  # 不允许写文件
    resource.setrlimit(resource.RLIMIT_NOFILE, (256, 256))
    resource.setrlimit(resource.RLIMIT_NPROC, (64, 64))
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))


class _Running:
    def __init__(self, folder):
        self.folder = folder
        self.meta = _read_json(folder / 'meta.json')
        self.started = time.monotonic()
        self.messages = []
        self.progress = None
        env = {'PATH': os.environ.get('PATH', ''), 'LANG': 'C.UTF-8', 'LC_ALL': 'C.UTF-8',
               'PYTHONIOENCODING': 'utf-8', 'PYTHONDONTWRITEBYTECODE': '1',
               'PYTHONPATH': str(config.ROOT_DIR), 'INSTOCK_DATA_DIR': str(config.DATA_DIR),
               'INSTOCK_QUANT_START': config.QUANT_START, 'TZ': os.environ.get('TZ', 'Asia/Shanghai')}
        if os.name == 'nt':
            env['SYSTEMROOT'] = os.environ.get('SYSTEMROOT', r'C:\Windows')
        kwargs = {}
        if _sandboxed():
            kwargs.update(user=_NOBODY, group=_NOBODY, extra_groups=[], preexec_fn=_limits, start_new_session=True)
        self.workdir = tempfile.mkdtemp(prefix='instock-bt-')
        if _sandboxed():
            os.chmod(self.workdir, 0o755)
        self.proc = subprocess.Popen([sys.executable, '-m', 'instock.quant.child'], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=subprocess.PIPE, cwd=self.workdir, env=env,
                                     **kwargs)
        request = {k: self.meta.get(k) for k in ('start', 'end', 'capital', 'benchmark', 'frequency')}
        request['code'] = (folder / 'strategy.py').read_text(encoding='utf-8')
        self._reader = threading.Thread(target=self._read, daemon=True)
        self._stderr = []
        threading.Thread(target=lambda: self._stderr.extend(self.proc.stderr.read().decode('utf-8', 'replace')
                                                            .splitlines()[-30:]), daemon=True).start()
        self.proc.stdin.write(json.dumps(request, ensure_ascii=False).encode('utf-8'))
        self.proc.stdin.close()
        self._reader.start()
        _write_json(folder / 'status.json', {'state': 'running', 'progress': 0,
                                             'started': tradecal.now().isoformat(' ', 'seconds')})

    def _read(self):
        for line in self.proc.stdout:
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if message.get('type') == 'progress':
                self.progress = message
            else:
                self.messages.append(message)

    def kill(self):
        if self.proc.poll() is None:
            self.proc.kill()

    def finish(self, state=None, error=None):
        self._reader.join(timeout=10)
        status = _read_json(self.folder / 'status.json', {})
        status.update(finished=tradecal.now().isoformat(' ', 'seconds'),
                      elapsed=round(time.monotonic() - self.started, 1))
        final = next((m for m in reversed(self.messages) if m.get('type') in ('result', 'error')), None)
        if state:
            status.update(state=state, error=error)
        elif final and final['type'] == 'result':
            _write_json(self.folder / 'result.json', final['result'])
            status.update(state='done', progress=1, error=None, summary=final['result']['summary'])
        elif final:
            status.update(state='failed', error=final['message'], traceback=final.get('traceback'),
                          logs=final.get('logs'))
        else:
            code = self.proc.returncode
            tail = ' '.join(self._stderr[-3:])
            reason = '内存超出限制' if code in (-9, 137) or 'MemoryError' in tail else f'进程异常退出（{code}）'
            status.update(state='failed', error=f'{reason}{"：" + tail if tail else ""}')
        _write_json(self.folder / 'status.json', status)
        shutil.rmtree(self.workdir, ignore_errors=True)
        log.info('回测 %s（%s）结束：%s %s', self.meta['id'], self.meta['user'], status['state'],
                 status.get('error') or '')


def _heartbeat():
    _write_json(config.QUANT_DIR / 'runner.json',
                {'time': time.time(), 'sandboxed': _sandboxed(), 'pid': os.getpid()})


def run_forever(concurrency=1):
    _ensure_jobs_dir()
    if _sandboxed():
        # 子进程（nobody）不能在 /tmp 建文件：避免不同任务借文件名互相传递信息；运行器的临时目录由 root 创建
        os.chmod(tempfile.gettempdir(), 0o755)
    for job in list_jobs():
        if job['status']['state'] == 'running':
            _write_json(jobs_dir() / job['id'] / 'status.json',
                        {**job['status'], 'state': 'failed', 'error': '回测服务重启，任务中断，请重新运行'})
    log.info('回测运行器已启动（沙箱：%s）', '是' if _sandboxed() else '否，仅管理员可提交回测')
    running = {}
    last_beat = 0.0
    while True:
        now = time.monotonic()
        if now - last_beat >= 5:
            _heartbeat()
            last_beat = now
        for job_id, job in list(running.items()):
            if (job.folder / 'cancel').exists():
                job.kill()
                job.proc.wait()
                job.finish('canceled', '已取消')
            elif job.proc.poll() is not None:
                job.finish()
            elif now - job.started > config.QUANT_TIMEOUT:
                job.kill()
                job.proc.wait()
                job.finish('failed', f'运行超过 {config.QUANT_TIMEOUT} 秒，已终止')
            else:
                if job.progress:
                    status = _read_json(job.folder / 'status.json', {})
                    status.update(progress=job.progress['progress'], date=job.progress['date'])
                    _write_json(job.folder / 'status.json', status)
                    job.progress = None
                continue
            del running[job_id]
        if len(running) < concurrency:
            for job in sorted(list_jobs(), key=lambda j: j['id']):
                if job['id'] in running or job['status']['state'] != 'queued':
                    continue
                folder = jobs_dir() / job['id']
                if (folder / 'cancel').exists():
                    _write_json(folder / 'status.json', {'state': 'canceled', 'error': '已取消'})
                    continue
                log.info('开始回测 %s（%s）：%s', job['id'], job['user'], job['name'])
                try:
                    running[job['id']] = _Running(folder)
                except Exception as e:
                    log.exception('启动回测失败')
                    _write_json(folder / 'status.json', {'state': 'failed', 'error': f'启动失败：{e}'})
                if len(running) >= concurrency:
                    break
        time.sleep(1)
