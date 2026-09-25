"""U-10: precedencia DICTADO_DATA vs cwd ./models (sin mic ni red)."""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from instant_app import paths

MARKER = os.path.join(paths.PARAKEET_SUBDIR, "encoder.int8.onnx")


def _touch(root):
    p = os.path.join(root, MARKER)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "wb").close()
    return p


def _check(name, got, want):
    ok = got == want
    print(("PASS " if ok else "FAIL ") + name)
    if not ok:
        print(f"  got={got!r} want={want!r}")
        raise SystemExit(1)


old_env = os.environ.get("DICTADO_DATA")
old_cwd = os.getcwd()
try:
    # 1. DICTADO_DATA gana sobre todo.
    with tempfile.TemporaryDirectory() as env_d, tempfile.TemporaryDirectory() as cwd_d:
        _touch(env_d)
        _touch(os.path.join(cwd_d, "models"))
        os.environ["DICTADO_DATA"] = env_d
        os.chdir(cwd_d)
        got = paths.resolve_data_dir()
        os.chdir(old_cwd)
        _check("env gana", got, env_d)

    # 2. cwd ./models con marcador gana al user dir.
    os.environ.pop("DICTADO_DATA", None)
    with tempfile.TemporaryDirectory() as cwd_d:
        _touch(os.path.join(cwd_d, "models"))
        os.chdir(cwd_d)
        got = paths.resolve_data_dir()
        os.chdir(old_cwd)
        _check("cwd con marcador", got, os.path.join(cwd_d, "models"))

    # 3. cwd sin marcador cae al user dir.
    with tempfile.TemporaryDirectory() as cwd_d:
        os.chdir(cwd_d)
        got = paths.resolve_data_dir()
        os.chdir(old_cwd)
        _check("cwd sin marcador", got, paths.user_data_dir())

    # 4. DICTADO_DATA inexistente se respeta tal cual.
    ghost = os.path.join(tempfile.gettempdir(), "instant-ghost-noexiste")
    import shutil
    shutil.rmtree(ghost, ignore_errors=True)
    os.environ["DICTADO_DATA"] = ghost
    os.chdir(old_cwd)
    _check("env inexistente", paths.resolve_data_dir(), ghost)
finally:
    os.chdir(old_cwd)
    if old_env is None:
        os.environ.pop("DICTADO_DATA", None)
    else:
        os.environ["DICTADO_DATA"] = old_env

print("OK: precedencia DICTADO_DATA verde.")
