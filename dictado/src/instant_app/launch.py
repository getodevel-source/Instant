"""Build isolated subprocess environments for the source and frozen app."""
import os
import sys


def app_command(args=()):
    if getattr(sys, "frozen", False):
        return [sys.executable, *args]
    return [sys.executable, "-m", "instant_app", *args]


def app_environment():
    """Give independent one-file children their own extraction directory."""
    env = os.environ.copy()
    if getattr(sys, "frozen", False):
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
    return env
