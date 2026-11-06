# 部署入口（只准备，不启用）

本文件不读取配置，不启用插件，不监听端口，不重启 Gateway。

## 已经核对、但没有打开的路径

`hermes config path` 打印：

`C:\Users\21292\AppData\Local\hermes\config.yaml`

📁 在资源管理器中打开

http://127.0.0.1:17831/open/b/QzpcVXNlcnNcMjEyOTJcQXBwRGF0YVxMb2NhbFxoZXJtZXNcY29uZmlnLnlhbWw

explorer /select,"C:\Users\21292\AppData\Local\hermes\config.yaml"

`hermes config env-path` 打印同目录 `.env`。文件没有打开。

📁 在资源管理器中打开

http://127.0.0.1:17831/open/b/QzpcVXNlcnNcMjEyOTJcQXBwRGF0YVxMb2NhbFxoZXJtZXNcLmVudg

explorer /select,"C:\Users\21292\AppData\Local\hermes\.env"

`hermes config get runtime_capability.manifest_file` 的值是相对名 `runtime-policy.json`。策略文件没有打开，也没有执行。

安装根：

`C:\Users\21292\AppData\Local\hermes\hermes-agent`

📁 在资源管理器中打开

http://127.0.0.1:17831/open/b/QzpcVXNlcnNcMjEyOTJcQXBwRGF0YVxMb2NhbFxoZXJtZXNcaGVybWVzLWFnZW50

explorer /select,"C:\Users\21292\AppData\Local\hermes\hermes-agent"

HEAD 仍是 `a992c8f1c47354748a9cfa669905bf58e50ee9c2`。先前对照的五份源码工作树 status 仍为空。

`hermes gateway list` 的 default/current PID 是 51168，计划任务 `Hermes_Gateway` 已注册。没有证据证明这个进程绑定的 `HERMES_HOME` 等于上面的 CLI config 目录。不要把这个推断写成已验证。

桌面目录存在：

`C:\Users\21292\Desktop`

📁 在资源管理器中打开

http://127.0.0.1:17831/open/b/QzpcVXNlcnNcMjEyOTJcRGVza3RvcA

explorer /select,"C:\Users\21292\Desktop"

## 操作员必须显式给 profile 路径

先看 CLI 打印的路径，再把**那个 profile 目录**传给脚本。脚本不调用 `expanduser`，不读取 `HERMES_HOME`，不读 config.yaml / .env。

只预览、不写文件：

```text
python plugins/feishu_base_export/prepare_profile.py --profile-home C:\Users\21292\AppData\Local\hermes
```

确认这个目录就是要改的那个 profile 之后才加 `--apply`。PID 51168 还没被证明使用这个目录时，不要加 `--apply`。

不要 `git pull`。不要 `hermes plugins enable`，除非操作员在确认 profile 之后自己执行。启用命令是 `hermes plugins enable feishu-base-export`。重定向只在那之后用单键写入：

```text
hermes config set plugins.entries.feishu-base-export.settings.redirect_uri <已在飞书登记的 https 地址>
hermes config set plugins.entries.feishu-base-export.settings.callback_enabled true
```

`redirect_uri` 必须是 https，主机名不能是 localhost、127.0.0.1、::1、.local 或 IP。监听默认 `127.0.0.1:8766`。没有这组配置时工具返回 `setup-required`，不会假装已经能收回调。

策略只在现有 `evaluate` 里调用 `policy_fragment.allow_feishu_base_export`，其它工具继续走原来的判断。本轮不写 `runtime-policy.json`。

## Windows 离线验证

在 Windows 上、插件拷入之后：

```text
scripts\run_tests.sh tests/plugins/test_feishu_base_export.py -k test_windows_dpapi_roundtrip_is_real_cryptprotect
```

Linux 上这条会被 `windows_only` 跳过。跳过不是通过。

图表 `chart_png` / `chart_pdf` 仍 blocked。`revoke` 只删本机 token，不是飞书侧撤销。
