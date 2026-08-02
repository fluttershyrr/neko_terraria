using Terraria.ModLoader;
using Terraria.ModLoader.Config;

namespace NekoTerrariaLink
{
    // 模组设置：在游戏内「模组设置」中可调，无需改代码。
    // 注意：mod_port 必须与 neko_terraria 插件 plugin.toml 里的 mod_port 保持一致。
    public class NekoConfig : ModConfig
    {
        public override ConfigScope Mode => ConfigScope.ServerSide;

        // 本模组监听的 TCP 端口（AI 猫娘插件通过它发送指令）
        [Label("监听端口 (mod_port)")]
        [Tooltip("本模组开放的控制接口端口。需与 neko_terraria 插件 plugin.toml 的 mod_port 一致。")]
        [Range(1024, 65535)]
        public int ModPort { get; set; } = 9877;

        // 是否仅允许本机连接（loopback）。关掉可允许局域网内其它机器连接。
        [Label("仅允许本机连接")]
        [Tooltip("开启时只接受 127.0.0.1 的连接，更安全；关闭可允许局域网连接。")]
        public bool LocalOnly { get; set; } = true;
    }
}
