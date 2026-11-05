"""Fixed structural checks. Identity-looking fields reach HW2's policy hook."""
from lab.types import PolicyDenied

PAYMENT = {"account": str, "payee": str, "amount_cents": int, "currency": str,
           "document_id": str, "document_version": int, "operation_id": str}
SCHEMAS = {
    "search_docs": ({"query": str}, {}),
    "read_doc": ({"doc_id": str}, {}),
    "send_message": ({"recipient": str, "body": str}, {}),
    "propose_payment": (PAYMENT, {}),
    "commit_payment": ({**PAYMENT, "approval_id": str}, {}),
    "remember": ({"key": str, "value": str}, {"confirmation_id": str}),
    "recall": ({}, {}),
    "unstable": ({"mode": str}, {}),
}
IDENTITY = {"user_id": str, "tenant_id": str, "role": str}


def validate(action):
    if action.tool not in SCHEMAS or not isinstance(action.args, dict):
        raise PolicyDenied("unknown_tool_or_arguments")
    required, optional = SCHEMAS[action.tool]
    fields = {**required, **optional, **IDENTITY}
    if not set(required) <= set(action.args) or not set(action.args) <= set(fields):
        raise PolicyDenied("invalid_fields")
    for k, v in action.args.items():
        if type(v) is not fields[k]:
            raise PolicyDenied("invalid_type")
        if isinstance(v, str) and len(v.encode()) > 32768:
            raise PolicyDenied("argument_too_large")


def tool_specs():
    descriptions = {
        "search_docs": "Search fixture documents and return authorized snippets.",
        "read_doc": "Read a fixture document by its ID.",
        "send_message": "Record a message in the LOCAL simulated outbox. No real mail.",
        "propose_payment": "Create a simulated payment proposal for a human reviewer.",
        "commit_payment": "Commit a previously approved simulated payment.",
        "remember": "Propose a preference memory; confirmation may be required.",
        "recall": "Retrieve active preferences for the authenticated user.",
        "unstable": "Read-only test service; modes transient, oversize, stall, normal.",
    }
    return [{"toolSpec": {"name": name, "description": descriptions[name],
             "inputSchema": {"json": {"type": "object", "properties": {
                 k: {"type": "integer" if v is int else "string"}
                 for k, v in {**req, **opt}.items()},
                 "required": list(req), "additionalProperties": False}}}}
            for name, (req, opt) in SCHEMAS.items()]
