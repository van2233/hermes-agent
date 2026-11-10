"""Insert this branch into an existing evaluate(). Do not replace that function.

Allowing feishu_base_export must not change the verdict of any other tool.
"""

EXPORT_TOOL = "feishu_base_export"


def allow_feishu_base_export(request, continue_policy):
    if request.get("tool_name") == EXPORT_TOOL:
        return {"allowed": True, "reason": "feishu base export"}
    return continue_policy(request)
