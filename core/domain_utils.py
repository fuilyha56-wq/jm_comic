"""JM 漫画域名获取与可用性测试工具。"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import jmcomic

from src.app.plugin_system.api.log_api import get_logger

if TYPE_CHECKING:
    from ..config import JmComicConfig

logger = get_logger("jm_comic.domain")

JM_KEYWORDS: tuple[str, ...] = (
    "禁漫",
    "JM",
    "18comic",
    "免費",
    "同人",
    "成人",
    "H漫",
)


def fetch_all_domains(config: "JmComicConfig") -> list[str]:
    """从禁漫官方公告页面抓取候选域名。

    Args:
        config: 插件配置。

    Returns:
        去重后的候选域名列表。
    """
    from curl_cffi import requests as postman

    template = "https://jmcmomic.github.io/go/{}.html"
    urls = [template.format(i) for i in range(300, 309)]
    domain_set: set[str] = set()
    meta_data: dict = {}
    if config.network.proxy:
        meta_data["proxies"] = {"https": config.network.proxy}

    def fetch_one(url: str) -> None:
        try:
            text = postman.get(
                url, allow_redirects=False, **meta_data
            ).text
            for domain in jmcomic.JmcomicText.analyse_jm_pub_html(text):
                if domain.startswith("jm365.work"):
                    continue
                domain_set.add(domain)
        except Exception as exc:
            logger.error(f"抓取 {url} 失败: {exc}")

    jmcomic.multi_thread_launcher(
        iter_objs=urls, apply_each_obj_func=fetch_one
    )
    return sorted(domain_set)


def test_domains(
    config: "JmComicConfig", domains: list[str]
) -> dict[str, str]:
    """对候选域名进行可用性检测。

    Args:
        config: 插件配置。
        domains: 待检测域名集合。

    Returns:
        ``{域名: 状态}``，状态为 ``"ok"`` 或失败原因。
    """
    from curl_cffi import requests as postman

    status: dict[str, str] = {}
    meta_data: dict = {"timeout": 10}
    if config.network.proxy:
        meta_data["proxies"] = {"https": config.network.proxy}

    def test_one(domain: str) -> None:
        try:
            url = f"https://{domain}"
            html = postman.get(url, **meta_data).text
            valid = any(keyword in html for keyword in JM_KEYWORDS)
            if not valid:
                try:
                    search_html = postman.get(
                        f"https://{domain}/search/albums", **meta_data
                    ).text
                    valid = any(
                        keyword in search_html for keyword in JM_KEYWORDS
                    )
                except Exception as exc:
                    logger.warning(f"搜索页面访问失败 {domain}: {exc}")
            status[domain] = "ok" if valid else "页面内容不正确"
        except Exception as exc:
            status[domain] = f"访问失败: {str(exc)[:60]}"

    jmcomic.multi_thread_launcher(
        iter_objs=domains, apply_each_obj_func=test_one
    )
    return status


async def fetch_and_test(
    config: "JmComicConfig",
) -> tuple[list[str], dict[str, str]]:
    """异步执行抓取+测试。

    Args:
        config: 插件配置。

    Returns:
        (域名列表, 域名->状态映射)。
    """
    domains = await asyncio.to_thread(fetch_all_domains, config)
    if not domains:
        return [], {}
    status = await asyncio.to_thread(test_domains, config, domains)
    return domains, status
