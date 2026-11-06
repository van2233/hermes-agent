# 飞书 Base 导出插件设计（2026-11-06）

状态：review 分支第二轮。配置齐全时 Excel 授权和导出代码会运行；图表实取仍 blocked。不是本机部署，也不是飞书实机通过。

## 目标

同事在飞书自建 bot 私聊里要求导出整个 Base 的 xlsx，或按聚合数据重绘柱状图 PNG/PDF，文件只回到本人私聊。每人独立用户 token。不用老板 token，不共用 CLI profile，不把文件发给别人。图必须带「据聚合数据重绘，非飞书原图」，不能当成飞书原图。

## 这一轮实际做到的边界

`export_xlsx` 在私聊绑定存在、并且 `FEISHU_APP_ID`、`FEISHU_APP_SECRET`、`redirect_uri` 都有值时，会发出授权链接、用回调里的 code 换 token、核对同一应用的 `open_id`、按需刷新，再调用官方 Drive 导出。缺任何一项返回 `setup-required`，不会无条件 blocked。`revoke` 删除该 open_id 的本地 token。`chart_png` / `chart_pdf` 仍 blocked。

私聊文件不改核心。网关把最终回复里的 `MEDIA:` 发给当前消息的 `chat_id`。自动补附件只信任 `text_to_speech` 和 `image_generate`（`gateway/run.py` 的 `_AUTO_APPEND_MEDIA_TOOL_NAMES`）。插件用 `transform_llm_output` 去掉模型写的其它 `MEDIA:`，再写上本轮唯一路径。发送者 open_id 只来自原始事件；工具参数里的 open_id 被忽略。会话 message_id 对不上绑定就拒绝。

机主和同一 OS 用户的 shell 仍能读到进程能读的文件。token 在 `mcp-tokens/` 下，读工具会拒绝，这不是强沙箱。非 Windows 不落盘明文，DPAPI 只在 Windows 调用。

对照本机 `a992c8f1` 的四个文件（未提交进仓库）：`register_tool` / `register_hook` 参数没变，`pre_gateway_dispatch` 和 `transform_llm_output` 仍在，工具线程仍经 `propagate_context_to_thread` 提交。`registry.dispatch` 仍是 `handler(args, **kwargs)`，多出来的 `task_id` / `session_id` / `user_task` 不能当飞书身份。本地 `model_tools.py` 在进 handler 前多了一道 capability 检查：结果是 `None` 或 `allowed` 为假就拒绝。插件不能把自己标成 read_only。`agent/runtime_capability.py` 不在这四份源码里，所以还不能证明这道门会放行 `feishu_base_export`。不把那份本地补丁抄进插件。

## 证据，含上轮需要改口的地方

基线提交 `5eb99eb2844b22ebb723711b8e6a0bbb80bb5f04`。`pyproject.toml` 版本是 `0.21.2`。提交时间 2026-09-14。仓库没有这个提交的 git tag。本机标签「2026.9.11」和提交时间不一致，只记作边界，不把两者说成同一个发布瞬间。

`git rev-list --count 5eb99eb2..HEAD` = **28255**，`HEAD..5eb99eb2` = **0**。该提交是当前 fork `main` 的祖先，28255 是 main 领先的提交数。`git rev-list --count HEAD` = 62833，pin 可达 34578。62833 不是领先数。

`a992c8f1c47` 不在这个 fork 里。父对话只读元数据：相对 pin 的两笔提交是 `29267cab718` 与 `a992c8f1c47`，65 files，+5834/-77。路径列表没有 feishu adapter，也没有 `gateway/platforms`、`plugins/platforms`。明确改过 `hermes_cli/plugins.py`、`tools/registry.py`、`model_tools.py`、`agent/tool_executor.py` 和 runtime/quality-gate。源码 patch 没拿到。因此 **不能把本仓库的单测写成这两笔提交已兼容**。ZIP 尚未上传，这里没有那份 diff。

## 前置复核后改掉的设计

### 身份不靠「hook 里的 ContextVar 一定能传到工具」

pin 上 `tools/thread_context.py::propagate_context_to_thread` 会 `contextvars.copy_context()`，再在 worker 里 `ctx.run`。工具线程池在 `agent/tool_executor.py` 和 `model_tools.py` 提交任务时调用它。这是 **5eb99eb2 的机制**。那两个文件都在未读的本地提交里，所以这条链路在本机上未证明。

本插件的工具处理函数不读 `HERMES_SESSION_*`，不读参数里的 open_id，也不发请求。绑定表只由 `pre_gateway_dispatch` 根据原始事件的 `sender.sender_id.open_id` 写入，并且只接受私聊 `dm` + 原始 `p2p`。会话里的 tenant `user_id` 不会被当成绑定键。工具在绑定存在时仍然 blocked。这样，本地工具线程即使丢了 ContextVar，也不会导出或串号；最坏情况是插件因本地 `register_tool` 签名不同而加载失败。

`transform_llm_output` 只在 `agent/turn_finalizer.py` 的最终文本上跑一次。`extract_media` 还出现在 `gateway/run_notifications.py`、`gateway/kanban_watchers.py`、`gateway/run_turn.py`。所以它盖不住全部出站路径。本轮不靠它，也不靠模型自觉。工具不返回 `MEDIA:` 路径。

### 设备授权没有写成前置

已核对的官方页面：

- 用户授权码：`GET https://accounts.feishu.cn/open-apis/authen/v1/authorize`，`response_type=code`，`redirect_uri` 必填且要预先登记。`state` 原样回传。`code_challenge` / `code_challenge_method=S256` 可选。`offline_access` 要写进 scope 才能拿 refresh token。
- 换 token 的 v2 页把 `grant_type` 写成固定值 `authorization_code`，并要求 `client_id` 与 `client_secret`。`expires_in` 是秒，文档要求用返回值，不要写死。`refresh_token` 只在授予 `offline_access` 时返回，且只能用一次。刷新页写明刷新后旧 refresh token 立即失效，并提到约 365 天后错误码 20037，必须重新授权。
- `GET https://open.feishu.cn/open-apis/authen/v1/user_info` 的 `open_id` 说明是「用户在应用内的唯一标识」。示例是 `ou-...`。适配器注释里的事件 id 是 `ou_`。绑定同时接受这两种前缀，并拒绝 `u_` / `on_`。
- 官方「Device Authorization Grant」文档出现在一键创建应用（`registerApp`）流程，产物是应用凭证，不是「已有自建 bot 用同一应用给同事换 user_access_token」。第三方仓库里的 `accounts.feishu.cn/oauth/v1/device_authorization` 没有被上述用户令牌文档列为 grant。CLI 实测设备登录成功，不能当成这个 bot 应用的官方设备码接口。

因此：不实现设备码轮询，不借用 CLI 的 client，不刮取 CLI 凭据，不监听公网回调，不建隧道。HTTPS 回调仍只是以后的备选。state 用 `secrets.token_urlsafe`，服务端保存 open_id 和 PKCE verifier；state 字符串本身不含 open_id，也不用 App Secret 签名。

### 图表 transport 未当成已验证

官方 server-docs 有 `GET /open-apis/bitable/v1/apps/:app_token/dashboards`（列出仪表盘）。组件聚合数据的 `GET /open-apis/base/v3/bases/:base_token/dashboards/blocks/:block_id/data` 只出现在 `open.feishu.cn` 上的 CLI skill 说明里，没有在 server-docs 里看到 scope。不实现这条 HTTP。

PNG 和 PDF 没有从工具枚举里拿掉。`chart_png` 与 `chart_pdf` 都返回 blocked，原因里同时写明 png 和 pdf。合成 `dimensions` / `measures` / `main_data` 的画图函数会出两种文件，并在像素里放上那句中文。这不是飞书实机结果。空 `main_data` 直接拒绝，不画空图。

### 导出 HTTP 只实现文档里的三步

- `POST /open-apis/drive/v1/export_tasks`，body 只有 `file_extension=xlsx`、`type=bitable`、文档 `token`。不传 `sub_id`（文档写明 sub_id 用于 csv）。
- `GET /open-apis/drive/v1/export_tasks/:ticket?token=`
- `GET /open-apis/drive/v1/export_tasks/file/:file_token/download`
- 权限文档写的是 `docs:document:export` 或 `drive:export:readonly` 之一。用户已用 CLI 测通的其余 scope 不在这里扩大。
- 文档 token 最大长度 27。下载须在任务结束后 10 分钟内。`job_status` 110/109 等失败不下载。
- 只允许 `https://open.feishu.cn` 与 `https://open.larksuite.com`，端口仅 443。拒绝 userinfo、IP 字面量、其他主机。3xx 直接失败，不跟随后续请求。
- 错误文本先按调用方传入的 secret 替换，再去掉 Bearer 和 `refresh_token=` / `code=` 一类参数。`job_error_msg` 不回传，避免把 token 带回模型。

实现在 `bitable_xlsx.py`（文件名避开仓库 `.gitignore` 的 `export*`）。`export_xlsx` 在 token 可用时调用它。没有监听新端口。

## 威胁边界（不承诺的部分）

`agent/file_safety.py` 写明：这些拒绝是纵深防御，不是安全边界；terminal 以同一 OS 用户运行，可以读写它能碰到的文件。token 放在 `HERMES_HOME/mcp-tokens/feishu-base-export/<sha256>.bin`，读工具会对这个目录返回拒绝，文案里包含 “not a security boundary” 和 terminal。这挡住的是走 `get_read_block_error` 的读工具，不是 shell，也不是机主。

DPAPI 只在 `sys.platform == win32` 时调用 `CryptProtectData`。其他平台 `production_protector()` 抛 `DpapiUnavailable`，不写一份假的「已加密」文件。本机 Linux 测试证明了拒绝。`windows_only` 往返测试在这次运行中被跳过，**不能写成 DPAPI 已通过**。

机主和带 shell 的模型不在隔离承诺里。

## 部署

不要在用户 Windows 安装目录上 `git pull` 这个 fork。那边的 origin 仍是 NousResearch 上游，拉取会盖住安装树和已有 dirty skills。本机 `HERMES_HOME`、WebSocket/webhook 未知。Gateway PID 51168 只作为只读元数据，本轮没有重启，也没有读它的配置或凭据。

部署前必须拿到并对照这四个本地文件的源码：`hermes_cli/plugins.py`、`tools/registry.py`、`model_tools.py`、`agent/tool_executor.py`。对照通过之前，不要把插件拷进运行中的 `HERMES_HOME`，不要改飞书权限，不要发版。
