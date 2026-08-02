"""免客户端登录：使用 Terraria/tModLoader 协议作为独立玩家进世界。

基于 2026-08-01 测试验证的 tModLoader 握手流程:
  - tML 对 modded 客户端跳过 Packet 3 (ConnectApproved)，直接发 SyncMods(251)
  - 密码包用 1字节长度头即可（短密码与 7-bit 编码相同）
  - player_slot 默认 0
"""

import asyncio
import os
from typing import Any, Dict, Optional
from datetime import datetime

from .connection import Connection
from .protocol import PacketManager

# 日志文件路径：插件根目录/data/login_debug.txt
# __file__ = .../neko_terraria/bridge/raw_bot.py
# 向上一级 = .../neko_terraria
_LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "login_debug.txt")


def _log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    line = f"[{ts}] {msg}\n"
    try:
        d = os.path.dirname(_LOG_FILE)
        os.makedirs(d, exist_ok=True)
        with open(_LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line)
            f.flush()
    except Exception:
        pass


class RawBot:
    """封装完整的 tModLoader 登录握手 + 游戏操作。"""

    def __init__(self, conn: Connection) -> None:
        self.conn = conn
        self.packet: PacketManager = conn.packet
        self.player_name = ""
        self.player_slot = 0
        self.logged_in = False
        self._server_mods: list[Any] = []
        self.x = 0.0
        self.y = 0.0
        self.velocity_x = 0.0
        self.velocity_y = 0.0
        self.direction = 1
        self._position_ready = False
        self._heartbeat_task: Optional[asyncio.Task[None]] = None
        self._entity_task: Optional[asyncio.Task[None]] = None

    async def login(self, name: str, password: str = "") -> bool:
        try:
            with open(_LOG_FILE, "w", encoding="utf-8") as f:
                f.write("")
        except Exception:
            pass

        self.player_name = name
        _log(f"=== login name={name} ===")

        # Step 0: 先连接 Mod 9877，获取服务器环境信息（版本/难度/世界）
        _log("Step0: 连接 mod 9877...")
        mod_ok = await self.conn.connect_mod()
        if mod_ok:
            _log("Step0: mod 连接成功，查询服务器环境信息...")
            info = await self.conn.request_mod({"cmd": "get_server_info"}, timeout=5.0)
            if info and info.get("type") == "server_info":
                ver = info.get("tmod_version_str", "")
                gm = info.get("game_mode", -1)
                if ver:
                    self.packet.version_str = ver
                    _log(f"Step0: 版本适配 → {ver}")
                if gm >= 0:
                    # Journey 世界 → Journey 玩家(3); Classic/Expert/Master → Softcore(0)
                    self.packet.difficulty = 3 if gm == 3 else 0
                    _log(f"Step0: 难度适配 → game_mode={gm}, difficulty={self.packet.difficulty}")
                ws = info.get("world_size", "")
                et = info.get("evil_type", "")
                wn = info.get("world_name", "")
                _log(f"Step0: 世界 → size={ws}, evil={et}, name={wn}")
            else:
                _log("Step0: 查询失败，使用默认配置")
        else:
            _log("Step0: mod 连接失败，使用默认版本/难度配置")
            # 尝试从用户配置回退版本字符串
            try:
                from ..core.config_store import load_user_config
                cfg = load_user_config()
                fallback_ver = cfg.get("tmod_version_str", "")
                if fallback_ver:
                    self.packet.version_str = fallback_ver
                    _log(f"Step0: 配置回退版本 → {fallback_ver}")
            except Exception:
                pass

        # Step 1: TCP 连接 7777
        _log("Step1: connect_server()...")
        if not await self.conn.connect_server():
            _log("Step1 FAIL")
            return False
        _log("Step1 OK")

        try:
            # Step 2: 发送 Connect
            _log("Step2: 发送 Connect")
            if not await self.conn.send_server_wait(self.packet.connect_packet()):
                return False

            # Step 3: 等 GetPassword(37) 或 SyncMods(251) 或 ConnectApproved(3)
            # tML 对 modded 客户端可能跳过 3 直接发 251
            _log("Step3: 等待 GetPassword/SyncMods/Approved...")
            result = await self.conn.recv_server_until({37, 251, 3}, timeout_per_packet=10.0)
            if result is None:
                _log("Step3 FAIL: 无回复")
                return False
            first_type = result[0]
            _log(f"Step3: 收到 type={first_type}")

            # 如果先收到 GetPassword，发密码后继续等
            if first_type == 37:
                _log("Step3: 发送密码")
                if not await self.conn.send_server_wait(self.packet.password_packet(password)):
                    return False
                result = await self.conn.recv_server_until({251, 3}, timeout_per_packet=10.0)
                if result is None:
                    _log("Step3 FAIL: 密码后无回复")
                    return False
                first_type = result[0]
                _log(f"Step3: 密码后收到 type={first_type}")

            # tML modded 客户端：收到 SyncMods(251) 而非 ConnectApproved(3)
            if first_type == 251:
                _log("Step3: tML modded 路径 - 直接 SyncMods")
                await self._handle_sync_mods(result[1][1:])
                # tML 路径：player_slot 默认 0（之后可能收到 3 来纠正）
                self.player_slot = 0
            elif first_type == 3:
                _log("Step3: 原版路径 - ConnectApproved")
                pkt_data = result[1]
                if len(pkt_data) >= 2:
                    self.player_slot = pkt_data[1] & 0xFF
                _log(f"Step3: player_slot={self.player_slot}")

            # Step 4: 发送玩家数据（difficulty 由 Mod 适配决定）
            _log("Step4: 发送玩家数据...")
            if not await self._send_player_data(name):
                return False
            _log("Step4 OK")

            # Step 5: 统一握手阶段——不等 WorldInfo，直接循环收包
            # 服务端在 tML 路径下可能不发 WorldInfo(7)，直接发后续包
            _log("Step5: 握手中间阶段（统一循环）...")
            if not await self._handle_handshake_unified():
                _log("Step5 FAIL")
                return False
            _log("Step5 OK")

            # Step 6: _handle_handshake_unified 已收到 AllowSpawn(49)，直接 Spawn
            spawn_pkt = self.packet.spawn_player_packet(self.player_slot)
            _log(f"Step6: 发送 SpawnPlayer slot={self.player_slot} hex={spawn_pkt.hex()}")
            if not await self.conn.send_server_wait(spawn_pkt):
                return False
            _log("Step6 OK")

            # Step 7: 循环接收直到 LoginComplete(129)，打印中间包
            _log("Step7: 循环等待 LoginComplete...")
            import asyncio
            deadline = asyncio.get_event_loop().time() + 15.0
            while asyncio.get_event_loop().time() < deadline:
                data = await self.conn.recv_server_packet(timeout=5.0)
                if data is None or len(data) == 0:
                    _log("Step7: 收到空数据/超时")
                    continue
                t = data[0]
                _log(f"Step7 pkt: type={t} len={len(data)}")
                if t == 129:
                    _log("Step7 OK! LoginComplete!")
                    break
                if t == 2:
                    _log("Step7: Disconnect!")
                    return False
                if t == 83:
                    continue  # 忽略后续的 tile 包
            else:
                _log("Step7: 超时未收到 LoginComplete")
                return False

            # Mod 已在 Step 0 连接，游戏登录完成后启动后台循环
            self.logged_in = True

            # 初始化位置（使用世界出生点或默认坐标）
            # 这样即使 Mod 未连接，玩家也能在游戏中可见
            if not self._position_ready:
                spawn_x = 1000.0  # 默认出生点 X（可从 WorldInfo 读取）
                spawn_y = 300.0   # 默认出生点 Y
                self.x = spawn_x
                self.y = spawn_y
                self._position_ready = True
                _log(f"使用默认出生点初始化位置: ({spawn_x}, {spawn_y})")

            # 启动后台循环（心跳接收 + 实体位置同步）
            # 即使 Mod 未连接也要启动，否则服务端会因 120 秒无响应而踢出
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            self._entity_task = asyncio.create_task(self._entity_sync_loop())
            if mod_ok:
                _log("网络接收与实体同步循环已启动（含 Mod 状态同步）")
            else:
                _log("网络接收与实体同步循环已启动（无 Mod，使用默认位置）")

            return True

        except Exception as e:
            _log(f"EXCEPTION: {type(e).__name__}: {e}")
            import traceback
            _log(traceback.format_exc())
            return False

    async def _send_player_data(self, name: str) -> bool:
        """按当前服务端槽位，串行提交完整玩家初始数据。"""
        slot = self.player_slot
        packets = [
            self.packet.player_appearance_packet(
                player_slot=slot, name=name, skin_variant=0, hair=0),
            self.packet.player_life_packet(
                player_slot=slot, health=400, max_health=400),
            self.packet.player_mana_packet(
                player_slot=slot, mana=20, max_mana=20),
            self.packet.player_buffs_packet(player_slot=slot),
        ]
        packets.extend(
            self.packet.set_inventory_packet(
                player_slot=slot, slot=s, item_id=0, stack=0)
            for s in range(59))
        for packet in packets:
            if not await self.conn.send_server_wait(packet):
                return False
        return True

    async def _handle_handshake_unified(self) -> bool:
        """统一握手循环：不等 WorldInfo，直接循环收包直到 AllowSpawn(49)。

        tML modded 客户端路径下，服务端在 SyncMods 后可能不按顺序发包。
        此函数处理所有中间包类型，不依赖特定顺序。
        """
        import asyncio
        deadline = asyncio.get_event_loop().time() + 60.0
        pkt_count = 0
        got_world_info = False
        got_tile_data = False

        _log("  HS-unified: 开始循环...")
        while asyncio.get_event_loop().time() < deadline:
            data = await self.conn.recv_server_packet(timeout=8.0)
            if data is None or len(data) == 0:
                continue
            pkt_count += 1
            pkt_type = data[0]
            _log(f"  HS pkt#{pkt_count}: type={pkt_type} (0x{pkt_type:02X}) len={len(data)}")

            # AllowSpawn → 退出
            if pkt_type == 49:
                _log("  HS: AllowSpawn(49)!")
                return True

            # WorldInfo → 发送 RequestTileData
            if pkt_type == 7:
                _log("  HS: WorldInfo(7), 发送 RequestTileData")
                if not await self.conn.send_server_wait(
                        self.packet.request_tile_data_packet()):
                    return False
                got_world_info = True
                continue

            # ConnectApproved → 更新 player_slot，主动请求 WorldInfo
            if pkt_type == 3:
                _log("  HS: ConnectApproved(3) - 更新 player_slot")
                if len(data) >= 2:
                    new_slot = data[1] & 0xFF
                    if new_slot != self.player_slot:
                        self.player_slot = new_slot
                        _log(f"  HS: player_slot 更新为 {self.player_slot}，重发玩家数据")
                        if not await self._send_player_data(self.player_name):
                            return False
                # tML 可能跳过 WorldInfo(7)，主动请求
                if not got_world_info:
                    _log("  HS: 主动请求 WorldInfo(6) + RequestTileData(8)")
                    if not await self.conn.send_server_wait(
                            self.packet.request_world_info_packet()):
                        return False
                    if not await self.conn.send_server_wait(
                            self.packet.request_tile_data_packet()):
                        return False
                    got_world_info = True
                continue

            # Tile data sections + PlayerBuffs(82) + 其他常见握手包 → 忽略
            if pkt_type in (10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22,
                             42, 45, 50, 77, 82, 130, 250):
                continue

            # 其他未知类型 → 记录但继续
            _log(f"  HS: 未知包 type={pkt_type}, 忽略")
            continue

        _log(f"  HS: 超时! 收到 {pkt_count} 个包")
        return False

    async def _handle_handshake_phase(self) -> bool:
        """保留旧接口兼容，委托给统一握手"""
        return await self._handle_handshake_unified()

    async def _handle_sync_mods(self, data: bytes) -> None:
        try:
            mod_list = self.packet.parse_sync_mods(data)
            _log(f"  SyncMods: {len(mod_list)} mods")
            reply = self.packet.build_sync_mods_reply(mod_list)
            if not await self.conn.send_server_wait(reply):
                _log("  SyncMods: 回复发送失败")
        except Exception as e:
            _log(f"  SyncMods ERROR: {e}")

    async def _heartbeat_loop(self) -> None:
        """后台循环：持续接收 7777 服务端包，维持连接不被关闭。"""
        _log("心跳循环: 开始")
        try:
            while self.logged_in and self.conn.connected:
                try:
                    data = await self.conn.recv_server_packet(timeout=5.0)
                    if data is None:
                        _log("心跳循环: recv 返回 None（超时或断开）")
                        continue
                except Exception as e:
                    _log(f"心跳循环: recv 异常 {type(e).__name__}: {e}")
                    break
        except Exception as e:
            _log(f"心跳循环: 外层异常 {type(e).__name__}: {e}")

        _log(f"心跳循环: 退出 (logged_in={self.logged_in}, connected={self.conn.connected})")

    async def _entity_sync_loop(self) -> None:
        """持续同步远程玩家状态，驱动 Terraria 原生实体渲染和动画。"""
        _log("实体同步循环: 开始")
        try:
            while self.logged_in and self.conn.connected:
                if self._position_ready:
                    packet = self.packet.player_controls_packet(
                        self.x, self.y, self.velocity_x, self.velocity_y,
                        player_slot=self.player_slot,
                        direction=self.direction,
                        moving_left=self.velocity_x < -0.01,
                        moving_right=self.velocity_x > 0.01,
                        jumping=self.velocity_y < -0.01)
                    if not await self.conn.send_server_wait(packet):
                        _log("实体同步循环: send 失败")
                        break
                await asyncio.sleep(0.1)
        except Exception as e:
            _log(f"实体同步循环: 异常 {type(e).__name__}: {e}")
            import traceback
            _log(traceback.format_exc())

        _log(f"实体同步循环: 退出 (logged_in={self.logged_in}, connected={self.conn.connected})")

    def sync_position(self, x: float, y: float) -> None:
        """用 Mod 观察到的机器人真实位置校准网络实体。"""
        if self._position_ready:
            return
        self.x = float(x)
        self.y = float(y)
        self._position_ready = True

    async def move_to(self, x: float, y: float,
                      duration: float = 0.5) -> bool:
        """平滑移动远程玩家，使位置、方向和走路动画保持一致。"""
        target_x, target_y = float(x), float(y)
        if not self._position_ready:
            self.x, self.y = target_x, target_y
            self._position_ready = True
            await self.conn.send_server_wait(self.packet.player_controls_packet(
                self.x, self.y, player_slot=self.player_slot))
            return True

        steps = max(1, int(max(0.1, duration) / 0.05))
        start_x, start_y = self.x, self.y
        self.velocity_x = (target_x - start_x) / max(duration, 0.1)
        self.velocity_y = (target_y - start_y) / max(duration, 0.1)
        self.direction = 1 if self.velocity_x >= 0 else -1
        for step in range(1, steps + 1):
            ratio = step / steps
            self.x = start_x + (target_x - start_x) * ratio
            self.y = start_y + (target_y - start_y) * ratio
            if not await self.conn.send_server_wait(
                    self.packet.player_controls_packet(
                        self.x, self.y, self.velocity_x, self.velocity_y,
                        player_slot=self.player_slot,
                        direction=self.direction,
                        moving_left=self.velocity_x < 0,
                        moving_right=self.velocity_x > 0,
                        jumping=self.velocity_y < 0)):
                return False
            await asyncio.sleep(0.05)
        self.velocity_x = self.velocity_y = 0.0
        return await self.conn.send_server_wait(
            self.packet.player_controls_packet(
                self.x, self.y, player_slot=self.player_slot,
                direction=self.direction))

    def send_msg(self, text: str) -> None:
        self.conn.send_server(self.packet.chat_packet(text, self.player_slot))

    def warp(self, x: float, y: float, vel_x: float = 0.0, vel_y: float = 0.0) -> None:
        self.conn.send_server(self.packet.warp_packet(x, y, vel_x, vel_y, self.player_slot))

    def damage_npc(self, npc_slot: int, damage: int) -> None:
        self.conn.send_server(self.packet.damage_npc_packet(npc_slot, damage))

    def summon_item(self, item_id: int, x: int, y: int, stack: int = 1) -> None:
        self.conn.send_server(self.packet.summon_item_packet(item_id, x, y, stack))

    async def request_mod(self, cmd: Dict[str, Any], timeout: float = 3.0) -> Optional[Dict[str, Any]]:
        return await self.conn.request_mod(cmd, timeout)
