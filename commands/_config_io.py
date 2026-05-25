"""配置持久化辅助工具。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from src.app.plugin_system.api.log_api import get_logger

if TYPE_CHECKING:
    from ..config import JmComicConfig

logger = get_logger("jm_comic.commands.config_io")


def _toml_value(value: Any) -> str:
    """把简单 Python 值渲染为 TOML 字面量。"""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    if isinstance(value, list):
        return "[" + ", ".join(_toml_value(item) for item in value) + "]"
    return json.dumps(str(value), ensure_ascii=False)


def config_path() -> Path:
    """获取 JM 插件配置文件路径。"""
    return Path("config") / "plugins" / "jm_comic" / "config.toml"


def save_config(config: "JmComicConfig") -> bool:
    """保存当前配置到默认 TOML 文件。

    Args:
        config: 当前配置对象。

    Returns:
        是否保存成功。
    """
    path = config_path()
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        content = "\n".join(
            [
                "# JM 漫画下载插件配置",
                "",
                "[plugin]",
                f"enabled = {_toml_value(config.plugin.enabled)}",
                f"version = {_toml_value(config.plugin.version)}",
                "",
                "[network]",
                f"domain_list = {_toml_value(list(config.network.domain_list))}",
                f"proxy = {_toml_value(config.network.proxy)}",
                f"avs_cookie = {_toml_value(config.network.avs_cookie)}",
                f"username = {_toml_value(config.network.username)}",
                f"password = {_toml_value(config.network.password)}",
                f"full_cookies = {_toml_value(config.network.full_cookies)}",
                "",
                "[download]",
                f"max_threads = {_toml_value(config.download.max_threads)}",
                f"show_cover = {_toml_value(config.download.show_cover)}",
                f"debug_mode = {_toml_value(config.download.debug_mode)}",
                "",
            ]
        )
        path.write_text(content, encoding="utf-8")
        return True
    except Exception as exc:
        logger.error(f"保存配置失败: {exc}")
        return False
