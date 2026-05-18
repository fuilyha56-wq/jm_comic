# -*- coding: utf-8 -*-
"""离线运行 JM 漫画插件冒烟测试。

通过 stub 注入 Neo-MoFox 与 jmcomic 后再导入插件包，对每个命令类
执行根命令以及多个子命令路由，验证 trie 路由是否能正确分发，
而不是直接调用第一个 ``@cmd_route`` 处理函数。

从插件根目录运行：
    python tests/test_commands.py
"""

from __future__ import annotations

import asyncio
import importlib
import os
import sys
from pathlib import Path
from unittest.mock import MagicMock

# 路径设置
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PLUGIN_ROOT.parent))
os.chdir(PLUGIN_ROOT)
sys.path.insert(0, str(PLUGIN_ROOT / "tests"))

import _stub  # noqa: E402

_stub.install()

PKG = PLUGIN_ROOT.name


def _import_targets():
    importlib.import_module(PKG)
    cfg = importlib.import_module(f"{PKG}.config")
    plg = importlib.import_module(f"{PKG}.plugin")
    return cfg, plg


def _build_fake_plugin(plugin_cls, config_cls):
    cfg = config_cls()
    plg = plugin_cls(config=cfg)
    plg.config = cfg
    plg.resource_manager = MagicMock(name="ResourceManager")
    plg.client_factory = MagicMock(name="ClientFactory")
    plg.downloader = MagicMock(name="Downloader")

    plg.resource_manager.base_dir = "data/plugins/jm_comic"
    plg.resource_manager.get_pdf_path = (
        lambda cid: f"data/plugins/jm_comic/pdfs/{cid}.pdf"
    )
    plg.resource_manager.get_cover_path = (
        lambda cid: f"data/plugins/jm_comic/covers/{cid}.jpg"
    )
    plg.resource_manager.find_comic_folder = lambda cid: ""
    plg.resource_manager.get_storage_info = lambda: {
        "total_size_mb": 0.0,
        "max_size_mb": 5120.0,
        "has_space": True,
        "usage_percent": 0.0,
    }
    plg.resource_manager.cleanup_old_files = lambda: 0
    plg.resource_manager.clear_cover_cache = lambda: 0
    plg.resource_manager.save_debug_text = lambda *a, **k: ""

    # 让 client.search_site() / month_ranking() 返回可比较/可迭代的真实数据
    fake_search_result = MagicMock(name="SearchSite")
    fake_search_result.total = 0
    fake_search_result.content = []
    fake_search_result.iter_id_title = lambda: iter([])

    fake_ranking = MagicMock(name="MonthRanking")
    fake_ranking.iter_id_title = lambda: iter([])

    fake_album = MagicMock(name="Album")
    fake_album.title = "stub-album"
    fake_album.tags = []
    fake_album.pub_date = "2024-01-01"
    fake_album.__iter__ = lambda self: iter([])

    fake_client = MagicMock(name="JmClient")
    fake_client.search_site = MagicMock(return_value=fake_search_result)
    fake_client.month_ranking = MagicMock(return_value=fake_ranking)
    fake_client.get_album_detail = MagicMock(return_value=fake_album)
    plg.client_factory.create_client = MagicMock(return_value=fake_client)

    async def fake_dl_cover(_id):
        return True, "data/plugins/jm_comic/covers/stub.jpg"

    async def fake_dl_comic(_id):
        return True, "data/plugins/jm_comic/pdfs/stub.pdf"

    plg.downloader.download_cover = fake_dl_cover
    plg.downloader.download_comic = fake_dl_comic
    plg.downloader.preview_download_comic = MagicMock(
        return_value=(False, "stub: preview disabled in test", [])
    )
    plg.downloader.shutdown = MagicMock()
    plg.downloader.downloading_comics = []
    plg.downloader.downloading_covers = []
    plg.rebuild_clients = MagicMock()
    return plg


def _build_fake_message(text: str):
    msg = MagicMock(name="MessageRecv")
    msg.processed_plain_text = text
    return msg


# 子命令测试矩阵：每个 command_name 对应一组子路由文本（已去掉前缀和命令名）
# 每条都期望 trie 路由能正确分发到对应 handler，不抛异常
SAMPLE_ARGS: dict[str, list[str]] = {
    "jm": ["", "12345"],
    "jminfo": ["", "12345"],
    "jmsearch": ["", "test", "test 1"],
    "jmauthor": ["", "someone", "someone 1"],
    "jmrecommend": [""],
    "jmimg": ["", "12345", "12345 1"],
    "jmpdf": ["", "12345"],
    "jmdomain": ["", "list", "test", "update"],
    "jmcleanup": [""],
    "jmstatus": [""],
    "jmconfig": [
        "",
        "info",
        "domain 18comic.vip",
        "proxy http://127.0.0.1:7890",
        "noproxy",
        "cookie abc",
        "threads 5",
        "debug on",
        "cover off",
        "clearcache",
        "reload",
    ],
    "jmhelp": [""],
}


async def _try_handle(cmd, label: str, sub_text: str) -> tuple[bool, str]:
    """通过真实 trie 路由调用命令。

    判定标准：路由本身没抛异常即视为通过；业务返回 ``(False, ...)``
    在 stub 环境里属于正常分支（例如下载未完成、缓存为空），不算失败。
    """
    try:
        ok, info = await cmd.execute(sub_text)
        return True, f"{label} -> ({ok}, {info!r})"
    except Exception as exc:
        return False, f"{label} -> raised {type(exc).__name__}: {exc}"


async def main() -> int:
    print("== JM 漫画插件离线冒烟测试 ==")
    cfg_mod, plg_mod = _import_targets()

    plugin_cls = plg_mod.JmComicPlugin
    config_cls = cfg_mod.JmComicConfig

    # 1. 配置完整性
    cfg = config_cls()
    for attr in ("plugin", "network", "download"):
        if not hasattr(cfg, attr):
            print(f"FAIL: JmComicConfig 缺少 '{attr}' 节")
            return 1
    print("[ OK ] 配置 plugin/network/download 节存在")

    # 2. 钩子签名
    import inspect as _inspect
    if not _inspect.iscoroutinefunction(plugin_cls.on_plugin_loaded):
        print("FAIL: on_plugin_loaded 必须是 async")
        return 1
    print("[ OK ] on_plugin_loaded 是 async")

    # 3. 遍历所有命令组件
    fake_plg = _build_fake_plugin(plugin_cls, config_cls)
    components = plugin_cls.get_components(fake_plg)
    print(f"[INFO] 共声明 {len(components)} 个命令组件")

    failures: list[str] = []
    total_cases = 0
    for cmd_cls in components:
        cname = getattr(cmd_cls, "command_name", "")
        if not cname:
            failures.append(f"{cmd_cls.__name__}: 缺少 command_name")
            continue
        samples = SAMPLE_ARGS.get(cname, [""])
        for sample in samples:
            total_cases += 1
            cmd = cmd_cls(
                plugin=fake_plg,
                stream_id="test_stream",
                message_id="m1",
                message=_build_fake_message(f"/{cname} {sample}".strip()),
            )
            label = f"/{cname} {sample}".strip()
            ok, info = await _try_handle(cmd, label, sample)
            marker = "[ OK ]" if ok else "[FAIL]"
            print(f"{marker} {info}")
            if not ok:
                failures.append(info)

    print()
    print(f"-- 共 {total_cases} 条用例, {len(failures)} 个失败 --")
    if failures:
        print("失败列表：")
        for f in failures:
            print(f"  - {f}")
        return 1
    print("== 所有命令路由通过 ==")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
