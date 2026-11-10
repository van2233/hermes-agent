# 部署（机器人身份，不监听）

本批不启用 OAuth，不监听，不重启，不改飞书权限。`prepare_profile.py` 只拷源码，不写配置。

## 复制

先确认 profile 目录仍是 `hermes config path` 的父目录。PID 51168 的 home 此前没有被官方命令单独证明。确认后再：

```text
py -3 plugins\feishu_base_export\prepare_profile.py --profile-home <config.yaml 的父目录> --apply
hermes plugins enable feishu-base-export
hermes config set plugins.entries.feishu-base-export.settings.base_token E6OpbISaeaZAVRsojtacOU9rnjf
```

应用凭据继续用现有的 `FEISHU_APP_ID` / `FEISHU_APP_SECRET`，不要 `config get` 它们。启用写入 `plugins.enabled`。Gateway 下次启动才会加载插件；本包不执行重启。

## 唯一的 ACL 动作

把多维表格 `E6OpbISaeaZAVRsojtacOU9rnjf` 分享给这个机器人应用，让它可以读其中的表。官方 `lark-cli drive +export --as bot` 已经以 bot 身份被接受，返回 `bitable_no_table_permission`，ticket `7705632562430135490`，没有 xlsx。这是目标表权限，不是 scope 不足。不要改 scope，不要改用用户身份，不要用 owner token。

## 图表

`chart_png` / `chart_pdf` 用官方查询记录接口在本地聚合后重画，不是飞书原图。参数是 `table`、`category`、`value`、`agg`（sum、count、avg）。只读已配置的 Base。最小权限是 `bitable:app:readonly`，不要另外申请写权限。仪表盘 block 没有公开的聚合数据 HTTP 接口，所以不调用它。

## 策略

若运行时门拒绝 `feishu_base_export`，只在现有 `evaluate` 开头插入 `POLICY_INSERT.txt` 的两行。不要替换整份策略，不要拒绝其它工具。未确认前不要写 `runtime-policy.json`。
