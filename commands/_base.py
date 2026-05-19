"""所有 JM 命令的公共基类与混入。"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import BaseCommand

from ..core.messaging import reply_image_file, reply_local_file, reply_text

if TYPE_CHECKING:
    from ..plugin import JmComicPlugin

logger = get_logger("jm_comic.commands")


class JmBaseCommand(BaseCommand):
    """JM 命令公共基类，封装常用回复与状态访问。"""

    @property
    def jm_plugin(self) -> "JmComicPlugin":
        """返回宿主插件实例。"""
        return self.plugin  # type: ignore[return-value]

    async def reply(self, text: str) -> None:
        """向触发命令的聊天流发送文本。"""
        await reply_text(self.stream_id, text)

    async def reply_image(
        self, file_path: str, processed_plain_text: str = "[图片]"
    ) -> bool:
        """发送图片消息。"""
        return await reply_image_file(self.stream_id, file_path, processed_plain_text)

    async def reply_file(
        self,
        file_path: str,
        file_name: str | None = None,
        processed_plain_text: str = "",
        platform: str | None = None,
    ) -> bool:
        """发送文件消息。

        同时支持 Windows 路径和 WSL 路径，会自动转换为 NapCat 可访问的格式。
        """
        return await reply_local_file(
            self.stream_id, file_path, file_name, processed_plain_text, platform
        )

    def split_args(self) -> list[str]:
        """按空白分割触发命令文本，便于沿用旧实现的参数解析。"""
        if self._message is None:
            return []
        text = (self._message.processed_plain_text or "").strip()
        return text.split()

    def ensure_runtime(self) -> tuple[Any, Any, Any] | None:
        """确认共享运行时已就绪。

        Returns:
            (resource_manager, client_factory, downloader) 或 None。
        """
        plugin = self.jm_plugin
        if (
            plugin.resource_manager is None
            or plugin.client_factory is None
            or plugin.downloader is None
        ):
            logger.error("JM 插件运行时未初始化")
            return None
        return plugin.resource_manager, plugin.client_factory, plugin.downloader
