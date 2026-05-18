"""JM 漫画域名获取与可用性测试工具。

抓取顺序：
1. 优先使用 jmcomic 库内置的 ``JmModuleConfig.JM_PUB_URL``（当前生效的官方公告页）
2. 兼容历史 GitHub 公告页 ``https://jmcmomic.github.io/go/{300..308}.html``（旧仓库已 404，仍尝试以防恢复）
3. 内置 fallback 公告页域名集合，避免某一来源失效就完全抓不到
4. 兜底返回 jmcomic 库的内置 ``DOMAIN_HTML_LIST`` 常量
"""

from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

import jmcomic

from src.app.plugin_system.api.log_api import get_logger

if TYPE_CHECKING:
    from ..config import JmComicConfig

logger = get_logger("jm_comic.domain")

# 用于校验"页面里确实是禁漫域名信息"的关键词
JM_KEYWORDS: tuple[str, ...] = (
    "禁漫",
    "JM",
    "18comic",
    "免費",
    "同人",
    "成人",
    "H漫",
)

# 抓取后需要过滤掉的"非禁漫镜像"域名：Telegram 频道、社交媒体短链、推广页等
NON_MIRROR_PREFIXES: tuple[str, ...] = (
    "t.me",
    "telegram",
    "twitter.com",
    "x.com",
    "discord",
    "weibo",
    "qq.com",
)


def _is_real_mirror_domain(domain: str) -> bool:
    """判断抓取到的字符串是否是有效的禁漫镜像域名。"""
    if not domain or " " in domain:
        return False
    # 含路径的不算单纯镜像（如 ``jm-88.cc/ZNPJam``）
    if "/" in domain:
        return False
    # 必须有 TLD
    if "." not in domain:
        return False
    lower = domain.lower()
    for prefix in NON_MIRROR_PREFIXES:
        if lower.startswith(prefix):
            return False
    return True

# 候选公告页 URL：按抓取优先级排列
# 第一组：jmcomic 库的官方公告页
# 第二组：历史 GitHub 公告页（虽然多数已 404，但保留以防恢复）
# 第三组：备用公告页镜像
PUB_URL_CANDIDATES: tuple[str, ...] = (
    "https://jmcomicgo.org",
    "https://jmcomic.work",
    "https://jmcomic.run",
    "https://jmcomic1.bet",
)

# 历史 GitHub 公告页（兼容性 fallback）
GITHUB_GO_TEMPLATE: str = "https://jmcmomic.github.io/go/{}.html"
GITHUB_GO_INDEXES: tuple[int, ...] = tuple(range(300, 320))


def fetch_all_domains(config: "JmComicConfig") -> list[str]:
    """从禁漫官方公告页抓取候选域名。

    Args:
        config: 插件配置。

    Returns:
        去重后的候选域名列表。任何一个公告页抓到非空结果就返回；
        所有源都失败时返回 jmcomic 库内置的 ``DOMAIN_HTML_LIST``。
    """
    from curl_cffi import requests as postman

    meta_data: dict = {"timeout": 15, "allow_redirects": True}
    if config.network.proxy:
        meta_data["proxies"] = {"https": config.network.proxy, "http": config.network.proxy}

    domain_set: set[str] = set()

    def _try_url(url: str, label: str) -> int:
        """抓取单个公告页，返回新增域名数。"""
        try:
            resp = postman.get(url, **meta_data)
            if resp.status_code != 200:
                logger.warning(f"公告页 {label} 状态码异常: {resp.status_code}")
                return 0
            text = resp.text or ""
            extracted = list(jmcomic.JmcomicText.analyse_jm_pub_html(text))
            added = 0
            for domain in extracted:
                if domain.startswith("jm365.work"):
                    continue
                if not _is_real_mirror_domain(domain):
                    continue
                if domain not in domain_set:
                    domain_set.add(domain)
                    added += 1
            logger.info(f"公告页 {label} 抓取到 {added} 个有效域名 (累计 {len(domain_set)})")
            return added
        except Exception as exc:
            logger.warning(f"抓取公告页 {label} 失败: {exc}")
            return 0

    # 1) 优先尝试 jmcomic 库提供的官方 PUB_URL
    pub_url = getattr(jmcomic.JmModuleConfig, "JM_PUB_URL", "")
    if pub_url:
        _try_url(pub_url, f"内置 PUB_URL ({pub_url})")

    # 2) 备选公告页（按优先级抓取，任何一个抓到非空就继续累加）
    for url in PUB_URL_CANDIDATES:
        if pub_url and url == pub_url:
            continue
        _try_url(url, url)

    # 3) 历史 GitHub 公告页：仅当前面都没抓到时再试一遍
    if not domain_set:
        for idx in GITHUB_GO_INDEXES:
            _try_url(GITHUB_GO_TEMPLATE.format(idx), f"github/{idx}")
            if domain_set:
                break

    # 4) 兜底：返回 jmcomic 库内置的 DOMAIN_HTML_LIST
    if not domain_set:
        builtin = list(getattr(jmcomic.JmModuleConfig, "DOMAIN_HTML_LIST", []) or [])
        if builtin:
            logger.warning(f"所有公告页均不可用，回退到 jmcomic 内置域名列表 ({len(builtin)} 个)")
            return sorted(set(builtin))

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
        meta_data["proxies"] = {"https": config.network.proxy, "http": config.network.proxy}

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
