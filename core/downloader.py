"""JM 漫画下载器。"""

from __future__ import annotations

import asyncio
import concurrent.futures
import os
from threading import Lock
from typing import Any, TYPE_CHECKING

from src.app.plugin_system.api.log_api import get_logger

from .helpers import humanize_download_error

if TYPE_CHECKING:
    from ..config import JmComicConfig
    from .client_factory import JMClientFactory
    from .resource_manager import ResourceManager

logger = get_logger("jm_comic.downloader")


class ComicDownloader:
    """漫画下载器，封装封面下载、整本下载与预览下载。"""

    def __init__(
        self,
        client_factory: "JMClientFactory",
        resource_manager: "ResourceManager",
        config: "JmComicConfig",
    ) -> None:
        """初始化下载器。

        Args:
            client_factory: JM 客户端工厂。
            resource_manager: 资源管理器。
            config: 插件配置。
        """
        self.client_factory = client_factory
        self.resource_manager = resource_manager
        self.config = config
        self.downloading_comics: set[str] = set()
        self.downloading_covers: set[str] = set()
        self._download_lock = Lock()
        self._thread_pool = concurrent.futures.ThreadPoolExecutor(
            max_workers=min(max(config.download.max_threads, 1), 20),
            thread_name_prefix="jm_download",
        )

    def shutdown(self) -> None:
        """优雅地关闭线程池。"""
        try:
            self._thread_pool.shutdown(wait=False)
        except Exception as exc:
            logger.warning(f"关闭下载线程池异常: {exc}")

    def __del__(self) -> None:  # pragma: no cover - 兜底
        try:
            self._thread_pool.shutdown(wait=False)
        except Exception:
            pass

    async def download_cover(self, album_id: str) -> tuple[bool, str]:
        """下载漫画封面。

        使用 ``jmcomic`` 官方客户端的 ``download_album_cover()`` 下载真正的
        本子封面图，而不是下载第一话第一张图片。
        """
        if album_id in self.downloading_covers:
            return False, "封面正在下载中"
        self.downloading_covers.add(album_id)
        try:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                self._thread_pool, self._download_cover_sync, album_id
            )
        finally:
            self.downloading_covers.discard(album_id)

    def _download_cover_sync(self, album_id: str) -> tuple[bool, str]:
        """同步下载封面，供线程池调用。"""
        try:
            logger.info(f"开始下载漫画封面 ID={album_id}")
            client = self.client_factory.create_client()
            cover_path = self.resource_manager.get_cover_path(album_id)

            # jmcomic 官方接口：/media/albums/{album_id}.jpg
            # size 为空表示原始封面；不是章节第一页。
            client.download_album_cover(album_id, cover_path)
            if os.path.exists(cover_path) and os.path.getsize(cover_path) >= 1000:
                return True, cover_path
            return False, "封面文件大小异常"
        except Exception as exc:
            logger.error(f"封面下载失败: {exc}")
            return False, humanize_download_error(exc, "封面下载")

    async def download_comic(self, album_id: str) -> tuple[bool, str | None]:
        """下载整本漫画并生成 PDF。

        Args:
            album_id: 漫画 ID。

        Returns:
            (是否成功, 状态/错误消息)。
        """
        with self._download_lock:
            if album_id in self.downloading_comics:
                return False, "该漫画正在下载中，请稍候"
            self.downloading_comics.add(album_id)
        try:
            has_space, _ = self.resource_manager.check_storage_space()
            if not has_space:
                cleaned = self.resource_manager.cleanup_old_files()
                logger.info(f"存储空间不足，已清理 {cleaned} 个文件")
                has_space, _ = self.resource_manager.check_storage_space()
                if not has_space:
                    return False, "存储空间不足，请手动清理后重试"
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(
                self._thread_pool, self._download_with_retry, album_id
            )
        finally:
            self.downloading_comics.discard(album_id)

    def _download_with_retry(self, album_id: str) -> tuple[bool, str | None]:
        """同步执行带重试的下载。

        对 403 地区限制/爬虫识别类错误不进行无意义重试，直接返回明确提示。
        """
        import jmcomic

        attempts = 0
        last_error: str | None = None
        for attempts in range(1, 4):
            try:
                jmcomic.download_album(album_id, self.client_factory.option)
                pdf_path = self.resource_manager.get_pdf_path(album_id)
                if os.path.exists(pdf_path) and os.path.getsize(pdf_path) > 0:
                    return True, pdf_path
                last_error = "下载完成但未生成 PDF"
            except Exception as exc:
                last_error = humanize_download_error(exc, f"下载第{attempts}次")
                logger.error(last_error)

                # 403 地区限制/爬虫被识别：重试无意义，直接返回
                error_str = str(exc)
                if "403" in error_str and (
                    "ip地区禁止访问" in error_str or "爬虫被识别" in error_str
                ):
                    hint = (
                        "⚠️ 下载失败：IP 地区被限制或爬虫被识别。\n"
                        "解决方法：\n"
                        "1. 配置代理：/jmconfig proxy http://127.0.0.1:7890\n"
                        "2. 配置 AVS Cookie：/jmconfig avs_cookie <你的cookie值>"
                    )
                    return False, hint

                # 其他 403 错误（如需要登录）也不重试
                if "403" in error_str:
                    return False, last_error
        return False, last_error or "下载失败"

    def preview_download_comic(
        self, client: Any, comic_id: str, max_pages: int = 3
    ) -> tuple[bool, str, list[str]]:
        """下载漫画前 ``max_pages`` 页作为预览图片。

        Args:
            client: JM 客户端实例。
            comic_id: 漫画 ID。
            max_pages: 预览页数上限。

        Returns:
            (是否成功, 状态消息, 图片路径列表)。
        """
        downloaded: list[str] = []
        try:
            album = client.get_album_detail(comic_id)
            if not album:
                return False, f"无法获取漫画 {comic_id} 的详情", []
            preview_dir = os.path.join(
                self.resource_manager.preview_dir, str(comic_id)
            )
            os.makedirs(preview_dir, exist_ok=True)
            page_count = 0
            for episode in album:
                if page_count >= max_pages:
                    break
                try:
                    photo_detail = client.get_photo_detail(episode.photo_id, False)
                    for photo in photo_detail:
                        if page_count >= max_pages:
                            break
                        img_path = os.path.join(
                            preview_dir, f"page_{page_count + 1:03d}.jpg"
                        )
                        try:
                            client.download_by_image_detail(photo, img_path)
                            if (
                                os.path.exists(img_path)
                                and os.path.getsize(img_path) > 1000
                            ):
                                downloaded.append(img_path)
                                page_count += 1
                            else:
                                logger.warning(f"预览图片过小: {img_path}")
                        except Exception as exc:
                            logger.warning(f"预览图片下载失败: {exc}")
                except Exception as exc:
                    logger.error(f"预览章节 {episode.photo_id} 失败: {exc}")
            if downloaded:
                return True, f"已下载 {len(downloaded)} 张预览图", downloaded
            return False, "未能下载任何预览图片", []
        except Exception as exc:
            logger.error(f"预览下载失败: {exc}")
            return False, humanize_download_error(exc, "预览下载"), downloaded
