# /jmhelp command module.

from __future__ import annotations

from src.app.plugin_system.base import cmd_route

from ._base import JmBaseCommand

HELP_TEXT = (
    'JM-Cosmos command list:\n'
    '/jm [ID] - Download comic as PDF\n'
    '/jmimg [ID] [pages] - Send preview images\n'
    '/jminfo [ID] - Show comic information\n'
    '/jmpdf [ID] - Show local PDF information\n'
    '/jmauthor [author] [count] - Search author works\n'
    '/jmsearch [keywords] [index] - Search comics\n'
    '/jmrecommend - Random recommendation\n'
    '/jmconfig - Configure plugin\n'
    '/jmdomain - Test and update domains\n'
    '/jmstatus - Show runtime status\n'
    '/jmcleanup - Cleanup old files\n'
    '/jmhelp - Show this help'
 )

class JmHelpCommand(JmBaseCommand):
    'Show JM plugin help.'

    command_name: str = 'jmhelp'
    command_description: str = 'Show JM plugin help'
    command_prefix: str = '/'

    @cmd_route()
    async def handle(self) -> tuple[bool, str]:
        'Send help text.'
        await self.reply(HELP_TEXT)
        return True, 'ok'
