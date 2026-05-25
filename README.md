# jm_comic — Neo-MoFox JM 漫画插件

> **开发重点：Cookie 登录管理改造**

## 概述

jm_comic 是一个面向 Neo-MoFox 框架的 JM 漫画下载与查询插件。本 README **重点记录插件在 Cookie 登录管理方面的核心改造**，包括自动登录、多渠道 Cookie 提取、持久化、过期自动重登录等，而非基础功能列表。

---

## 一、Cookie 登录管理核心架构

### 1. 整体设计

```
                ┌─────────────────────────────────────────┐
                │           JmSessionManager              │
                │         (core/session.py)               │
                │                                         │
                │   login() ←── username + password        │
                │     │                                    │
                │     ├──→ _extract_cookies()              │
                │     │     ├── 方式1: meta_data['cookies']│
                │     │     ├── 方式2: session.cookies     │
                │     │     ├── 方式3: client.cookies      │
                │     │     └── 方式4: GET 请求触发        │
                │     │                                    │
                │     └──→ _save_cookies(cookies)          │
                │           ├── full_cookies (JSON)        │
                │           └── avs_cookie (向后兼容)      │
                │                                         │
                │   ensure_logged_in() ←── 懒加载策略      │
                │   logout() ←── 清除 Cookie               │
                └─────────────────────────────────────────┘
                            │
                            ▼
                ┌─────────────────────────────────────────┐
                │           JMClientFactory                │
                │       (core/client_factory.py)           │
                │                                         │
                │   _resolve_cookies()                     │
                │     ├── full_cookies JSON (优先)         │
                │     └── avs_cookie (降级兼容)            │
                │                                         │
                │   create_client() ←── 确保登录后创建     │
                │   update_option()  ←── 重建 Option      │
                └─────────────────────────────────────────┘
                            │
                            ▼
                ┌─────────────────────────────────────────┐
                │           ComicDownloader                │
                │       (core/downloader.py)               │
                │                                         │
                │   403/登录过期检测                        │
                │     ├── 有凭证 → 自动重登录 → 重试       │
                │     └── 无凭证 → 提示用户配置            │
                └─────────────────────────────────────────┘
```

### 2. 四种 Cookie 提取策略（`JmSessionManager._extract_cookies()`）

由于 jmcomic 库在不同版本、不同客户端实现（`html` / `api` / `curl_cffi` / `curl_cffi_session`）中存储 Cookie 的位置不同，插件实现了**四级降级提取**：

| 优先级 | 提取方式 | 适用场景 |
|--------|----------|----------|
| ① | `client.get_meta_data("cookies")` | 推荐方式，jmcomic `login()` 会将新 Cookie 写入 `meta_data['cookies']` |
| ② | `client.session.cookies` | `AbstractSessionPostman( curl_cffi_session)`实现，Cookie 存储在 session 中 |
| ③ | `client.cookies` 属性 | 部分客户端实现直接在 client 实例上挂载 cookies 属性 |
| ④ | GET 请求首页触发 `set-cookie` | 兜底，登录后再请求一次以触发服务端下发 Cookie |

```python
# session.py — 核心提取逻辑（简化）
def _extract_cookies(self, client) -> dict[str, str]:
    cookies = {}
    
    # 方式1：meta_data['cookies']
    meta_cookies = client.get_meta_data("cookies")
    if meta_cookies: cookies.update(meta_cookies)
    
    # 方式2：session.cookies
    if not cookies:
        jar = getattr(getattr(client, "session", None), "cookies", None)
        if jar: cookies.update(jar)
    
    # 方式3：client.cookies
    if not cookies:
        jar = getattr(client, "cookies", None)
        if jar: cookies.update(jar)
    
    # 方式4：GET 请求触发
    if not cookies:
        resp = client.get("https://domain/")
        rc = getattr(resp, "cookies", None)
        if rc: cookies.update(rc)
    
    # 兜底：保留已有 AVS Cookie
    if not cookies and self.config.network.avs_cookie:
        cookies["AVS"] = self.config.network.avs_cookie
    
    return cookies
```

> **为什么需要这四种方式？** jmcomic 库在 2.5.x~3.x 之间的客户端实现多次变更，从 `AbstractPostman` 到 `AbstractSessionPostman`，Cookie 存储位置从 `meta_data` 迁移到 `session.cookies`。四级降级策略保证不论用户使用哪个版本的 jmcomic，都能正确提取到登录后的完整 Cookie。

### 3. Cookie 持久化（`_save_cookies()` + `_persist_config()`）

登录成功后，Cookie 按以下方式持久化：

```python
def _save_cookies(self, cookies):
    # 保存完整 Cookie JSON（所有 Cookie 字段）
    self.config.network.full_cookies = json.dumps(cookies)
    
    # 同时更新 AVS Cookie（向后兼容旧版配置）
    if "AVS" in cookies:
        self.config.network.avs_cookie = cookies["AVS"]

def _persist_config(self):
    # 调用 _config_io.save_config() 写入 config.toml
    save_config(self.config)
```

**为什么既保存 `full_cookies` 又保留 `avs_cookie`？** 旧版配置只支持单个 `avs_cookie` 字段。升级到完整 Cookie 后，同时保留 `avs_cookie` 确保：
- 新版代码（优先读 `full_cookies`）能使用完整 Cookie 访问受限资源
- 降级时（`full_cookies` 格式异常）自动回退到 `avs_cookie`
- 用户手动查看/修改配置时两种格式都可见

### 4. Cookie 解析与使用（`JMClientFactory._resolve_cookies()`）

```python
def _resolve_cookies(self, net):
    # 优先级1：完整 Cookie JSON
    if net.full_cookies:
        try:
            parsed = json.loads(net.full_cookies)
            if isinstance(parsed, dict):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    
    # 优先级2：单字段 AVS Cookie（向后兼容）
    if net.avs_cookie:
        return {"AVS": net.avs_cookie}
    
    return {}
```

### 5. 登录过期自动重登录（`ComicDownloader._download_with_retry()`）

```python
# downloader.py — 下载过程中检测登录过期
if is_login_needed:
    if self.client_factory.session_manager.has_credentials:
        # 自动重新登录
        login_ok = self.client_factory.session_manager.login()
        if login_ok:
            self.client_factory.update_option()  # 重建 Option 使用新 Cookie
            continue  # 重试下载
        else:
            return False, "自动重新登录失败，请检查用户名密码"
    else:
        return False, "登录已过期，请配置用户名密码或手动设置 Cookie"
```

**工作流**：
```
用户下载漫画 → 403 (登录过期)
  ├── 有 username/password → 自动重新登录 → 更新 Cookie → 重试下载
  └── 无凭证 → 提示用户配置
```

---

## 二、用户命令：Cookie 管理接口

| 命令 | 功能 | 内部实现 |
|------|------|----------|
| `/jmconfig login` | 执行自动登录 | `JmSessionManager.login()` → 提取 Cookie → 持久化 → 重建客户端 |
| `/jmconfig logout` | 清除登录状态 | 清空 `avs_cookie` + `full_cookies` → 持久化 → 重建客户端 |
| `/jmconfig cookie [值]` | 手动设置 AVS Cookie | 直接写入配置 → 持久化 → 重建客户端 |
| `/jmconfig username [值]` | 设置用户名 | 写入配置 → 持久化 |
| `/jmconfig password [值]` | 设置密码 | 写入配置 → 持久化 |
| `/jmconfig info` | 查看配置与登录状态 | 显示 `full_cookies`/`avs_cookie`/用户名状态 |

**`/jmconfig info` 登录状态展示**：
```
Cookie: 已设置
完整Cookie: ✅ 已登录（完整Cookie已保存）
```
或：
```
Cookie: 已设置
完整Cookie: ⚠️ 部分Cookie（仅AVS，可能过期）
```

---

## 三、消息链路适配（辅助修改）

除 Cookie 管理外，插件还做了以下消息链路适配：

### 路径转换（`core/messaging.py`）

NapCat 运行在 WSL 中，无法直接访问 Windows 相对路径。`messaging.py` 实现了：

- **`_windows_path_to_wsl_path()`**：`C:/path` → `/mnt/c/path`
- **`_resolve_to_napcat_path()`**：统一转换相对/Windows绝对/WSL绝对路径

### 文件发送封装（`reply_local_file`）

```python
napcat_path = _resolve_to_napcat_path(file_path)
return await send_file(file_path=napcat_path, stream_id=stream_id, file_name=name)
```

### 图文合并发送（`reply_search_result_item`）

发送搜索结果时，优先使用 `send_text_with_image` 将标题和封面图合并为一条消息；失败时降级为逐条发送。

---

## 四、其他架构设计

| 模块 | 职责 |
|------|------|
| `plugin.py` | 生命周期管理，初始化 ResourceManager/JMClientFactory/ComicDownloader |
| `config.py` | 配置模型（TOML） |
| `core/resource_manager.py` | 目录管理、存储限额（5GiB）、过期清理（7天） |
| `core/client_factory.py` | JM 客户端工厂，代理自动检测（环境变量→Windows注册表） |
| `core/domain_utils.py` | 多源域名抓取与可用性测试 |
| `core/search_session.py` | 搜索翻页缓存（5分钟过期） |
| `core/helpers.py` | 输入校验、错误提示、HTML 解析等工具函数 |

---

## 五、设计约束

- **不修改任何 Neo-MoFox 框架文件**：所有改造均在插件目录内完成。
- **多重降级**：Cookie 提取四级降级、图文发送二级降级、域名抓取四源降级，确保关键功能不因上游变更而失效。
- **向后兼容**：同时维护 `full_cookies`（新版）和 `avs_cookie`（旧版），平滑过渡。
- **自动恢复**：下载过程中检测到登录过期时，自动重新登录并重试，无需用户干预。

---

## 六、依赖

- `jmcomic>=2.5.39` — JM 漫画官方客户端
- `PyYAML>=6.0`
- `curl_cffi>=0.6.0`
- `img2pdf`

---

## 免责声明

本插件仅供学习交流使用，请遵守当地法律法规与目标站点规则。
