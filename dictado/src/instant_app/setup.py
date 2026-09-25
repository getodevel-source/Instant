"""TUI setup simple (stdlib): modelos juntos, mic con medidor, tecla, test final.

Sobrevive sin modelos (avisa y sigue) y sin mic (no crashea).
Modo no interactivo: `instant setup --yes` (no pregunta nada; usa config
actual salvo flags --mic/--key/--threads/--sound/--no-sound/--llm-url).
"""
import logging

from instant_app import audio, config, hotkey
from instant_app.paths import resolve_data_dir, user_data_dir

log = logging.getLogger("instant")

SKIP_DEVICES = ("sound mapper", "primary sound", "stereo mix", "what u hear",
                "wave out", "loopback", "speakers wave", "microphone wave")


def _ask(prompt, default=None):
    suffix = f" [{default}]" if default is not None else ""
    try:
        v = input(f"  {prompt}{suffix}: ").strip()
    except (EOFError, KeyboardInterrupt):
        print()
        raise KeyboardInterrupt
    return v if v else (default if default is not None else "")


def _ask_int(prompt, default, lo, hi):
    while True:
        v = _ask(prompt, str(default))
        try:
            n = int(v)
            if lo <= n <= hi:
                return n
        except ValueError:
            pass
        print(f"  numero entre {lo} y {hi}.")


def _parse_args(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="instant setup")
    ap.add_argument("-y", "--yes", action="store_true",
                    help="no interactivo: usa defaults/config actual sin preguntar")
    ap.add_argument("--mic", type=int, default=None, help="indice sounddevice del mic")
    ap.add_argument("--key", default=None, help="tecla hold-to-talk")
    ap.add_argument("--threads", type=int, default=None, help="hilos CPU")
    ap.add_argument("--sound", action="store_true", default=None, help="activa pitidos")
    ap.add_argument("--no-sound", action="store_true", help="apaga pitidos")
    ap.add_argument("--llm-url", default=None, help="llama-server local (vacio=off)")
    ap.add_argument("--no-meter", action="store_true", help="salta medidor de nivel")
    ap.add_argument("--no-probe", action="store_true", help="salta probe final y warmup")
    return ap.parse_args(argv)


def _real_inputs():
    """Lista de mics reales; [] si no hay backend/mics (nunca crashea)."""
    try:
        all_in = audio.list_inputs()
    except Exception:
        log.exception("sin backend de audio (instala PortAudio?)")
        return []
    return [t for t in all_in if not any(s in t[1].lower() for s in SKIP_DEVICES)]


def cmd_setup(argv=None):
    o = _parse_args(argv)
    print("== instant setup ==")
    cfg = config.load()
    rc = 0

    # 1. Modelos juntos: Parakeet (~670MB) + VAD (~1MB) en un solo paso.
    data_dir = resolve_data_dir()
    if data_dir == user_data_dir():
        print(f"  modelos en: {data_dir}")
    else:
        print(f"  modelos en: {data_dir} (dev/DICTADO_DATA)")
    from instant_app import models as dl
    status = dl.check(data_dir)
    models_ok = all(status.values())
    if models_ok:
        print("  modelos OK (Parakeet + VAD).")
    else:
        missing = sorted(k for k, ok in status.items() if not ok)
        print(f"  faltan: {', '.join(missing)}.")
        print("  descargando modelos juntos: Parakeet (~670MB) + VAD (~1MB)...")
        try:
            dl.download_models(data_dir)
            models_ok = all(dl.check(data_dir).values())
            print("  modelos OK (Parakeet + VAD)." if models_ok
                  else "  descarga incompleta, reintenta luego.")
        except Exception:
            log.exception("SIN MODELOS: sin red o sin espacio; el resto se configura igual. "
                          "Re-corre `instant setup` con red para descargar.")
            models_ok = False
            rc = 2
    if not models_ok:
        print("  AVISO: sin modelos `instant run` no transcribe hasta descargarlos.")

    # 2. Microfono: lista real + medidor + probe final; guarda mic_index.
    inputs = _real_inputs()
    if not inputs:
        print("  sin dispositivos de entrada. Conecta un mic y re-corre `instant setup`.")
        rc = max(rc, 2)
    else:
        print("  microfonos:")
        for n, (i, name, ch, _rate) in enumerate(inputs):
            mark = ""
            try:
                import sounddevice as sd
                if tuple(sd.default.device)[0] == i:
                    mark = "  (default del sistema)"
            except Exception:
                pass
            print(f"    {n}. [{i}] {name} ({ch}ch){mark}")
        if o.mic is not None:
            idx, name = o.mic, next((n for i, n, _c, _r in inputs if i == o.mic), None)
            if name is None:
                print(f"  --mic {o.mic} no es entrada valida; queda {cfg.get('mic_index')}.")
                rc = max(rc, 2)
            else:
                cfg["mic_index"] = idx
                cfg["mic_hint"] = ""
                print(f"  elegido (--mic): [{idx}] {name}")
        elif o.yes:
            # --yes no pisa el mic del usuario: solo muestra el actual.
            cur = cfg.get("mic_index")
            name = next((n for i, n, _c, _r in inputs if i == cur), None)
            if name is None:
                print(f"  mic (config actual): [{cur}] (no esta en la lista; se conserva)")
            else:
                print(f"  mic (config actual): [{cur}] {name}")
        else:
            cur = cfg.get("mic_index")
            dflt = 0
            for n, (i, _n, _c, _r) in enumerate(inputs):
                if cur is not None and i == cur:
                    dflt = n
            sel = _ask_int("microfono (numero de la lista)", dflt, 0, len(inputs) - 1)
            idx, name = inputs[sel][0], inputs[sel][1]
            cfg["mic_index"] = idx
            cfg["mic_hint"] = ""
            print(f"  elegido: [{idx}] {name}")
            if not o.no_meter:
                if _ask("probar nivel (habla 3s)? s/n", "s").lower().startswith("s"):
                    audio.peak_meter(idx)

    # 3. Idioma fijo: espanol unico (se guarda para futuro; el engine no cambia).
    cfg["lang"] = "es"
    print("  idioma: Español (único)")

    # 4. Tecla con captura: presiona la tecla para asignar.
    keys = hotkey.available_keys()
    if o.key is not None:
        if o.key.lower() in keys:
            cfg["key"] = o.key.lower()
        else:
            print(f"  --key invalida. Opciones: {', '.join(keys)}; queda {cfg.get('key')}.")
            rc = max(rc, 2)
    elif o.yes:
        print(f"  tecla (config actual): {cfg.get('key', 'f9')}")
    else:
        print(f"  teclas validas: {', '.join(keys)}")
        cfg["key"] = hotkey.capture_key(
            "Presiona la tecla para dictar... (Enter = F9)",
            cfg.get("key", "f9"))
        print(f"  tecla: {cfg['key']}")

    # 5. Avanzados solo por flags (no se preguntan): threads/sound/llm-url.
    import multiprocessing
    max_t = max(1, multiprocessing.cpu_count())
    if o.threads is not None:
        cfg["threads"] = min(max(1, o.threads), max_t)
    if o.sound:
        cfg["sound"] = True
    elif o.no_sound:
        cfg["sound"] = False
    if o.llm_url is not None:
        cfg["llm_url"] = o.llm_url

    path = config.save(cfg)

    # 6. Test final: probe mic + warmup modelos.
    print(f"  config en: {path}")
    if o.no_probe:
        print(f"Listo. Mantén {cfg.get('key', 'f9').upper()} y dicta.")
        return rc
    mic_ok = True
    if inputs:
        from instant_app.audio import probe, resolve_mic
        mic = resolve_mic("", cfg.get("mic_index"))
        mic_ok = probe(mic)
        print(f"  mic probe: {'OK' if mic_ok else 'FAIL (revisa uso exclusivo)'}")
    else:
        print("  mic probe: SKIP (sin mics)")
        mic_ok = False
    if models_ok:
        try:
            from instant_app.engine import Engine
            eng = Engine(data_dir, threads=cfg.get("threads", 4),
                         max_seg=cfg.get("max_seg", 20.0))
            eng.recognizer()
            eng.vad()
            print("  warmup modelos: OK")
        except Exception:
            log.exception("warmup modelos FAIL")
            models_ok = False
    else:
        print("  warmup modelos: SKIP (sin modelos)")
    print(f"Listo. Mantén {cfg.get('key', 'f9').upper()} y dicta.")
    if not (mic_ok and models_ok):
        return 2
    return rc
