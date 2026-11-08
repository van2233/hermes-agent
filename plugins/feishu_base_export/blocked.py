"""User-visible stop reasons. These are the live tool's whole behavior."""

EXPORT_BLOCKED = (
    "blocked: no user token is acquired and no file is written. "
    "Official self-built-app user tokens use grant_type=authorization_code and a "
    "pre-registered redirect_uri. The documented device-authorization grant creates "
    "an app; it does not prove this existing bot can mint a user_access_token. "
    "No callback server is started. Delivery is also blocked because "
    "transform_llm_output does not cover every extract_media path, and the local "
    "tool-chain patch was not compared."
)

CHART_BLOCKED = (
    "未接通: png 和 pdf 没有从飞书拉取。官方 server-docs 只有仪表盘列表 "
    "GET /open-apis/bitable/v1/apps/:app_token/dashboards，没有已确认的聚合数据接口和 scope。"
    "CLI 技能里的 GET /open-apis/base/v3/bases/:base_token/dashboards/blocks/:block_id/data "
    "不能当作已接通。Excel 导出不依赖这条路径。"
)
