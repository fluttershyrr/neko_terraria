# NekoTerrariaLink — tModLoader 服务端 Mod 编译说明

猫娘 Agent 的精细动作落地端。插件通过本地 TCP（默认 9877）发送 JSON 指令，mod 回执状态/结果。

## 编译（tModLoader 官方方式，无需手动配置引用）

把 `mod/NekoTerrariaLink/` 目录内容复制到 tModLoader 的 ModSources 目录：

```
steamapps/common/tModLoader/ModSources/NekoTerrariaLink/
```

然后任选一种编译：

- **游戏内**：tModLoader 主菜单 → 模组 → 开发 → 构建 NekoTerrariaLink
- **命令行**：
  ```bash
  cd steamapps/common/tModLoader
  dotnet tModLoader.dll -build ModSources/NekoTerrariaLink
  ```

产物 `NekoTerrariaLink.tmod` 自动生成到 `Mods/` 目录，启动世界即加载。
**用户端只需 tModLoader（自带 .NET runtime），无需 .NET SDK 或任何开发环境。**

## 指令协议（插件 → mod）

| cmd | 字段 | 说明 |
|-----|------|------|
| move | dirs: ["jump","left",...] | 移动/跳跃/飞行 |
| place_tile | x,y,tile | 在坐标放方块（垫土） |
| hook | x,y | 抓钩锚定 |
| use_item | x,y | 使用当前物品（攻击/采集） |
| select_item | slot | 切换物品栏 |
| craft | item_id,amount | 合成物品 |
| equip | inv,equip | 装备栏穿戴 |
| give_item | item_id,stack | 给玩家物品 |
| get_inventory | — | 返回背包 |
| get_recipes | cat | 返回可用配方 |
| get_state | — | 返回 hp/mp/坐标/附近怪/时间 |
| enum_items | — | 枚举所有已加载 mod 物品（含用途分类） |

## 回执（mod → 插件，每行一个 JSON）

- `{"ok":true}`
- `{"crafted":N}`
- `{"items":[{"id":..,"stack":..,"slot":..,"name":..,"defense":..}]}`
- `{"recipes":[{"item_id":..,"name":..}]}`
- `{"type":"state","player":{..},"nearbyNpcs":[..],"nearbyPlayers":[..],"time":{..}}`
- `{"type":"item_registry","mods":[{"mod":..,"count":..,"items":[{"id":..,"name":..,"use":..}]}]}`

## 前置

- tModLoader 2026.5.3.0（泰拉瑞亚玩家标配）
- 服务端模式启动并加载本 mod
- 端口在 plugin.toml 的 [neko_terraria].mod_port 配置
