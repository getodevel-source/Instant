"""CLI y entrada gráfica de Instant."""
import argparse
import logging
import os
import sys


def _log_setup():
    from instant_app.paths import config_dir

    directory = config_dir()
    os.makedirs(directory, exist_ok=True)
    handlers = [logging.FileHandler(
        os.path.join(directory, "instant.log"), encoding="utf-8")]
    has_console = sys.stdout is not None and sys.stderr is not None
    if has_console:
        handlers.append(logging.StreamHandler())
    else:
        if sys.stdout is None:
            sys.stdout = open(os.devnull, "w", encoding="utf-8")
        if sys.stderr is None:
            sys.stderr = open(os.devnull, "w", encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=handlers,
    )


def _run_gui(*args, **kwargs):
    from importlib import import_module

    return import_module("instant_app.gui").run_gui(*args, **kwargs)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="instant", description="Dictado local en español.")
    sub = ap.add_subparsers(dest="cmd")
    p_setup = sub.add_parser("setup", help="configuración de Instant")
    p_setup.add_argument("-y", "--yes", action="store_true",
                         help="no interactivo: usa defaults/config actual")
    p_setup.add_argument("--mic", type=int, default=None)
    p_setup.add_argument("--key", default=None)
    p_setup.add_argument("--threads", type=int, default=None)
    p_setup.add_argument("--sound", action="store_true", default=None)
    p_setup.add_argument("--no-sound", action="store_true")
    p_setup.add_argument("--llm-url", default=None)
    p_setup.add_argument("--context-profile", default=None)
    p_setup.add_argument("--context-term", action="append", default=[])
    p_setup.add_argument("--context-remove-term", action="append", default=[])
    p_setup.add_argument("--context-delete-profile", action="store_true")
    p_setup.add_argument("--autostart", action="store_true", default=None,
                         help="activa arranque con el sistema")
    p_setup.add_argument("--no-autostart", action="store_true",
                         help="desactiva el arranque con el sistema")
    p_setup.add_argument("--no-meter", action="store_true")
    p_setup.add_argument("--no-probe", action="store_true")
    p_setup.add_argument("--check-deps", action="store_true",
                         help="muestra tabla de dependencias y sigue")
    p_setup.add_argument("--fix-deps", action="store_true",
                         help="autoinstala lo permitido por el SO y re-chequea")
    sub.add_parser("run", help="daemon hold-to-talk")
    sub.add_parser("check", help="diagnóstico de teclado, micrófono y modelos")
    sub.add_parser("diagnostics", help="abre el diagnóstico visual")

    args, rest = ap.parse_known_args(argv)
    _log_setup()
    if args.cmd is None:
        if rest:
            ap.error("argumentos no reconocidos: " + " ".join(rest))
        if sys.platform == "win32":
            return _run_gui("home", start_daemon_on_open=True)
        ap.print_help()
        return 0

    if args.cmd == "diagnostics":
        if sys.platform == "win32":
            return _run_gui("diagnostics")
        args.cmd = "check"

    if args.cmd == "setup":
        cli_options = (
            args.yes, args.mic is not None, args.key is not None,
            args.threads is not None, args.sound is not None, args.no_sound,
            args.llm_url is not None, args.context_profile is not None,
            bool(args.context_term), bool(args.context_remove_term),
            args.context_delete_profile, args.no_meter, args.no_probe,
            args.check_deps, args.fix_deps, bool(rest))
        if sys.platform == "win32" and not any(cli_options):
            override = False if args.no_autostart else True if args.autostart else None
            return _run_gui("setup", autostart_override=override)

        from instant_app.setup import cmd_setup
        forward = ["--yes"] if args.yes else []
        for key in ("mic", "key", "threads", "llm_url", "context_profile"):
            value = getattr(args, key)
            if value is not None:
                forward.extend((f"--{key.replace('_', '-')}", str(value)))
        for value in args.context_term:
            forward.extend(("--context-term", value))
        for value in args.context_remove_term:
            forward.extend(("--context-remove-term", value))
        if args.context_delete_profile:
            forward.append("--context-delete-profile")
        for flag in ("sound", "no_sound", "no_meter", "no_probe", "check_deps",
                     "fix_deps", "autostart", "no_autostart"):
            if getattr(args, flag):
                forward.append(f"--{flag.replace('_', '-')}")
        forward.extend(rest)
        try:
            return cmd_setup(forward)
        except KeyboardInterrupt:
            print("\nsetup cancelado.")
            return 130

    from instant_app import config
    cfg = config.load()
    if args.cmd == "check":
        from instant_app.daemon import cmd_check
        return cmd_check(cfg)

    from instant_app.daemon_lifecycle import (
        acquire_daemon_mutex, release_daemon_mutex)
    mutex = acquire_daemon_mutex()
    if mutex is None:
        logging.getLogger("instant").info(
            "daemon ya activo; se omite el segundo inicio.")
        return 0
    try:
        from instant_app.daemon import Daemon
        Daemon(cfg).run()
    except FileNotFoundError as exc:
        logging.getLogger("instant").error(
            "%s -> corre `instant setup` primero.", exc)
        return 2
    finally:
        release_daemon_mutex(mutex)
    return 0


if __name__ == "__main__":
    sys.exit(main())
