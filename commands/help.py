"""``/jmhelp`` 命令：显示插件帮助。"""

from __future__ import annotations

from src.app.plugin_system.base import cmd_route

from ._base import JmBaseCommand

HELP_TEXT = (
    "📚 JM 漫画插件命令列表：\n"
    "1️⃣ /jm [ID] - 下载漫画为 PDF\n"
    "2️⃣ /jmimg [ID] [页数] - 发送漫画前几页图片\n"
    "3️⃣ /jminfo [ID] - 查看漫画信息\n"
    "4️⃣ /jmpdf [ID] - 检查 PDF 文件信息\n"
    "5️⃣ /jmauthor [作者] [序号] - 搜索作者作品\n"
    "6️⃣ /jmsearch [关键词] [序号(可选)] - 搜索漫画（仅关键词=翻页，加序号=查看详情）\n"
    "7️⃣ /jmrecommend - 随机推荐漫画\n"
    "8️⃣ /jmconfig - 配置插件\n"
    "9️⃣ /jmdomain - 测试并更新可用域名\n"
    "🔟 /jmstatus - 查看插件状态\n"
    "1️⃣1️⃣ /jmcleanup - 清理过期文件\n"
    "1️⃣2️⃣ /jmhelp - 查看帮助\n"
    "\n"
    "📌 说明：\n"
    "· /jmsearch 仅输入关键词可查看前10条，再次输入相同关键词自动翻页\n"
    "· [序号] 表示结果中的第几个，从 1 开始\n"
    "· 搜索多个关键词时用空格分隔\n"
    "· 作者搜索按时间倒序排列\n"
    "· 如果 PDF 发送失败，可使用 /jmimg 命令获取图片\n"
    "· 如果遇到网站结构更新导致失败，请通过 /jmdomain update 更新域名\n"
    "· 可通过 /jmconfig cover on/off 控制是否显示封面图片\n"
    "· 使用 /jmstatus 查看存储使用情况，/jmcleanup 清理过期文件"
)


class JmHelpCommand(JmBaseCommand):
    """``/jmhelp``：显示插件帮助。"""

    command_name: str = "jmhelp"
    command_description: str = "显示 JM 漫画插件帮助信息"
    command_prefix: str = "/"

    @cmd_route()
    async def handle(self) -> tuple[bool, str]:
        """发送帮助文本到当前聊天流。"""
        await self.reply(HELP_TEXT)
        return True, "ok"
