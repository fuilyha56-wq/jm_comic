"""消息发送相关公共工具。"""

from __future__ import annotations

import base64
import os
from typing import Any

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.api.send_api import send_file, send_image, send_text

logger = get_logger("jm_comic.messaging")


async def reply_text(stream_id: str, text: str) -> bool:
    """向当前聊天流发送文本消息。

    Args:
        stream_id: 聊天流 ID。
        text: 文本内容。

    Returns:
        发送是否成功。
    """
    try:
        return await send_text(text, stream_id=stream_id)
    except Exception as exc:
        logger.error(f"发送文本失败: {exc}")
        return False


async def reply_image_file(
    stream_id: str, file_path: str, processed_plain_text: str = "[图片]"
) -> bool:
    """读取本地图片并以 base64 形式发送。

    Args:
        stream_id: 聊天流 ID。
        file_path: 图片文件绝对路径。
        processed_plain_text: 文本占位描述。

    Returns:
        发送是否成功。
    """
    if not os.path.exists(file_path):
        logger.warning(f"图片文件不存在: {file_path}")
        return False
    try:
        with open(file_path, "rb") as fp:
            data = fp.read()
        encoded = base64.b64encode(data).decode("utf-8")
        return await send_image(
            image_data=encoded,
            stream_id=stream_id,
            processed_plain_text=processed_plain_text,
        )
    except Exception as exc:
        logger.error(f"发送图片失败 {file_path}: {exc}")
        return False


async def reply_local_file(
    stream_id: str,
    file_path: str,
    file_name: str | None = None,
    processed_plain_text: str = "",
) -> bool:
    """通过 send_file 发送本地文件。

    Args:
        stream_id: 聊天流 ID。
        file_path: 文件绝对路径。
        file_name: 展示给用户的文件名，缺省则取 basename。
        processed_plain_text: 文本占位描述。

    Returns:
        发送是否成功。
    """
    if not os.path.exists(file_path):
        logger.warning(f"待发送文件不存在: {file_path}")
        return False
    name = file_name or os.path.basename(file_path)
    try:
        kwargs: dict[str, Any] = {
            "file_path": file_path,
            "stream_id": stream_id,
            "file_name": name,
        }
        if processed_plain_text:
            kwargs["processed_plain_text"] = processed_plain_text
        return await send_file(**kwargs)
    except Exception as exc:
        logger.error(f"发送文件失败 {file_path}: {exc}")
        return False
