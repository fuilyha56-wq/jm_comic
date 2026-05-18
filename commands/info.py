"""``/jminfo`` 命令：查询 JM 漫画信息。"""

from __future__ import annotations

import os
import traceback

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import cmd_route

from ..core.helpers import (
    extract_title_from_html,
    humanize_download_error,
    validate_comic_id,
)
from ._album import send_album_message
from ._base import JmBaseCommand

logger = get_logger("jm_comic.commands.info")


class JmInfoCommand(JmBaseCommand):
    """``/jminfo <漫画ID>``：查询并展示漫画信息。"""

    command_name: str = "jminfo"
    command_description: str = "查询 JM 漫画信息（标题、标签、页数、封面）"
    command_prefix: str = "/"

    @cmd_route()
    async def handle(self, comic_id: str = "") -> tuple[bool, str]:
        """查询并发送漫画信息。

        Args:
            comic_id: 漫画 ID（纯数字）。
        """
        if not comic_id:
            await self.reply("请提供漫画ID，例如：/jminfo 12345")
            return True, "missing comic_id"

        if not validate_comic_id(comic_id):
            await self.reply("无效的漫画ID格式，请提供纯数字ID")
            return True, "invalid comic_id"

        runtime = self.ensure_runtime()
        if runtime is None:
            await self.reply("插件运行时未初始化")
            return False, "runtime missing"
        resource_manager, client_factory, downloader = runtime
        cfg = self.jm_plugin.config

        client = client_factory.create_client()
        try:
            try:
                album = client.get_album_detail(comic_id)
            except Exception as exc:
                error_msg = humanize_download_error(exc, "获取漫画信息")
                if "网站结构可能已更改" in error_msg:
                    try:
                        domains = list(cfg.network.domain_list)
                        domain = domains[0] if domains else "18comic.vip"
                        html = client._postman.get_html(
                            f"https://{domain}/album/{comic_id}"
                        )
                        resource_manager.save_debug_text(
                            f"info_html_{comic_id}", html
                        )
                        title = extract_title_from_html(html)
                        await self.reply(f"{error_msg}\n但找到了标题: {title}")
                    except Exception:
                        await self.reply(error_msg)
                else:
                    await self.reply(error_msg)
                return True, "fetch failed"

            cover_path = resource_manager.get_cover_path(comic_id)
            if not os.path.exists(cover_path):
                success, result = await downloader.download_cover(comic_id)
                if not success:
                    await self.reply(
                        f"{getattr(album, 'title', '未知标题')}\n"
                        f"封面下载失败: {result}"
                    )
                    return True, "cover failed"
                cover_path = result

            await send_album_message(
                self.stream_id,
                client,
                album,
                comic_id,
                cover_path,
                cfg.download.show_cover,
            )
            return True, "ok"

        except Exception as exc:
            logger.error(f"获取漫画信息失败: {exc}")
            resource_manager.save_debug_text(
                f"info_error_{comic_id}", traceback.format_exc()
            )
            await self.reply(f"获取漫画信息失败: {exc}")
            return True, "error"
