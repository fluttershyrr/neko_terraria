"""Terraria 协议连接 + tModLoader mod 接口双通道管理。

- 7777 通道：Terraria 服务端（完整登录握手 + 游戏操作）
- 9877 通道：tModLoader C# mod 辅助控制接口（JSON-over-TCP）
"""

import asyncio
import json
import socket
import struct
from typing import Optional, Tuple

from .protocol import PacketManager


class Connection:
    """管理 Terraria 协议 TCP 与 mod 本地接口双通道。"""

    def __init__(self, server_host: str, server_port: int,
                 mod_host: str, mod_port: int) -> None:
        self.server_host = server_host
        self.server_port = server_port
        self.mod_host = mod_host
        self.mod_port = mod_port
        self.packet = PacketManager()
        # 7777 服务端 socket（用于异步收发）
        self._sock: Optional[socket.socket] = None
        # 9877 mod 接口 stream
        self._mod_reader: Optional[asyncio.StreamReader] = None
        self._mod_writer: Optional[asyncio.StreamWriter] = None
        self.connected = False
        # 7777 发送串行锁，防止并发游戏操作交错写入
        self._send_lock = asyncio.Lock()
        # mod 串行锁
        self._mod_lock = asyncio.Lock()
        self._req_seq = 0

    # ===== 7777 Terraria 服务端通道 =====

    async def connect_server(self) -> bool:
        """TCP 连接到 Terraria 服务端，设为非阻塞模式以支持 asyncio"""
        try:
            self._sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self._sock.setblocking(False)
            loop = asyncio.get_event_loop()
            await loop.sock_connect(self._sock, (self.server_host, self.server_port))
            self.connected = True
            return True
        except Exception as e:
            self.connected = False
            return False

    async def send_server_wait(self, packet: bytes) -> bool:
        """向 7777 完整发送一个原始协议包，并等待发送完成。"""
        if not self._sock or not self.connected:
            return False
        try:
            loop = asyncio.get_running_loop()
            await loop.sock_sendall(self._sock, packet)
            return True
        except (OSError, RuntimeError) as e:
            from .raw_bot import _log
            _log(f"send_server_wait 失败: {type(e).__name__}: {e}")
            self.connected = False
            return False

    def send_server(self, packet: bytes) -> Optional[asyncio.Task[bool]]:
        """调度协议包发送，供无需等待结果的游戏期同步接口使用。"""
        if not self._sock or not self.connected:
            return None
        try:
            return asyncio.get_running_loop().create_task(
                self.send_server_wait(packet))
        except RuntimeError:
            self.connected = False
            return None

    async def _recv_exactly(self, size: int, timeout: float) -> Optional[bytes]:
        """在超时前从服务端精确读取指定字节数。"""
        if not self._sock:
            return None
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        chunks = bytearray()
        while len(chunks) < size:
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            chunk = await asyncio.wait_for(
                loop.sock_recv(self._sock, size - len(chunks)), timeout=remaining)
            if not chunk:
                self.connected = False
                return None
            chunks.extend(chunk)
        return bytes(chunks)

    async def recv_server_packet(self, timeout: float = 5.0) -> Optional[bytes]:
        """从 7777 接收一个完整的 Terraria 协议包
        
        Returns:
            包数据（不含长度头），或超时/断开时返回 None
        """
        if not self._sock or not self.connected:
            return None
        try:
            header = await self._recv_exactly(2, timeout)
            if header is None:
                return None
            length = struct.unpack("<H", header)[0] - 2
            if length <= 0 or length > 65533:
                return None
            return await self._recv_exactly(length, timeout)
        except (asyncio.TimeoutError, OSError):
            return None

    async def recv_server_until(self, target_types: set,
                                 timeout_per_packet: float = 5.0,
                                 max_packets: int = 50) -> Optional[Tuple[int, bytes]]:
        """持续接收包直到遇到目标类型之一
        
        Args:
            target_types: 期望的包类型集合，如 {3, 7, 49, 129}
            timeout_per_packet: 每个包的超时时间
            max_packets: 最大接收包数（防止死循环）
        
        Returns:
            (packet_type, data) 或 None（超时/断开）
        """
        for _ in range(max_packets):
            data = await self.recv_server_packet(timeout_per_packet)
            if data is None or len(data) == 0:
                return None
            pkt_type = data[0]
            if pkt_type in target_types:
                return (pkt_type, data)
            # 其他类型的包忽略，继续等待目标类型
        return None

    # ===== 9877 Mod 接口通道 =====

    async def connect_mod(self, retry_ports: bool = True) -> bool:
        """TCP 连接到 tModLoader mod 的辅助控制接口

        Args:
            retry_ports: 如果默认端口失败，是否尝试其他端口 (9878-9886)

        Returns:
            连接成功返回 True，否则 False
        """
        # 首先尝试默认端口
        try:
            self._mod_reader, self._mod_writer = await asyncio.open_connection(
                self.mod_host, self.mod_port)
            return True
        except Exception as e:
            # 默认端口失败，如果启用重试，尝试其他端口
            if not retry_ports:
                return False

            # 尝试端口范围: 9878-9886 (共10个备用端口)
            original_port = self.mod_port
            for port in range(original_port + 1, original_port + 11):
                try:
                    self._mod_reader, self._mod_writer = await asyncio.open_connection(
                        self.mod_host, port)
                    # 连接成功，更新端口
                    self.mod_port = port
                    return True
                except Exception:
                    continue

            # 所有端口都失败
            return False

    async def request_mod(self, cmd: dict, timeout: float = 3.0) -> Optional[dict]:
        """向 mod 接口发送 JSON 命令并等待匹配的回执"""
        async with self._mod_lock:
            self._req_seq = (self._req_seq + 1) & 0xFFFF
            req_id = self._req_seq
            cmd = dict(cmd)
            cmd["req_id"] = req_id
            await self._send_mod_raw(cmd)
            return await self._recv_mod_raw(req_id, timeout)

    async def _send_mod_raw(self, cmd: dict) -> None:
        if not self._mod_writer:
            return
        data = (json.dumps(cmd) + "\n").encode("utf-8")
        try:
            self._mod_writer.write(data)
            await self._mod_writer.drain()
        except Exception:
            pass

    async def _recv_mod_raw(self, req_id: int, timeout: float = 1.0) -> Optional[dict]:
        if not self._mod_reader:
            return None
        deadline = asyncio.get_event_loop().time() + timeout
        tries = 0
        while True:
            remain = deadline - asyncio.get_event_loop().time()
            if remain <= 0:
                return None
            try:
                line = await asyncio.wait_for(
                    self._mod_reader.readline(), timeout=remain)
            except Exception:
                return None
            if not line:
                return None
            try:
                resp = json.loads(line.decode("utf-8"))
            except Exception:
                continue
            if resp.get("req_id") == req_id:
                return resp
            tries += 1
            if tries > 8:
                return None

    # ===== 通用 =====

    def close(self) -> None:
        """关闭所有连接"""
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        if self._mod_writer:
            try:
                self._mod_writer.close()
            except Exception:
                pass
        self.connected = False
