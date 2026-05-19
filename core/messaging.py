"""消息发送相关公共工具。"""

from __future__ import annotations

import base64
import os

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.api.send_api import (
    send_file,
    send_image,
    send_text,
    send_text_with_image,
)

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


def _resolve_to_napcat_path(file_path: str) -> str:
    """将任意路径（相对/Windows 绝对/WSL 绝对）转换为 NapCat 可访问的 WSL 路径。

    NapCat 运行在 WSL 中，无法解析 mofox 的相对路径或 Windows 风格的路径。
    本函数统一转换流程：

    1. 如果已经是 WSL 路径（``/mnt/x/...`` 或其他 Linux 路径），保持不变
    2. 否则视为 Windows 路径或相对路径，先用 ``os.path.abspath()``
       转为绝对 Windows 路径，再转为 WSL 路径
    """

    normalized = file_path.strip()
    # 已经是 Linux/WSL 风格的绝对路径，原样返回
    if normalized.startswith("/"):
        return normalized
    # 相对路径或 Windows 路径：先转为 Windows 绝对路径
    abs_path = os.path.abspath(normalized)
    # 再转为 WSL 路径
    return _windows_path_to_wsl_path(abs_path)


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
        file_path: 图片文件路径（相对或绝对）。
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
    """通过 send_file 发送本地文件给运行在 WSL 上的 NapCat。

    自动处理路径转换：

    - 输入支持**相对路径**（如 ``data/plugins/jm_comic/pdfs/46464.pdf``）
    - 输入支持 Windows 绝对路径（如 ``E:\\...\\46464.pdf``）
    - 输入支持 WSL 绝对路径（如 ``/mnt/e/.../46464.pdf``）
    - 发送给 NapCat 时统一转换为 WSL 绝对路径

    Args:
        stream_id: 聊天流 ID。
        file_path: 文件路径（相对/Windows 绝对/WSL 绝对都可以）。
        file_name: 展示给用户的文件名，缺省则取 basename。
        processed_plain_text: 保留参数用于向后兼容。``send_file`` 不接受此参数，
            它会自动用 ``file_name`` 作为占位文本。
        platform: 平台名称（可选，不传时从 stream_id 推断）。

    Returns:
        发送是否成功。
    """
    # 文件存在性检查：直接用原始路径（相对路径在 mofox 工作目录下有效）
    if not os.path.exists(file_path):
        logger.warning(f"待发送文件不存在: {file_path}")
        return False

    # 文件名：从原始路径取 basename（兼容 Windows / WSL / 相对路径）
    name = file_name
    if not name:
        normalized_for_basename = file_path.replace("\\", "/")
        name = normalized_for_basename.rstrip("/").rsplit("/", 1)[-1] or "file"

    # 转换为 NapCat 可访问的 WSL 绝对路径
    napcat_file_path = _resolve_to_napcat_path(file_path)
    logger.info(f"发送文件 {file_path} → NapCat 路径: {napcat_file_path}")

    try:
        # 注意：send_file() 不接受 processed_plain_text 参数，
        # 它内部会自动用 file_name 作为 processed_plain_text 传递
        if platform:
            return await send_file(
                file_path=napcat_file_path,
                stream_id=stream_id,
                platform=platform,
                file_name=name,
            )
        return await send_file(
            file_path=napcat_file_path,
            stream_id=stream_id,
            file_name=name,
        )
    except Exception as exc:
        logger.error(f"发送文件失败 {file_path} (napcat={napcat_file_path}): {exc}")
        return False


async def reply_search_result_item(
    stream_id: str,
    idx_text: str,
    title_text: str,
    cover_b64: str | None,
) -> bool:
    """发送单条搜索结果（标题+封面图合并为一条消息）。

    使用 send_text_with_image 将文本和图片合并发送，
    确保标题与封面图在同一个消息气泡中显示。

    Args:
        stream_id: 聊天流 ID。
        idx_text: 序号文本（如 "1. [12345]"）。
        title_text: 漫画标题。
        cover_b64: 封面图 base64 数据，为 None 时仅发送文本。

    Returns:
        是否发送成功。
    """
    text = f"{idx_text} {title_text}"

    if not cover_b64:
        # 没有封面图，仅发送文本
        return await reply_text(stream_id, text)

    try:
        return await send_text_with_image(text, cover_b64, stream_id=stream_id)
    except Exception as exc:
        logger.warning(f"图文合并发送失败，降级为逐条发送: {exc}")
        # 降级：先发文本，再发图片
        text_ok = await reply_text(stream_id, text)
        try:
            await send_image(
                image_data=cover_b64,
                stream_id=stream_id,
                processed_plain_text="[封面]",
            )
        except Exception:
            pass
        return text_ok
