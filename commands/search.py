"""``/jmsearch`` 与 ``/jmauthor`` 搜索类命令。"""

from __future__ import annotations

import os
import traceback

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import cmd_route

from ..core.helpers import safe_text_preview
from ._album import send_album_message
from ._base import JmBaseCommand

logger = get_logger("jm_comic.commands.search")


def _parse_keyword_and_order(args: list[str]) -> tuple[list[str], int | None, str]:
    """从参数列表中提取关键词与序号。

    Args:
        args: 子路由参数列表，例如 ``["关键词1", "关键词2", "3"]``。

    Returns:
        (关键词列表, 序号, 错误信息)。错误信息非空表示解析失败。
    """
    if len(args) < 2:
        return [], None, "至少需要关键词与序号两个参数"
    *keywords, order_str = args
    if not keywords:
        return [], None, "缺少关键词"
    try:
        order = int(order_str)
    except ValueError:
        return [], None, "序号必须是数字"
    if order < 1:
        return [], None, "序号必须≥1"
    return list(keywords), order, ""


class JmSearchCommand(JmBaseCommand):
    """``/jmsearch <关键词...> <序号>``：按关键词搜索漫画。"""

    command_name: str = "jmsearch"
    command_description: str = "按关键词搜索 JM 漫画并查看指定序号的结果"
    command_prefix: str = "/"

    @cmd_route()
    async def handle(self) -> tuple[bool, str]:
        """根据关键词搜索漫画。"""
        runtime = self.ensure_runtime()
        if runtime is None:
            await self.reply("插件运行时未初始化")
            return False, "runtime missing"
        resource_manager, client_factory, downloader = runtime
        cfg = self.jm_plugin.config

        # split_args 形如 ["/jmsearch", "key1", "key2", "3"]，仅移除命令名本身。
        raw_parts = self.split_args()
        sub_parts = raw_parts[1:]
        keywords, order, error = _parse_keyword_and_order(sub_parts)
        if error or order is None:
            await self.reply(f"格式: /jmsearch [关键词] [序号]\n{error}")
            return True, "bad args"

        client = client_factory.create_client()
        search_query = " ".join(f"+{k}" for k in keywords)
        await self.reply(
            f"正在搜索: {' '.join(keywords)}，请求序号: {order}..."
        )

        results: list[tuple[str, str]] = []
        try:
            for page in range(1, 6):
                try:
                    search_result = client.search_site(search_query, page)
                    page_results = list(search_result.iter_id_title())
                    if cfg.download.debug_mode:
                        preview_lines = "\n".join(
                            f"{i + 1}. [{aid}] {title}"
                            for i, (aid, title) in enumerate(page_results)
                        )
                        logger.info(
                            f"第{page}页搜索结果:\n{safe_text_preview(preview_lines)}"
                        )
                    results.extend(page_results)
                    if len(results) >= order:
                        break
                except Exception as exc:
                    error_msg = str(exc)
                    logger.error(f"搜索第{page}页失败: {error_msg}")
                    if "文本没有匹配上字段" in error_msg:
                        await self.reply(
                            "搜索失败: 网站结构可能已更改，请尝试 /jmdomain update"
                        )
                        return True, "structure changed"
                    if page == 1:
                        await self.reply(f"搜索失败: {error_msg}")
                        return True, "search failed"
                    break

            if not results:
                await self.reply("未找到任何结果")
                return True, "no result"

            if len(results) < order:
                listing = "\n".join(
                    f"{i + 1}. [{aid}] {title}"
                    for i, (aid, title) in enumerate(results)
                )
                await self.reply(
                    f"仅找到{len(results)}条结果，无法显示第{order}条:\n{listing}"
                )
                return True, "not enough"

            album_id, _title = results[order - 1]
            try:
                album = client.get_album_detail(album_id)
            except Exception as exc:
                if "文本没有匹配上字段" in str(exc):
                    await self.reply(
                        f"获取漫画详情失败: 网站结构可能已更改，"
                        f"但搜索结果ID是: {album_id}"
                    )
                else:
                    await self.reply(f"获取漫画详情失败: {exc}")
                return True, "detail failed"

            await self.reply(
                f"搜索结果第{order}条: [{album_id}] {album.title}\n正在下载封面..."
            )
            success, cover_path = await downloader.download_cover(album_id)
            if not success:
                await self.reply(
                    f"封面下载失败: {cover_path}\n但搜索结果ID是: {album_id}"
                )
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
            logger.error(f"搜索漫画失败: {exc}")
            resource_manager.save_debug_text(
                "search_error", traceback.format_exc()
            )
            await self.reply(f"搜索漫画失败: {exc}")
            return True, "error"


class JmAuthorCommand(JmBaseCommand):
    """``/jmauthor <作者名> <序号>``：按作者搜索作品。"""

    command_name: str = "jmauthor"
    command_description: str = "按作者名搜索 JM 漫画作品"
    command_prefix: str = "/"

    @cmd_route()
    async def handle(self) -> tuple[bool, str]:
        """根据作者名搜索作品并展示前 N 部。"""
        runtime = self.ensure_runtime()
        if runtime is None:
            await self.reply("插件运行时未初始化")
            return False, "runtime missing"
        resource_manager, client_factory, downloader = runtime
        cfg = self.jm_plugin.config

        raw_parts = self.split_args()
        sub_parts = raw_parts[1:]
        author_parts, order, error = _parse_keyword_and_order(sub_parts)
        if error or order is None:
            await self.reply(f"格式: /jmauthor [作者名] [序号]\n{error}")
            return True, "bad args"

        author_name = " ".join(author_parts)
        client = client_factory.create_client()

        try:
            from jmcomic import JmMagicConstants

            logger.info(f"搜索作者: '{author_name}'")
            first_page = client.search_site(
                search_query=author_name,
                page=1,
                order_by=JmMagicConstants.ORDER_BY_LATEST,
            )
            total_count = first_page.total
            if total_count == 0:
                await self.reply(
                    f"未找到作者 {author_name} 的作品，请检查作者名是否正确"
                )
                return True, "no result"

            page_size = len(first_page.content) or 1
            all_results: list[tuple[str, str]] = list(first_page.iter_id_title())
            target_count = min(order, total_count)
            total_page = (total_count + page_size - 1) // page_size

            for page in range(2, total_page + 1):
                try:
                    page_result = client.search_site(
                        search_query=author_name,
                        page=page,
                        order_by=JmMagicConstants.ORDER_BY_LATEST,
                    )
                    all_results.extend(list(page_result.iter_id_title()))
                except Exception as exc:
                    logger.error(f"获取第{page}页失败: {exc}")
                if len(all_results) >= target_count:
                    break

            available_count = min(len(all_results), target_count)
            if available_count == 0:
                await self.reply(
                    f"作者 {author_name} 共有 {total_count} 部作品，"
                    "但无法获取作品列表"
                )
                return True, "empty results"

            message_lines = [
                f"🎨 作者 {author_name} 共有 {total_count} 部作品",
                f"📋 显示前 {available_count} 部作品:",
            ]
            for i in range(available_count):
                aid, title = all_results[i]
                message_lines.append(f"{i + 1}. 🆔{aid}: {title}")
            await self.reply("\n".join(message_lines))

            if order == 1 and available_count >= 1:
                aid, _title = all_results[0]
                try:
                    album = client.get_album_detail(aid)
                except Exception as exc:
                    await self.reply(f"获取作品详情失败: {exc}")
                    return True, "detail failed"
                cover_path = resource_manager.get_cover_path(aid)
                if not os.path.exists(cover_path):
                    success, result = await downloader.download_cover(aid)
                    if not success:
                        await self.reply(f"⚠️ 封面下载失败: {result}")
                        return True, "cover failed"
                    cover_path = result
                await send_album_message(
                    self.stream_id,
                    client,
                    album,
                    aid,
                    cover_path,
                    cfg.download.show_cover,
                    extra_text=f"🎨 作者 {author_name} 共有 {total_count} 部作品",
                )
            return True, "ok"

        except Exception as exc:
            logger.error(f"搜索作者失败: {exc}")
            resource_manager.save_debug_text(
                "author_error", traceback.format_exc()
            )
            await self.reply(f"搜索作者失败: {exc}")
            return True, "error"
