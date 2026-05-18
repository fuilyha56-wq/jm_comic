# -*- coding: utf-8 -*-
"""Inject Neo-MoFox stubs into sys.modules.

This module is imported by tests/test_commands.py BEFORE importing the
plugin package, so that ``src.app.plugin_system.*``, ``jmcomic`` and a
few other dependencies resolve to lightweight fakes.
"""

from __future__ import annotations

import sys
import types
from unittest.mock import MagicMock


def _make_module(name: str) -> types.ModuleType:
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


# ---------- Neo-MoFox public surface ---------------------------------------
class FakeLogger:
    """Single-arg logger compatible with Neo-MoFox runtime semantics."""

    def __init__(self, name: str = "") -> None:
        self.name = name

    def _log(self, level: str, msg: str) -> None:
        print(f"[{level:>5}] {self.name} | {msg}")

    def info(self, msg: str) -> None:
        self._log("INFO", msg)

    def debug(self, msg: str) -> None:
        self._log("DEBUG", msg)

    def warning(self, msg: str) -> None:
        self._log("WARN", msg)

    def error(self, msg: str, *, exc_info: bool = False) -> None:
        self._log("ERROR", msg)

    def critical(self, msg: str) -> None:
        self._log("FATAL", msg)


def _stub_field(default=None, default_factory=None, **_kwargs):
    if default_factory is not None:
        return default_factory()
    return default


class StubSectionBase:
    pass


def _stub_config_section(*_args, **_kwargs):
    def _decorator(cls):
        return cls
    return _decorator


class StubBaseConfig:
    pass


import inspect
import shlex
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:
    from src.core.components.base.plugin import BasePlugin
    from src.core.models.message import Message

@dataclass
class CommandNode:
    name: str
    handler: Callable | None = None
    children: dict[str, "CommandNode"] = field(default_factory=dict)
    description: str = ""

class StubBaseCommand:
    plugin_name: str = ""
    command_name: str = ""
    command_description: str = ""
    command_prefix: str = "/"

    def __init__(
        self,
        plugin=None,
        stream_id="test_stream",
        message_id="",
        message=None,
    ):
        self.plugin = plugin
        self.stream_id = stream_id
        self.message_id = message_id
        self._message = message
        self._root = CommandNode(name="root")
        self._build_command_tree()

    def _build_command_tree(self) -> None:
        """构建命令树。扫描所有被 @cmd_route 装饰的方法。"""
        for name, method in inspect.getmembers(self, predicate=inspect.ismethod):
            if hasattr(method, "_cmd_route"):
                route_path = method._cmd_route  # type: ignore
                self._register_route(route_path, method)

    def _register_route(self, path: list[str], handler: Callable) -> None:
        current = self._root
        for segment in path:
            if segment not in current.children:
                current.children[segment] = CommandNode(name=segment)
            current = current.children[segment]
        current.handler = handler
        current.description = handler.__doc__ or ""

    async def execute(self, message_text: str) -> tuple[bool, str]:
        message_text = message_text.strip()
        # 移除前缀
        if message_text.startswith(self.command_prefix):
            message_text = message_text[len(self.command_prefix):].strip()
        # 移除命令名
        if message_text.startswith(self.command_name):
            message_text = message_text[len(self.command_name):].strip()

        return await self._route_and_execute(message_text)

    async def _route_and_execute(self, command_text: str) -> tuple[bool, str]:
        try:
            parts = shlex.split(command_text)
        except ValueError as e:
            return False, f"参数解析错误: {e}"

        if not parts:
            if self._root.handler is not None:
                return await self._call_handler(self._root.handler, [])
            return False, "空命令"

        current = self._root
        consumed = 0
        for part in parts:
            if part in current.children:
                current = current.children[part]
                consumed += 1
            else:
                break

        if current.handler is None:
            # 简化帮助生成
            return True, f"HELP: {self.command_name}"

        args = parts[consumed:]
        try:
            return await self._call_handler(current.handler, args)
        except Exception as e:
            return False, f"执行错误: {e}"

    def _convert_type(self, value: str, target_type: type) -> Any:
        from typing import get_origin, get_args
        origin = get_origin(target_type)
        args = get_args(target_type)
        if origin is list:
            if not args:
                return [value]
            inner_type = args[0]
            return [self._convert_type(v.strip(), inner_type) for v in value.split(",")]
        type_map = {
            int: int,
            str: str,
            float: float,
            bool: lambda x: x.lower() in ("true", "1", "yes", "on"),
        }
        if target_type in type_map:
            return type_map[target_type](value)
        try:
            return target_type(value)
        except Exception:
            raise ValueError(f"无法转换为 {target_type}")

    async def _call_handler(self, handler: Callable, args: list[str]) -> tuple[bool, str]:
        import typing
        sig = inspect.signature(handler)
        try:
            resolved_hints = typing.get_type_hints(handler)
        except Exception:
            resolved_hints = {}
        parameters = [(name, param) for name, param in sig.parameters.items() if name != "self"]
        converted_args = []
        for i, (arg_name, param) in enumerate(parameters):
            if i >= len(args):
                if param.default == inspect.Parameter.empty:
                    return False, f"缺少参数: {arg_name}"
                break
            arg_value = args[i]
            annotation = resolved_hints.get(arg_name, param.annotation)
            if annotation != inspect.Parameter.empty:
                try:
                    converted_value = self._convert_type(arg_value, annotation)
                except ValueError as e:
                    return False, f"参数类型错误: {arg_name} - {e}"
            else:
                converted_value = arg_value
            converted_args.append(converted_value)
        
        result = await handler(*converted_args)
        if isinstance(result, tuple) and len(result) == 2:
            return result
        return True, str(result)


class StubBasePlugin:
    plugin_name = ""
    plugin_description = ""
    plugin_version = ""
    configs: list = []
    dependent_components: list = []

    def __init__(self, config=None):
        self.config = config

    def get_components(self) -> list:
        return []

    async def on_plugin_loaded(self) -> None:
        pass

    async def on_plugin_unloaded(self) -> None:
        pass


def _stub_register_plugin(cls):
    return cls


def _stub_cmd_route(*path: str):
    def _decorator(func):
        func._cmd_route = list(path)
        return func
    return _decorator


# Register all stubs ---------------------------------------------------------
def install() -> None:
    """Install all stub modules into sys.modules."""
    _make_module("src")
    _make_module("src.app")
    _make_module("src.app.plugin_system")
    _make_module("src.app.plugin_system.api")

    base_mod = _make_module("src.app.plugin_system.base")
    base_mod.BaseCommand = StubBaseCommand
    base_mod.BasePlugin = StubBasePlugin
    base_mod.BaseConfig = StubBaseConfig
    base_mod.SectionBase = StubSectionBase
    base_mod.Field = _stub_field
    base_mod.config_section = _stub_config_section
    base_mod.register_plugin = _stub_register_plugin
    base_mod.cmd_route = _stub_cmd_route

    log_api = _make_module("src.app.plugin_system.api.log_api")
    log_api.get_logger = lambda name="jm_test": FakeLogger(name)

    # config_api stub: 提供 reload_config / load_config / get_config
    config_api = _make_module("src.app.plugin_system.api.config_api")

    def _stub_reload_config(plugin_name, config_class, *, auto_update=True):
        return config_class()

    def _stub_load_config(plugin_name, config_class, *, auto_generate=True, auto_update=True):
        return config_class()

    config_api.reload_config = _stub_reload_config
    config_api.load_config = _stub_load_config
    config_api.get_config = lambda *_a, **_k: None

    send_api = _make_module("src.app.plugin_system.api.send_api")

    async def _fake_send(*args, **kwargs):
        text = (
            kwargs.get("text")
            or kwargs.get("processed_plain_text")
            or ""
        )
        if args and isinstance(args[0], str) and not text:
            text = args[0]
        if text:
            # 控制台兼容：截断 + 安全编码，避免 Windows GBK 报错
            preview = text[:120]
            try:
                print(f"[ SEND] {preview}")
            except UnicodeEncodeError:
                print(f"[ SEND] {preview.encode('utf-8', 'backslashreplace').decode('ascii', 'replace')}")
        return True

    send_api.send_text = _fake_send
    send_api.send_image = _fake_send
    send_api.send_file = _fake_send

    # jmcomic stub
    jmc = _make_module("jmcomic")

    class _FakeJmOption:
        @staticmethod
        def construct(_data):
            inst = _FakeJmOption()
            inst.data = _data
            return inst

        def new_jm_client(self):
            return MagicMock(name="JmClient")

    class _FakeJmMagicConstants:
        ORDER_BY_LATEST = "latest"

    class _FakeJmModuleConfig:
        JM_PUB_URL = ""
        DOMAIN_HTML_LIST = ["18comic.vip", "18comic.org", "jm365.xyz"]

    jmc.JmOption = _FakeJmOption
    jmc.JmMagicConstants = _FakeJmMagicConstants
    jmc.JmModuleConfig = _FakeJmModuleConfig
    jmc.JmcomicText = MagicMock()
    jmc.JmcomicText.analyse_jm_pub_html = MagicMock(return_value=[])
    jmc.multi_thread_launcher = lambda **kwargs: None
    jmc.download_album = MagicMock(return_value=None)
