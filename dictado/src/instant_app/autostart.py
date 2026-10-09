"""Arranque con el sistema, gobernado desde la TUI (solo stdlib).

Windows: acceso `Instant Dictado.lnk` en Startup -> lanzador oculto.
Linux: `~/.config/autostart/instant.desktop` (freedesktop, oculto con nohup).
macOS: `~/Library/LaunchAgents/com.instant.dictado.plist` (plistlib).

`enable` es idempotente (si ya apunta a lo mismo, no duplica).
`disable` solo borra lo nuestro (verifica marca/contenido antes de borrar;
nunca toca archivos ajenos). `is_enabled` nunca crashea.
"""
import logging
import os
import shlex
import shutil
import subprocess
import sys

log = logging.getLogger("instant")

LINK_NAME = "Instant Dictado.lnk"
DESKTOP_NAME = "instant.desktop"
PLIST_LABEL = "com.instant.dictado"
PLIST_NAME = PLIST_LABEL + ".plist"
MARK = "instant-autostart-managed"
DESC = "Instant dictado hold-to-talk (daemon oculto)"


def _platform():
    """Plataforma efectiva; INSTANT_AUTOSTART_PLATFORM solo para tests."""
    ov = os.environ.get("INSTANT_AUTOSTART_PLATFORM", "").strip().lower()
    if ov.startswith("win"):
        return "win32"
    if ov.startswith("darwin") or ov.startswith("mac"):
        return "darwin"
    if ov.startswith("linux"):
        return "linux"
    return sys.platform


def _find_repo_file(name):
    """Busca un archivo del repo subiendo desde este modulo + cwd."""
    here = os.path.abspath(os.path.dirname(__file__))
    cands = [here]
    d = here
    for _ in range(6):
        d = os.path.dirname(d)
        cands.append(d)
    cands.append(os.getcwd())
    for c in cands:
        p = os.path.join(c, name)
        if os.path.isfile(p):
            return p
    return None


# --- Rutas (respetan APPDATA/HOME/XDG para poder redirigir en tests) ---

def _win_startup_dir():
    base = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(base, "Microsoft", "Windows", "Start Menu",
                        "Programs", "Startup")


def _link_path():
    return os.path.join(_win_startup_dir(), LINK_NAME)


def _linux_config_base():
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        return xdg
    return os.path.join(os.path.expanduser("~"), ".config")


def _desktop_file():
    return os.path.join(_linux_config_base(), "autostart", DESKTOP_NAME)


def _plist_path():
    return os.path.join(os.path.expanduser("~"), "Library",
                        "LaunchAgents", PLIST_NAME)


# --- Resolucion del lanzador ---

def _resolve_win_launch():
    """(target, args, workdir) para el daemon, incluido el ejecutable congelado."""
    if getattr(sys, "frozen", False):
        executable = sys.executable
        return (executable, "run", os.path.dirname(executable))
    bat = _find_repo_file("instant-run.bat")
    if bat:
        return (bat, "", os.path.dirname(bat))
    exe = shutil.which("instant") or shutil.which("instant.exe")
    if exe:
        return (exe, "run", os.path.expanduser("~"))
    pyw = sys.executable or "pythonw.exe"
    if pyw.lower().endswith("python.exe"):
        cand = pyw[: -len("python.exe")] + "pythonw.exe"
        if os.path.isfile(cand):
            pyw = cand
    return (pyw, "-m instant_app run", os.path.expanduser("~"))


def _resolve_posix_argv():
    """argv para linux/mac: sh del repo si existe, si no `instant run`, si no python."""
    if getattr(sys, "frozen", False):
        return [sys.executable, "run"]
    sh = _find_repo_file("instant-run.sh")
    if sh:
        return ["sh", sh]
    exe = shutil.which("instant")
    if exe:
        return [exe, "run"]
    return [sys.executable or "python3", "-m", "instant_app", "run"]


# --- Windows (via powershell existente, sin dependencias nuevas) ---

def _ps_quote(s):
    return "'" + str(s).replace("'", "''") + "'"


def _powershell(script, timeout=20):
    return subprocess.run(["powershell", "-NoProfile", "-Command", script],
                          capture_output=True, text=True, timeout=timeout)


def _write_win_stub(link, target, args):
    """Texto marcador cuando no hay powershell (solo tests con plataforma forzada)."""
    with open(link, "w", encoding="utf-8") as f:
        f.write("# %s: gestionado por `instant setup`, no editar a mano.\n" % MARK)
        f.write("TargetPath=%s\n" % target)
        f.write("Arguments=%s\n" % args)


def _read_win_target(link):
    """(target, args) del .lnk, o None si no se puede leer / es ajeno."""
    try:
        script = ("$s=(New-Object -COM WScript.Shell).CreateShortcut(%s);"
                  "Write-Output $s.TargetPath;Write-Output $s.Arguments"
                  % _ps_quote(link))
        r = _powershell(script, timeout=15)
        if r.returncode == 0:
            lines = (r.stdout or "").splitlines()
            t = lines[0].strip() if len(lines) > 0 else ""
            a = lines[1].strip() if len(lines) > 1 else ""
            if t:
                return (t, a)
            # Target vacio: .lnk invalido o archivo de texto -> sigo al fallback.
    except FileNotFoundError:
        pass
    except Exception:
        log.exception("no se pudo leer el acceso de Startup")
        return None
    try:
        with open(link, "rb") as f:
            raw = f.read()
    except OSError:
        return None
    try:
        txt = raw.decode("utf-8")
    except UnicodeDecodeError:
        txt = ""
    if MARK in txt:
        t, a = "", ""
        for line in txt.splitlines():
            if line.startswith("TargetPath="):
                t = line[len("TargetPath="):].strip()
            elif line.startswith("Arguments="):
                a = line[len("Arguments="):].strip()
        return (t, a) if t else None
    if txt:
        return None  # texto ajeno, no es nuestro acceso.
    return None  # binario sin powershell: no se puede verificar por target.


def _is_ours_win(link):
    if not os.path.isfile(link):
        return False
    cur = _read_win_target(link)
    if cur:
        hay = ("%s %s" % cur).lower()
        # Estricto: solo nuestros targets, no cualquier .lnk ajeno que
        # mencione "instant" (antes se pisaba/borraba arranques ajenos).
        return ("instant-run.bat" in hay or "instant.exe" in hay
                or "instant-update" in hay
                or (("python.exe" in hay or "pythonw.exe" in hay)
                    and "instant" in hay))
    if cur:
        return False
    # Binario real pero sin powershell para leerlo: busca la marca en crudo.
    try:
        with open(link, "rb") as f:
            return b"instant" in f.read().lower()
    except OSError:
        return False


def _win_is_enabled():
    try:
        return _is_ours_win(_link_path())
    except Exception:
        log.exception("is_enabled(win) fallo")
        return False


def _win_enable():
    target, args, workdir = _resolve_win_launch()
    link = _link_path()
    os.makedirs(os.path.dirname(link), exist_ok=True)
    if os.path.exists(link) and not _is_ours_win(link):
        raise RuntimeError(
            "hay un archivo ajeno en %s; sacalo a mano antes de activar." % link)
    if os.path.isfile(link):
        cur = _read_win_target(link)
        if cur and os.path.normcase(cur[0]) == os.path.normcase(target) \
                and cur[1].strip() == args.strip():
            return "Arranque ya estaba activado: %s" % link
    script = ("$s=(New-Object -COM WScript.Shell).CreateShortcut(%s);"
              "$s.TargetPath=%s;$s.Arguments=%s;$s.WorkingDirectory=%s;"
              "$s.Description=%s;$s.Save()" % (
                  _ps_quote(link), _ps_quote(target), _ps_quote(args),
                  _ps_quote(workdir), _ps_quote(DESC)))
    try:
        r = _powershell(script)
    except FileNotFoundError:
        if os.environ.get("INSTANT_AUTOSTART_PLATFORM"):
            _write_win_stub(link, target, args)
            return "Arranque activado: %s" % link
        raise RuntimeError(
            "sin powershell no puedo crear el acceso. Hacelo a mano con "
            "install-autostart.bat en la raiz del repo.")
    if r.returncode != 0 or not os.path.isfile(link):
        err = (r.stderr or "").strip().splitlines()
        hint = err[-1] if err else "powershell devolvio %d" % r.returncode
        raise RuntimeError(
            "no se pudo crear el acceso en Startup (%s). Alternativa: corre "
            "install-autostart.bat en la raiz del repo." % hint)
    return "Arranque activado: %s -> %s%s" % (
        link, target, (" " + args) if args else "")


def _win_disable():
    link = _link_path()
    if not os.path.exists(link):
        return "Arranque ya estaba desactivado."
    if not _is_ours_win(link):
        return "No toco %s: no es de Instant." % link
    try:
        os.remove(link)
    except OSError as e:
        raise RuntimeError("no pude borrar %s (%s); borralo a mano." % (link, e))
    return "Arranque desactivado: se borro %s" % link


def _win_describe():
    try:
        target, args, _w = _resolve_win_launch()
        dest = target + ((" " + args) if args else "")
    except Exception:
        dest = "el lanzador de Instant"
    return "Windows: acceso '%s' en Inicio -> %s" % (LINK_NAME, dest)


# --- Linux (freedesktop) ---

def _desktop_content():
    inner = " ".join(shlex.quote(x) for x in _resolve_posix_argv())
    return (
        "# %s: gestionado por `instant setup`, no editar a mano.\n"
        "[Desktop Entry]\n"
        "Type=Application\n"
        "Name=Instant Dictado\n"
        "Comment=%s\n"
        "Exec=sh -c \"nohup %s >/dev/null 2>&1 &\"\n"
        "Terminal=false\n"
        "Hidden=false\n"
        "X-GNOME-Autostart-enabled=true\n" % (MARK, DESC, inner)
    )


def _read_desktop(path):
    try:
        with open(path, encoding="utf-8") as f:
            return f.read()
    except OSError:
        return None


def _linux_is_enabled():
    try:
        cur = _read_desktop(_desktop_file())
        return bool(cur) and MARK in cur
    except Exception:
        log.exception("is_enabled(linux) fallo")
        return False


def _linux_enable():
    path = _desktop_file()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    want = _desktop_content()
    if os.path.exists(path):
        cur = _read_desktop(path)
        if cur is None:
            raise RuntimeError("no puedo leer %s; revisalo a mano." % path)
        if MARK not in cur:
            raise RuntimeError(
                "hay un archivo ajeno en %s; sacalo a mano antes de activar." % path)
        if cur == want:
            return "Arranque ya estaba activado: %s" % path
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write(want)
    except OSError as e:
        raise RuntimeError("no pude escribir %s (%s)." % (path, e))
    return "Arranque activado: %s" % path


def _linux_disable():
    path = _desktop_file()
    if not os.path.exists(path):
        return "Arranque ya estaba desactivado."
    cur = _read_desktop(path)
    if cur is None or MARK not in cur:
        return "No toco %s: no es de Instant." % path
    try:
        os.remove(path)
    except OSError as e:
        raise RuntimeError("no pude borrar %s (%s); borralo a mano." % (path, e))
    return "Arranque desactivado: se borro %s" % path


def _linux_describe():
    try:
        inner = " ".join(_resolve_posix_argv())
    except Exception:
        inner = "el lanzador de Instant"
    return "Linux: %s en autostart -> %s (oculto)" % (DESKTOP_NAME, inner)


# --- macOS (LaunchAgent, plistlib stdlib) ---

def _plist_dict():
    return {
        "Label": PLIST_LABEL,
        "ProgramArguments": _resolve_posix_argv(),
        "RunAtLoad": True,
        "KeepAlive": False,
        "StandardOutPath": "/dev/null",
        "StandardErrorPath": "/dev/null",
        "InstantManaged": True,
    }


def _read_plist(path):
    try:
        import plistlib
        with open(path, "rb") as f:
            data = plistlib.load(f)
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def _mac_is_enabled():
    try:
        data = _read_plist(_plist_path())
        return bool(data) and data.get("Label") == PLIST_LABEL
    except Exception:
        log.exception("is_enabled(mac) fallo")
        return False


def _mac_enable():
    path = _plist_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        data = _read_plist(path)
        if data is None or data.get("Label") != PLIST_LABEL:
            raise RuntimeError(
                "hay un archivo ajeno en %s; sacalo a mano antes de activar." % path)
        cur_argv = data.get("ProgramArguments")
        if cur_argv == _resolve_posix_argv() or data.get("InstantManaged"):
            # Idempotente: si ya es nuestro y apunta igual (o lo gestionamos),
            # reescribo igual para dejarlo canonico sin duplicar.
            pass
    try:
        import plistlib
        with open(path, "wb") as f:
            plistlib.dump(_plist_dict(), f)
    except OSError as e:
        raise RuntimeError("no pude escribir %s (%s)." % (path, e))
    return "Arranque activado: %s" % path


def _mac_disable():
    path = _plist_path()
    if not os.path.exists(path):
        return "Arranque ya estaba desactivado."
    data = _read_plist(path)
    if data is None or data.get("Label") != PLIST_LABEL:
        return "No toco %s: no es de Instant." % path
    try:
        os.remove(path)
    except OSError as e:
        raise RuntimeError("no pude borrar %s (%s); borralo a mano." % (path, e))
    return "Arranque desactivado: se borro %s" % path


def _mac_describe():
    try:
        inner = " ".join(_resolve_posix_argv())
    except Exception:
        inner = "el lanzador de Instant"
    return "macOS: LaunchAgent %s -> %s" % (PLIST_LABEL, inner)


# --- API publica ---

def is_enabled():
    """True si el arranque de Instant esta activo. Nunca crashea."""
    try:
        p = _platform()
        if p == "win32":
            return _win_is_enabled()
        if p == "darwin":
            return _mac_is_enabled()
        return _linux_is_enabled()
    except Exception:
        log.exception("is_enabled fallo; devuelvo False")
        return False


def enable():
    """Activa el arranque (idempotente). Devuelve que hizo/ruta. Falla con hint."""
    p = _platform()
    if p == "win32":
        return _win_enable()
    if p == "darwin":
        return _mac_enable()
    return _linux_enable()


def disable():
    """Desactiva el arranque (idempotente, solo borra lo nuestro). Devuelve que hizo."""
    p = _platform()
    if p == "win32":
        return _win_disable()
    if p == "darwin":
        return _mac_disable()
    return _linux_disable()


def describe():
    """Una linea en ES con que crea el arranque en este SO. Nunca crashea."""
    try:
        p = _platform()
        if p == "win32":
            return _win_describe()
        if p == "darwin":
            return _mac_describe()
        return _linux_describe()
    except Exception:
        log.exception("describe fallo")
        return "Arranque no disponible en este sistema"
