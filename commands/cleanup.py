"""``/jmcleanup`` 命令：清理过期文件。"""

from __future__ import annotations

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import cmd_route

from ._base import JmBaseCommand

logger = get_logger("jm_comic.commands.cleanup")


class JmCleanupCommand(JmBaseCommand):
    """``/jmcleanup``：清理插件过期缓存文件。"""

    command_name: str = "jmcleanup"
    command_description: str = "清理 JM 漫画过期缓存文件"
    command_prefix: str = "/"

    @cmd_route()
    async def handle(self) -> tuple[bool, str]:
        """清理过期文件并显示释放空间。"""
        runtime = self.ensure_runtime()
        if runtime is None:
            await self.reply("插件运行时未初始化")
            return False, "runtime missing"
        resource_manager, _client_factory, _downloader = runtime

        try:
            await self.reply("开始清理过期文件...")
            before = resource_manager.get_storage_info()
            cleaned_count = resource_manager.cleanup_old_files()
            after = resource_manager.get_storage_info()
            freed = before["total_size_mb"] - after["total_size_mb"]

            result = (
                "🧹 清理完成！\n\n"
                f"📁 清理文件数: {cleaned_count} 个\n"
                f"💾 释放空间: {freed:.2f} MB\n"
                f"📊 当前使用率: {after['usage_percent']}% "
                f"({after['total_size_mb']}/{after['max_size_mb']} MB)"
            )
            result += (
                "\n✅ 成功释放存储空间" if freed > 0 else "\n💡 没有找到可清理的过期文件"
            )
            await self.reply(result)
            return True, "ok"
        except Exception as exc:
            logger.error(f"清理存储空间失败: {exc}")
            await self.reply(f"清理失败: {exc}")
            return True, "error"
