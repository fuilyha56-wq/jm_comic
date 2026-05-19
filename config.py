"""JM 漫画插件配置定义。"""

from __future__ import annotations

from typing import ClassVar

from src.app.plugin_system.base import (
    BaseConfig,
    Field,
    SectionBase,
    config_section,
)


class JmComicConfig(BaseConfig):
    """JM 漫画插件配置。"""

    config_name: ClassVar[str] = "config"
    config_description: ClassVar[str] = "JM 漫画下载插件配置"

    @config_section("plugin", title="插件设置", tag="plugin")
    class PluginSection(SectionBase):
        """插件基础设置。"""

        enabled: bool = Field(
            default=True,
            description="是否启用插件",
            label="启用插件",
            tag="plugin",
        )
        version: str = Field(
            default="1.2.0",
            description="插件版本",
            label="插件版本",
            disabled=True,
            tag="plugin",
        )

    @config_section("network", title="网络设置", tag="network")
    class NetworkSection(SectionBase):
        """网络与镜像站设置。"""

        domain_list: list[str] = Field(
            default=["18comic.vip", "jm365.xyz", "18comic.org"],
            description="禁漫镜像站域名列表，不需要 http/https 前缀",
            label="镜像站域名",
            tag="network",
            item_type="str",
        )
        proxy: str = Field(
            default="",
            description="访问禁漫站点的 HTTP 代理，例如 http://127.0.0.1:7890",
            label="HTTP 代理",
            tag="network",
        )
        avs_cookie: str = Field(
            default="",
            description="登录后的 AVS Cookie 值，用于获取需登录内容",
            label="AVS Cookie",
            tag="network",
        )

    @config_section("download", title="下载设置", tag="download")
    class DownloadSection(SectionBase):
        """下载行为设置。"""

        max_threads: int = Field(
            default=10,
            description="同时下载的最大线程数，建议不超过 20",
            label="最大下载线程数",
            tag="download",
            ge=1,
            le=20,
        )
        show_cover: bool = Field(
            default=True,
            description="是否在漫画信息和搜索结果中显示封面图片",
            label="显示封面",
            tag="download",
        )
        debug_mode: bool = Field(
            default=False,
            description="启用调试模式后会保存更多日志信息，帮助排查问题",
            label="调试模式",
            tag="download",
        )

    # 配置节实例：必须在外层挂接，否则运行时无法用 self.config.network 等访问
    plugin: PluginSection = Field(default_factory=PluginSection)
    network: NetworkSection = Field(default_factory=NetworkSection)
    download: DownloadSection = Field(default_factory=DownloadSection)
