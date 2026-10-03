"""Actualizaciones desde GitHub Releases, solo stdlib (sin deps nuevas).

Ciclo: check (API) -> download (asset + sidecar .sha256) -> verify. Este
módulo nunca pisa un ejecutable en uso: el swap con todo frenado lo hace
`instant-update.bat`, que respalda el exe anterior antes de cambiarlo.
"""
import hashlib
import json
import os
import re
import sys
import urllib.request

REPO = "getodevel-source/Instant"
API_LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
TIMEOUT = 20
CHUNK = 65536

# Plataforma local -> asset del release.
ASSETS = {"win32": "Instant.exe", "linux": "instant-linux", "darwin": "instant-macos"}


def current_version():
    from instant_app import __version__
    return __version__


def normalize(tag):
    """'v0.1.0' -> '0.1.0' (tolerante con mayúsculas y espacios)."""
    return tag.strip().lstrip("vV")


def _parts(version):
    return tuple(int(piece) for piece in re.findall(r"\d+", version))


def is_newer(latest, current):
    """True si latest supera a current comparando números (no strings)."""
    try:
        return _parts(normalize(latest)) > _parts(normalize(current))
    except Exception:
        return normalize(latest) != normalize(current)


def fetch_json(url):
    """GET JSON con UA propia (la API de GitHub la exige) y timeout."""
    request = urllib.request.Request(url, headers={"User-Agent": "Instant-updater"})
    with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
        return json.loads(response.read().decode("utf-8"))


def latest_release():
    """Lee el último release: tag, versión, notas y URLs por asset."""
    payload = fetch_json(API_LATEST)
    assets = {item.get("name", ""): item.get("browser_download_url", "")
              for item in payload.get("assets", [])}
    return {"tag": payload.get("tag_name", ""),
            "version": normalize(payload.get("tag_name", "")),
            "notes": payload.get("body", "") or "",
            "assets": assets}


def platform_asset():
    """Nombre del asset que corresponde a este SO. KeyError si no hay."""
    try:
        return ASSETS[sys.platform]
    except KeyError:
        raise LookupError(f"sin asset para sys.platform={sys.platform!r}")


def check():
    """Compara la versión instalada con el último release."""
    current = current_version()
    release = latest_release()
    if not release["version"]:
        raise RuntimeError(
            "GitHub no devolvió versión (¿rate-limit o sin releases?). "
            "No se informa 'al día' sin haber consultado.")
    name = platform_asset()
    url = release["assets"].get(name, "")
    if release["version"] and not url:
        available = ", ".join(sorted(release["assets"])) or "ninguno"
        raise LookupError(
            f"el release {release['tag']} no trae {name} (hay: {available})")
    return {"update": bool(release["version"]) and is_newer(release["version"], current),
            "current": current, "latest": release["version"],
            "notes": release["notes"], "asset": name, "asset_url": url}


def fetch_expected_sha256(asset_url):
    """Baja el sidecar '<asset>.sha256' ('<hash>  <nombre]'). 404 = error.

    Sin sidecar no hay instalación: instalar sin verificar sería peor que
    no actualizar.
    """
    sidecar = asset_url + ".sha256"
    request = urllib.request.Request(sidecar, headers={"User-Agent": "Instant-updater"})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            text = response.read().decode("utf-8", "replace")
    except Exception as exc:
        raise RuntimeError(f"sin sidecar SHA256 ({sidecar}): {exc}")
    token = text.strip().split()
    if not token or not re.fullmatch(r"[0-9a-fA-F]{64}", token[0]):
        raise ValueError(f"sidecar SHA256 ilegible: {text[:80]!r}")
    return token[0].lower()


def download(url, dest, progress=None, expected_sha256=None):
    """Descarga por stream con hash al vuelo; si no coincide, borra y falla.

    Cualquier error de red a mitad de stream también borra el parcial: nunca
    queda un archivo a medias haciéndose pasar por descarga.
    """
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    digest = hashlib.sha256()
    request = urllib.request.Request(url, headers={"User-Agent": "Instant-updater"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            header = response.getheader("Content-Length") if hasattr(
                response, "getheader") else None
            total = int(header) if header and header.isdigit() else None
            done = 0
            with open(dest, "wb") as handle:
                while True:
                    block = response.read(CHUNK)
                    if not block:
                        break
                    handle.write(block)
                    digest.update(block)
                    done += len(block)
                    if progress is not None:
                        progress(done, total)
    except Exception:
        try:
            os.remove(dest)
        except OSError:
            pass
        raise
    actual = digest.hexdigest()
    if expected_sha256 and actual != expected_sha256.lower():
        try:
            os.remove(dest)
        except OSError:
            pass
        raise ValueError(
            f"SHA256 no coincide (esperado {expected_sha256[:12]}…, "
            f"bajado {actual[:12]}…); archivo eliminado.")
    return dest


def clean_notes(notes, max_lines=8, max_chars=600):
    """Notas del release a texto plano corto (sin prefijos markdown)."""
    lines = []
    for raw in (notes or "").splitlines():
        line = re.sub(r"^#+\s*", "", raw).strip()
        if line:
            lines.append(line)
    text = "\n".join(lines[:max_lines])
    return text[:max_chars]


def cmd_update(download_dir=None):
    """CLI `instant update [--download DIR]`: informa y opcionalmente baja."""
    try:
        info = check()
    except Exception as exc:
        print(f"No se pudo consultar versiones: {exc}")
        return 2
    print(f"instalada: {info['current'] or '?'} / última: {info['latest'] or '?'}")
    if not info["update"]:
        print("Estás al día.")
        return 0
    notes = clean_notes(info["notes"])
    print(f"Hay versión nueva: {info['latest']} ({info['asset']})")
    for line in notes.splitlines():
        print("  " + line)
    if not download_dir:
        print("Para bajarla: instant update --download DIR  "
              "(verifica SHA256 solo).")
        print("Para aplicarla con todo frenado: instant-update.bat <archivo>.")
        return 0
    try:
        expected = fetch_expected_sha256(info["asset_url"])
    except Exception as exc:
        print(f"No se puede verificar la descarga: {exc}")
        return 2
    dest = os.path.join(download_dir, info["asset"])

    def progress(done, total):
        if total:
            print(f"\r  {done / total:.0%} ({done // 1024} KB)", end="")

    try:
        download(info["asset_url"], dest, progress=progress,
                 expected_sha256=expected)
    except Exception as exc:
        print(f"\nDescarga fallida: {exc}")
        return 2
    print(f"\nDescargado y verificado: {dest}")
    print(f"SHA256: {expected}")
    print("Aplicá con: instant-update.bat "
          f"\"{dest}\" {expected}  (frena todo, re-verifica, respalda "
          "el exe anterior y lo cambia).")
    return 0
