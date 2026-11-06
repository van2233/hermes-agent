# Feishu Base Export Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在 pin `5eb99eb2` 上放一个独立、默认不启用的插件，把已核实的安全检查和导出/画图纯函数落地，并把未证实的 OAuth、图表拉取和出站文件标成 blocked。

**Architecture:** `plugins/feishu_base_export/` 不改 Hermes 核心。工具三个动作都直接返回 blocked JSON。绑定、state、token 路径、URL 限制、xlsx 检查、导出客户端和合成图渲染是可单测的库。它们不被当前工具调用去访问飞书。

**Tech Stack:** Python 3.12 标准库，pin 上已有的 `agent.file_safety` 与 `tools.thread_context`。不新增依赖，不改 `pyproject.toml`。

## Global Constraints

- 分支从 `5eb99eb2844b22ebb723711b8e6a0bbb80bb5f04` 拉出，不升级，不改核心。
- 不覆盖已有 skills，不 `git add -A`，不向 NousResearch 推送，不合并。
- 不部署用户机，不改 bot 配置或飞书权限，不重启，不读凭据，不发消息，不开隧道。
- 不把 `a992c8f1` 写成已兼容。那两笔本地提交的源码不在本仓库。
- 设备码、公网回调、图表 v3 HTTP、出站 `MEDIA:` 都不实现。
- Linux 上的 DPAPI 测试只允许证明「拒绝」。Windows 往返必须在 `windows_only` 上跑过才算 DPAPI 通过。
- 单文件不超过 400 行。

---

### Task 1: 失败关闭的工具与绑定

**Files:**

- Create: `plugins/feishu_base_export/tool.py`
- Create: `plugins/feishu_base_export/blocked.py`
- Create: `plugins/feishu_base_export/binding.py`
- Create: `plugins/feishu_base_export/identity.py`
- Create: `plugins/feishu_base_export/__init__.py`
- Create: `plugins/feishu_base_export/plugin.yaml`
- Test: `tests/plugins/test_feishu_base_export.py`

**Interfaces:**

- Consumes: 飞书事件对象上的 `source.chat_type`、`source.platform`、`raw_message.event.sender.sender_id.open_id`
- Produces: `handle(args, **kwargs) -> str`，`consider_event(event, store) -> TurnBinding | None`，`register(ctx)`

- [x] **Step 1: 写失败测试**

断言 schema 枚举就是 `export_xlsx`、`chart_png`、`chart_pdf`；三者都是 `status=blocked`；传入的 transport 不被调用；群聊和 tenant id 不产生绑定；原始 open_id 覆盖 session user_id。

- [x] **Step 2: 看到收集失败**

`scripts/run_tests.sh tests/plugins/test_feishu_base_export.py` 在模块不存在时 `ModuleNotFoundError`。

- [x] **Step 3: 最小实现**

工具不读 open_id 参数。hook 只记录私聊绑定，返回 None，不丢消息。

- [x] **Step 4: 测试通过**

见文末命令。Windows DPAPI 用例被跳过，不计入通过。

### Task 2: OAuth state、token 路径、DPAPI 拒绝

**Files:**

- Create: `plugins/feishu_base_export/oauth_state.py`
- Create: `plugins/feishu_base_export/token_store.py`
- Create: `plugins/feishu_base_export/dpapi.py`
- Test: 同上

**Interfaces:**

- Produces: `StateStore.issue/consume`，`pkce_pair() -> (verifier, challenge)`，`TokenStore.save/load`，`production_protector()`

- [x] state 是一次性随机串，不含 open_id。PKCE 为 S256，verifier 长度 43 到 128。
- [x] token 文件在 `mcp-tokens/feishu-base-export/`，文件名是 sha256 前缀，明文不落盘（测试用 LoopProtector，名字是 `test-loop`，不是 DPAPI）。
- [x] `linux_only`：`WindowsDpapiProtector.protect` 与 `production_protector` 抛 `DpapiUnavailable`。
- [ ] `windows_only`：`CryptProtectData` 往返。本轮 Linux 跳过，未完成。

### Task 3: 导出客户端与 xlsx 界限

**Files:**

- Create: `plugins/feishu_base_export/http_guard.py`
- Create: `plugins/feishu_base_export/xlsx_safe.py`
- Create: `plugins/feishu_base_export/bitable_xlsx.py`
- Create: `plugins/feishu_base_export/redact.py`

**Interfaces:**

- Produces: `parse_official_https(url) -> str`，`assert_safe_xlsx(data)`，`export_bitable_xlsx(*, user_token, base_token, transport, host="open.feishu.cn", sleep, attempts=6) -> bytes`

- [x] 只接受官方 https 主机；302 不再请求；body 无 `sub_id`；`type=bitable`，`file_extension=xlsx`。
- [x] `job_status` 110 不下载，错误不含 user token。
- [x] 非 PK、`..` 路径、高压缩比 zip 被拒绝。
- [ ] 不把客户端接到工具。接上等于在未对照本地工具链、且没有用户 token 获取路径时发真实下载。保持 blocked。

### Task 4: 合成图，不接飞书

**Files:**

- Create: `plugins/feishu_base_export/chart_data.py`
- Create: `plugins/feishu_base_export/chart_draw.py`
- Create: `plugins/feishu_base_export/disclaimer_rgb.py`

**Interfaces:**

- Produces: `parse_aggregate(dict) -> ChartTable`，`render_pixels(table) -> (w, h, rgb)`，`render_chart(table, "png"|"pdf") -> bytes`

- [x] 空 `main_data` 抛 `EmptyAggregate`。超过 500 行抛 `PayloadBoundsError`。
- [x] PNG 魔数与 PDF 头都生成。免责声明位图像素贴在 (8, 8)，测试检查画布 (66, 12) 不是白色。
- [ ] 不实现 v3 block data HTTP。工具对 png 和 pdf 都返回 blocked，原因里两个格式都出现。

### Task 5: 仍不能做的事

- [ ] 对照本地四文件后再决定 hook 是否还能注册。
- [ ] 官方如果补上「已有自建应用的设备码换 user_access_token」，再写获取流程。在那之前不开回调。
- [ ] server-docs 写出图表数据接口的方法和 scope 之后，再让 `chart_png` / `chart_pdf` 调用它，并继续使用现有画图函数加水印。
- [ ] 出站改成不经过模型回显的发送之后，才允许工具写 xlsx 并让网关发给当前私聊。禁止 home channel，禁止参数里的 chat_id。

## 验证命令

```bash
HERMES_PYTHON=/tmp/feishu-venv/bin/python scripts/run_tests.sh tests/plugins/test_feishu_base_export.py --tb=short -q
```

2026-11-06 在本工作区的结果：15 passed，1 skipped（`windows_only`）。跳过的那条不是 DPAPI 通过。
