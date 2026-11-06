# 部署入口

离线验证不读配置、不改配置、不写策略、不监听、不重启。`prepare_profile.py` 只拷贝新增源码。启用和 `redirect_uri` 只能用官方 `hermes plugins enable` / `hermes config set`，不能靠这个拷贝脚本。

## 已在 Windows 实测（56982 字节那一包）

包已解到：

`C:\Users\21292\Desktop\FeishuExportValidation-20261106\pkg`

📁 在资源管理器中打开

http://127.0.0.1:17831/open/b/QzpcVXNlcnNcMjEyOTJcRGVza3RvcFxGZWlzaHVFeHBvcnRWYWxpZGF0aW9uLTIwMjYxMTA2XHBrZw

explorer /select,"C:\Users\21292\Desktop\FeishuExportValidation-20261106\pkg"

现有 venv 对 `test_windows_dpapi_roundtrip_is_real_cryptprotect` 的结果是 1 passed、14 deselected、退出码 0。这是真实 Windows DPAPI 往返，输出里没有密文。

`prepare_profile.py --profile-home C:\Users\21292\AppData\Local\hermes` 不带 `--apply`：`dry_run=true`，`files=25`，退出码 0。没有写入。

`hermes config get plugins.entries.feishu-base-export.enabled` 和 `plugins.entries.feishu-base-export.settings.redirect_uri` 都是 Config key not set。`runtime_capability.manifest_file` 仍是 `runtime-policy.json`。`hermes plugins list --plain` 只有 bundled `feishu-platform`（not enabled），没有本导出插件。`feishu-platform` 未启用不能用来判断飞书消息是否健康。default gateway PID 51168 仍在运行。CLI config path 与 env-path 同此前。该 PID 的实际 home 仍没有官方证明。

未安装、未启用、未写配置、未监听、未重启、未发消息。回调 URL 仍缺，不能上线。

## 1. 现在就能跑的 Windows 离线验证

把 zip 解到一个空的临时目录，不要解进 Hermes 安装根，不要 `git pull`。

```text
mkdir %TEMP%\feishu-base-export-verify
tar -xf feishu-base-export-windows-offline.zip -C %TEMP%\feishu-base-export-verify
py -3 %TEMP%\feishu-base-export-verify\plugins\feishu_base_export\windows_offline_verify.py --work-dir %TEMP%\feishu-base-export-verify-work
```

通过标准：进程退出码 `0`，并且输出里同时有

```text
deps=stdlib_only
dry_run=true
temp_copy=true
charts=blocked
policy_insert=additive
listening=false
auth_ready=false
config_modified=false
policy_modified=false
dpapi=roundtrip_ok
result=PASS
```

`dpapi=windows_only` 或退出码 `2` 不是通过。`--work-dir` 里如果已经有 `config.yaml` 或 `.env`，脚本拒绝并退出码 `1`，不会往下写。工作目录里不应出现 Hermes 的 `config.yaml`。这条命令不表示飞书认证已经就绪。

## 2. 复查 Gateway 用的是哪个 profile

上次 default/current PID 是 51168。PID 可能已经变了，用官方命令重查。这三条都不打印 secret，也不打印完整进程命令行：

```text
hermes gateway list
hermes profile
hermes config path
```

`hermes gateway list` 把 PID 印在 profile 名字旁边。这个 PID 来自该 profile 目录里的 `gateway.pid`，命令本身不打印目录。`hermes profile` 印出的 Path 只属于当前 Active profile。

两者是同一个 profile，仅当 PID 那一行的名字等于 Active profile 的名字。这时 `hermes config path` 的父目录才是 Gateway 的 profile。上次查到的 config path 是：

`C:\Users\21292\AppData\Local\hermes\config.yaml`

📁 在资源管理器中打开

http://127.0.0.1:17831/open/b/QzpcVXNlcnNcMjEyOTJcQXBwRGF0YVxMb2NhbFxoZXJtZXNcY29uZmlnLnlhbWw

explorer /select,"C:\Users\21292\AppData\Local\hermes\config.yaml"

`hermes config env-path` 是同目录 `.env`，文件没有打开。

📁 在资源管理器中打开

http://127.0.0.1:17831/open/b/QzpcVXNlcnNcMjEyOTJcQXBwRGF0YVxMb2NhbFxoZXJtZXNcLmVudg

explorer /select,"C:\Users\21292\AppData\Local\hermes\.env"

如果 PID 旁边的名字不是 Active profile，改跑 `hermes -p <那个名字> config path`，用那个文件的父目录。不要把默认 CLI 路径写成已经证明的 Gateway home。

安装根仍是：

`C:\Users\21292\AppData\Local\hermes\hermes-agent`

📁 在资源管理器中打开

http://127.0.0.1:17831/open/b/QzpcVXNlcnNcMjEyOTJcQXBwRGF0YVxMb2NhbFxoZXJtZXNcaGVybWVzLWFnZW50

explorer /select,"C:\Users\21292\AppData\Local\hermes\hermes-agent"

HEAD 记录仍是 `a992c8f1c47354748a9cfa669905bf58e50ee9c2`。部署只复制插件目录，不在这棵树上 `git pull`。

`runtime_capability.manifest_file` 上次的值是相对名 `runtime-policy.json`。文件未打开，本包不替换它。

## 3. 复制插件（只拷代码，不改配置）

`prepare_profile.py` 不读取、不写入 `config.yaml`、`.env`、`runtime-policy.json`。不要用它做启用或填写回调。

对 56982 字节那包，针对 CLI profile 目录的无 `--apply` 预览已经跑过，结果是 `files=25`。在 PID 的 home 被官方命令证明之前，不要加 `--apply`。本更新包的拷贝清单是 27 个文件；若再预览，应看到新的 `files=` 计数，且 `dry_run=true`。

## 4. 官方配置启用（会改配置，现在不做）

启用开关是 `plugins.enabled`，由下面这条官方命令写入，不是 `plugins.entries.feishu-base-export.enabled`，也不是拷贝脚本：

```text
hermes plugins enable feishu-base-export
```

回调地址只能在操作员已经选定并在飞书后台登记之后，用官方命令写入：

```text
hermes config set plugins.entries.feishu-base-export.settings.redirect_uri <已登记的完整 URI>
hermes config set plugins.entries.feishu-base-export.settings.callback_enabled true
hermes config get plugins.entries.feishu-base-export.settings.redirect_uri
hermes plugins list --plain --enabled
```

当前 `redirect_uri` 是 Config key not set。没有这个值就不能上线。不要 `config get` / `config set` 任何 secret 键。

## 5. 授权方式

已有自建应用没有一条不需要预先登记 `redirect_uri` 的用户 token 路径。设备码文档只覆盖创建应用，不给这个 bot 换 `user_access_token`。聊天收 code 和公网临时隧道都不使用。

同一台机器上的浏览器可以走飞书安全设置允许登记的 loopback HTTP，不必新买域名。当前应用还没有登记任何回调。若操作员选择这条，控制台「安全设置 → 重定向 URL」要逐字添加，并发布版本：

```text
http://127.0.0.1:8766/feishu/oauth/callback
```

监听保持 `127.0.0.1:8766`，只接受这个路径。不要写成 `localhost`，否则可能落到 `::1`，连不上这个监听。这只覆盖坐在这台电脑前的浏览器。远程同事的浏览器访问不到 `127.0.0.1`。

远程同事仍要你自己已有的 HTTPS 反向代理，本包不新建服务、不花钱、不建隧道。代理只把 `GET /feishu/oauth/callback` 转到 `127.0.0.1:8766`。控制台和 `redirect_uri` 都写：

```text
https://<你已有的主机名>/feishu/oauth/callback
```

主机名不能是 localhost、127.0.0.1、::1、.local 或 IP。

最小 scope：`offline_access` 和 `drive:export:readonly`。在权限管理里申请后发布版本。`docs:document:export` 不是这条导出路径的必需项。

没有完成第 4 步和第 5 步时，工具返回 `setup-required`。离线验证里的 `auth_ready=false` 必须保持为 false。

## 6. 重启和真实用户

重启是 `hermes gateway restart`，由操作员在上面几步完成之后自己执行。本包不重启。

每个要导出的人在自己的飞书私聊里说一次导出，打开机器人给出的授权链接，用自己的飞书账号点同意，再在同一个私聊里说一次导出。两个人就是两遍这个动作。不要把回调地址发回聊天。`revoke` 只删除本机 token，不是飞书侧撤销。

## 7. 策略增量（待批准，不执行）

`POLICY_INSERT.txt` 只有两行，插进现有 `evaluate(request)` 的开头。其它工具继续走原来的 return。不要用一份只允许导出、拒绝其它工具的文件换掉 `runtime-policy.json`。批准后还要按现有清单规则更新 sha256。本轮不写这个文件。

`chart_png` 和 `chart_pdf` 仍 blocked。整批不能当成已经可用。
