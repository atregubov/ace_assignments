from labagent.types import allow, deny


def check(context, doc, runtime):
    return allow("vulnerable_global_search") if doc else deny("unknown_document")


def observe(doc, runtime):
    pass  # VULNERABLE: discards provenance when content is read.
