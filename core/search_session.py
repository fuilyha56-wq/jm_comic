"""搜索会话缓存管理。

按用户 ID + 关键词 维护搜索翻页状态，支持自动过期清理。
"""

from __future__ import annotations

import time

# 搜索会话缓存：{(用户ID, 关键词): (当前页码, 上次访问时间戳)}
# 页码从 1 开始，每次相同关键词翻页时 +1
_search_sessions: dict[tuple[str, str], tuple[int, float]] = {}

# 会话过期时间（秒）
_SEARCH_SESSION_TTL: float = 300.0


def get_search_page(user_id: str, keyword: str) -> int:
    """获取用户的搜索会话当前页码，不存在则返回 1。

    同时清理过期会话。

    Args:
        user_id: 用户 ID。
        keyword: 搜索关键词。

    Returns:
        当前应请求的页码（从 1 开始）。
    """
    _cleanup_expired_sessions()
    key = (user_id, keyword)
    if key in _search_sessions:
        page, _ts = _search_sessions[key]
        return page
    return 1


def advance_search_page(user_id: str, keyword: str) -> None:
    """将用户的搜索会话页码 +1，并刷新访问时间。

    Args:
        user_id: 用户 ID。
        keyword: 搜索关键词。
    """
    key = (user_id, keyword)
    if key in _search_sessions:
        page, _ts = _search_sessions[key]
        _search_sessions[key] = (page + 1, time.time())
    else:
        _search_sessions[key] = (2, time.time())


def reset_search_page(user_id: str, keyword: str) -> None:
    """重置用户的搜索会话页码为 1。

    Args:
        user_id: 用户 ID。
        keyword: 搜索关键词。
    """
    _search_sessions[(user_id, keyword)] = (1, time.time())


def _cleanup_expired_sessions() -> None:
    """清理过期的搜索会话。"""
    now = time.time()
    expired = [
        k for k, (_page, ts) in _search_sessions.items()
        if now - ts > _SEARCH_SESSION_TTL
    ]
    for k in expired:
        del _search_sessions[k]
