"""JM 漫画客户端工厂。"""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

import jmcomic

from src.app.plugin_system.api.log_api import get_logger

if TYPE_CHECKING:
    from ..config import JmComicConfig
    from .resource_manager import ResourceManager

logger = get_logger("jm_comic.client_factory")


class JMClientFactory:
    """JM 客户端工厂。"""

    def __init__(
        self,
        config: "JmComicConfig",
        resource_manager: "ResourceManager",
    ) -> None:
        """初始化客户端工厂。

        Args:
            config: 插件配置实例。
            resource_manager: 资源管理器。
        """
        self.config = config
        self.resource_manager = resource_manager
        self.option = self._create_option()

    def _create_option(self) -> Any:
        """根据当前配置生成 jmcomic 选项对象。"""
        net = self.config.network
        download = self.config.download
        proxies = {"https": net.proxy} if net.proxy else None
        option_dict = {
            "client": {
                "impl": "html",
                "domain": list(net.domain_list),
                "retry_times": 5,
                "postman": {
                    "meta_data": {
                        "proxies": proxies,
                        "cookies": {"AVS": net.avs_cookie},
                        "headers": {
                            "User-Agent": (
                                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                "AppleWebKit/537.36 (KHTML, like Gecko) "
                                "Chrome/116.0.0.0 Safari/537.36"
                            ),
                            "Accept": (
                                "text/html,application/xhtml+xml,application/xml;"
                                "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,"
                                "application/signed-exchange;v=b3;q=0.7"
                            ),
                            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                            "Referer": (
                                f"https://{net.domain_list[0]}/"
                                if net.domain_list
                                else "https://18comic.vip/"
                            ),
                            "Connection": "keep-alive",
                            "Cache-Control": "max-age=0",
                        },
                    }
                },
            },
            "download": {
                "cache": True,
                "image": {"decode": True, "suffix": ".jpg"},
                "threading": {
                    "image": download.max_threads,
                    "photo": download.max_threads,
                },
            },
            "dir_rule": {"base_dir": self.resource_manager.downloads_dir},
            "plugins": {
                "after_album": [
                    {
                        "plugin": "img2pdf",
                        "kwargs": {
                            "pdf_dir": self.resource_manager.pdfs_dir,
                            "filename_rule": "Aid",
                        },
                    }
                ]
            },
        }
        return jmcomic.JmOption.construct(option_dict)

    def create_client(self) -> Any:
        """创建一个 JM HTML 客户端实例。"""
        return self.option.new_jm_client()

    def update_option(self) -> None:
        """重新构建客户端选项以应用配置变更。"""
        self.option = self._create_option()
