"""``/jmimg`` 命令：下载并发送漫画预览图片。"""

from __future__ import annotations

import asyncio
import os
import shutil

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import cmd_route

from ..core.helpers import validate_comic_id
from ._base import JmBaseCommand

logger = get_logger("jm_comic.commands.preview")


class JmPreviewCommand(JmBaseCommand):
    """``/jmimg <漫画ID> [页数]``：发送前几页预览图片。"""

    command_name: str = "jmimg"
    command_description: str = "下载 JM 漫画前几页作为预览图片"
    command_prefix: str = "/"

    @cmd_route()
    async def handle(
        self, comic_id: str = "", max_pages: int = 3
    ) -> tuple[bool, str]:
        """下载漫画预览图片。

        Args:
            comic_id: 漫画 ID。
            max_pages: 预览页数，范围 1-10。
        """
        if not comic_id:
            await self.reply("请提供漫画ID，例如：/jmimg 12345")
            return True, "missing comic_id"
        if not validate_comic_id(comic_id):
            await self.reply("无效的漫画ID格式，请提供纯数字ID")
            return True, "invalid comic_id"
        max_pages = min(max(int(max_pages), 1), 10)

        runtime = self.ensure_runtime()
        if runtime is None:
            await self.reply("插件运行时未初始化")
            return False, "runtime missing"
        _resource_manager, client_factory, downloader = runtime

        await self.reply(
            f"开始预览下载漫画ID: {comic_id}的前{max_pages}页，请稍候..."
        )

        try:
            client = client_factory.create_client()
            if not client:
                await self.reply("无法连接到JM网站，请检查网络连接")
                return True, "client failed"

            success, message, image_paths = downloader.preview_download_comic(
                client, comic_id, max_pages
            )
            if not success:
                await self.reply(f"预览下载失败: {message}")
                return True, "preview failed"
            if not image_paths:
                await self.reply("预览下载成功但未获取到图片")
                return True, "empty preview"

            sent_count = 0
            for i, image_path in enumerate(image_paths, 1):
                if not os.path.exists(image_path):
                    logger.warning(f"图片文件不存在: {image_path}")
                    continue
                file_size_mb = os.path.getsize(image_path) / (1024 * 1024)
                if file_size_mb > 20:
                    await self.reply(
                        f"第{i}页图片过大({file_size_mb:.1f}MB)，跳过发送"
                    )
                    continue
                if i > 1:
                    await asyncio.sleep(1)
                ok = await self.reply_image(image_path, f"[预览第{i}页]")
                if ok:
                    sent_count += 1
                else:
                    await self.reply(f"发送第{i}页图片失败")

            await self.reply(
                f"✅ 预览完成！已发送 {sent_count} 页\n"
                f"💡 如需完整漫画，请使用 /jm {comic_id}"
            )

            try:
                preview_dir = os.path.dirname(image_paths[0]) if image_paths else ""
                if preview_dir and os.path.exists(preview_dir):
                    shutil.rmtree(preview_dir)
            except Exception as exc:
                logger.warning(f"清理预览文件失败: {exc}")
            return True, "ok"

        except Exception as exc:
            logger.error(f"预览下载过程中出错: {exc}")
            await self.reply(f"预览下载失败: {exc}")
            return True, "error"
