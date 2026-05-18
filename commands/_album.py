"""漫画信息消息构建工具。

集中存放原 ``_build_album_message`` 与 ``get_total_pages`` 逻辑，
被多个命令复用。
"""

from __future__ import annotations

import os
from typing import Any

from src.app.plugin_system.api.log_api import get_logger

from ..core.messaging import reply_image_file, reply_text

logger = get_logger("jm_comic.commands.album")


def get_total_pages(client: Any, album: Any) -> int:
    """获取漫画总页数。

    Args:
        client: JM 客户端实例。
        album: 漫画详情对象。

    Returns:
        总页数；获取失败时返回 0。
    """
    try:
        return sum(
            len(client.get_photo_detail(p.photo_id, False)) for p in album
        )
    except Exception as exc:
        logger.error(f"获取总页数失败: {exc}")
        return 0


def build_album_text(
    client: Any, album: Any, album_id: str, total_pages: int | None = None
) -> str:
    """生成漫画信息文本。

    Args:
        client: JM 客户端实例。
        album: 漫画详情对象。
        album_id: 漫画 ID。
        total_pages: 已知总页数；为 None 时实时计算。

    Returns:
        格式化后的多行文本。
    """
    if total_pages is None:
        total_pages = get_total_pages(client, album)
    title = getattr(album, "title", "未知标题")
    tags = getattr(album, "tags", []) or []
    pub_date = getattr(album, "pub_date", "未知")
    return (
        f"📖: {title}\n"
        f"🆔: {album_id}\n"
        f"🏷️: {', '.join(list(tags)[:5])}\n"
        f"📅: {pub_date}\n"
        f"📃: {total_pages}"
    )


async def send_album_message(
    stream_id: str,
    client: Any,
    album: Any,
    album_id: str,
    cover_path: str,
    show_cover: bool,
    extra_text: str = "",
) -> None:
    """发送漫画信息（文本 + 可选封面）。

    Args:
        stream_id: 聊天流 ID。
        client: JM 客户端实例。
        album: 漫画详情对象。
        album_id: 漫画 ID。
        cover_path: 封面图片路径。
        show_cover: 是否发送封面图片。
        extra_text: 附加在前面的文本（例如作者搜索的统计行）。
    """
    text = build_album_text(client, album, album_id)
    if extra_text:
        text = f"{extra_text}\n{text}"
    await reply_text(stream_id, text)
    if show_cover and cover_path and os.path.exists(cover_path):
        await reply_image_file(stream_id, cover_path, "[封面]")
