"""``/jmsearch`` 与 ``/jmauthor`` 搜索类命令。"""

from __future__ import annotations

import asyncio
import base64
import os
import traceback

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import cmd_route
from src.kernel.concurrency import get_task_manager

from ..core.helpers import safe_text_preview
from ..core.messaging import reply_search_result_item, reply_text
from ..core.search_session import advance_search_page, get_search_page, reset_search_page
from ._album import send_album_message
from ._base import JmBaseCommand

logger = get_logger("jm_comic.commands.search")

# 每页展示的搜索结果数量
_PAGE_SIZE = 10


def _parse_search_args(args: list[str]) -> tuple[list[str], int | None, str]:
    """从参数列表中提取关键词与可选序号。

    Args:
        args: 子路由参数列表，例如 ``["关键词1", "关键词2"]`` 或 ``["关键词1", "3"]``。

    Returns:
        (关键词列表, 序号或None, 错误信息)。错误信息非空表示解析失败。
        序号为 None 时表示"列表模式"（展示分页结果）。
    """
    if not args:
        return [], None, "至少需要关键词参数"

    # 尝试把最后一个参数解析为序号
    *keywords, last = args
    try:
        order = int(last)
        if order < 1:
            return [], None, "序号必须≥1"
        # 最后一个参数是合法序号，但关键词不能为空
        if not keywords:
            return [], None, "缺少关键词（序号前需要有关键词）"
        return list(keywords), order, ""
    except ValueError:
        # 最后一个参数不是数字，全部视为关键词
        return list(args), None, ""


class JmSearchCommand(JmBaseCommand):
    """``/jmsearch <关键词...> [序号]``：按关键词搜索漫画。

    - 仅输入关键词时进入列表模式，展示前 10 条结果；
      再次输入相同关键词自动翻页（第 11-20 条，以此类推）。
    - 输入关键词 + 序号时直接查看该条结果的详情。
    """

    command_name: str = "jmsearch"
    command_description: str = "按关键词搜索 JM 漫画（仅关键词=列表翻页，加序号=直接查看详情）"
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

        raw_parts = self.split_args()
        sub_parts = raw_parts[1:]
        keywords, order, error = _parse_search_args(sub_parts)
        if error:
            await self.reply(
                f"格式: /jmsearch [关键词] [序号(可选)]\n{error}\n"
                "示例:\n"
                "  /jmsearch 校园  → 查看前10条结果\n"
                "  /jmsearch 校园  → 再次输入翻到第11-20条\n"
                "  /jmsearch 校园 3 → 直接查看第3条详情"
            )
            return True, "bad args"

        # 获取用户 ID（用于搜索会话翻页）
        user_id = ""
        if self._message is not None:
            user_id = getattr(self._message, "sender_id", "") or ""

        search_query = " ".join(f"+{k}" for k in keywords)
        keyword_text = " ".join(keywords)
        client = client_factory.create_client()

        # 序号模式：直接查看指定结果的详情
        if order is not None:
            return await self._handle_order_mode(
                client, downloader, resource_manager, cfg,
                search_query, keyword_text, order,
            )

        # 列表模式：分页展示搜索结果（含封面图）
        # 派发到后台任务，避免事件总线超时
        stream_id = self.stream_id
        get_task_manager().create_task(
            self._run_list_mode(
                client, downloader, resource_manager,
                search_query, keyword_text, user_id, stream_id,
            ),
            name=f"jm_search_list_{keyword_text}",
        )
        return True, "scheduled"

    async def _handle_order_mode(
        self,
        client: object,
        downloader: object,
        resource_manager: object,
        cfg: object,
        search_query: str,
        keyword_text: str,
        order: int,
    ) -> tuple[bool, str]:
        """序号模式：查找指定序号的结果并展示详情。

        Args:
            client: JM 客户端实例。
            downloader: 下载器实例。
            resource_manager: 资源管理器实例。
            cfg: 插件配置。
            search_query: 搜索查询字符串。
            keyword_text: 用户输入的关键词文本。
            order: 目标序号（从 1 开始）。
        """
        await self.reply(f"正在搜索: {keyword_text}，请求序号: {order}...")

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
                        logger.info(f"第{page}页搜索结果:\n{safe_text_preview(preview_lines)}")
                    results.extend(page_results)
                    if len(results) >= order:
                        break
                except Exception as exc:
                    error_msg = str(exc)
                    logger.error(f"搜索第{page}页失败: {error_msg}")
                    if "文本没有匹配上字段" in error_msg:
                        await self.reply("搜索失败: 网站结构可能已更改，请尝试 /jmdomain update")
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
                await self.reply(f"仅找到{len(results)}条结果，无法显示第{order}条:\n{listing}")
                return True, "not enough"

            album_id, _title = results[order - 1]
            try:
                album = client.get_album_detail(album_id)
            except Exception as exc:
                if "文本没有匹配上字段" in str(exc):
                    await self.reply(
                        f"获取漫画详情失败: 网站结构可能已更改，但搜索结果ID是: {album_id}"
                    )
                else:
                    await self.reply(f"获取漫画详情失败: {exc}")
                return True, "detail failed"

            await self.reply(f"搜索结果第{order}条: [{album_id}] {album.title}\n正在下载封面...")
            success, cover_path = await downloader.download_cover(album_id)
            if not success:
                await self.reply(f"封面下载失败: {cover_path}\n但搜索结果ID是: {album_id}")
                cover_path = resource_manager.get_cover_path(album_id)

            await send_album_message(
                self.stream_id, client, album, album_id, cover_path, cfg.download.show_cover,
            )
            return True, "ok"

        except Exception as exc:
            logger.error(f"搜索漫画失败: {exc}")
            resource_manager.save_debug_text("search_error", traceback.format_exc())
            await self.reply(f"搜索漫画失败: {exc}")
            return True, "error"

    async def _run_list_mode(
        self,
        client: object,
        downloader: object,
        resource_manager: object,
        search_query: str,
        keyword_text: str,
        user_id: str,
        stream_id: str,
    ) -> None:
        """后台任务：分页展示搜索结果（含封面图）。

        根据用户的搜索会话决定当前页码，展示 _PAGE_SIZE 条结果，
        下载每条结果的封面图，逐条发送，并在成功后递增页码供下次翻页使用。

        本方法作为后台任务运行，避免事件总线超时。

        Args:
            client: JM 客户端实例。
            downloader: 下载器实例。
            resource_manager: 资源管理器实例。
            search_query: 搜索查询字符串。
            keyword_text: 用户输入的关键词文本。
            user_id: 用户 ID（用于搜索会话）。
            stream_id: 聊天流 ID。
        """
        # 获取当前页码（从 1 开始）
        page = get_search_page(user_id, keyword_text)

        await reply_text(stream_id, f"正在搜索: {keyword_text}，第{page}页（含封面图下载，请稍候）...")

        try:
            # 请求对应页码的搜索结果
            results: list[tuple[str, str]] = []
            try:
                search_result = client.search_site(search_query, page)
                results = list(search_result.iter_id_title())
            except Exception as exc:
                error_msg = str(exc)
                logger.error(f"搜索第{page}页失败: {error_msg}")
                if "文本没有匹配上字段" in error_msg:
                    await reply_text(stream_id, "搜索失败: 网站结构可能已更改，请尝试 /jmdomain update")
                    return
                await reply_text(stream_id, f"搜索失败: {error_msg}")
                return

            if not results:
                await reply_text(stream_id, f"未找到「{keyword_text}」的相关结果")
                reset_search_page(user_id, keyword_text)
                return

            # 截取前 _PAGE_SIZE 条
            display = results[:_PAGE_SIZE]
            offset = (page - 1) * _PAGE_SIZE

            # 逐条下载封面图并发送（标题+封面图合并为一条消息，单条超时10秒）
            for i, (aid, title) in enumerate(display):
                idx_text = f"{offset + i + 1}. [{aid}]"
                cover_b64 = await self._download_cover_b64(downloader, aid)
                await reply_search_result_item(stream_id, idx_text, title, cover_b64)

            # 发送翻页提示
            hint_text = (
                f"🔍 搜索「{keyword_text}」结果（第{offset + 1}-{offset + len(display)}条）"
                f"\n💡 再次输入 /jmsearch {keyword_text} 查看下一页"
                f"\n💡 输入 /jmsearch {keyword_text} 序号 直接查看详情"
            )
            await reply_text(stream_id, hint_text)

            # 成功展示后递增页码，下次翻页
            advance_search_page(user_id, keyword_text)

        except Exception as exc:
            logger.error(f"搜索漫画失败: {exc}")
            resource_manager.save_debug_text("search_error", traceback.format_exc())
            await reply_text(stream_id, f"搜索漫画失败: {exc}")


    async def _download_cover_b64(self, downloader: object, album_id: str) -> str | None:
        """下载真正封面并读取为 base64；单本最多等待 10 秒。"""
        try:
            success, result = await asyncio.wait_for(
                downloader.download_cover(album_id),
                timeout=10.0,
            )
        except asyncio.TimeoutError:
            logger.warning(f"封面下载超时(10s) {album_id}，跳过")
            return None
        except Exception as exc:
            logger.debug(f"封面下载异常 {album_id}: {exc}")
            return None

        if not success:
            logger.debug(f"封面下载失败 {album_id}: {result}")
            return None
        if not os.path.exists(result):
            logger.debug(f"封面文件不存在 {album_id}: {result}")
            return None
        try:
            with open(result, "rb") as fp:
                return base64.b64encode(fp.read()).decode("utf-8")
        except Exception as exc:
            logger.debug(f"读取封面文件失败 {album_id}: {exc}")
            return None


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
        author_parts, order, error = _parse_search_args(sub_parts)
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
