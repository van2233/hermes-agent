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
    "blocked: png and pdf were not fetched from Feishu and no image file was written. "
    "Official server-docs list dashboards with GET /open-apis/bitable/v1/apps/:app_token/dashboards "
    "and do not document an aggregate-data scope. The CLI skill path "
    "GET /open-apis/base/v3/bases/:base_token/dashboards/blocks/:block_id/data "
    "is not a verified transport. Both png and pdf stay blocked."
)
