"""``/jmpdf`` 命令：查看本地 PDF 文件信息。"""

from __future__ import annotations

import os
from datetime import datetime

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import cmd_route

from ..core.helpers import validate_comic_id
from ._base import JmBaseCommand

logger = get_logger("jm_comic.commands.pdf")

IMAGE_EXTENSIONS: tuple[str, ...] = (".jpg", ".jpeg", ".png", ".webp")


class JmPdfCommand(JmBaseCommand):
    """``/jmpdf <漫画ID>``：查看 PDF 与原始图片目录信息。"""

    command_name: str = "jmpdf"
    command_description: str = "查看 JM 漫画 PDF 文件信息"
    command_prefix: str = "/"

    @cmd_route()
    async def handle(self, comic_id: str = "") -> tuple[bool, str]:
        """查看指定漫画 PDF 信息。

        Args:
            comic_id: 漫画 ID。
        """
        if not comic_id:
            await self.reply("请提供漫画ID，例如：/jmpdf 12345")
            return True, "missing comic_id"
        if not validate_comic_id(comic_id):
            await self.reply("无效的漫画ID格式，请提供纯数字ID")
            return True, "invalid comic_id"

        runtime = self.ensure_runtime()
        if runtime is None:
            await self.reply("插件运行时未初始化")
            return False, "runtime missing"
        resource_manager, client_factory, _downloader = runtime

        pdf_path = resource_manager.get_pdf_path(comic_id)
        if not os.path.exists(pdf_path):
            await self.reply(f"PDF文件不存在: {pdf_path}")
            return True, "pdf missing"

        try:
            file_size = os.path.getsize(pdf_path) / (1024 * 1024)
            creation_time = datetime.fromtimestamp(
                os.path.getctime(pdf_path)
            ).strftime("%Y-%m-%d %H:%M:%S")
            modify_time = datetime.fromtimestamp(
                os.path.getmtime(pdf_path)
            ).strftime("%Y-%m-%d %H:%M:%S")

            try:
                client = client_factory.create_client()
                album = client.get_album_detail(comic_id)
                title = album.title
            except Exception:
                title = f"漫画_{comic_id}"

            size_level = "正常"
            size_note = ""
            if file_size > 100:
                size_level = "⚠️ 超过QQ文件上限"
                size_note = "无法通过QQ发送，建议使用 /jmimg 命令查看前几页"
            elif file_size > 90:
                size_level = "⚠️ 接近QQ文件上限"
                size_note = "发送可能失败，建议使用 /jmimg 命令"
            elif file_size > 50:
                size_level = "⚠️ 较大"
                size_note = "发送可能较慢"

            img_folder = resource_manager.find_comic_folder(comic_id)
            total_images = 0
            image_folders: list[str] = []

            if img_folder and os.path.exists(img_folder):
                direct_images = [
                    name
                    for name in os.listdir(img_folder)
                    if name.lower().endswith(IMAGE_EXTENSIONS)
                    and os.path.isfile(os.path.join(img_folder, name))
                ]
                if direct_images:
                    total_images = len(direct_images)
                    image_folders.append(f"主目录({total_images}张)")
                else:
                    for photo_folder in os.listdir(img_folder):
                        photo_path = os.path.join(img_folder, photo_folder)
                        if not os.path.isdir(photo_path):
                            continue
                        count = len(
                            [
                                name
                                for name in os.listdir(photo_path)
                                if name.lower().endswith(IMAGE_EXTENSIONS)
                                and os.path.isfile(os.path.join(photo_path, name))
                            ]
                        )
                        if count > 0:
                            total_images += count
                            image_folders.append(f"{photo_folder}({count}张)")

            info_text = (
                f"📖 {title}\n"
                f"🆔 {comic_id}\n"
                f"📁 文件大小: {file_size:.2f} MB ({size_level})\n"
                f"📅 创建时间: {creation_time}\n"
                f"🔄 修改时间: {modify_time}\n"
                f"🖼️ 总图片数: {total_images}张\n"
                f"📚 章节: {', '.join(image_folders[:5])}"
            )
            if size_note:
                info_text += f"\n📝 注意: {size_note}"
            if not img_folder or not os.path.exists(img_folder):
                info_text += "\n⚠️ 原始图片目录不存在，无法使用 /jmimg 命令"
            elif total_images == 0:
                info_text += "\n⚠️ 未找到图片文件，但目录存在。可能需要重新下载"

            await self.reply(info_text)
            return True, "ok"
        except Exception as exc:
            logger.error(f"获取PDF信息失败: {exc}")
            await self.reply(f"获取PDF信息失败: {exc}")
            return True, "error"
