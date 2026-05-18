# jm_comic

Neo-MoFox JM 漫画下载与查询插件，支持下载为 PDF、漫画信息查询、关键词搜索、作者搜索、随机推荐、预览图片、域名测试与运行状态查看。

## 命令

- `/jm [ID]`：下载漫画为 PDF 并发送
- `/jmimg [ID] [页数]`：发送漫画前几页预览图片
- `/jminfo [ID]`：查看漫画信息
- `/jmpdf [ID]`：检查本地 PDF 文件信息
- `/jmsearch [关键词] [序号]`：搜索漫画并显示指定结果
- `/jmauthor [作者] [序号]`：搜索作者作品
- `/jmrecommend`：随机推荐漫画
- `/jmdomain list|test|update`：查看、测试或更新镜像域名
- `/jmconfig`：在线查看或修改配置
- `/jmstatus`：查看插件运行状态
- `/jmcleanup`：清理过期文件
- `/jmhelp`：显示帮助

## 配置

插件使用 Neo-MoFox 配置系统，配置文件路径为 `config/plugins/jm_comic/config.toml`。

可配置项包括：镜像域名列表、代理、AVS Cookie、最大下载线程数、是否显示封面、调试模式。

## 依赖

- `jmcomic>=2.5.39`
- `PyYAML>=6.0`
- `curl_cffi>=0.6.0`
- `img2pdf`

## 免责声明

本插件仅供学习交流使用，请遵守当地法律法规与目标站点规则。
