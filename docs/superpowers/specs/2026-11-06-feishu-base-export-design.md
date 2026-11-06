# 飞书 Base 导出插件设计（2026-11-06）

状态：review 分支上的失败关闭实现。不是本机部署，也不是业务已打通。

## 目标

同事在飞书自建 bot 私聊里要求导出整个 Base 的 xlsx，或按聚合数据重绘柱状图 PNG/PDF，文件只回到本人私聊。每人独立用户 token。不用老板 token，不共用 CLI profile，不把文件发给别人。图必须带「据聚合数据重绘，非飞书原图」，不能当成飞书原图。

## 这一轮实际做到的边界

插件 `plugins/feishu_base_export/` 已注册三个动作：`export_xlsx`、`chart_png`、`chart_pdf`。三个动作目前都返回 `status=blocked`，不发网络请求，不写文件，不把路径交给模型。旁边有已测过的纯函数：身份绑定、一次性 opaque state、PKCE、token 文件位置、URL 主机限制、xlsx 压缩包检查、导出请求组装、合成数据画 PNG/PDF。

完整私聊回文件 **未 ready**。

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

实现在 `bitable_xlsx.py`（文件名避开仓库 `.gitignore` 的 `export*`）。工具本身还不调用它。

## 威胁边界（不承诺的部分）

`agent/file_safety.py` 写明：这些拒绝是纵深防御，不是安全边界；terminal 以同一 OS 用户运行，可以读写它能碰到的文件。token 放在 `HERMES_HOME/mcp-tokens/feishu-base-export/<sha256>.bin`，读工具会对这个目录返回拒绝，文案里包含 “not a security boundary” 和 terminal。这挡住的是走 `get_read_block_error` 的读工具，不是 shell，也不是机主。

DPAPI 只在 `sys.platform == win32` 时调用 `CryptProtectData`。其他平台 `production_protector()` 抛 `DpapiUnavailable`，不写一份假的「已加密」文件。本机 Linux 测试证明了拒绝。`windows_only` 往返测试在这次运行中被跳过，**不能写成 DPAPI 已通过**。

机主和带 shell 的模型不在隔离承诺里。

## 部署

不要在用户 Windows 安装目录上 `git pull` 这个 fork。那边的 origin 仍是 NousResearch 上游，拉取会盖住安装树和已有 dirty skills。本机 `HERMES_HOME`、WebSocket/webhook 未知。Gateway PID 51168 只作为只读元数据，本轮没有重启，也没有读它的配置或凭据。

部署前必须拿到并对照这四个本地文件的源码：`hermes_cli/plugins.py`、`tools/registry.py`、`model_tools.py`、`agent/tool_executor.py`。对照通过之前，不要把插件拷进运行中的 `HERMES_HOME`，不要改飞书权限，不要发版。
