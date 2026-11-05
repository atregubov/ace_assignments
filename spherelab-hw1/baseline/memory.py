from lab.types import allow


def check(context, row, runtime):
    return allow("vulnerable_trust_all_memory")
