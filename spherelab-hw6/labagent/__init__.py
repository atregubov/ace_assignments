"""Spherelab's OpenAI agent, local tools, security controls, and evaluation harness."""
import sys

if sys.version_info < (3, 11):
    raise RuntimeError(
        f"Spherelab requires Python 3.11 or newer; this interpreter is {sys.version.split()[0]}. "
        "Create the virtual environment with a newer interpreter, e.g. python3.11 -m venv .venv"
    )
