"""JM 漫画插件资源/路径管理。"""

from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

from src.app.plugin_system.api.log_api import get_logger

logger = get_logger("jm_comic.resource")


class ResourceManager:
    """统一管理插件下载/封面/调试目录与存储清理。"""

    DEFAULT_MAX_STORAGE_BYTES: int = 5 * 1024 * 1024 * 1024  # 5 GiB
    DEFAULT_MAX_AGE_DAYS: int = 7

    def __init__(
        self,
        plugin_name: str,
        base_dir: str | os.PathLike[str] | None = None,
        max_storage_bytes: int = DEFAULT_MAX_STORAGE_BYTES,
        max_file_age_days: int = DEFAULT_MAX_AGE_DAYS,
    ) -> None:
        """初始化资源管理器。

        Args:
            plugin_name: 插件名称，用于子目录命名。
            base_dir: 自定义根目录；为 None 时使用 ``data/plugins/{plugin_name}``。
            max_storage_bytes: 允许占用的最大字节数。
            max_file_age_days: 自动清理的过期天数。
        """
        self.plugin_name = plugin_name
        if base_dir is None:
            base_dir = Path("data") / "plugins" / plugin_name
        self.base_dir: str = str(Path(base_dir))
        self.downloads_dir: str = os.path.join(self.base_dir, "downloads")
        self.pdfs_dir: str = os.path.join(self.base_dir, "pdfs")
        self.covers_dir: str = os.path.join(self.base_dir, "covers")
        self.preview_dir: str = os.path.join(self.base_dir, "preview_downloads")
        self.debug_dir: str = os.path.join(self.base_dir, "debug")
        self.max_storage_size: int = int(max_storage_bytes)
        self.max_file_age_days: int = int(max_file_age_days)
        self._ensure_dirs()

    def _ensure_dirs(self) -> None:
        """确保所有依赖目录存在。"""
        for path in (
            self.base_dir,
            self.downloads_dir,
            self.pdfs_dir,
            self.covers_dir,
            self.preview_dir,
            self.debug_dir,
        ):
            os.makedirs(path, exist_ok=True)

    def get_pdf_path(self, comic_id: str) -> str:
        """获取漫画 PDF 的目标路径。"""
        return os.path.join(self.pdfs_dir, f"{comic_id}.pdf")

    def get_cover_path(self, comic_id: str) -> str:
        """获取漫画封面图片的目标路径。"""
        return os.path.join(self.covers_dir, f"{comic_id}.jpg")

    def check_storage_space(self) -> tuple[bool, int]:
        """检查存储占用是否仍在限额之内。

        Returns:
            (是否有剩余空间, 当前占用字节)。
        """
        total = 0
        try:
            for root, _dirs, files in os.walk(self.base_dir):
                for name in files:
                    path = os.path.join(root, name)
                    if os.path.exists(path):
                        total += os.path.getsize(path)
        except Exception as exc:
            logger.error(f"计算存储空间失败: {exc}")
            return False, 0
        return total < self.max_storage_size, total

    def cleanup_old_files(self) -> int:
        """清理超过 ``max_file_age_days`` 的文件。"""
        cutoff = time.time() - self.max_file_age_days * 86400
        cleaned = 0
        try:
            for root, _dirs, files in os.walk(self.base_dir):
                for name in files:
                    path = os.path.join(root, name)
                    try:
                        if os.path.getmtime(path) < cutoff:
                            os.remove(path)
                            cleaned += 1
                            logger.info(f"清理过期文件: {path}")
                    except Exception as exc:
                        logger.error(f"删除过期文件失败 {path}: {exc}")
        except Exception as exc:
            logger.error(f"清理文件遍历异常: {exc}")
        return cleaned

    def get_storage_info(self) -> dict[str, Any]:
        """获取存储占用统计信息。"""
        has_space, total = self.check_storage_space()
        return {
            "total_size_mb": round(total / (1024 * 1024), 2),
            "max_size_mb": round(self.max_storage_size / (1024 * 1024), 2),
            "has_space": has_space,
            "usage_percent": (
                round(total / self.max_storage_size * 100, 2)
                if self.max_storage_size > 0
                else 0.0
            ),
        }

    def clear_cover_cache(self) -> int:
        """清空封面缓存目录。"""
        if not os.path.exists(self.covers_dir):
            return 0
        deleted = 0
        try:
            for name in os.listdir(self.covers_dir):
                path = os.path.join(self.covers_dir, name)
                if os.path.isfile(path):
                    try:
                        os.remove(path)
                        deleted += 1
                    except Exception as exc:
                        logger.error(f"删除封面缓存失败 {path}: {exc}")
        except Exception as exc:
            logger.error(f"清理封面缓存异常: {exc}")
        return deleted

    def find_comic_folder(self, comic_id: str) -> str:
        """根据漫画 ID 推测下载目录（兼容多种命名方式）。"""
        comic_id = str(comic_id)
        direct = os.path.join(self.downloads_dir, comic_id)
        if os.path.exists(direct):
            return direct
        if not os.path.exists(self.downloads_dir):
            return ""
        exact: list[str] = []
        partial: list[str] = []
        for item in os.listdir(self.downloads_dir):
            full = os.path.join(self.downloads_dir, item)
            if not os.path.isdir(full):
                continue
            if (
                item.startswith(f"{comic_id}_")
                or item.endswith(f"_{comic_id}")
                or item.startswith(f"[{comic_id}]")
                or item == comic_id
            ):
                exact.append(full)
            elif comic_id in item:
                partial.append(full)
        if exact:
            return exact[0]
        if partial:
            return partial[0]
        return ""

    def save_debug_text(self, name: str, content: str) -> str:
        """把调试文本写入 ``debug_dir``，返回文件路径。"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        safe_name = "".join(c if c.isalnum() or c in "._-" else "_" for c in name)
        path = os.path.join(self.debug_dir, f"{safe_name}_{timestamp}.txt")
        try:
            with open(path, "w", encoding="utf-8") as fp:
                fp.write(content)
        except Exception as exc:
            logger.error(f"保存调试文件失败 {path}: {exc}")
        return path
