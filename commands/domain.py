"""``/jmdomain`` 命令：JM 镜像域名测试与更新。"""

from __future__ import annotations

import traceback

from src.app.plugin_system.api.log_api import get_logger
from src.app.plugin_system.base import cmd_route

from ..core.domain_utils import fetch_and_test
from ._base import JmBaseCommand
from ._config_io import save_config

logger = get_logger("jm_comic.commands.domain")


class JmDomainCommand(JmBaseCommand):
    """``/jmdomain``：显示、测试或更新 JM 域名。"""

    command_name: str = "jmdomain"
    command_description: str = "测试并更新可用的 JM 镜像域名"
    command_prefix: str = "/"

    @cmd_route()
    async def handle(self) -> tuple[bool, str]:
        """显示域名命令帮助。"""
        await self.reply(
            "📋 禁漫域名工具用法:\n\n"
            "/jmdomain list - 显示当前配置的域名\n"
            "/jmdomain test - 测试所有可获取的域名并显示结果\n"
            "/jmdomain update - 测试并自动更新为可用域名\n\n"
            "说明: 测试和更新操作可能需要几分钟时间，请耐心等待"
        )
        return True, "help"

    @cmd_route("list")
    async def list_domains(self) -> tuple[bool, str]:
        """显示当前配置的域名列表。"""
        cfg = self.jm_plugin.config
        domains = list(cfg.network.domain_list)
        domains_text = "\n".join(
            f"- {index}. {domain}" for index, domain in enumerate(domains, 1)
        )
        await self.reply(f"当前配置的域名列表:\n{domains_text}")
        return True, "ok"

    @cmd_route("test")
    async def test_domains(self) -> tuple[bool, str]:
        """测试可获取域名的可用性。"""
        return await self._fetch_test_and_maybe_update(update=False)

    @cmd_route("update")
    async def update_domains(self) -> tuple[bool, str]:
        """测试并将配置更新为可用域名。"""
        return await self._fetch_test_and_maybe_update(update=True)

    async def _fetch_test_and_maybe_update(self, update: bool) -> tuple[bool, str]:
        """抓取并测试域名，必要时更新配置。"""
        runtime = self.ensure_runtime()
        if runtime is None:
            await self.reply("插件运行时未初始化")
            return False, "runtime missing"
        resource_manager, _client_factory, _downloader = runtime
        cfg = self.jm_plugin.config

        await self.reply("开始获取全部禁漫域名，这可能需要一些时间...")
        try:
            domains, status = await fetch_and_test(cfg)
            if not domains:
                await self.reply("未能获取到任何域名，请检查网络连接")
                return True, "no domains"

            await self.reply(f"获取到{len(domains)}个域名，已完成可用性测试")
            ok_domains = [domain for domain, state in status.items() if state == "ok"]

            if not update:
                result = (
                    f"测试完成，共{len(domains)}个域名，其中{len(ok_domains)}个可用\n\n"
                )
                if ok_domains:
                    result += "✅ 可用域名:\n"
                    for index, domain in enumerate(ok_domains[:10], 1):
                        result += f"{index}. {domain}\n"
                    if len(ok_domains) > 10:
                        result += f"...等共{len(ok_domains)}个可用域名\n"
                else:
                    result += "❌ 没有找到可用域名"
                    if not cfg.network.proxy:
                        result += (
                            "\n可能原因:\n1. 所有域名都被屏蔽\n2. 网络问题\n\n"
                            "建议配置代理后再试:\n/jmconfig proxy http://127.0.0.1:7890"
                        )
                await self.reply(result.strip())
                return True, "ok"

            if not ok_domains:
                result = "未找到可用域名，保持当前配置不变"
                if not cfg.network.proxy:
                    result += (
                        "\n\n可能原因:\n1. 所有域名都被屏蔽\n2. 网络问题\n\n"
                        "建议配置代理后再试:\n/jmconfig proxy http://127.0.0.1:7890"
                    )
                await self.reply(result)
                return True, "no ok"

            old_domains = set(cfg.network.domain_list)
            cfg.network.domain_list = list(ok_domains[:5])
            removed = old_domains.difference(set(cfg.network.domain_list))
            if not save_config(cfg):
                await self.reply("更新域名失败，无法保存配置")
                return True, "save failed"
            self.jm_plugin.rebuild_clients()

            result = "域名更新完成！\n\n"
            result += f"✅ 已配置以下{len(cfg.network.domain_list)}个可用域名:\n"
            for index, domain in enumerate(cfg.network.domain_list, 1):
                result += f"{index}. {domain}\n"
            if removed:
                result += f"\n❌ 已移除{len(removed)}个不可用域名"
            await self.reply(result.strip())
            return True, "ok"

        except Exception as exc:
            logger.error(f"测试域名失败: {exc}")
            resource_manager.save_debug_text(
                "domain_test_error", traceback.format_exc()
            )
            result = f"测试域名失败: {exc}"
            lower = str(exc).lower()
            if "timeout" in lower or "connect" in lower:
                result += (
                    "\n\n可能是网络问题，建议配置代理后再试:\n"
                    "/jmconfig proxy http://127.0.0.1:7890"
                )
            await self.reply(result)
            return True, "error"
