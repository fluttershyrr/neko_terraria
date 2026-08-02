using System;
using System.Collections.Generic;
using System.Linq;
using System.Net;
using System.Net.Sockets;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using Terraria;
using Terraria.ModLoader;
using Terraria.ModLoader.Core;
using Terraria.ID;
using Terraria.DataStructures;
using Microsoft.Xna.Framework;

namespace NekoTerrariaLink
{
    public class NekoTerrariaLink : Mod
    {
        // ModConfig 实例（游戏内模组设置）。tModLoader 会自动加载。
        public NekoConfig Config => ModContent.GetInstance<NekoConfig>();

        private TcpListener _listener;
        private Thread _listenThread;
        private readonly object _lock = new object();

        // 统一的实体来源，用于 QuickSpawnItem / DropItem（1.4 要求 IEntitySource）
        private sealed class NekoEntitySource : IEntitySource
        {
            public string Context => "NekoTerrariaLink";
        }
        private static readonly IEntitySource Src = new NekoEntitySource();

        public override void Load()
        {
            // 读取模组设置中的监听端口（默认 9877），须与插件端 mod_port 一致
            int port = 9877;
            try
            {
                var cfg = ModContent.GetInstance<NekoConfig>();
                if (cfg != null) port = cfg.ModPort;
            }
            catch { /* Config 可能尚未就绪，使用默认端口 */ }

            // 尝试启动监听器，如果端口被占用则尝试其他端口
            bool started = false;
            int finalPort = port;

            for (int tryPort = port; tryPort < port + 10 && !started; tryPort++)
            {
                try
                {
                    _listener = new TcpListener(IPAddress.Loopback, tryPort);
                    // 启用 SO_REUSEADDR，允许端口快速重用
                    _listener.Server.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.ReuseAddress, true);
                    _listener.Start();
                    _listenThread = new Thread(ListenLoop) { IsBackground = true };
                    _listenThread.Start();
                    finalPort = tryPort;
                    started = true;

                    if (tryPort == port)
                    {
                        Logger.Info($"NekoTerrariaLink: 监听端口 {tryPort} 启动成功");
                    }
                    else
                    {
                        Logger.Warn($"NekoTerrariaLink: 默认端口 {port} 被占用，使用备用端口 {tryPort}");
                    }
                }
                catch (SocketException ex) when (ex.SocketErrorCode == SocketError.AddressAlreadyInUse)
                {
                    // 端口被占用，尝试下一个
                    if (tryPort == port + 9)
                    {
                        // 最后一次尝试也失败了
                        Logger.Error($"NekoTerrariaLink: 端口 {port}-{port+9} 全部被占用");
                        Logger.Error("解决方案:");
                        Logger.Error("  1. 使用命令: netstat -ano | findstr \"987\"");
                        Logger.Error("  2. 使用命令: taskkill /F /PID <进程ID>");
                        Logger.Error("  3. 或者重启计算机清理所有残留进程");
                    }
                    continue;
                }
                catch (Exception ex)
                {
                    Logger.Error($"NekoTerrariaLink: 端口 {tryPort} 启动失败 - {ex.Message}");
                    break;
                }
            }
        }

        public override void Unload()
        {
            try { _listener?.Stop(); } catch { }
        }

        private void ListenLoop()
        {
            while (true)
            {
                try
                {
                    using var client = _listener.AcceptTcpClient();
                    var stream = client.GetStream();
                    var buf = new byte[4096];
                    var sb = new StringBuilder();
                    int n;
                    while ((n = stream.Read(buf, 0, buf.Length)) > 0)
                    {
                        sb.Append(Encoding.UTF8.GetString(buf, 0, n));
                        string text = sb.ToString();
                        int idx;
                        while ((idx = text.IndexOf('\n')) >= 0)
                        {
                            string line = text.Substring(0, idx).Trim();
                            text = text.Substring(idx + 1);
                            if (line.Length > 0) HandleLine(line, stream);
                        }
                        sb.Clear(); sb.Append(text);
                    }
                }
                catch { Thread.Sleep(500); }
            }
        }

        private void HandleLine(string line, NetworkStream stream)
        {
            var cmd = JsonParser.Parse(line);
            if (cmd == null) return;
            // 透传 req_id：Python 侧用它把回执与请求一一对应，避免串线
            long reqId = (long)cmd.GetNum("req_id");
            // 每次命令都是一次性脉冲：先清上一帧的 use/hook，避免持续触发
            var p0 = Main.LocalPlayer;
            if (p0 != null) { p0.controlUseItem = false; p0.controlHook = false; }
            string type = cmd == null ? "" : cmd.GetValue("cmd");
            switch (type)
            {
                case "move": SendAck(stream, reqId, Move(cmd)); break;
                case "place_tile": SendAck(stream, reqId, PlaceTile(cmd)); break;
                case "break_tile": SendAck(stream, reqId, BreakTile(cmd)); break;
                case "hook": SendAck(stream, reqId, Hook(cmd)); break;
                case "use_item": SendAck(stream, reqId, UseItem(cmd)); break;
                case "select_item": SendAck(stream, reqId, SelectItem(cmd)); break;
                case "craft": SendCraft(stream, reqId, Craft(cmd)); break;
                case "equip": SendAck(stream, reqId, Equip(cmd)); break;
                case "give_item": SendAck(stream, reqId, GiveItem(cmd)); break;
                case "drop_item": SendAck(stream, reqId, DropItem(cmd)); break;
                case "use_item_slot": SendAck(stream, reqId, UseItemSlot(cmd)); break;
                case "navigate_to": NavigateTo(stream, cmd, reqId); break;
                case "get_inventory": SendInventory(stream, reqId); break;
                case "enum_chests": SendChests(stream, reqId); break;
                case "store_item": SendAck(stream, reqId, StoreItem(cmd)); break;
                case "take_chest": SendAck(stream, reqId, TakeFromChest(cmd)); break;
                case "get_recipes": SendRecipes(stream, reqId, cmd.GetValue("cat")); break;
                case "get_state": SendState(stream, reqId, cmd.GetValue("player_name")); break;
                case "enum_items": SendItemRegistry(stream, reqId); break;
                case "get_capabilities": SendCapabilities(stream, reqId); break;
                case "scan_ledges": SendLedges(stream, reqId, cmd); break;
                case "get_server_info": SendServerInfo(stream, reqId); break;
            }
        }

        private bool Move(Dict cmd)
        {
            var dirs = cmd.GetArray("dirs") ?? new List<string> { cmd.GetValue("direction") };
            var player = Main.LocalPlayer;
            player.controlLeft = player.controlRight = player.controlJump
                = player.controlUp = player.controlDown = false;
            foreach (var d in dirs)
            {
                switch (d)
                {
                    case "left": player.controlLeft = true; break;
                    case "right": player.controlRight = true; break;
                    case "jump": player.controlJump = true; break;
                    case "up": player.controlUp = true; break;
                    case "down": player.controlDown = true; break;
                }
            }
            return true;
        }

        private bool BreakTile(Dict cmd)
        {
            int x = (int)cmd.GetNum("x"), y = (int)cmd.GetNum("y");
            WorldGen.KillTile(x, y, false, false, true);
            return true;
        }

        private bool PlaceTile(Dict cmd)
        {
            int x = (int)cmd.GetNum("x"), y = (int)cmd.GetNum("y");
            int tile = (int)cmd.GetNum("tile");
            return WorldGen.PlaceTile(x, y, tile, false, false, -1, 0);
        }

        private bool Hook(Dict cmd)
        {
            var player = Main.LocalPlayer;
            player.controlHook = true;
            return true;
        }

        private bool UseItem(Dict cmd)
        {
            var player = Main.LocalPlayer;
            player.controlUseItem = true;
            return true;
        }

        private bool SelectItem(Dict cmd)
        {
            int slot = (int)cmd.GetNum("slot");
            Main.LocalPlayer.selectedItem = slot;
            return true;
        }

        private int Craft(Dict cmd)
        {
            int id = (int)cmd.GetNum("item_id");
            int amount = (int)(cmd.GetNum("amount") > 0 ? cmd.GetNum("amount") : 1);
            var player = Main.LocalPlayer;
            var item = new Item();
            item.SetDefaults(id);
            if (item.type == 0) return 0;
            item.stack = amount;
            player.QuickSpawnItem(Src, item, amount);
            return amount;
        }

        private bool Equip(Dict cmd)
        {
            int inv = (int)cmd.GetNum("inv"), equip = (int)cmd.GetNum("equip");
            var player = Main.LocalPlayer;
            if (inv >= 0 && inv < player.inventory.Length)
            {
                var item = player.inventory[inv];
                player.armor[equip] = item.Clone();
                return true;
            }
            return false;
        }

        private bool GiveItem(Dict cmd)
        {
            int id = (int)cmd.GetNum("item_id"), stack = (int)cmd.GetNum("stack");
            var player = Main.LocalPlayer;
            var item = new Item();
            item.SetDefaults(id);
            item.stack = stack;
            player.QuickSpawnItem(Src, item, stack);
            return true;
        }

        private void SendInventory(NetworkStream s, long reqId)
        {
            var player = Main.LocalPlayer;
            var hotbar = new List<Dict>();
            var inv = new List<Dict>();
            for (int i = 0; i < player.inventory.Length; i++)
            {
                var it = player.inventory[i];
                if (it.type == 0) continue;
                var entry = new Dict {
                    ["id"] = it.type, ["stack"] = it.stack, ["inv_slot"] = i,
                    ["name"] = it.Name, ["defense"] = it.defense,
                };
                if (i >= 0 && i < 10) hotbar.Add(entry);
                else if (i >= 10 && i < 50) inv.Add(entry);
            }
            var equipped = new List<Dict>();
            for (int a = 0; a < player.armor.Length; a++)
            {
                var it = player.armor[a];
                if (it.type == 0) continue;
                equipped.Add(new Dict {
                    ["id"] = it.type, ["stack"] = it.stack, ["armor_slot"] = a,
                    ["name"] = it.Name, ["defense"] = it.defense,
                });
            }
            Send(s, new Dict {
                ["req_id"] = reqId, ["type"] = "inventory",
                ["hotbar"] = hotbar, ["equipped"] = equipped, ["inventory"] = inv,
                ["selected_slot"] = player.selectedItem,
            });
        }

        private bool DropItem(Dict cmd)
        {
            int slot = (int)cmd.GetNum("slot");
            int stack = (int)(cmd.GetNum("stack") > 0 ? cmd.GetNum("stack") : 1);
            var player = Main.LocalPlayer;
            if (slot < 0 || slot >= player.inventory.Length) return false;
            var item = player.inventory[slot];
            if (item.type == 0) return false;
            var drop = item.Clone();
            drop.stack = Math.Min(stack, item.stack);
            player.inventory[slot].stack -= drop.stack;
            if (player.inventory[slot].stack <= 0)
                player.inventory[slot].SetDefaults(0);
            Item d = drop;
            player.DropItem(Src, player.Center, ref d);
            return true;
        }

        private bool UseItemSlot(Dict cmd)
        {
            int slot = (int)cmd.GetNum("slot");
            var player = Main.LocalPlayer;
            if (slot < 0 || slot >= player.inventory.Length) return false;
            if (player.inventory[slot].type == 0) return false;
            player.selectedItem = slot;
            player.controlUseItem = true;
            return true;
        }

        private void NavigateTo(NetworkStream s, Dict cmd, long reqId)
        {
            int tx = (int)cmd.GetNum("x"), ty = (int)cmd.GetNum("y");
            int timeout = (int)(cmd.GetNum("timeout") > 0 ? cmd.GetNum("timeout") : 15);
            Task.Run(() => NavigateSync(s, tx, ty, timeout, reqId));
        }

        private void NavigateSync(NetworkStream s, int tx, int ty, int timeout, long reqId)
        {
            var player = Main.LocalPlayer;
            if (player == null) { Send(s, new Dict { ["req_id"] = reqId, ["ok"] = false, ["reason"] = "no_player" }); return; }
            int steps = 0;
            int maxSteps = timeout * 10;
            int stuckCounter = 0;
            int lastPx = 0, lastPy = 0;
            int jumpHold = 0;
            bool arrived = false;
            while (steps < maxSteps)
            {
                int px = (int)(player.Center.X / 16);
                int py = (int)(player.Center.Y / 16);
                int dx = tx - px;
                int dy = ty - py;
                if (Math.Abs(dx) <= 1 && Math.Abs(dy) <= 1) { arrived = true; break; }

                player.controlLeft = player.controlRight = false;
                if (jumpHold <= 0) player.controlJump = false;
                else jumpHold--;

                int dir = dx > 0 ? 1 : -1;
                bool onGround = (player.velocity.Y == 0);

                bool footSolid = IsStandable(px + dir, py + 1) || IsStandable(px + dir, py + 2);
                bool aheadSolid = IsSolid(px + dir, py) || IsSolid(px + dir, py - 1) || IsSolid(px + dir, py - 2);
                bool headSolid = IsSolid(px, py - 3);

                if (dx != 0) { if (dx > 0) player.controlRight = true; else player.controlLeft = true; }

                if (aheadSolid && onGround && jumpHold <= 0)
                {
                    player.controlJump = true; jumpHold = 8;
                }
                else if (headSolid && onGround && jumpHold <= 0)
                {
                    player.controlJump = true; jumpHold = 8;
                }
                else if (!footSolid && onGround)
                {
                    player.controlLeft = player.controlRight = false;
                    if (!TryBridge(px, py, dir))
                    {
                        if (!TryHook(dir)) Thread.Sleep(100);
                    }
                }

                if (px == lastPx && py == lastPy)
                {
                    stuckCounter++;
                    if (stuckCounter > 20) { TryStepUp(px, py); stuckCounter = 0; }
                }
                else { stuckCounter = 0; lastPx = px; lastPy = py; }

                Thread.Sleep(100);
                steps++;
            }
            player.controlLeft = player.controlRight = player.controlJump = player.controlHook = false;
            Send(s, new Dict { ["req_id"] = reqId, ["ok"] = arrived, ["x"] = (int)(player.Center.X / 16), ["y"] = (int)(player.Center.Y / 16) });
        }

        private bool IsSolid(int x, int y)
        {
            if (x < 0 || y < 0 || x >= Main.maxTilesX || y >= Main.maxTilesY) return false;
            var t = Main.tile[x, y];
            if (t == null || !t.HasTile) return false;
            int type = t.TileType;
            if (type == 19 || type == 51 || type == 52 || type == 382 || type == 385 || type == 387 || type == 388) return false;
            return true;
        }

        private bool IsStandable(int x, int y)
        {
            if (x < 0 || y < 0 || x >= Main.maxTilesX || y >= Main.maxTilesY) return false;
            var t = Main.tile[x, y];
            if (t == null || !t.HasTile) return false;
            return true;
        }

        private bool TryBridge(int px, int py, int dir)
        {
            int bx = px + dir, by = py + 1;
            if (IsStandable(bx, by)) return false;
            bool placed = false;
            Main.QueueMainThreadAction(() =>
            {
                placed = WorldGen.PlaceTile(bx, by, 0, false, false, -1, 0);
            });
            for (int i = 0; i < 10 && !placed; i++) Thread.Sleep(20);
            return placed;
        }

        private bool TryStepUp(int px, int py)
        {
            bool placed = false;
            Main.QueueMainThreadAction(() =>
            {
                if (!IsStandable(px, py + 1))
                    placed = WorldGen.PlaceTile(px, py + 1, 0, false, false, -1, 0);
                else
                    placed = WorldGen.PlaceTile(px, py - 1, 0, false, false, -1, 0);
            });
            for (int i = 0; i < 10 && !placed; i++) Thread.Sleep(20);
            return placed;
        }

        private bool TryHook(int dir)
        {
            var player = Main.LocalPlayer;
            if (player == null || !HasHook(player)) return false;
            player.controlHook = true;
            Thread.Sleep(400);
            player.controlHook = false;
            return true;
        }

        private static bool HasHook(Player player)
        {
            // 1.4：检测背包是否持有钩爪。无直接 API 时，用 ProjectileID 钩爪列表判断：
            // 钩爪弹幕的 aiStyle 为 7（钩爪），遍历背包检查持有物是否发射该风格弹幕。
            for (int i = 0; i < player.inventory.Length; i++)
            {
                var it = player.inventory[i];
                if (it.shoot > 0)
                {
                    try
                    {
                        var proj = ContentSamples.ProjectilesByType[it.shoot];
                        if (proj != null && proj.aiStyle == 7) return true;
                    }
                    catch { }
                }
            }
            return false;
        }

        private void SendChests(NetworkStream s, long reqId)
        {
            var player = Main.LocalPlayer;
            var list = new List<Dict>();
            int px = (int)(player.Center.X / 16), py = (int)(player.Center.Y / 16);
            for (int i = 0; i < Main.chest.Length; i++)
            {
                var c = Main.chest[i];
                if (c == null || c.x <= 0 || c.y <= 0) continue;
                var contents = new List<Dict>();
                for (int k = 0; k < c.item.Length; k++)
                {
                    var it = c.item[k];
                    if (it.type == 0) continue;
                    contents.Add(new Dict { ["id"] = it.type, ["name"] = it.Name, ["stack"] = it.stack });
                }
                int dist = Math.Abs(c.x - px) + Math.Abs(c.y - py);
                list.Add(new Dict { ["index"] = i, ["x"] = c.x, ["y"] = c.y, ["dist"] = dist, ["items"] = contents });
            }
            Send(s, new Dict { ["req_id"] = reqId, ["type"] = "chests", ["chests"] = list });
        }

        private int OpenChestNear(int x, int y)
        {
            var player = Main.LocalPlayer;
            int px = (int)(player.Center.X / 16), py = (int)(player.Center.Y / 16);
            if (Math.Abs(px - x) > 4 || Math.Abs(py - y) > 4) return -1;
            int idx = Chest.FindChest(x, y);
            if (idx < 0) return -1;
            player.chest = idx;
            return idx;
        }

        private bool StoreItem(Dict cmd)
        {
            // 直接操作箱子物品槽（最稳，不依赖 Chest 的 put API 重载差异）
            int x = (int)cmd.GetNum("x"), y = (int)cmd.GetNum("y");
            int slot = (int)cmd.GetNum("slot");
            int stack = (int)(cmd.GetNum("stack") > 0 ? cmd.GetNum("stack") : 1);
            var player = Main.LocalPlayer;
            int idx = OpenChestNear(x, y);
            if (idx < 0) return false;
            try
            {
                var src = player.inventory[slot];
                if (src.type == 0) return false;
                var chest = Main.chest[idx];
                for (int k = 0; k < chest.item.Length; k++)
                {
                    var ci = chest.item[k];
                    if (ci.type == 0)
                    {
                        var nw = src.Clone();
                        nw.stack = Math.Min(stack, src.stack);
                        chest.item[k] = nw;
                        return true;
                    }
                    if (ci.type == src.type && ci.stack < ci.maxStack)
                    {
                        int add = Math.Min(stack, Math.Min(src.stack, ci.maxStack - ci.stack));
                        ci.stack += add;
                        src.stack -= add;
                        if (src.stack <= 0) src.SetDefaults(0);
                        return true;
                    }
                }
                return false;
            }
            finally { player.chest = -1; }
        }

        private bool TakeFromChest(Dict cmd)
        {
            int x = (int)cmd.GetNum("x"), y = (int)cmd.GetNum("y");
            int id = (int)cmd.GetNum("item_id");
            int stack = (int)(cmd.GetNum("stack") > 0 ? cmd.GetNum("stack") : 1);
            var player = Main.LocalPlayer;
            int idx = OpenChestNear(x, y);
            if (idx < 0) return false;
            try
            {
                var chest = Main.chest[idx];
                for (int k = 0; k < chest.item.Length; k++)
                {
                    var it = chest.item[k];
                    if (it.type != id || it.stack <= 0) continue;
                    int take = Math.Min(stack, it.stack);
                    var got = it.Clone(); got.stack = take;
                    player.QuickSpawnItem(Src, got, take);
                    it.stack -= take;
                    if (it.stack <= 0) it.SetDefaults(0);
                    return true;
                }
                return false;
            }
            finally { player.chest = -1; }
        }

        private void SendCapabilities(NetworkStream s, long reqId)
        {
            var player = Main.LocalPlayer;
            bool hasHook = player != null && HasHook(player);
            int dirtCount = 0, hasPick = 0, pickPower = 0, rope = 0;
            if (player != null)
            {
                for (int i = 0; i < player.inventory.Length; i++)
                {
                    var it = player.inventory[i];
                    if (it.type == 0) continue;
                    if (it.type == 0 || it.type == 1) dirtCount += it.stack;
                    if (it.pick > 0) { hasPick = 1; pickPower = Math.Max(pickPower, it.pick); }
                    if (it.createTile == 65 || it.createTile == 415) rope += it.stack;
                }
            }
            Send(s, new Dict {
                ["req_id"] = reqId, ["type"] = "capabilities",
                ["has_hook"] = hasHook, ["hook_range"] = hasHook ? 22 : 0,
                ["dirt_count"] = dirtCount, ["has_pickaxe"] = hasPick == 1,
                ["pickaxe_power"] = pickPower, ["rope_count"] = rope,
                ["nearby_stations"] = NearbyStations(player),
            });
        }

        private List<string> NearbyStations(Player player)
        {
            var names = new List<string>();
            if (player == null) return names;
            int px = (int)(player.Center.X / 16), py = (int)(player.Center.Y / 16);
            const int R = 6;
            var seen = new HashSet<int>();
            for (int x = px - R; x <= px + R; x++)
            {
                for (int y = py - R; y <= py + R; y++)
                {
                    if (x < 0 || y < 0 || x >= Main.maxTilesX || y >= Main.maxTilesY) continue;
                    var t = Main.tile[x, y];
                    if (t == null || !t.HasTile) continue;
                    int type = t.TileType;
                    if (seen.Contains(type)) continue;
                    seen.Add(type);
                    if (Main.tileTable[type] || type == TileID.WorkBenches || type == TileID.Furnaces
                        || type == TileID.Anvils || type == TileID.MythrilAnvil || type == TileID.AdamantiteForge
                        || type == TileID.Hellforge || type == TileID.Bottles || type == TileID.CookingPots
                        || type == TileID.Loom || type == TileID.Sawmill || type == TileID.TinkerersWorkbench
                        || type == TileID.AlchemyTable)
                    {
                        names.Add(TileName(type));
                    }
                }
            }
            return names;
        }

        private void SendLedges(NetworkStream s, long reqId, Dict cmd)
        {
            int x0 = (int)cmd.GetNum("x0"), y0 = (int)cmd.GetNum("y0");
            int x1 = (int)cmd.GetNum("x1"), y1 = (int)cmd.GetNum("y1");
            int loY = Math.Min(y0, y1), hiY = Math.Max(y0, y1);
            int loX = Math.Max(0, Math.Min(x0, x1) - 40);
            int hiX = Math.Min(Main.maxTilesX - 1, Math.Max(x0, x1) + 40);
            var found = new List<Dict>();
            var foundY = new List<int>();
            for (int y = hiY - 1; y >= loY && found.Count < 24; y--)
            {
                int bestX = -1, bestDist = int.MaxValue;
                for (int x = loX; x <= hiX; x++)
                {
                    if (!IsStandable(x, y)) continue;
                    if (IsSolid(x, y - 1) || IsSolid(x, y - 2)) continue;
                    int d = Math.Abs(x - x0);
                    if (d < bestDist) { bestDist = d; bestX = x; }
                }
                if (bestX < 0) continue;
                bool tooClose = false;
                foreach (int py in foundY)
                    if (Math.Abs(py - (y - 1)) < 6) { tooClose = true; break; }
                if (tooClose) continue;
                found.Add(new Dict { ["x"] = bestX, ["y"] = y - 1 });
                foundY.Add(y - 1);
            }
            Send(s, new Dict { ["req_id"] = reqId, ["type"] = "ledges", ["points"] = found });
        }

        private void SendServerInfo(NetworkStream s, long reqId)
        {
            // 构建 tModLoader 版本字符串 (Packet 1 格式: tModLoader.v{全版本}!{短版本})
            // BuildInfo.tMLVersion 在此 tModLoader 版本中返回 System.Version 对象，需 ToString()
            string tmlVer = "";
            try { tmlVer = BuildInfo.tMLVersion?.ToString() ?? ""; } catch { }
            if (string.IsNullOrEmpty(tmlVer)) tmlVer = "2026.6.3.0";
            string shortVer = tmlVer;
            int lastDot = tmlVer.LastIndexOf('.');
            if (lastDot > 0) shortVer = tmlVer.Substring(0, lastDot);
            string versionStr = $"tModLoader.v{tmlVer}!{shortVer}";

            // 世界难度 (0=Classic, 1=Expert, 2=Master, 3=Journey)
            int gameMode = Main.GameMode;

            // 世界大小
            string worldSize = "Small";
            if (Main.maxTilesX >= 8400) worldSize = "Large";
            else if (Main.maxTilesX >= 6300) worldSize = "Medium";

            // 邪恶类型
            string evilType = WorldGen.crimson ? "Crimson" : "Corruption";

            // 世界名称
            string worldName = Main.worldName ?? "";

            Send(s, new Dict {
                ["req_id"] = reqId, ["type"] = "server_info",
                ["tmod_version_str"] = versionStr,
                ["tmod_version"] = tmlVer,
                ["terraria_version"] = Main.versionNumber ?? "",
                ["game_mode"] = gameMode,
                ["world_size"] = worldSize,
                ["evil_type"] = evilType,
                ["world_name"] = worldName,
            });
        }

        private void SendRecipes(NetworkStream s, long reqId, string cat)
        {
            bool onlyAvailable = cat == "available";
            var list = new List<Dict>();
            for (int i = 0; i < Recipe.numRecipes; i++)
            {
                Recipe r = Main.recipe[i];
                if (r == null || r.createItem == null || r.createItem.type <= 0) continue;
                if (onlyAvailable && !RecipeAvailable(r)) continue;

                var mats = new List<Dict>();
                foreach (var ing in r.requiredItem)
                {
                    if (ing == null || ing.type <= 0 || ing.stack <= 0) continue;
                    mats.Add(new Dict { ["id"] = ing.type, ["name"] = ing.Name, ["stack"] = ing.stack });
                }
                if (mats.Count == 0) continue;

                var stations = new List<Dict>();
                foreach (var tile in r.requiredTile)
                {
                    if (tile <= 0) continue;
                    stations.Add(new Dict { ["tile"] = tile, ["name"] = TileName(tile) });
                }

                var createItem = r.createItem;
                string modName = createItem.ModItem == null ? "Terraria" : createItem.ModItem.Mod.Name;

                list.Add(new Dict {
                    ["item_id"] = createItem.type, ["name"] = createItem.Name,
                    ["amount"] = createItem.stack, ["mod"] = modName,
                    ["available"] = RecipeAvailable(r),
                    ["materials"] = mats, ["stations"] = stations,
                });
            }
            Send(s, new Dict { ["req_id"] = reqId, ["type"] = "recipes", ["recipes"] = list });
        }

        private static bool RecipeAvailable(Recipe r)
        {
            var player = Main.LocalPlayer;
            if (player == null) return false;
            foreach (var ing in r.requiredItem)
            {
                if (ing == null || ing.type <= 0 || ing.stack <= 0) continue;
                if (player.CountItem(ing.type) < ing.stack) return false;
            }
            return true;
        }

        private string TileName(int tile)
        {
            try
            {
                var mt = TileLoader.GetTile(tile);
                if (mt != null) return mt.Name;
            }
            catch { }
            switch (tile)
            {
                case TileID.WorkBenches: return "Work Bench";
                case TileID.Furnaces: return "Furnace";
                case TileID.Anvils: return "Iron Anvil";
                case TileID.MythrilAnvil: return "Mythril Anvil";
                case TileID.AdamantiteForge: return "Adamantite Forge";
                case TileID.Hellforge: return "Hellforge";
                case TileID.Bottles: return "Bottle";
                case TileID.Tables: return "Table";
                case TileID.CookingPots: return "Cooking Pot";
                case TileID.Loom: return "Loom";
                case TileID.Sawmill: return "Sawmill";
                case TileID.TinkerersWorkbench: return "Tinkerer's Workshop";
                case TileID.AlchemyTable: return "Alchemy Table";
                default: return "Tile" + tile;
            }
        }

        private Player FindTrackedPlayer(string playerName)
        {
            if (!string.IsNullOrWhiteSpace(playerName))
            {
                // 统计在线玩家
                int onlineCount = 0;
                string onlineNames = "";

                // 遍历所有玩家槽位，寻找匹配的在线玩家
                for (int i = 0; i < Main.maxPlayers; i++)
                {
                    if (i >= Main.player.Length) break; // 防止数组越界
                    var candidate = Main.player[i];
                    if (candidate != null && candidate.active)
                    {
                        onlineCount++;
                        if (onlineNames.Length > 0) onlineNames += ", ";
                        onlineNames += candidate.name;

                        if (string.Equals(candidate.name, playerName,
                            StringComparison.OrdinalIgnoreCase))
                        {
                            ModContent.GetInstance<NekoTerrariaLink>().Logger.Debug(
                                $"FindTrackedPlayer: 找到玩家 '{playerName}' 在槽位 {i}");
                            return candidate;
                        }
                    }
                }
                // 未找到玩家
                ModContent.GetInstance<NekoTerrariaLink>().Logger.Debug(
                    $"FindTrackedPlayer: 未找到玩家 '{playerName}'，当前在线 {onlineCount} 人: {onlineNames}");
            }
            return string.IsNullOrWhiteSpace(playerName) ? Main.LocalPlayer : null;
        }

        private void SendState(NetworkStream s, long reqId, string playerName)
        {
            var p = FindTrackedPlayer(playerName);
            if (p == null)
            {
                ModContent.GetInstance<NekoTerrariaLink>().Logger.Warn(
                    $"SendState: 玩家 '{playerName}' 不在线，无法返回状态");
                Send(s, new Dict {
                    ["req_id"] = reqId, ["type"] = "state", ["found"] = false,
                });
                return;
            }
            var npcs = new List<Dict>();
            for (int i = 0; i < Main.npc.Length; i++)
            {
                var npc = Main.npc[i];
                if (npc.active && npc.life > 0)
                {
                    int dx = (int)(npc.Center.X / 16 - p.Center.X / 16);
                    int dy = (int)(npc.Center.Y / 16 - p.Center.Y / 16);
                    if (Math.Abs(dx) < 50 && Math.Abs(dy) < 50)
                        npcs.Add(new Dict {
                            ["name"] = npc.TypeName, ["slot"] = i, ["life"] = npc.life,
                            ["tileX"] = (int)(npc.Center.X / 16), ["tileY"] = (int)(npc.Center.Y / 16),
                            ["damage"] = npc.damage,
                        });
                }
            }
            var players = new List<Dict>();
            for (int i = 0; i < Main.player.Length; i++)
            {
                var pl = Main.player[i];
                if (pl != null && pl.active && pl != p)
                {
                    int dx = (int)(pl.Center.X / 16 - p.Center.X / 16);
                    int dy = (int)(pl.Center.Y / 16 - p.Center.Y / 16);
                    if (Math.Abs(dx) < 80 && Math.Abs(dy) < 80)
                        players.Add(new Dict { ["name"] = pl.name, ["tile_x"] = (int)(pl.Center.X / 16), ["tile_y"] = (int)(pl.Center.Y / 16) });
                }
            }
            Send(s, new Dict {
                ["req_id"] = reqId, ["type"] = "state",
                ["player"] = new Dict {
                    ["name"] = p.name, ["hp"] = p.statLife, ["maxLife"] = p.statLifeMax,
                    ["mana"] = p.statMana, ["maxMana"] = p.statManaMax,
                    ["x"] = p.position.X, ["y"] = p.position.Y,
                    ["tileX"] = (int)(p.Center.X / 16), ["tileY"] = (int)(p.Center.Y / 16),
                    ["velocityX"] = p.velocity.X, ["velocityY"] = p.velocity.Y,
                    ["grounded"] = p.velocity.Y == 0, ["selectedItem"] = p.selectedItem,
                },
                ["nearbyNpcs"] = npcs, ["nearbyPlayers"] = players,
                ["time"] = new Dict { ["dayTime"] = Main.dayTime, ["time"] = Main.time },
            });
        }

        private void SendAck(NetworkStream s, long reqId, bool ok) =>
            Send(s, new Dict { ["req_id"] = reqId, ["ok"] = ok });

        private void SendCraft(NetworkStream s, long reqId, int n) =>
            Send(s, new Dict { ["req_id"] = reqId, ["crafted"] = n });

        private void SendItemRegistry(NetworkStream s, long reqId)
        {
            var byMod = new Dictionary<string, List<Dict>>();
            for (int i = 0; i < ItemLoader.ItemCount; i++)
            {
                var modItem = ItemLoader.GetItem(i);
                if (modItem == null || modItem.Name == null || modItem.Name.Length == 0) continue;
                string modName = modItem.Mod == null ? "Terraria" : modItem.Mod.Name;
                // ItemUse/ItemTags 接收 Item 实例，用物品 ID 构造一个 Item 传入
                var itemInst = new Item();
                itemInst.SetDefaults(i);
                if (!byMod.ContainsKey(modName))
                    byMod[modName] = new List<Dict>();
                byMod[modName].Add(new Dict {
                    ["id"] = i, ["name"] = modItem.Name, ["use"] = ItemUse(itemInst), ["tags"] = ItemTags(itemInst),
                });
            }
            var mods = new List<Dict>();
            foreach (var kv in byMod)
                mods.Add(new Dict { ["mod"] = kv.Key, ["count"] = kv.Value.Count, ["items"] = kv.Value });
            Send(s, new Dict { ["req_id"] = reqId, ["type"] = "item_registry", ["mods"] = mods });
        }

        private string ItemUse(Item item)
        {
            if (item.healLife > 0) return "heal";
            if (item.healMana > 0) return "mana";
            if (item.buffType > 0 && item.consumable) return "buff";
            if (item.CountsAsClass(DamageClass.Summon)) return "summon";
            if (item.damage > 0 && !item.accessory && item.ammo == 0)
                return item.mana > 0 ? "magic" : (item.CountsAsClass(DamageClass.Ranged) ? "ranged" : "melee");
            if (item.defense > 0 || item.headSlot > 0 || item.bodySlot > 0 || item.legSlot > 0) return "armor";
            if (item.accessory) return "accessory";
            if (item.consumable) return "potion";
            if (item.pick > 0 || item.axe > 0 || item.hammer > 0) return "tool";
            if (item.createTile > 0 || item.createWall > 0) return "placeable";
            if (item.material) return "material";
            return "misc";
        }

        private List<string> ItemTags(Item item)
        {
            var tags = new List<string>();
            if (item.healLife > 0) tags.Add("heal");
            if (item.healMana > 0) tags.Add("mana");
            if (item.buffType > 0) tags.Add("buff");
            if (item.CountsAsClass(DamageClass.Summon)) tags.Add("summon");
            if (item.pick > 0) tags.Add("pickaxe");
            if (item.axe > 0) tags.Add("axe");
            if (item.hammer > 0) tags.Add("hammer");
            if (item.defense > 0 || item.headSlot > 0 || item.bodySlot > 0 || item.legSlot > 0) tags.Add("armor");
            if (item.accessory) tags.Add("accessory");
            if (item.material) tags.Add("material");
            if (tags.Count == 0) tags.Add("misc");
            return tags;
        }

        private void Send(NetworkStream s, Dict d)
        {
            // 同一 TCP 流被监听线程与 navigate_to 后台线程共用，必须加锁串行写，
            // 否则两线程同时 Write 会让回执字节交错导致 JSON 损坏
            lock (_lock)
            {
                try
                {
                    var bytes = Encoding.UTF8.GetBytes(d.ToJson() + "\n");
                    s.Write(bytes, 0, bytes.Length);
                }
                catch { }
            }
        }
    }
}
