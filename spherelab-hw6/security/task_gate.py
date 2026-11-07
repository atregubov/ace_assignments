from labagent.types import allow, deny


def check(context, action, runtime):
    if context is None or action.tool not in context.allowed_tools:
        return deny("task_tool_not_allowed")
    if action.tool == "send_message" and action.args.get("recipient") not in context.allowed_recipients:
        return deny("task_recipient_not_allowed")
    return allow()
