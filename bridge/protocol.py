"""Terraria 协议包构造（基于真实抓包的 tModLoader 握手流程）。

抓包来源: capture_proxy.py 通过 7779 代理捕获的真实 tModLoader 客户端流量
服务端版本: tModLoader v2026.6.3.0 / Terraria 1.4.4.9
"""

import struct


class PacketManager:
    """构造发往 Terraria/tModLoader 服务端的协议包。"""

    DEFAULT_VERSION_STR = "tModLoader.v2026.6.3.0!2026.6.3"
    DEFAULT_DIFFICULTY = 0          # 0=Softcore(Classic), 1=Mediumcore, 2=Hardcore, 3=Journey

    def __init__(self) -> None:
        self.version_str: str = self.DEFAULT_VERSION_STR
        self.difficulty: int = self.DEFAULT_DIFFICULTY

    # ===== 底层包构建 =====

    @staticmethod
    def build(msg_type: int, data: bytes = b"") -> bytes:
        """构建标准 Terraria 协议包。

        格式（抓包验证）: [Length(2B LE)] [Type(1B)] [Data]
        Length 值 = 2(自身) + 1(type) + len(Data)
        """
        payload = bytes([msg_type]) + data
        length = len(payload) + 2
        return struct.pack("<H", length) + payload

    @staticmethod
    def _write7bit_encoded_int(value: int) -> bytes:
        """Terraria BinaryWriter.Write7BitEncodedInt: 7-bit 变长整数编码。

        参考 C# BinaryWriter.Write7BitEncodedInt:
          while value >= 0x80:
            write byte: (value & 0x7F) | 0x80
            value >>= 7
          write byte: value
        """
        result = bytearray()
        while value >= 0x80:
            result.append((value & 0x7F) | 0x80)
            value >>= 7
        result.append(value)
        return bytes(result)

    @staticmethod
    def _str(s: str) -> bytes:
        """旧版 Terraria 字符串格式：长度(1B) + UTF-8 数据。

        用于 Packet 1 (版本字符串)、Packet 4 (玩家外观/名字) 等旧协议包。
        """
        b = s.encode("utf-8")
        return struct.pack("<B", len(b)) + b

    @staticmethod
    def _str_7bit(s: str) -> bytes:
        """新版 Terraria BinaryWriter.WriteString 格式: [7-bit长度] + [UTF-8]。

        tModLoader 的 MessageBuffer 使用 C# BinaryReader.ReadString()
        读取密码等字段，长度部分用 7-bit 变长编码。
        """
        b = s.encode("utf-8")
        return PacketManager._write7bit_encoded_int(len(b)) + b

    @staticmethod
    def _byte(v: int) -> bytes:
        return struct.pack("<B", v & 0xFF)

    @staticmethod
    def _short(v: int) -> bytes:
        return struct.pack("<h", v)

    @staticmethod
    def _int32(v: int) -> bytes:
        return struct.pack("<i", v)

    @staticmethod
    def _float(v: float) -> bytes:
        return struct.pack("<f", v)

    # ===== 登录握手包 =====

    def connect_packet(self) -> bytes:
        """Packet 1: 连接请求 —— 发送 tModLoader 版本字符串。

        版本值由 self.version_str 决定 (可通过 Mod get_server_info 动态适配)。
        格式: "tModLoader.v{主版本}!{内部版本}"
        """
        version_str = self._str(self.version_str)
        return self.build(1, version_str)

    def password_packet(self, password: str) -> bytes:
        """Packet 0x26: 发送密码（响应服务端 Packet 37/GetPassword）。

        tModLoader 使用 C# BinaryReader.ReadString() 读取密码，
        字符串长度用 7-bit 变长编码！
        """
        data = self._str_7bit(password)
        return self.build(0x26, data)

    def player_appearance_packet(self, player_slot: int, name: str,
                                  skin_variant: int = 0, hair: int = 0,
                                  hair_dye: int = 0,
                                  hide_acc: int = 0, hide_acc_v2: int = 0,
                                  hide_misc: int = 0,
                                  hair_color: tuple = (255, 0, 255),
                                  skin_color: tuple = (255, 255, 255),
                                  eye_color: tuple = (0, 0, 255),
                                  shirt_color: tuple = (255, 255, 0),
                                  undershirt_color: tuple = (0, 255, 255),
                                  pants_color: tuple = (0, 255, 0),
                                  shoe_color: tuple = (255, 255, 255),
                                  difficulty: int = None) -> bytes:
        """Packet 4: 玩家外观信息

        difficulty: 玩家难度 (0=Softcore,1=Mediumcore,2=Hardcore,3=Journey)
                    默认由 self.difficulty 决定（可通过 Mod 动态适配）
        """
        if difficulty is None:
            difficulty = self.difficulty
        d = bytearray()
        d += self._byte(player_slot)
        d += self._byte(skin_variant)
        d += self._byte(hair)
        d += self._str(name)
        d += self._byte(hair_dye)
        d += self._byte(hide_acc)
        d += self._byte(hide_acc_v2)
        d += self._byte(hide_misc)
        d += self._byte(hair_color[0])
        d += self._byte(hair_color[1])
        d += self._byte(hair_color[2])
        d += self._byte(skin_color[0])
        d += self._byte(skin_color[1])
        d += self._byte(skin_color[2])
        d += self._byte(eye_color[0])
        d += self._byte(eye_color[1])
        d += self._byte(eye_color[2])
        d += self._byte(shirt_color[0])
        d += self._byte(shirt_color[1])
        d += self._byte(shirt_color[2])
        d += self._byte(undershirt_color[0])
        d += self._byte(undershirt_color[1])
        d += self._byte(undershirt_color[2])
        d += self._byte(pants_color[0])
        d += self._byte(pants_color[1])
        d += self._byte(pants_color[2])
        d += self._byte(shoe_color[0])
        d += self._byte(shoe_color[1])
        d += self._byte(shoe_color[2])
        d += self._byte(difficulty)
        return self.build(4, bytes(d))

    def player_life_packet(self, player_slot: int,
                           health: int = 400, max_health: int = 400) -> bytes:
        """Packet 10: 玩家生命值"""
        d = self._byte(player_slot)
        d += self._byte(0)
        d += self._short(health)
        d += self._byte(0)
        d += self._short(max_health)
        return self.build(10, d)

    def player_mana_packet(self, player_slot: int,
                           mana: int = 20, max_mana: int = 20) -> bytes:
        """Packet 0x2A: 玩家法力值"""
        d = self._byte(player_slot)
        d += self._byte(0)
        d += self._short(mana)
        d += self._byte(0)
        d += self._short(max_mana)
        return self.build(0x2A, d)

    def player_buffs_packet(self, player_slot: int) -> bytes:
        """Packet 0x32: 玩家 Buff 列表（22 个 buff 槽位，全部为 0）"""
        d = self._byte(player_slot)
        for _ in range(22):
            d += self._byte(0)
        return self.build(0x32, d)

    def set_inventory_packet(self, player_slot: int, slot: int,
                              item_id: int = 0, stack: int = 0,
                              prefix_id: int = 0) -> bytes:
        """Packet 5: 设置背包/装备栏物品"""
        d = self._byte(player_slot)
        d += self._byte(slot)
        d += self._short(stack)
        d += self._byte(prefix_id)
        d += self._short(item_id)
        return self.build(5, d)

    def request_world_info_packet(self) -> bytes:
        """Packet 6: 请求世界信息"""
        return self.build(6, b"")

    def request_tile_data_packet(self) -> bytes:
        """Packet 8: 请求初始地图瓦片数据"""
        return self.build(8, bytes.fromhex("ffffffffffffffff"))

    def spawn_player_packet(self, player_slot: int) -> bytes:
        """Packet 0xC: 生成/Spawn 玩家到世界。

        格式:
          [player_slot:1B] [ffffffff:4B] [00000000:4B] [05000000:4B] [01:1B]
        """
        payload = bytes([player_slot]) + bytes.fromhex("ffffffff000000000500000001")
        return self.build(0xC, payload)

    # ===== tModLoader SyncMods 包 =====

    @staticmethod
    def parse_sync_mods(data: bytes) -> list:
        """解析服务端发来的 SyncMods (Msg 251) 数据。

        抓包验证的格式:
          [int32: mod_count]
          FOR each mod:
            [string: mod_name]     (Terraria 字符串格式)
            [string: version]      (Terraria 字符串格式)
            [bytes20: sha1_hash]
            [int32: unknown]       (可能是文件数)

        Args:
            data: Msg 251 的 payload（不含长度头和类型字节）

        Returns:
            list of dict: [{"name": str, "version": str, "hash": bytes, "unknown": int}, ...]
        """
        mods = []
        offset = 0

        # 读 mod 数量 (int32)
        if offset + 4 > len(data):
            return mods
        mod_count = struct.unpack_from("<i", data, offset)[0]
        offset += 4

        for _ in range(mod_count):
            if offset >= len(data):
                break

            # 读 mod name (string)
            name_len = data[offset]
            offset += 1
            if offset + name_len > len(data):
                break
            name = data[offset:offset + name_len].decode("utf-8", errors="replace")
            offset += name_len

            # 读 version (string)
            if offset >= len(data):
                break
            ver_len = data[offset]
            offset += 1
            if offset + ver_len > len(data):
                break
            version = data[offset:offset + ver_len].decode("utf-8", errors="replace")
            offset += ver_len

            # 读 SHA1 hash (20 bytes)
            if offset + 20 > len(data):
                break
            mod_hash = data[offset:offset + 20]
            offset += 20

            # 读 unknown int32
            if offset + 4 > len(data):
                break
            unknown = struct.unpack_from("<i", data, offset)[0]
            offset += 4

            mods.append({
                "name": name,
                "version": version,
                "hash": mod_hash,
                "unknown": unknown,
            })

        return mods

    @staticmethod
    def build_sync_mods_reply(mod_list: list) -> bytes:
        """构造 SyncMods 回复包 (Msg 251 C→S)。

        Bot 策略: 原样回传服务端的 mod 列表，假装自己拥有所有 mod。
        这是最简单的通过方式——告诉服务端"我也有这些 mod"。

        Args:
            mod_list: parse_sync_mods() 返回的 mod 列表

        Returns:
            完整的 Msg 251 协议包（含长度头），可直接 send_server()
        """
        payload = bytearray()

        # mod 数量
        payload += struct.pack("<i", len(mod_list))

        for mod in mod_list:
            # mod name
            name_bytes = mod["name"].encode("utf-8")
            payload += struct.pack("<B", len(name_bytes))
            payload += name_bytes

            # version
            ver_bytes = mod["version"].encode("utf-8")
            payload += struct.pack("<B", len(ver_bytes))
            payload += ver_bytes

            # SHA1 hash (原样回传)
            payload += mod["hash"]

            # unknown int32 (原样回传)
            payload += struct.pack("<i", mod["unknown"])

        # 构建完整包: [Length][Type=251][Payload]
        data = bytes([0xFB]) + bytes(payload)
        length = len(data) + 2
        return struct.pack("<H", length) + data

    # ===== 游戏操作包 =====

    def chat_packet(self, text: str, player_slot: int = 0) -> bytes:
        """Packet 82: 发送聊天消息"""
        d = self._byte(1)
        d += self._byte(0)
        d += self._byte(player_slot)
        d += self._byte(0)
        d += self._str(text)
        d += self._byte(255)
        d += self._byte(255)
        d += self._byte(255)
        return self.build(82, d)

    def player_controls_packet(self, x: float, y: float,
                               vel_x: float = 0.0, vel_y: float = 0.0,
                               player_slot: int = 0, direction: int = 1,
                               selected_item: int = 0,
                               moving_left: bool = False,
                               moving_right: bool = False,
                               jumping: bool = False,
                               using_item: bool = False) -> bytes:
        """Packet 13: 同步远程玩家位置、方向和动作状态。"""
        controls = 0
        if moving_left:
            controls |= 0x04
        if moving_right:
            controls |= 0x08
        if jumping:
            controls |= 0x10
        if using_item:
            controls |= 0x20
        if direction > 0:
            controls |= 0x40

        d = self._byte(player_slot)
        d += self._byte(controls)
        d += self._byte(0)  # pulley flags
        d += self._byte(0x04)  # misc flags: velocity 字段存在
        d += self._byte(selected_item)
        d += self._float(x)
        d += self._float(y)
        d += self._float(vel_x)
        d += self._float(vel_y)
        return self.build(13, d)

    def warp_packet(self, x: float, y: float,
                    vel_x: float = 0.0, vel_y: float = 0.0,
                    player_slot: int = 0) -> bytes:
        """兼容旧调用：发送静止状态的 PlayerControls。"""
        return self.player_controls_packet(
            x, y, vel_x, vel_y, player_slot=player_slot)

    def damage_npc_packet(self, npc_slot: int, damage: int) -> bytes:
        """Packet 28: 对 NPC 造成伤害"""
        d = self._short(npc_slot)
        d += self._short(damage)
        d += self._float(4.657323415813153e-10)
        d += self._byte(0)
        d += self._byte(0)
        return self.build(28, d)

    def summon_item_packet(self, item_id: int, x: int, y: int,
                            stack: int = 1, item_slot: int = 0) -> bytes:
        """Packet 90: 召唤物品到指定位置"""
        import struct as _st
        payload = _st.pack("<iiii", item_id, x, y, stack)
        return self.build(90, payload)
