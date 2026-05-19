"""JM 漫画插件公共辅助函数。"""

from __future__ import annotations

import re
import traceback
from typing import Any


def extract_title_from_html(html_content: str) -> str:
    """从 HTML 内容中提取漫画标题，作为兜底解析。

    Args:
        html_content: 网页 HTML 文本。

    Returns:
        匹配到的标题文本，未匹配到时返回 "未知标题"。
    """
    patterns = [
        r"<h1[^>]*>([^<]+)</h1>",
        r"<title>([^<]+)</title>",
        r'name:\s*[\'"]([^\'"]+)[\'"]',
        r'"name":\s*"([^"]+)"',
        r'data-title=[\'"]([^\'"]+)[\'"]',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, html_content)
        if matches:
            return matches[0].strip()
    return "未知标题"


def validate_comic_id(comic_id: str) -> bool:
    """校验漫画 ID 格式，防止路径遍历攻击。

    Args:
        comic_id: 用户提供的漫画 ID。

    Returns:
        是否通过校验。
    """
    if not isinstance(comic_id, str):
        return False
    if not re.match(r"^\d+$", comic_id):
        return False
    return len(comic_id) <= 10


def validate_domain(domain: str) -> bool:
    """校验域名格式，防止注入恶意域名。

    Args:
        domain: 用户提供的域名。

    Returns:
        是否通过校验。
    """
    if not isinstance(domain, str):
        return False
    pattern = (
        r"^[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?"
        r"(\.[a-zA-Z0-9]([a-zA-Z0-9\-]{0,61}[a-zA-Z0-9])?)*$"
    )
    if not re.match(pattern, domain):
        return False
    if len(domain) > 253:
        return False
    return domain not in {"localhost", "127.0.0.1", "0.0.0.0"}


def humanize_download_error(error: Exception, context: str) -> str:
    """将下载相关异常转成对用户友好的中文提示。

    Args:
        error: 原始异常。
        context: 当前操作上下文描述。

    Returns:
        组装好的人类可读错误信息。
    """
    error_msg = str(error)
    lower_msg = error_msg.lower()
    if "timeout" in lower_msg:
        return f"{context}超时，请检查网络连接或稍后重试"
    if "connection" in lower_msg:
        return f"{context}连接失败，请检查网络或代理设置"
    if "文本没有匹配上字段" in error_msg:
        return f"{context}失败：网站结构可能已更改，请尝试 /jmdomain update 更新域名"
    if "not found" in lower_msg or "404" in error_msg:
        return f"{context}失败：资源不存在或已被删除"
    if "403" in error_msg:
        if "ip地区禁止访问" in error_msg or "爬虫被识别" in error_msg:
            return (
                f"{context}失败：IP 地区被限制或爬虫被识别\n"
                "解决方法：\n"
                "1. 配置代理：/jmconfig proxy http://127.0.0.1:7890\n"
                "2. 配置 AVS Cookie：/jmconfig avs_cookie <你的cookie值>"
            )
        return f"{context}失败：访问被拒绝（403），可能需要登录或配置代理"
    return f"{context}失败：{error_msg[:200]}"


def format_traceback(exc: BaseException | None = None) -> str:
    """生成异常的 traceback 字符串。

    Args:
        exc: 异常对象，None 表示当前异常上下文。

    Returns:
        traceback 文本。
    """
    if exc is None:
        return traceback.format_exc()
    return "".join(traceback.format_exception(type(exc), exc, exc.__traceback__))


def safe_text_preview(text: Any, limit: int = 200) -> str:
    """对任意值生成安全长度的字符串预览。

    Args:
        text: 任意输入。
        limit: 字符上限。

    Returns:
        截断后的字符串表示。
    """
    s = str(text)
    if len(s) <= limit:
        return s
    return s[:limit] + "..."
