"""CLI: `instant setup` (TUI) y `instant run` (daemon)."""
import argparse
import logging
import os
import sys


def _log_setup():
    from instant_app.paths import config_dir
    d = config_dir()
    os.makedirs(d, exist_ok=True)
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
        handlers=[logging.FileHandler(os.path.join(d, "instant.log"), encoding="utf-8"),
                  logging.StreamHandler()],
    )


def main(argv=None):
    ap = argparse.ArgumentParser(prog="instant", description="Hold-to-talk ES offline.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p_setup = sub.add_parser("setup", help="TUI: modelos, microfono, tecla")
    p_setup.add_argument("-y", "--yes", action="store_true",
                         help="no interactivo: usa defaults/config actual")
    p_setup.add_argument("--mic", type=int, default=None)
    p_setup.add_argument("--key", default=None)
    p_setup.add_argument("--threads", type=int, default=None)
    p_setup.add_argument("--sound", action="store_true", default=None)
    p_setup.add_argument("--no-sound", action="store_true")
    p_setup.add_argument("--llm-url", default=None)
    p_setup.add_argument("--no-meter", action="store_true")
    p_setup.add_argument("--no-probe", action="store_true")
    sub.add_parser("run", help="daemon hold-to-talk")
    sub.add_parser("check", help="boot rapido: tecla + mic + warmup (<5s)")
    args, rest = ap.parse_known_args(argv)
    _log_setup()
    if args.cmd == "setup":
        from instant_app.setup import cmd_setup
        fwd = []
        if args.yes:
            fwd.append("--yes")
        for k in ("mic", "key", "threads", "llm_url"):
            v = getattr(args, k)
            if v is not None:
                fwd += [f"--{k.replace('_', '-')}", str(v)]
        for flag in ("sound", "no_sound", "no_meter", "no_probe"):
            if getattr(args, flag):
                fwd.append(f"--{flag.replace('_', '-')}")
        fwd += rest
        try:
            return cmd_setup(fwd)
        except KeyboardInterrupt:
            print("\nsetup cancelado.")
            return 130
    from instant_app import config
    from instant_app.daemon import Daemon, cmd_check
    cfg = config.load()
    if args.cmd == "check":
        return cmd_check(cfg)
    try:
        Daemon(cfg).run()
    except FileNotFoundError as e:
        logging.getLogger("instant").error("%s -> corre `instant setup` primero.", e)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
