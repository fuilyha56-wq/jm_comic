"""``/jm`` 命令：下载漫画并发送 PDF。"""

from __future__ import annotations

import asyncio
import os

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import cmd_route
from src.kernel.concurrency import get_task_manager

from ..core.helpers import (
    format_traceback,
    humanize_download_error,
    validate_comic_id,
)
from ..core.messaging import reply_local_file, reply_text
from ._base import JmBaseCommand

logger = get_logger("jm_comic.commands.download")


class JmDownloadCommand(JmBaseCommand):
    """``/jm <漫画ID>``：下载漫画为 PDF 并发送。"""

    command_name: str = "jm"
    command_description: str = "下载 JM 漫画为 PDF 并发送给用户"

    @cmd_route()
    async def handle(self, comic_id: str = "") -> tuple[bool, str]:
        """下载漫画并发送。

        下载 + 发送是耗时操作（数秒到数分钟），如果同步等待会触发
        ``on_message_received`` 事件总线超时熔断（约 10 秒）。
        因此这里只做参数校验，把实际的下载+发送派发到后台任务，
        命令处理器立即返回，避免阻塞事件流水线。
        """
        logger.info(f"[/jm] 命令触发，comic_id={comic_id!r}")
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

        cfg = self.jm_plugin.config
        if cfg.download.debug_mode:
            await self.reply(
                f"开始下载漫画 ID: {comic_id}，请稍候...\n"
                f"当前配置最大线程数: {cfg.download.max_threads}"
            )
        else:
            await self.reply(f"开始下载漫画 ID: {comic_id}，请稍候...")

        # 把下载+发送派发到后台任务，立即返回避免触发事件超时
        stream_id = self.stream_id
        get_task_manager().create_task(
            self._run_download_and_send(comic_id, stream_id),
            name=f"jm_download_send_{comic_id}",
        )
        logger.info(f"[/jm {comic_id}] 已派发后台下载任务")
        return True, "scheduled"

    async def _run_download_and_send(self, comic_id: str, stream_id: str) -> None:
        """后台执行下载并发送 PDF。"""
        runtime = self.ensure_runtime()
        if runtime is None:
            await reply_text(stream_id, "插件运行时已失效，请稍后重试")
            return
        rm, _client_factory, downloader = runtime
        pdf_path = rm.get_pdf_path(comic_id)
        pdf_name = f"{comic_id}.pdf"
        logger.info(f"[/jm {comic_id}] 后台任务启动，目标 PDF: {pdf_path}")

        try:
            success, result = await downloader.download_comic(comic_id)
            logger.info(
                f"[/jm {comic_id}] 下载结束 success={success} result={result!r}"
            )
            if not success:
                await reply_text(stream_id, f"下载失败: {result}")
                return

            if not os.path.exists(pdf_path):
                logger.error(f"[/jm {comic_id}] PDF 不存在: {pdf_path}")
                await reply_text(stream_id, "下载完成但未找到 PDF 文件，请检查日志")
                return

            file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
            logger.info(
                f"[/jm {comic_id}] PDF 已就绪，大小 {file_size_mb:.2f} MB，"
                f"准备发送..."
            )
            if file_size_mb > 90:
                await reply_text(
                    stream_id,
                    f"⚠️ PDF 大小 {file_size_mb:.2f} MB，超过 90 MB 上限，"
                    "可能无法成功发送，请使用 /jmimg 预览",
                )

            await asyncio.sleep(0.5)
            logger.info(
                f"[/jm {comic_id}] 调用 reply_local_file: path={pdf_path}, "
                f"name={pdf_name}"
            )
            sent = await reply_local_file(
                stream_id=stream_id,
                file_path=pdf_path,
                file_name=pdf_name,
                processed_plain_text=f"漫画 {comic_id}",
            )
            logger.info(f"[/jm {comic_id}] reply_local_file 返回: {sent}")
            if sent:
                await reply_text(
                    stream_id,
                    f"✅ 漫画 {comic_id} 已发送（{file_size_mb:.2f} MB）",
                )
            else:
                await reply_text(
                    stream_id,
                    f"PDF 发送失败，文件已保存到: {pdf_path}，可手动取用",
                )
        except Exception as exc:
            logger.error(f"[/jm {comic_id}] 后台任务异常: {format_traceback(exc)}")
            await reply_text(stream_id, humanize_download_error(exc, "下载漫画"))
