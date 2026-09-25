"""Chequeo + autoinstalacion asistida de dependencias (solo stdlib).

Responde a: "la instalacion puede detectar y descargar dependencias
faltantes junto con la app?" Si: `instant setup --check-deps` muestra la
tabla y `--fix-deps` instala lo que el SO permite sin intervencion.

Matriz auto / no-auto:
- Windows: Python>=3.10, pip y paquetes por pip (auto=si). Sin
  dependencias del sistema (entrada "sistema": ok=True con nota).
- Linux: portaudio (libportaudio2), xclip/xsel y xdotool por apt
  (auto=si solo con sudo sin password o root; nunca pide password).
  En Wayland xdotool no anda (ok=False, auto=False).
- macOS: portaudio por brew (auto=si solo si brew existe).
- Sin red no se instala nada: queda [FALTA] con hint, sin traceback.
"""
import ctypes.util
import importlib.util
import logging
import os
import shutil
import socket
import subprocess
import sys

log = logging.getLogger("instant")

_PIP = {
    "numpy": "numpy",
    "sounddevice": "sounddevice",
    "sherpa_onnx": "sherpa-onnx",
    "keyboard": "keyboard",
    "pynput": "pynput",
    "pyperclip": "pyperclip",
    "huggingface_hub": "huggingface_hub",
}

_APT = {
    "portaudio": "libportaudio2",
    "xclip/xsel": "xclip",
    "xdotool": "xdotool",
}


def _entry(ok, hint, auto=False):
    return {"ok": bool(ok), "hint": hint, "auto": bool(auto)}


def _importable(mod):
    try:
        return importlib.util.find_spec(mod) is not None
    except Exception:
        return False


def _run(cmd, timeout):
    return subprocess.run(cmd, stdout=subprocess.DEVNULL,
                          stderr=subprocess.STDOUT, timeout=timeout)


def _can_apt():
    """True si apt-get puede correr sin pedir password (root o sudo -n)."""
    try:
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            return True
        r = _run(["sudo", "-n", "true"], timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def _lib_present(name):
    """Busca libreria .so por ctypes, ldconfig o dpkg (solo Linux)."""
    try:
        if ctypes.util.find_library(name):
            return True
    except Exception:
        pass
    try:
        r = subprocess.run(["ldconfig", "-p"], capture_output=True,
                           text=True, timeout=10)
        if r.returncode == 0 and name in r.stdout:
            return True
    except Exception:
        pass
    return False


def _dpkg_ok(pkg):
    try:
        r = _run(["dpkg", "-s", pkg], timeout=10)
        return r.returncode == 0
    except Exception:
        return False


def _has_net():
    """Hay red para descargar? Via proxy se asume que si (pip lo usa)."""
    if os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY"):
        return True
    try:
        socket.create_connection(("pypi.org", 443), timeout=4).close()
        return True
    except Exception:
        return False


def check():
    """Devuelve dict por dependencia: {nombre: {ok, hint, auto}}."""
    out = {}
    plat = sys.platform

    ver = sys.version_info
    out["python"] = _entry(
        ver >= (3, 10),
        f"Python {sys.version.split()[0]} (>=3.10 OK)."
        if ver >= (3, 10) else
        f"Python {sys.version.split()[0]}: necesitas 3.10+ desde python.org.",
        auto=False)

    out["pip"] = _entry(
        _importable("pip"),
        "pip disponible." if _importable("pip")
        else "python -m ensurepip (o reinstala Python con pip).",
        auto=True)  # via ensurepip (stdlib, sin red)

    pkgs = ["numpy", "sounddevice", "sherpa_onnx", "pyperclip",
            "huggingface_hub"]
    pkgs.append("keyboard" if plat == "win32" else "pynput")
    for mod in pkgs:
        ok = _importable(mod)
        if ok:
            out[mod] = _entry(True, "instalado (importable).", auto=True)
        else:
            extra = ""
            if mod == "keyboard":
                extra = " Si la tecla no anda en apps elevadas, corre como admin."
            if mod == "pynput":
                extra = " En Linux necesita X11."
            out[mod] = _entry(False, f"pip install {_PIP[mod]}.{extra}",
                              auto=True)

    if plat == "win32":
        out["sistema"] = _entry(
            True, "Windows no necesita dependencias del sistema.", auto=False)
        return out

    if plat == "darwin":
        try:
            r = _run(["brew", "--prefix", "portaudio"], timeout=15)
            ok = r.returncode == 0
        except Exception:
            ok = False
        brew = shutil.which("brew") is not None
        out["portaudio"] = _entry(
            ok, "portaudio presente (brew)." if ok
            else "brew install portaudio.", auto=brew)
        out["sistema"] = _entry(
            True, "macOS usa pbcopy nativo (sin xclip/xdotool).", auto=False)
        return out

    # Linux.
    can_apt = _can_apt()
    ok_pa = _lib_present("portaudio") or _dpkg_ok("libportaudio2")
    out["portaudio"] = _entry(
        ok_pa, "libportaudio2 presente." if ok_pa
        else "sudo apt install libportaudio2.", auto=can_apt)
    ok_cb = shutil.which("xclip") is not None or shutil.which("xsel") is not None
    out["xclip/xsel"] = _entry(
        ok_cb, "portapapeles presente (xclip/xsel)." if ok_cb
        else "sudo apt install xclip.", auto=can_apt)
    wayland = bool(os.environ.get("WAYLAND_DISPLAY")) or \
        os.environ.get("XDG_SESSION_TYPE") == "wayland"
    if wayland:
        out["xdotool"] = _entry(
            False, "En Wayland xdotool no anda: usa sesion X11 o wtype manual.",
            auto=False)
    else:
        ok_xd = shutil.which("xdotool") is not None
        out["xdotool"] = _entry(
            ok_xd, "xdotool presente (X11)." if ok_xd
            else "sudo apt install xdotool.", auto=can_apt)
    return out


def report(results=None):
    """Texto ES simple con la tabla [OK]/[FALTA]."""
    if results is None:
        results = check()
    title = {"win32": "Windows", "darwin": "macOS"}.get(sys.platform, "Linux")
    lines = [f"Dependencias ({title}):"]
    for name, e in results.items():
        mark = "OK" if e["ok"] else "FALTA"
        auto = " (auto)" if (not e["ok"] and e["auto"]) else ""
        lines.append(f"  [{mark}] {name}: {e['hint']}{auto}")
    return "\n".join(lines)


def _install_one(name):
    if name == "pip":
        subprocess.run([sys.executable, "-m", "ensurepip", "--default-pip"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
                       timeout=120, check=True)
        return
    if name in _PIP:
        print(f"  instalando {name} con pip...")
        subprocess.run([sys.executable, "-m", "pip", "install", _PIP[name]],
                       stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
                       timeout=300, check=True)
        return
    if sys.platform.startswith("linux") and name in _APT:
        pkg = _APT[name]
        cmd = ["apt-get", "install", "-y", pkg]
        if not (hasattr(os, "geteuid") and os.geteuid() == 0):
            cmd = ["sudo", "-n"] + cmd  # nunca pide password
        print(f"  instalando {pkg} con apt...")
        subprocess.run(cmd, stdout=subprocess.DEVNULL,
                       stderr=subprocess.STDOUT, timeout=300, check=True)
        return
    if sys.platform == "darwin" and name == "portaudio":
        print("  instalando portaudio con brew...")
        subprocess.run(["brew", "install", "portaudio"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT,
                       timeout=300, check=True)
        return
    raise RuntimeError(f"{name} no es autoinstalable")


def ensure(auto=False):
    """Si auto=True, instala lo auto-instalable y devuelve check() fresco.

    Sin red no instala nada (hint "sin red", sin traceback). Con auto=False
    solo chequea, sin tocar nada.
    """
    results = check()
    if not auto:
        return results
    pending = [n for n, e in results.items() if not e["ok"] and e["auto"]]
    if not pending:
        return results
    if not _has_net():
        for n in pending:
            results[n]["hint"] += " (sin red: no se pudo autoinstalar)."
        return results
    for n in pending:
        try:
            _install_one(n)
        except Exception as e:
            log.info("no se pudo autoinstalar %s: %s", n, e)
    return check()
