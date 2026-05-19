"""消息发送相关公共工具。"""

from __future__ import annotations

import base64
import os
from typing import Any

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.api.send_api import send_file, send_image, send_text

logger = get_logger("jm_comic.messaging")


def _windows_path_to_wsl_path(file_path: str) -> str:
    """将 Windows 绝对路径转换为 WSL 可访问路径。

    - Windows 路径 ``C:/data/file.pdf`` → ``/mnt/c/data/file.pdf``
    - 已经是 WSL 路径 ``/mnt/c/data/file.pdf`` → 保持不变
    - 其他 Linux 路径 ``/home/user/file.pdf`` → 保持不变
    """

    normalized = file_path.strip()
    if len(normalized) >= 3 and normalized[1] == ":" and normalized[2] in ("\\", "/"):
        drive = normalized[0].lower()
        rest = normalized[3:].replace("\\", "/")
        return f"/mnt/{drive}/{rest}" if rest else f"/mnt/{drive}"
    return normalized


def _wsl_path_to_windows_path(file_path: str) -> str:
    """将 WSL 的 /mnt/x/ 路径转换为 Windows 路径。

    - WSL 路径 ``/mnt/c/data/file.pdf`` → ``C:/data/file.pdf``
    - 非 /mnt/ 路径 ``/home/user/file.pdf`` → 保持不变
    - 已经是 Windows 路径 → 保持不变
    """

    normalized = file_path.strip()
    if normalized.startswith("/mnt/") and len(normalized) >= 7:
        # /mnt/x/rest → x:/rest
        drive_and_rest = normalized[5:]  # 去掉 "/mnt/"
        drive = drive_and_rest[0]
        rest = drive_and_rest[1:]  # 去掉盘符
        if rest.startswith("/"):
            rest = rest[1:]
        return f"{drive.upper()}:/{rest}" if rest else f"{drive.upper()}:/"
    return normalized


def _normalize_path_for_napcat(file_path: str) -> str:
    """将文件路径规范化为 NapCat 可访问的路径。

    NapCat 可能运行在 WSL 或 Windows 环境中。本函数根据输入路径格式
    自动判断并转换为对应的 WSL 路径，确保 NapCat 能正确找到文件：

    - Windows 路径（``C:\\data\\file.pdf``）→ 转换为 WSL 路径 ``/mnt/c/data/file.pdf``
    - WSL 路径（``/mnt/c/data/file.pdf``）→ 保持不变
    - 纯 Linux 路径（``/home/user/file.pdf``）→ 保持不变
    """

    return _windows_path_to_wsl_path(file_path)


def _normalize_path_for_local(file_path: str) -> str:
    """将文件路径规范化为本地系统可访问的路径（用于文件存在性检查）。

    在 Windows 宿主环境中运行时，需要将 WSL 路径转回 Windows 路径
    才能通过 ``os.path.exists()`` 检查文件是否存在：

    - WSL 路径（``/mnt/c/data/file.pdf``）→ 转换为 Windows 路径 ``C:/data/file.pdf``
    - Windows 路径（``C:\\data\\file.pdf``）→ 保持不变
    - 纯 Linux 路径 → 保持不变
    """

    return _wsl_path_to_windows_path(file_path)


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
    platform: str | None = None,
) -> bool:
    """通过 send_file 发送本地文件。

    同时支持 Windows 路径和 WSL 路径作为输入：

    - Windows 路径（如 ``C:\\data\\file.pdf``）→ 自动转换为 WSL 路径发送给 NapCat
    - WSL 路径（如 ``/mnt/c/data/file.pdf``）→ 直接使用

    文件存在性检查会自动将 WSL 路径转回 Windows 路径，确保在 Windows 宿主
    环境下 ``os.path.exists()`` 能正确判定。

    Args:
        stream_id: 聊天流 ID。
        file_path: 文件绝对路径（支持 Windows 或 WSL 格式）。
        file_name: 展示给用户的文件名，缺省则取 basename。
        processed_plain_text: 文本占位描述。
        platform: 平台名称（可选，不传时从 stream_id 推断）。

    Returns:
        发送是否成功。
    """
    # 用本地路径格式检查文件是否存在（WSL 路径需要转回 Windows 路径才能在宿主环境中判断）
    local_path = _normalize_path_for_local(file_path)
    if not os.path.exists(local_path):
        logger.warning(f"待发送文件不存在: {file_path}（本地路径: {local_path}）")
        return False
    # 用 basename 逻辑生成文件名（需要从本地可识别的路径中提取）
    name = file_name or os.path.basename(local_path)
    # 将路径规范化为 NapCat 可访问的路径（Windows→WSL 转换）
    napcat_file_path = _normalize_path_for_napcat(file_path)
    try:
        kwargs: dict[str, Any] = {
            "file_path": napcat_file_path,
            "stream_id": stream_id,
            "file_name": name,
        }
        if platform:
            kwargs["platform"] = platform
        # 注意：send_file() 不接受 processed_plain_text 参数，
        # file_name 会自动作为 processed_plain_text 传递
        return await send_file(**kwargs)
    except Exception as exc:
        logger.error(f"发送文件失败 {file_path}: {exc}")
        return False
