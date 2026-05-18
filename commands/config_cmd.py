"""``/jmconfig`` 命令：在线调整 JM 插件配置。"""

from __future__ import annotations

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import cmd_route

from ..core.helpers import validate_domain
from ._base import JmBaseCommand
from ._config_io import save_config

logger = get_logger("jm_comic.commands.config")

HELP_TEXT = (
    "用法:\n"
    "/jmconfig proxy [代理URL] - 设置代理URL\n"
    "/jmconfig noproxy - 清除代理设置\n"
    "/jmconfig cookie [AVS Cookie] - 设置登录Cookie\n"
    "/jmconfig threads [数量] - 设置最大下载线程数\n"
    "/jmconfig domain [域名] - 添加JM漫画域名\n"
    "/jmconfig debug [on/off] - 开启/关闭调试模式\n"
    "/jmconfig cover [on/off] - 控制是否显示封面图片\n"
    "/jmconfig info - 显示当前配置信息\n"
    "/jmconfig reload - 重新加载配置文件\n"
    "/jmconfig clearcache - 清理封面缓存"
)


class JmConfigCommand(JmBaseCommand):
    """``/jmconfig``：查看或修改配置。"""

    command_name: str = "jmconfig"
    command_description: str = "在线配置 JM 插件"
    command_prefix: str = "/"

    @cmd_route()
    async def handle(self) -> tuple[bool, str]:
        """显示配置命令帮助。"""
        await self.reply(HELP_TEXT)
        return True, "help"

    @cmd_route("info")
    async def info(self) -> tuple[bool, str]:
        """显示当前配置。"""
        cfg = self.jm_plugin.config
        await self.reply(
            "当前配置信息:\n"
            f"域名列表: {', '.join(cfg.network.domain_list)}\n"
            f"代理: {cfg.network.proxy if cfg.network.proxy else '未设置'}\n"
            f"Cookie: {'已设置' if cfg.network.avs_cookie else '未设置'}\n"
            f"最大线程数: {cfg.download.max_threads}\n"
            f"调试模式: {'开启' if cfg.download.debug_mode else '关闭'}\n"
            f"显示封面: {'显示' if cfg.download.show_cover else '不显示'}"
        )
        return True, "ok"

    @cmd_route("clearcache")
    async def clearcache(self) -> tuple[bool, str]:
        """清理封面缓存。"""
        runtime = self.ensure_runtime()
        if runtime is None:
            await self.reply("插件运行时未初始化")
            return False, "runtime missing"
        resource_manager, _client_factory, _downloader = runtime
        count = resource_manager.clear_cover_cache()
        await self.reply(f"封面缓存清理完成，共删除 {count} 个文件")
        return True, "ok"

    @cmd_route("reload")
    async def reload(self) -> tuple[bool, str]:
        """重新加载配置文件。"""
        try:
            from src.app.plugin_system.api.config_api import reload_config

            from ..config import JmComicConfig

            new_cfg = reload_config(self.jm_plugin.plugin_name, JmComicConfig)
            self.jm_plugin.config = new_cfg
            self.jm_plugin.rebuild_clients()
            await self.reply("已重新加载配置")
            return True, "ok"
        except Exception as exc:
            logger.error(f"重新加载配置失败: {exc}")
            await self.reply(f"重新加载配置失败: {exc}")
            return True, "error"

    @cmd_route("proxy")
    async def proxy(self, proxy_url: str = "") -> tuple[bool, str]:
        """设置代理 URL。"""
        if not proxy_url:
            await self.reply("请提供代理URL，例如：/jmconfig proxy http://127.0.0.1:7890")
            return True, "bad args"
        cfg = self.jm_plugin.config
        cfg.network.proxy = proxy_url
        if save_config(cfg):
            self.jm_plugin.rebuild_clients()
            await self.reply(f"已设置代理URL为: {proxy_url}")
            return True, "ok"
        await self.reply("保存配置失败，请检查权限")
        return True, "save failed"

    @cmd_route("noproxy")
    async def noproxy(self) -> tuple[bool, str]:
        """清除代理设置。"""
        cfg = self.jm_plugin.config
        cfg.network.proxy = ""
        if save_config(cfg):
            self.jm_plugin.rebuild_clients()
            await self.reply("已清除代理设置")
            return True, "ok"
        await self.reply("保存配置失败，请检查权限")
        return True, "save failed"

    @cmd_route("cookie")
    async def cookie(self, avs_cookie: str = "") -> tuple[bool, str]:
        """设置 AVS Cookie。"""
        if not avs_cookie:
            await self.reply("请提供 AVS Cookie")
            return True, "bad args"
        cfg = self.jm_plugin.config
        cfg.network.avs_cookie = avs_cookie
        if save_config(cfg):
            self.jm_plugin.rebuild_clients()
            await self.reply("已设置登录Cookie")
            return True, "ok"
        await self.reply("保存配置失败，请检查权限")
        return True, "save failed"

    @cmd_route("threads")
    async def threads(self, threads: int = 0) -> tuple[bool, str]:
        """设置最大下载线程数。"""
        if threads < 1:
            await self.reply("线程数必须≥1")
            return True, "bad args"
        if threads > 20:
            threads = 20
        cfg = self.jm_plugin.config
        cfg.download.max_threads = threads
        if save_config(cfg):
            self.jm_plugin.rebuild_clients()
            await self.reply(f"已设置最大下载线程数为: {threads}")
            return True, "ok"
        await self.reply("保存配置失败，请检查权限")
        return True, "save failed"

    @cmd_route("domain")
    async def domain(self, domain: str = "") -> tuple[bool, str]:
        """添加 JM 域名。"""
        if not domain:
            await self.reply("请提供域名，例如：/jmconfig domain 18comic.vip")
            return True, "bad args"
        domain = domain.removeprefix("https://").removeprefix("http://").strip("/")
        if not validate_domain(domain):
            await self.reply("无效的域名格式")
            return True, "bad domain"
        cfg = self.jm_plugin.config
        if domain in cfg.network.domain_list:
            await self.reply(f"域名已存在: {domain}")
            return True, "exists"
        cfg.network.domain_list.append(domain)
        if save_config(cfg):
            self.jm_plugin.rebuild_clients()
            await self.reply(f"已添加域名: {domain}")
            return True, "ok"
        await self.reply("保存配置失败，请检查权限")
        return True, "save failed"

    @cmd_route("debug")
    async def debug(self, mode: str = "") -> tuple[bool, str]:
        """开启或关闭调试模式。"""
        mode = mode.lower()
        if mode not in {"on", "off"}:
            await self.reply("参数错误，请使用 on 或 off")
            return True, "bad args"
        cfg = self.jm_plugin.config
        cfg.download.debug_mode = mode == "on"
        if save_config(cfg):
            await self.reply("已开启调试模式" if mode == "on" else "已关闭调试模式")
            return True, "ok"
        await self.reply("保存配置失败，请检查权限")
        return True, "save failed"

    @cmd_route("cover")
    async def cover(self, mode: str = "") -> tuple[bool, str]:
        """开启或关闭封面显示。"""
        mode = mode.lower()
        if mode not in {"on", "off"}:
            await self.reply("参数错误，请使用 on 或 off")
            return True, "bad args"
        cfg = self.jm_plugin.config
        cfg.download.show_cover = mode == "on"
        if save_config(cfg):
            await self.reply("已开启封面图片显示" if mode == "on" else "已关闭封面图片显示")
            return True, "ok"
        await self.reply("保存配置失败，请检查权限")
        return True, "save failed"
