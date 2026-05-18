"""``/jm`` 命令：下载漫画并发送 PDF。"""

from __future__ import annotations

import asyncio
import os

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import cmd_route

from ..core.helpers import (
    format_traceback,
    humanize_download_error,
    validate_comic_id,
)
from ._base import JmBaseCommand

logger = get_logger("jm_comic.commands.download")


class JmDownloadCommand(JmBaseCommand):
    """``/jm <漫画ID>``：下载漫画为 PDF 并发送。"""

    command_name: str = "jm"
    command_description: str = "下载 JM 漫画为 PDF 并发送给用户"

    @cmd_route()
    async def handle(self, comic_id: str = "") -> tuple[bool, str]:
        """下载漫画并发送。"""
        if not comic_id:
            await self.reply("请提供漫画 ID，例如：/jm 12345")
            return False, "missing comic id"

        if not validate_comic_id(comic_id):
            await self.reply("无效的漫画 ID 格式，请提供纯数字 ID")
            return False, "invalid comic id"

        runtime = self.ensure_runtime()
        if runtime is None:
            await self.reply("插件未初始化，请稍后重试")
            return False, "plugin not ready"
        rm, _client_factory, downloader = runtime
        cfg = self.jm_plugin.config

        if cfg.download.debug_mode:
            await self.reply(
                f"开始下载漫画 ID: {comic_id}，请稍候...\n"
                f"当前配置最大线程数: {cfg.download.max_threads}"
            )
        else:
            await self.reply(f"开始下载漫画 ID: {comic_id}，请稍候...")

        pdf_path = rm.get_pdf_path(comic_id)
        pdf_name = f"{comic_id}.pdf"

        try:
            success, result = await downloader.download_comic(comic_id)
            if not success:
                await self.reply(f"下载失败: {result}")
                return False, "download failed"

            if not os.path.exists(pdf_path):
                await self.reply("下载完成但未找到 PDF 文件，请检查日志")
                return False, "pdf missing"

            file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
            if file_size_mb > 90:
                await self.reply(
                    f"⚠️ PDF 大小 {file_size_mb:.2f} MB，超过 90 MB 上限，"
                    "可能无法成功发送，请使用 /jmimg 预览"
                )

            await asyncio.sleep(0.5)
            sent = await self.reply_file(
                pdf_path,
                file_name=pdf_name,
                processed_plain_text=f"漫画 {comic_id}",
            )
            if sent:
                await self.reply(
                    f"✅ 漫画 {comic_id} 已发送（{file_size_mb:.2f} MB）"
                )
                return True, "sent"
            await self.reply(
                f"PDF 发送失败，文件已保存到: {pdf_path}，可手动取用"
            )
            return False, "send failed"
        except Exception as exc:
            logger.error(f"下载漫画异常: {format_traceback(exc)}")
            await self.reply(humanize_download_error(exc, "下载漫画"))
            return False, "exception"
