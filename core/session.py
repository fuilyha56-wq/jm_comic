"""JM 漫画登录会话管理器。

负责：
- 使用 username/password 自动登录
- 管理完整 Cookie 集的持久化
- 检测 Cookie 状态并提供重新登录能力
"""

from __future__ import annotations

import json
from typing import Any, TYPE_CHECKING

import jmcomic

from src.app.plugin_system.api.log_api import get_logger

if TYPE_CHECKING:
    from ..config import JmComicConfig

logger = get_logger("jm_comic.session")


class JmSessionManager:
    """JM 漫画登录会话管理器。

    核心职责：
    1. 根据配置的 username/password 执行自动登录
    2. 登录后提取完整 Cookie 集并持久化到配置
    3. 检测 Cookie 有效性，提供重新登录能力
    4. 提供 logout 清除登录状态
    """

    def __init__(self, config: "JmComicConfig") -> None:
        """初始化会话管理器。

        Args:
            config: 插件配置实例。
        """
        self.config = config
        self._logged_in: bool = False
        self._just_logged_in: bool = False

    # ---- 公开属性 ----

    @property
    def has_credentials(self) -> bool:
        """是否已配置用户名密码登录凭证。"""
        return bool(self.config.network.username and self.config.network.password)

    @property
    def has_cookies(self) -> bool:
        """是否已有（可能过期的）Cookie。"""
        return bool(self.config.network.avs_cookie or self.config.network.full_cookies)

    @property
    def just_logged_in(self) -> bool:
        """本轮是否发生了新的登录（供工厂类判断是否需要重建 option）。"""
        return self._just_logged_in

    def reset_just_logged_in(self) -> None:
        """重置登录标记。"""
        self._just_logged_in = False

    # ---- 核心方法 ----

    def login(self) -> bool:
        """使用配置中的用户名密码执行登录。

        登录成功后自动提取完整 Cookie 并保存到配置中。

        Returns:
            是否登录成功。
        """
        if not self.has_credentials:
            logger.warning("未配置用户名密码，无法自动登录")
            return False

        username = self.config.network.username
        password = self.config.network.password
        net = self.config.network

        try:
            proxy_url = net.proxy or None
            proxies = {"https": proxy_url, "http": proxy_url} if proxy_url else None
            domain_list = list(net.domain_list) if net.domain_list else ["18comic.vip"]

            option_dict: dict[str, Any] = {
                "client": {
                    "impl": "html",
                    "domain": domain_list,
                    "retry_times": 3,
                    "postman": {
                        "meta_data": {
                            "proxies": proxies,
                            "headers": {
                                "User-Agent": (
                                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                                    "Chrome/116.0.0.0 Safari/537.36"
                                ),
                                "Accept": (
                                    "text/html,application/xhtml+xml,"
                                    "application/xml;q=0.9,image/avif,"
                                    "image/webp,image/apng,*/*;q=0.8,"
                                    "application/signed-exchange;v=b3;q=0.7"
                                ),
                                "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                                "Referer": f"https://{domain_list[0]}/",
                            },
                        }
                    },
                },
                "dir_rule": {"base_dir": "/tmp/jm_login_temp"},
            }

            option = jmcomic.JmOption.construct(option_dict)
            client = option.new_jm_client()

            logger.info(f"正在执行 JM 自动登录（username={username}）...")
            resp = client.login(username, password)

            if not resp:
                logger.error("JM 登录返回空响应")
                self._logged_in = False
                self._just_logged_in = False
                return False

            # 登录成功，提取完整 Cookie
            cookies = self._extract_cookies(client)
            self._save_cookies(cookies)

            self._logged_in = True
            self._just_logged_in = True
            logger.info(f"JM 自动登录成功，已获取 {len(cookies)} 个 Cookie 并持久化到配置")
            # 登录后自动持久化配置
            self._persist_config()
            return True

        except Exception as exc:
            logger.error(f"JM 自动登录失败: {exc}")
            self._logged_in = False
            self._just_logged_in = False
            return False

    def logout(self) -> None:
        """清除登录状态和所有 Cookie。"""
        self.config.network.avs_cookie = ""
        self.config.network.full_cookies = ""
        self._logged_in = False
        self._just_logged_in = False
        self._persist_config()
        logger.info("已清除 JM 登录状态")

    def ensure_logged_in(self) -> bool:
        """确保已登录。

        策略（懒加载）：
        1. 如果本轮已成功登录过，直接返回 True
        2. 如果配置了 username/password 且无有效 Cookie，执行自动登录
        3. 没有凭证但已有 Cookie，返回 True（由调用方在 403 时触发重新登录）

        Returns:
            当前是否处于有 Cookie 状态。
        """
        if self._logged_in:
            return True

        if self.has_credentials and not self.has_cookies:
            return self.login()

        # 没有凭证但可能有 Cookie（旧版配置），视为可用
        return self.has_cookies

    # ---- 内部方法 ----

    def _extract_cookies(self, client: Any) -> dict[str, str]:
        """从 jmcomic 客户端中提取完整 Cookie 集。

        尝试多种方式提取，提高兼容性。

        Args:
            client: jmcomic 客户端实例。

        Returns:
            Cookie 字典（name -> value）。
        """
        cookies: dict[str, str] = {}

        # 方式1（推荐）：通过 client.get_meta_data('cookies')
        # jmcomic login() 调用 self['cookies'] = new_cookies
        # AbstractPostman（curl_cffi）→ 设置到 meta_data
        try:
            meta_cookies = client.get_meta_data("cookies")
            if isinstance(meta_cookies, dict) and meta_cookies:
                cookies.update(meta_cookies)
                logger.debug(f"从 meta_data 提取到 {len(meta_cookies)} 个 Cookie")
        except Exception as exc:
            logger.debug(f"get_meta_data('cookies') 失败: {exc}")

        # 方式2：通过 client.session.cookies
        # AbstractSessionPostman（curl_cffi_session）→ login() 设置到 session.cookies（类型为 dict）
        if not cookies:
            session = getattr(client, "session", None)
            if session is not None:
                jar = getattr(session, "cookies", None)
                if jar is not None:
                    try:
                        if isinstance(jar, dict):
                            cookies.update(jar)  # type: ignore[arg-type]
                            logger.debug(
                                f"从 session.cookies(dict) 提取到 {len(jar)} 个 Cookie"
                            )
                        else:
                            for cookie in jar:
                                if hasattr(cookie, "value") and cookie.value:
                                    cookies[cookie.name] = cookie.value
                    except Exception as exc:
                        logger.debug(f"提取 session.cookies 失败: {exc}")

        # 方式3：通过 client.cookies 属性
        if not cookies:
            jar = getattr(client, "cookies", None)
            if jar is not None:
                try:
                    if isinstance(jar, dict):
                        cookies.update(jar)  # type: ignore[arg-type]
                    else:
                        for cookie in jar:
                            if hasattr(cookie, "value") and cookie.value:
                                cookies[cookie.name] = cookie.value
                except Exception as exc:
                    logger.debug(f"提取 client.cookies 失败: {exc}")

        # 方式4：登录后再请求一次以触发 set-cookie
        if not cookies:
            try:
                domain = self.config.network.domain_list[0] if self.config.network.domain_list else "18comic.vip"
                resp = client.get(f"https://{domain}/")
                rc = getattr(resp, "cookies", None)
                if rc is not None:
                    if isinstance(rc, dict):
                        cookies.update(rc)  # type: ignore[arg-type]
                    else:
                        try:
                            for cookie in rc:
                                if hasattr(cookie, "value") and cookie.value:
                                    cookies[cookie.name] = cookie.value
                        except TypeError:
                            pass
            except Exception as exc:
                logger.debug(f"通过 GET 请求提取 Cookie 失败: {exc}")

        # 兜底：至少保留已有的 AVS Cookie
        if not cookies and self.config.network.avs_cookie:
            cookies["AVS"] = self.config.network.avs_cookie

        return cookies

    def _save_cookies(self, cookies: dict[str, str]) -> None:
        """保存 Cookie 到配置中。

        Args:
            cookies: Cookie 字典。
        """
        if not cookies:
            logger.warning("无可保存的 Cookie")
            return

        # 保存完整 Cookie JSON
        self.config.network.full_cookies = json.dumps(cookies, ensure_ascii=False)

        # 同时更新 AVS Cookie（向后兼容）
        if "AVS" in cookies:
            self.config.network.avs_cookie = cookies["AVS"]
        else:
            # 如果提取到的 Cookie 中没有 AVS，尝试用已有的
            pass

        logger.debug(f"已保存 {len(cookies)} 个 Cookie 到配置")

    def _persist_config(self) -> None:
        """持久化当前配置到 TOML 文件。"""
        try:
            from ..commands._config_io import save_config

            save_config(self.config)
        except Exception as exc:
            logger.warning(f"自动保存配置失败: {exc}")
