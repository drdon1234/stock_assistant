"""命令行入口。

python -m instock web                         启动 Web 服务
python -m instock worker                      启动调度（盘中刷新行情，收盘后完整作业）
python -m instock run                         运行一次当前交易日的完整作业
python -m instock run 2024-03-01              指定日期（多日用逗号分隔）
python -m instock run 2024-03-01 2024-03-31   指定区间
python -m instock run --only spot,etf         只运行部分任务
"""
import argparse
import sys

from instock import jobs, logs


def main(argv=None):
    parser = argparse.ArgumentParser(prog='python -m instock', description='InStock 股票系统')
    sub = parser.add_subparsers(dest='command', required=True)
    sub.add_parser('web', help='启动 Web 服务')
    sub.add_parser('worker', help='启动调度进程')
    run = sub.add_parser('run', help='手动运行作业')
    run.add_argument('dates', nargs='*', help='日期：空=当前，单日/逗号分隔多日，或起止两个日期')
    run.add_argument('--only', help=f"只运行指定任务，逗号分隔：{','.join(jobs.TASK_KEYS)}")
    args = parser.parse_args(argv)

    logs.setup(args.command)
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
