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
    args = parser.parse_args(argv)

    if args.command == 'user':
        _user_command(args)
        return
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
