def event(runtime, kind, action=None, decision=None, outcome=None):
    return {"event_id": f"{runtime.run_id}:{len(runtime.events)}", "kind": kind}
