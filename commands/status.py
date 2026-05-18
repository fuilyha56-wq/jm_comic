"""``/jmstatus`` 命令：显示插件运行状态。"""

from __future__ import annotations

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import cmd_route

from ._base import JmBaseCommand

logger = get_logger("jm_comic.commands.status")


class JmStatusCommand(JmBaseCommand):
    """``/jmstatus``：查看存储、下载与配置状态。"""

    command_name: str = "jmstatus"
    command_description: str = "显示 JM 插件运行状态"
    command_prefix: str = "/"

    @cmd_route()
    async def handle(self) -> tuple[bool, str]:
        """显示插件状态信息。"""
        runtime = self.ensure_runtime()
        if runtime is None:
            await self.reply("插件运行时未初始化")
            return False, "runtime missing"
        resource_manager, _client_factory, downloader = runtime
        cfg = self.jm_plugin.config

        try:
            storage_info = resource_manager.get_storage_info()
            active_downloads = len(downloader.downloading_comics)
            active_covers = len(downloader.downloading_covers)
            config_info = (
                f"域名数: {len(cfg.network.domain_list)}, "
                f"最大线程: {cfg.download.max_threads}"
            )
            status_text = (
                "📊 JM-Cosmos 状态报告\n\n"
                f"💾 存储使用: {storage_info['usage_percent']}% "
                f"({storage_info['total_size_mb']}/{storage_info['max_size_mb']} MB)\n"
                f"⬇️ 活跃下载: {active_downloads} 个漫画, {active_covers} 个封面\n"
                f"⚙️ 配置: {config_info}\n"
                f"🌐 代理: {'已配置' if cfg.network.proxy else '未配置'}\n"
                f"🐛 调试模式: {'开启' if cfg.download.debug_mode else '关闭'}\n"
                f"🖼️ 封面显示: {'开启' if cfg.download.show_cover else '关闭'}"
            )
            if storage_info["usage_percent"] > 80:
                status_text += "\n\n⚠️ 存储使用率较高，建议执行清理操作"
            await self.reply(status_text)
            return True, "ok"
        except Exception as exc:
            logger.error(f"获取状态信息失败: {exc}")
            await self.reply(f"获取状态失败: {exc}")
            return True, "error"
