"""JM 漫画客户端工厂。"""

from __future__ import annotations

import json
import os
from typing import Any, TYPE_CHECKING

import jmcomic

from src.app.plugin_system.api.log_api import get_logger

from .session import JmSessionManager

if TYPE_CHECKING:
    from ..config import JmComicConfig
    from .resource_manager import ResourceManager

logger = get_logger("jm_comic.client_factory")


def _detect_system_proxy() -> str | None:
    """自动检测系统代理。

    检测顺序：

    1. 环境变量 ``HTTPS_PROXY`` / ``HTTP_PROXY`` / ``ALL_PROXY``
    2. Windows 注册表中的系统代理设置（``ProxyEnable=1``）

    Returns:
        代理 URL（如 ``http://127.0.0.1:7890``），未检测到则返回 None。
    """
    # 1. 环境变量优先
    for var in (
        "HTTPS_PROXY",
        "https_proxy",
        "HTTP_PROXY",
        "http_proxy",
        "ALL_PROXY",
        "all_proxy",
    ):
        value = os.environ.get(var)
        if value:
            logger.info(f"自动代理检测：从环境变量 {var} 读取到 {value}")
            return value

    # 2. Windows 注册表
    try:
        import winreg  # type: ignore[import-not-found]

        key_path = r"Software\Microsoft\Windows\CurrentVersion\Internet Settings"
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
            enable, _ = winreg.QueryValueEx(key, "ProxyEnable")
            if enable:
                proxy_server, _ = winreg.QueryValueEx(key, "ProxyServer")
                if proxy_server:
                    # ProxyServer 可能是 "host:port" 或 "http=h:p;https=h:p"
                    proxy_str = str(proxy_server).strip()
                    if "=" in proxy_str:
                        parts: dict[str, str] = {}
                        for segment in proxy_str.split(";"):
                            if "=" in segment:
                                scheme, addr = segment.split("=", 1)
                                parts[scheme.strip().lower()] = addr.strip()
                        host_port = parts.get("https") or parts.get("http")
                    else:
                        host_port = proxy_str
                    if host_port:
                        proxy_url = (
                            host_port
                            if host_port.startswith(("http://", "https://", "socks"))
                            else f"http://{host_port}"
                        )
                        logger.info(
                            f"自动代理检测：从 Windows 注册表读取到 {proxy_url}"
                        )
                        return proxy_url
    except (ImportError, OSError, FileNotFoundError) as exc:
        logger.debug(f"自动代理检测：跳过 Windows 注册表（{exc}）")
    except Exception as exc:
        logger.warning(f"自动代理检测：读取 Windows 注册表失败 {exc}")

    return None


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
        self.session_manager = JmSessionManager(config)
        self.option = self._create_option()

    def _resolve_proxy(self) -> str | None:
        """解析最终生效的代理地址。

        优先级：
        1. 用户在配置中显式填写的 ``network.proxy``
        2. 系统自动检测（环境变量 / Windows 注册表）
        """
        net = self.config.network
        if net.proxy:
            logger.debug(f"使用配置文件中的代理：{net.proxy}")
            return net.proxy
        auto = _detect_system_proxy()
        if auto:
            logger.info(f"未配置代理，自动启用系统代理：{auto}")
        else:
            logger.debug("未配置代理，且未检测到系统代理")
        return auto

    def _resolve_cookies(self, net: Any) -> dict[str, str]:
        """解析最终生效的 Cookie 字典。

        优先级：
        1. 完整 Cookie JSON（``full_cookies``），登录后自动保存
        2. 单字段 ``avs_cookie``（向后兼容）

        Args:
            net: NetworkSection 配置节。

        Returns:
            Cookie 字典。
        """
        if net.full_cookies:
            try:
                parsed = json.loads(net.full_cookies)
                if isinstance(parsed, dict):
                    return parsed
            except (json.JSONDecodeError, TypeError):
                logger.warning("解析 full_cookies JSON 失败，回退到 avs_cookie")
        if net.avs_cookie:
            return {"AVS": net.avs_cookie}
        return {}

    def _create_option(self) -> Any:
        """根据当前配置生成 jmcomic 选项对象。"""
        net = self.config.network
        download = self.config.download
        proxy_url = self._resolve_proxy()
        proxies = {"https": proxy_url, "http": proxy_url} if proxy_url else None
        option_dict = {
            "client": {
                "impl": "html",
                "domain": list(net.domain_list),
                "retry_times": 5,
                "postman": {
                    "meta_data": {
                        "proxies": proxies,
                        "cookies": self._resolve_cookies(net),
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
        """创建一个 JM HTML 客户端实例。

        懒加载策略：
        1. 首次调用时通过 ``session_manager`` 确保已登录
        2. 如果发生了新的登录，自动重建 Option 以使用最新 Cookie
        3. 返回使用最新配置的客户端实例
        """
        self.session_manager.ensure_logged_in()
        if self.session_manager.just_logged_in:
            self.update_option()
            self.session_manager.reset_just_logged_in()
        return self.option.new_jm_client()

    def update_option(self) -> None:
        """重新构建客户端选项以应用配置变更。"""
        self.option = self._create_option()
