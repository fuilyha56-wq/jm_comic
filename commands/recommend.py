"""``/jmrecommend`` 命令：随机推荐 JM 漫画。"""

from __future__ import annotations

import random
import traceback

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import cmd_route

from ._album import send_album_message
from ._base import JmBaseCommand

logger = get_logger("jm_comic.commands.recommend")

POPULAR_IDS: tuple[str, ...] = (
    "376448",
    "358333",
    "375872",
    "377315",
    "376870",
    "375784",
    "374463",
    "374160",
    "373768",
    "373548",
)


class JmRecommendCommand(JmBaseCommand):
    """``/jmrecommend``：随机推荐一部漫画并展示信息。"""

    command_name: str = "jmrecommend"
    command_description: str = "随机推荐 JM 漫画"
    command_prefix: str = "/"

    @cmd_route()
    async def handle(self) -> tuple[bool, str]:
        """随机推荐漫画。"""
        runtime = self.ensure_runtime()
        if runtime is None:
            await self.reply("插件运行时未初始化")
            return False, "runtime missing"
        resource_manager, client_factory, downloader = runtime
        cfg = self.jm_plugin.config

        await self.reply("正在获取推荐漫画，请稍候...")
        client = client_factory.create_client()

        try:
            ranking = None
            try:
                ranking = client.month_ranking(1)
            except Exception as exc:
                logger.error(f"获取月榜失败: {exc}")

            if ranking:
                ranking_list = list(ranking.iter_id_title())
                if ranking_list:
                    album_id, title = random.choice(ranking_list)
                    await self.reply(f"从排行榜中随机推荐: [{album_id}] {title}")
                else:
                    album_id = random.choice(POPULAR_IDS)
                    await self.reply(
                        f"排行榜为空，随机推荐一部热门漫画(ID: {album_id})..."
                    )
            else:
                album_id = random.choice(POPULAR_IDS)
                await self.reply(
                    f"获取排行榜失败，随机推荐一部热门漫画(ID: {album_id})..."
                )

            try:
                album = client.get_album_detail(album_id)
            except Exception as exc:
                await self.reply(
                    f"获取漫画详情失败: {exc}\n"
                    "请尝试使用 /jmconfig clearcache 清理封面缓存后再试"
                )
                return True, "detail failed"

            await self.reply(f"正在下载封面，ID: {album_id}...")
            success, result = await downloader.download_cover(album_id)
            if success:
                cover_path = result
            else:
                await self.reply(f"封面下载失败: {result}\n尝试继续显示漫画信息")
                cover_path = resource_manager.get_cover_path(album_id)

            await send_album_message(
                self.stream_id,
                client,
                album,
                album_id,
                cover_path,
                cfg.download.show_cover,
            )
            return True, "ok"

        except Exception as exc:
            logger.error(f"推荐漫画失败: {exc}")
            resource_manager.save_debug_text(
                "recommend_error", traceback.format_exc()
            )
            await self.reply(
                f"推荐漫画失败: {exc}\n"
                "请尝试使用 /jmconfig clearcache 清理封面缓存后再试"
            )
            return True, "error"
