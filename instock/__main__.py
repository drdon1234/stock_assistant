"""命令行入口。

python -m instock web                         启动 Web 服务
python -m instock worker                      启动调度（盘中刷新行情，收盘后完整作业）
python -m instock run                         运行一次当前交易日的完整作业
python -m instock run 2024-03-01              指定日期（多日用逗号分隔）
python -m instock run 2024-03-01 2024-03-31   指定区间
python -m instock run --only spot,etf         只运行部分任务
python -m instock user add alice [--admin]    新建网页登录账号（第一个账号自动成为管理员）
python -m instock user passwd alice           重置密码（该账号所有设备需重新登录）
python -m instock user list | del | logout    列出账号 / 删除账号 / 强制下线
python -m instock quant sync                  回补/增量同步回测数据（BaoStock，可中断后重跑续传）
python -m instock quant status                查看回测数据状态
python -m instock quant runner                启动回测运行器（执行网页提交的聚宽策略）
python -m instock quant run s.py 2020-01-01 2024-12-31   在命令行直接回测一个聚宽策略文件
"""
import argparse
import getpass
import sys

from instock import jobs, logs


def _read_password():
    """终端中交互输入两次；非交互（如管道）时从标准输入读一行。"""
    if not sys.stdin.isatty():
        return sys.stdin.readline().rstrip('\r\n')
    password = getpass.getpass('密码：')
    if getpass.getpass('再次输入：') != password:
        sys.exit('两次输入的密码不一致')
    return password


def _user_command(args):
    from instock import auth, db
    db.init()
    try:
        if args.action == 'list':
            for u in auth.list_users():
                role = '管理员' if u['admin'] else '普通'
                print(f"{u['username']:<32} {role:<4} 创建 {u['created_at']}  在线设备 {u['sessions']}"
                      f"  最近使用 {u['last_used'] or '-'}")
            return
        if not args.name:
            sys.exit('请指定账号')
        name = auth.normalize(args.name)
        if args.action == 'add':
            user = auth.create_user(name, _read_password(), admin=args.admin)
            print(f"已创建{'管理员' if user['admin'] else ''}账号 {user['username']}")
        elif args.action == 'passwd':
            auth.set_password(name, _read_password())
            print(f'已重置 {name} 的密码，该账号所有设备需要重新登录')
        elif args.action == 'del':
            auth.delete_user(name)
            print(f'已删除账号 {name} 及其关注列表')
        elif args.action == 'logout':
            auth.get_user(name) or sys.exit(f'账号 {name} 不存在')
            auth.revoke_user(name)
            print(f'已吊销 {name} 的全部登录凭证')
    except auth.AuthError as e:
        sys.exit(str(e))


def _quant_command(args, parser):
    from instock.quant import data, runner, store
    if args.action == 'sync':
        data.sync(workers=args.workers, codes=args.codes.split(',') if args.codes else None)
    elif args.action == 'rebuild':
        data.rebuild()
    elif args.action == 'status':
        status = runner.data_status()
        print(f"数据：{'就绪' if status['ready'] else '未就绪'}，{status['start'] or '-'} ~ {status['end'] or '-'}，"
              f"股票 {status['securities'] or 0} 只，最近同步 {status['synced_at'] or '-'}")
        print(f"原始数据 {len(store.raw_codes())} 只证券；运行器：{runner.runner_status()}")
    elif args.action == 'runner':
        runner.run_forever()
    elif args.action == 'run':
        _quant_run(args, parser)


def _quant_run(args, parser):
    import json
    from pathlib import Path
    from instock.quant import check, child

    if len(args.args) != 3:
        parser.error('用法：quant run <策略文件> <开始日期> <结束日期>')
    code = Path(args.args[0]).read_text(encoding='utf-8')
    report = check.check(code)
    for kind in ('errors', 'warnings', 'notes'):
        for item in report[kind]:
            print(f"[{kind}] 第 {item['line'] or '-'} 行：{item['message']}")
    if report['errors']:
        sys.exit(1)
    try:
        result = child.run_strategy(code, args.args[1], args.args[2], args.capital, args.benchmark,
                                    lambda p, day: print(f'\r{day} {p:6.1%}', end='', file=sys.stderr))
    except child.StrategyFailure as e:
        print('\n'.join(e.logs[-20:]))
        for frame in e.trace:
            print(f"  第 {frame['line']} 行 {frame['function']}：{frame['code']}")
        sys.exit(f'回测失败：{e.message}')
    print(file=sys.stderr)
    print('\n'.join(result['logs'][-20:]))
    print(json.dumps(result['summary'], ensure_ascii=False, indent=1))


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m instock', description='InStock 股票系统')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('web', help='启动 Web 服务')
    sub.add_parser('worker', help='启动调度进程')
    run = sub.add_parser('run', help='手动运行作业')
    run.add_argument('dates', nargs='*', help='日期：空=当前，单日/逗号分隔多日，或起止两个日期')
    run.add_argument('--only', help=f"只运行指定任务，逗号分隔：{','.join(jobs.TASK_KEYS)}")
    user = sub.add_parser('user', help='管理网页登录账号')
    user.add_argument('action', choices=('list', 'add', 'passwd', 'del', 'logout'),
                      help='list 列出，add 新建，passwd 重置密码，del 删除，logout 强制下线')
    user.add_argument('name', nargs='?', help='账号')
    user.add_argument('--admin', action='store_true', help='新建为管理员')
    quant = sub.add_parser('quant', help='聚宽兼容回测：数据同步、运行器与命令行回测')
    quant.add_argument('action', choices=('sync', 'rebuild', 'status', 'runner', 'run'),
                       help='sync 同步数据，rebuild 重建宽表，status 状态，runner 启动运行器，run 命令行回测')
    quant.add_argument('args', nargs='*', help='run：策略文件 开始日期 结束日期')
    quant.add_argument('--workers', type=int, help='sync：BaoStock 并发进程数')
    quant.add_argument('--codes', help='sync：只同步指定证券（聚宽代码，逗号分隔），调试用')
    quant.add_argument('--capital', type=float, default=1_000_000, help='run：初始资金')
    quant.add_argument('--benchmark', default='000300.XSHG', help='run：基准指数')
    args = parser.parse_args(argv)

    if args.command == 'user':
        _user_command(args)
        return
    logs.setup(f'quant-{args.action}' if args.command == 'quant' and args.action != 'run' else args.command)
    if args.command == 'quant':
        _quant_command(args, parser)
        return
    if args.command == 'web':
        from instock.web import app
        app.main()
    elif args.command == 'worker':
        from instock import worker
        worker.main()
    else:
        keys = tuple(args.only.split(',')) if args.only else jobs.TASK_KEYS
        unknown = set(keys) - set(jobs.TASK_KEYS)
        if unknown:
            parser.error(f"未知任务：{','.join(sorted(unknown))}")
        if len(args.dates) > 2:
            parser.error('日期参数最多两个（起止日期）')
        jobs.run(jobs.parse_days(args.dates), keys)


if __name__ == '__main__':
    sys.exit(main())
