"""通达信行情服务器（TCP）：历史分时数据——每个交易日 240 个点（09:31~11:30、13:01~15:00），
每点为该分钟的收盘价与成交量（手）。最后一点等于当日收盘价，成交量合计等于当日成交量；没有分钟内的开高低。

只实现回测需要的这一条指令。协议：连接后发送 3 个初始化包；响应为 16 字节包头（含压缩前后长度）+ 可能经
zlib 压缩的包体；价格以“变长有符号整数”编码的逐点差值（分）表示。2005 年以来的数据都可查询，停牌日返回空。
"""
import socket
import struct
import zlib

import numpy as np

# 2026-10 实测可用的公共行情服务器（按响应速度排序）
HOSTS = [
    ('218.6.170.47', 7709), ('182.131.3.245', 7709), ('117.34.114.18', 7709), ('117.34.114.20', 7709),
    ('117.34.114.15', 7709), ('117.34.114.13', 7709), ('117.34.114.14', 7709), ('117.34.114.16', 7709),
    ('117.34.114.17', 7709), ('117.34.114.27', 7709), ('175.6.5.153', 7709), ('180.153.18.170', 7709),
    ('60.12.136.250', 7709), ('218.106.92.182', 7709), ('123.125.108.14', 7709), ('180.153.18.172', 80),
    ('202.108.253.139', 80), ('58.63.254.217', 7709), ('183.60.224.177', 7709), ('119.29.19.242', 7709),
    ('115.238.90.165', 7709), ('115.238.56.198', 7709), ('60.191.117.167', 7709), ('183.60.224.178', 7709),
    ('220.178.55.71', 7709), ('218.75.126.9', 7709), ('123.125.108.90', 7709), ('218.106.92.183', 7709),
    ('220.178.55.86', 7709), ('58.63.254.191', 7709), ('182.118.47.151', 7709), ('202.100.166.27', 7709),
]
MINUTES = 240
_SETUP = (
    '0c 02 18 93 00 01 03 00 03 00 0d 00 01',
    '0c 02 18 94 00 01 03 00 03 00 0d 00 02',
    '0c 03 18 99 00 01 20 00 20 00 db 0f d5 d0 c9 cc d6 a4 a8 af 00 00 00 8f c2 25 40 13 00 00 d5 00 c9 cc bd f0 '
    'd7 ea 00 00 00 02',
)
_MINUTE_CMD = bytes.fromhex('0c 01 30 00 01 01 0d 00 0d 00 b4 0f')


class TdxError(Exception):
    pass


def _varint(buf, pos):
    """通达信的变长有符号整数：首字节低 6 位 + 符号位(0x40)，后续字节各 7 位。"""
    byte = buf[pos]
    value, shift, negative = byte & 0x3f, 6, bool(byte & 0x40)
    while byte & 0x80:
        pos += 1
        byte = buf[pos]
        value += (byte & 0x7f) << shift
        shift += 7
    return (-value if negative else value), pos + 1


def parse_minutes(body):
    """历史分时响应 -> (收盘价 float64[n], 成交量 手 int64[n])。"""
    (count,) = struct.unpack('<H', body[:2])
    pos, last = 6, 0
    prices = np.empty(count)
    volumes = np.empty(count, dtype=np.int64)
    for i in range(count):
        delta, pos = _varint(body, pos)
        _, pos = _varint(body, pos)
        vol, pos = _varint(body, pos)
        last += delta
        prices[i] = last / 100
        volumes[i] = vol
    return prices, volumes


class Client:
    def __init__(self, host, timeout=10):
        self.host = host
        self.timeout = timeout
        self.sock = None

    def connect(self):
        self.close()
        self.sock = socket.create_connection(self.host, timeout=self.timeout)
        for pkg in _SETUP:
            self._call(bytes.fromhex(pkg))
        return self

    def close(self):
        if self.sock is not None:
            try:
                self.sock.close()
            except OSError:
                pass
            self.sock = None

    def _recv(self, size):
        buf = bytearray()
        while len(buf) < size:
            chunk = self.sock.recv(size - len(buf))
            if not chunk:
                raise TdxError(f'服务器 {self.host[0]} 断开了连接')
            buf += chunk
        return bytes(buf)

    def _call(self, pkg):
        if self.sock is None:
            raise TdxError('未连接')
        self.sock.sendall(pkg)
        _, _, _, zipped, size = struct.unpack('<IIIHH', self._recv(16))
        body = self._recv(zipped)
        return zlib.decompress(body) if zipped != size else body

    def minutes(self, code, day):
        """code 为聚宽格式，day 为 date。返回 (收盘价, 成交量手)；停牌或无数据返回 None。"""
        num, market = code.split('.')
        pkg = _MINUTE_CMD + struct.pack('<IB6s', int(day.strftime('%Y%m%d')), 1 if market == 'XSHG' else 0,
                                        num.encode())
        prices, volumes = parse_minutes(self._call(pkg))
        if len(prices) == 0:
            return None
        if len(prices) != MINUTES:
            raise TdxError(f'{code} {day} 分时点数异常：{len(prices)}')
        return prices, volumes
