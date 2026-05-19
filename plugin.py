"""JM 漫画插件入口模块。

注册所有命令组件，并维护下载器/资源管理器/客户端工厂等共享状态。
"""

from __future__ import annotations

from typing import ClassVar

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import BasePlugin, register_plugin

from .commands.cleanup import JmCleanupCommand
from .commands.config_cmd import JmConfigCommand
from .commands.domain import JmDomainCommand
from .commands.download import JmDownloadCommand
from .commands.help import JmHelpCommand
from .commands.info import JmInfoCommand
from .commands.pdf_cmd import JmPdfCommand
from .commands.preview import JmPreviewCommand
from .commands.recommend import JmRecommendCommand
from .commands.search import JmAuthorCommand, JmSearchCommand
from .commands.status import JmStatusCommand
from .config import JmComicConfig
from .core import ComicDownloader, JMClientFactory, ResourceManager

logger = get_logger("jm_comic.plugin")


@register_plugin
class JmComicPlugin(BasePlugin):
    """JM 漫画插件。

    注册一组以 ``/jm*`` 开头的命令，提供漫画下载、查询、搜索、域名管理等功能。
    """

    plugin_name: ClassVar[str] = "jm_comic"
    plugin_description: ClassVar[str] = (
        "JM 漫画下载与查询插件：下载为 PDF、查询信息、关键词/作者搜索、"
        "随机推荐、预览图片、域名测试等。"
    )
    plugin_version: ClassVar[str] = "1.2.1"

    configs: list[type] = [JmComicConfig]
    dependent_components: list[str] = []

    # 共享运行时状态（在 on_plugin_loaded 中初始化）
    resource_manager: ResourceManager | None = None
    client_factory: JMClientFactory | None = None
    downloader: ComicDownloader | None = None

    def get_components(self) -> list[type]:
        """注册插件全部命令组件。"""
        return [
            JmDownloadCommand,
            JmInfoCommand,
            JmSearchCommand,
            JmAuthorCommand,
            JmRecommendCommand,
            JmPreviewCommand,
            JmPdfCommand,
            JmDomainCommand,
            JmCleanupCommand,
            JmStatusCommand,
            JmConfigCommand,
            JmHelpCommand,
        ]

    async def on_plugin_loaded(self) -> None:
        """插件加载时构建共享资源。"""
        try:
            cfg = self.config
            assert isinstance(cfg, JmComicConfig)
            self.resource_manager = ResourceManager(self.plugin_name)
            self.client_factory = JMClientFactory(cfg, self.resource_manager)
            self.downloader = ComicDownloader(
                self.client_factory, self.resource_manager, cfg
            )
            logger.info(
                f"JM 漫画插件已加载，下载目录: {self.resource_manager.base_dir}"
            )
        except Exception as exc:
            logger.error(f"JM 漫画插件初始化失败: {exc}")
            raise

    async def on_plugin_unloaded(self) -> None:
        """插件卸载时释放资源。"""
        try:
            if self.downloader is not None:
                self.downloader.shutdown()
        except Exception as exc:
            logger.warning(f"卸载 JM 插件时关闭下载器异常: {exc}")
        self.resource_manager = None
        self.client_factory = None
        self.downloader = None
        logger.info("JM 漫画插件已卸载")

    def rebuild_clients(self) -> None:
        """配置变化后重新构建客户端工厂与下载器。"""
        if self.resource_manager is None:
            return
        cfg = self.config
        assert isinstance(cfg, JmComicConfig)
        try:
            if self.downloader is not None:
                self.downloader.shutdown()
        except Exception:
            pass
        self.client_factory = JMClientFactory(cfg, self.resource_manager)
        self.downloader = ComicDownloader(
            self.client_factory, self.resource_manager, cfg
        )
        logger.info("已根据最新配置重建 JM 客户端与下载器")
