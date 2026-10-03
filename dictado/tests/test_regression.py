"""Regresion minima: solo comportamiento consumidor-visible."""
import os
import sys
import tempfile
from unittest.mock import patch

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from instant_app import config, context, llm
from instant_app.engine import join_texts, merge_short_bounds



def _check(name, cond):
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        raise SystemExit(1)


# Overlay progression is ordered by session/phase, with errors preempting completion.
from instant_app import daemon as daemon_module
from instant_app.overlay import OverlayTransitions


_states = OverlayTransitions()
_check("overlay start to listening to processing",
       _states.accept(1, "starting") < _states.accept(1, "listening")
       < _states.accept(1, "processing"))
_check("late listening cannot replace processing",
       _states.accept(1, "listening") is None)
_check("success appears after processing", _states.accept(1, "success") is not None)
_check("error replaces success and stays terminal",
       _states.accept(1, "error") is not None
       and _states.accept(1, "success") is None)
_check("new press starts a new overlay session",
       _states.accept(2, "starting") is not None)


class _OverlaySequence:
    def __init__(self):
        self.transitions = OverlayTransitions()
        self.events = []

    def _append(self, session, state, *detail):
        if self.transitions.accept(session, state) is not None:
            self.events.append((state, session, *detail))

    def starting(self, session):
        self._append(session, "starting")

    def listening(self, session):
        self._append(session, "listening")

    def processing(self, session):
        self._append(session, "processing")

    def success_for(self, session, milliseconds=760):
        self._append(session, "success", milliseconds)

    def show_notice_for(self, session, text, color="#f2c36a", milliseconds=2000):
        self._append(session, "notice", text, color, milliseconds)

    def show_error_for(self, session, text, color="#ff908b", milliseconds=3000):
        self._append(session, "error", text, color, milliseconds)

    def hide(self):
        self.transitions.hide()
        self.events.append(("idle",))


_deferred_jobs = []


class _DeferredJob:
    def __init__(self, target, args, daemon):
        self.target = target
        self.args = args
        _deferred_jobs.append(self)

    def start(self):
        pass


class _FakeEngine:
    min_dur = 0.0

    def transcribe(self, _wav):
        return "recognized"


_daemon = daemon_module.Daemon.__new__(daemon_module.Daemon)
_daemon.lock = daemon_module.threading.Lock()
_daemon.rec = {
    "sid": 0, "grabando": False, "frames": [], "t_start": 0.0,
    "done": None, "busy": False,
}
_daemon.overlay = _OverlaySequence()
_daemon.engine = _FakeEngine()
_daemon.cfg = {"llm_url": ""}
_daemon.beep = lambda **_kwargs: None
with patch("instant_app.daemon.threading.Thread", _DeferredJob):
    _daemon.on_press()
_check("key-down sends immediate starting state",
       _daemon.overlay.events == [("starting", 1)])
_daemon.rec["frames"] = [daemon_module.np.array([0.2, 0.2], dtype=daemon_module.np.float32)]
_daemon.rec["done"].set()
with patch("instant_app.daemon.threading.Thread", _DeferredJob):
    _daemon.on_release()
_check("release goes directly to processing",
       _daemon.overlay.events == [("starting", 1), ("processing", 1)])
_daemon.overlay.listening(1)
_check("late mic-open update cannot reverse release transition",
       _daemon.overlay.events[-1] == ("processing", 1))
with patch("instant_app.paste.paste", return_value=None):
    _deferred_jobs[-1].target(*_deferred_jobs[-1].args)
_check("successful paste produces brief confirmation",
       _daemon.overlay.events[-1] == ("success", 1, 760))
_daemon.overlay.starting(2)
_daemon.overlay.listening(2)
_daemon.overlay.processing(2)
_daemon.engine.transcribe = lambda _wav: (_ for _ in ()).throw(RuntimeError("recognizer failed"))
_daemon._job(daemon_module.np.array([0.2], dtype=daemon_module.np.float32), 1.0, 2)
_check("recognition error replaces processing with actionable feedback",
       _daemon.overlay.events[-1][0:2] == ("error", 2)
       and "Diagnóstico" in _daemon.overlay.events[-1][2])

# The daemon job uses the active local glossary before paste.
_daemon.overlay.starting(3)
_daemon.overlay.processing(3)
_daemon.engine.transcribe = lambda _wav: "in stand"
_daemon.cfg = {
    "llm_url": "",
    "active_context": "Trabajo",
    "context_profiles": {
        "General": [],
        "Trabajo": [{"term": "Instant", "aliases": ["in stand"]}],
    },
}
with patch("instant_app.paste.paste") as _pasted:
    _daemon._job(daemon_module.np.array([0.2], dtype=daemon_module.np.float32), 1.0, 3)
_check("daemon pastes context-corrected transcription",
       _pasted.call_args.args[0] == "Instant ")


# join_texts: une, pega puntuacion, colapsa espacios.
_check("join vacios", join_texts(["", "  ", ""]) == "")
_check("join puntuacion", join_texts(["hola mundo", ", ¿ como estas ?"]) == "hola mundo, ¿como estas?")
_check("join espacios", join_texts(["  hola   mundo  "]) == "hola mundo")

# merge_short_bounds: une cortos adyacentes, deja largos solos.
_check("merge cortos", merge_short_bounds([(0.0, 0.3), (0.5, 2.0)]) == [(0.0, 2.0)])
_check("merge largos", merge_short_bounds([(0.0, 3.0), (5.0, 8.0)]) == [(0.0, 3.0), (5.0, 8.0)])
_check("merge gap grande", merge_short_bounds([(0.0, 0.3), (5.0, 5.5)]) == [(0.0, 0.3), (5.0, 5.5)])

# config: defaults + env override + roundtrip de llm_url.
os.environ.pop("DICTADO_LLM_URL", None)
c = config.load()
_check("default llm_url vacio", c.get("llm_url", "") == "")
_check("default sound off", c.get("sound") is False)
_check("default lang es", c.get("lang") == "es")
_check("default threads 4", c.get("threads") == 4)
os.environ["DICTADO_LLM_URL"] = "http://127.0.0.1:8080"
_check("env llm_url", config.load()["llm_url"] == "http://127.0.0.1:8080")
del os.environ["DICTADO_LLM_URL"]

# llm: sin URL -> identico (pipeline sin red).
_check("llm off identico", llm.maybe_polish("hola mundo", {"llm_url": ""}) == "hola mundo")
_check("llm sin server identico",
        llm.maybe_polish("hola mundo", {"llm_url": "http://127.0.0.1:9"}) == "hola mundo")

# Context profiles apply only user-authored whole-word variants, without fuzzy
# substitutions that could rewrite ordinary words.
_work_context = {
    "active_context": "Trabajo",
    "context_profiles": {
        "General": [],
        "Trabajo": [
            {"term": "Instant", "aliases": ["instante", "in stand"]},
            {"term": "Parakeet", "aliases": ["para kit"]},
        ],
    },
}
_check("profile replaces explicit aliases only",
       context.correct_aliases(
           "instante abre el instanteo; in stand y para kit.",
           _work_context)
       == "Instant abre el instanteo; Instant y Parakeet.")
_check("inactive profile does not bias text",
       context.correct_aliases("instante", {
           **_work_context, "active_context": "General"
       }) == "instante")
_check("local glossary works with LLM disabled",
       llm.maybe_polish("in stand", _work_context) == "Instant")
with patch("urllib.request.urlopen", side_effect=OSError("server unavailable")):
    _check("LLM failure keeps explicit local glossary correction",
           llm.maybe_polish(
               "instante",
               {**_work_context, "llm_url": "http://local"})
           == "Instant")


class _FakeResponse:
    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self):
        return self.body


def _llm_response(text):
    import json
    return _FakeResponse(json.dumps({
        "choices": [{"message": {"content": text}}],
    }).encode())


with patch("urllib.request.urlopen", return_value=_llm_response("¿Cómo estás?")):
    _check("LLM may improve punctuation and accents without changing words",
           llm.polish("como estas", "http://local") == "¿Cómo estás?")
with patch("urllib.request.urlopen", return_value=_llm_response("Hola, mundo y todo.")):
    _check("LLM additions are rejected",
           llm.polish("Hola mundo", "http://local") == "Hola mundo")

with tempfile.TemporaryDirectory() as temp:
    config_file = os.path.join(temp, "config.json")
    with patch("instant_app.config.config_path", return_value=config_file):
        config.save({
            **config.DEFAULTS,
            "active_context": "Trabajo",
            "context_profiles": _work_context["context_profiles"],
        })
        _roundtrip = config.load()
        with patch.dict(os.environ, {"DICTADO_CONTEXT": "General"}):
            _selected = config.load()
        _check("environment selects the active context profile",
               _selected["active_context"] == "General")
    _check("context profiles persist through config",
           _roundtrip["active_context"] == "Trabajo"
           and _roundtrip["context_profiles"]["Trabajo"][0]["term"] == "Instant")

# hotkey: claves win esperadas.
from instant_app import hotkey
_check("keys win", set(hotkey.WINDOWS_KEYS) == {"f9", "f10", "f20", "scroll", "pause"})
_check("keys posix", tuple(hotkey.POSIX_KEYS) == ("f9", "f10", "f11", "f12"))

# hotkey: normalización para captura (vacío = default, case-insensitive).
_check("normalize enter", hotkey.normalize_key("", "f9") == "f9")
_check("normalize none", hotkey.normalize_key(None, "f9") == "f9")
_check("normalize named enter", hotkey.normalize_key("enter", "f9") == "enter")
_check("normalize case", hotkey.normalize_key("F10", "f9") == "f10")
_check("normalize strip", hotkey.normalize_key("  f9  ", "f9") == "f9")
with patch("sys.platform", "win32"):
    _check("arbitrary VK accepted", hotkey.is_valid_key("vk:65"))
    _check("letter maps to VK", hotkey._windows_vk("a") == 0x41)
    _check("custom key label", hotkey.key_label("vk:65") == "A")
    _check("mouse button rejected", not hotkey.is_valid_key("vk:1"))
with patch("sys.platform", "linux"):
    _check("POSIX character accepted", hotkey.is_valid_key("x"))
    _check("Windows VK rejected on POSIX", not hotkey.is_valid_key("vk:65"))

# hotkey: captura asigna tecla valida, Enter = default, repite si invalida.
_orig_read = hotkey._read_keypress
try:
    hotkey._read_keypress = lambda: "f10"
    _check("capture directa", hotkey.capture_key("prompt", "f9") == "f10")
    hotkey._read_keypress = lambda: "x"
    _check("capture arbitrary character", hotkey.capture_key("prompt", "f9") == "x")
    hotkey._read_keypress = lambda: "space"
    _check("capture spacebar", hotkey.capture_key("prompt", "f9") == "space")
    hotkey._read_keypress = lambda: ""
    _check("capture enter default", hotkey.capture_key("prompt", "f9") == "f9")
    seq = iter(["invalida", "f9"])
    hotkey._read_keypress = lambda: next(seq)
    _check("capture reintenta", hotkey.capture_key("prompt", "f9") == "f9")
finally:
    hotkey._read_keypress = _orig_read

# Windows WASAPI runs at the device's native rate; permit shared-mode
# conversion when Instant requests the recognizer's 16 kHz stream.
from io import StringIO

with patch("sys.stdin", StringIO("f10\n")):
    _check("captura de tecla sin TTY",
           hotkey.capture_key("prompt", "f9") == "f10")
from instant_app import audio


class _FakeSettings:
    def __init__(self, auto_convert):
        self.auto_convert = auto_convert


class _FakeSounddevice:
    def __init__(self, hostapi):
        self.hostapi = hostapi

    def query_devices(self, device, kind):
        return {"hostapi": 0, "max_input_channels": 2}

    def query_hostapis(self, index):
        return {"name": self.hostapi}

    def WasapiSettings(self, *, auto_convert):
        return _FakeSettings(auto_convert)


def _stream_options(hostapi):
    fake_sd = _FakeSounddevice(hostapi)
    with patch("instant_app.audio.sys.platform", "win32"):
        with patch.dict(sys.modules, {"sounddevice": fake_sd}):
            return audio.input_stream_options(26)


wasapi_options = _stream_options("Windows WASAPI")
_check("WASAPI 16 kHz auto-convert",
       wasapi_options["extra_settings"].auto_convert is True)
_check("MME does not get WASAPI settings", _stream_options("MME") == {})

import numpy as np

stereo = np.array([[0.0, 0.2], [0.0, -0.2]], dtype=np.float32)
_check("stereo elige canal con señal",
       np.array_equal(audio.to_mono(stereo), stereo[:, 1]))
_check("mono conserva el canal",
       np.array_equal(audio.to_mono(stereo[:, 1:2]), stereo[:, 1]))

fake_sd = _FakeSounddevice("MME")
with patch.dict(sys.modules, {"sounddevice": fake_sd}):
    _check("captura estéreo cuando el mic ofrece dos canales",
           audio.input_channels(26) == 2)

class _FakeMicDevices:
    def __init__(self):
        self.devices = [
            {"name": "HyperX", "max_input_channels": 1, "default_samplerate": 48000},
            {"name": "DGM20", "max_input_channels": 1, "default_samplerate": 48000},
        ]

    def query_devices(self, device=None, kind=None):
        if device is None:
            return self.devices
        return self.devices[device]


with patch.dict(sys.modules, {"sounddevice": _FakeMicDevices()}):
    _check("mic name survives shifted device index",
           audio.resolve_mic("DGM20", 0) == 1)

class _FakePortAudioChoices:
    hostapis = ("MME", "Windows DirectSound", "Windows WASAPI", "Windows WDM-KS")
    devices = [
        {"name": "Microsoft Sound Mapper - Input", "hostapi": 0, "max_input_channels": 2},
        {"name": "Microphone (DGM20 USB Microphon", "hostapi": 0, "max_input_channels": 1},
        {"name": "Microphone (DGM20 USB Microphone)", "hostapi": 1, "max_input_channels": 1},
        {"name": "Microphone (DGM20 USB Microphone)", "hostapi": 2, "max_input_channels": 1},
        {"name": "Stereo Mix (Realtek HD Audio)", "hostapi": 3, "max_input_channels": 2},
        {"name": "Microphone (Twin USB Microphone)", "hostapi": 2, "max_input_channels": 1},
        {"name": "Microphone (Twin USB Microphone)", "hostapi": 2, "max_input_channels": 1},
        {"name": "Microphone (Twin USB Microphone)", "hostapi": 0, "max_input_channels": 1},
        {"name": "Microphone (Twin USB Microphone)", "hostapi": 0, "max_input_channels": 1},
        {"name": "Line In (Realtek HD Audio)", "hostapi": 3, "max_input_channels": 2},
        {"name": "Microphone (DGM20 USB Microphone)", "hostapi": 3, "max_input_channels": 1},
    ]

    def query_devices(self, device=None, kind=None):
        return self.devices if device is None else self.devices[device]

    def query_hostapis(self, index):
        return {"name": self.hostapis[index]}


with patch("sys.platform", "win32"), patch.dict(
        sys.modules, {"sounddevice": _FakePortAudioChoices()}):
    choices = audio.input_choices()
    _check("mic aliases collapse to preferred backend",
           [entry[0] for entry in choices] == [3, 5, 6, 9])
    _check("saved WDM-KS index resolves to preferred WASAPI mic",
           audio.resolve_mic("Microphone (DGM20 USB Microphone)", 10) == 3)
    _check("legacy mic index maps to visible alias",
           audio.preferred_input_index(1, choices) == 3)

class _ChangedDeviceList:
    hostapis = ("Windows WASAPI",)
    devices = [
        {"name": "Microphone (Different USB Microphone)",
         "hostapi": 0, "max_input_channels": 1},
    ]

    def query_devices(self, device=None, kind=None):
        return self.devices if device is None else self.devices[device]

    def query_hostapis(self, index):
        return {"name": self.hostapis[index]}


with patch("sys.platform", "win32"), patch.dict(
        sys.modules, {"sounddevice": _ChangedDeviceList()}):
    _check("missing saved mic does not select a reused device index",
           audio.resolve_mic("Microphone (DGM20 USB Microphone)", 0,
                             strict_hint=True) is None)


class _FakeStartStream:
    def __init__(self, device, kwargs, attempts, fail_devices):
        self.device = device
        self.kwargs = kwargs
        self.attempts = attempts
        self.fail_devices = fail_devices

    def start(self):
        self.attempts.append((self.device, self.kwargs.get("callback")))
        if self.device in self.fail_devices:
            raise RuntimeError("Windows callback start failed")

    def close(self):
        pass

    def stop(self):
        pass


class _FakeAudioOpen(_FakePortAudioChoices):
    def __init__(self):
        self.attempts = []
        self.fail_devices = {2, 3}

    @staticmethod
    def WasapiSettings(auto_convert):
        return _FakeSettings(auto_convert)

    def InputStream(self, **kwargs):
        return _FakeStartStream(
            kwargs["device"], kwargs, self.attempts, self.fail_devices)



class _FakeMeterStream(_FakeStartStream):
    def start(self):
        super().start()
        if self.kwargs["device"] not in self.fail_devices:
            self.kwargs["callback"](
                np.array([[0.25, -0.1]], dtype=np.float32), 1, None, None)


class _FakeMeterOpen(_FakeAudioOpen):
    def InputStream(self, **kwargs):
        return _FakeMeterStream(
            kwargs["device"], kwargs, self.attempts, self.fail_devices)


meter_sd = _FakeMeterOpen()
meter_levels = []
with patch("sys.platform", "win32"), patch.dict(
        sys.modules, {"sounddevice": meter_sd}):
    meter_peak = audio.peak_meter(3, seconds=0.05, on_level=meter_levels.append)
    _check("GUI meter measures callback audio after same-mic fallback",
           meter_peak == 0.25 and meter_levels == [0.25] and
           [device for device, _callback in meter_sd.attempts] == [3, 2, 1])

class _FakeDuplicateMicOpen(_FakeAudioOpen):
    # DirectSound and WDM expose the two identical names in reverse physical order.
    devices = [
        {"name": "Microphone (Twin USB Microphone)", "hostapi": 0,
         "max_input_channels": 1, "physical_id": "A"},
        {"name": "Microphone (Twin USB Microphone)", "hostapi": 0,
         "max_input_channels": 1, "physical_id": "B"},
        {"name": "Microphone (Twin USB Microphone)", "hostapi": 1,
         "max_input_channels": 1, "physical_id": "B"},
        {"name": "Microphone (Twin USB Microphone)", "hostapi": 1,
         "max_input_channels": 1, "physical_id": "A"},
        {"name": "Microphone (Twin USB Microphone)", "hostapi": 2,
         "max_input_channels": 1, "physical_id": "A"},
        {"name": "Microphone (Twin USB Microphone)", "hostapi": 2,
         "max_input_channels": 1, "physical_id": "B"},
        {"name": "Microphone (Twin USB Microphone)", "hostapi": 3,
         "max_input_channels": 1, "physical_id": "B"},
        {"name": "Microphone (Twin USB Microphone)", "hostapi": 3,
         "max_input_channels": 1, "physical_id": "A"},
    ]

    def __init__(self):
        super().__init__()
        self.fail_devices = {5}


duplicate_sd = _FakeDuplicateMicOpen()
duplicate_callback = lambda *_args: None
with patch("sys.platform", "win32"), patch.dict(
        sys.modules, {"sounddevice": duplicate_sd}):
    try:
        audio.open_input_stream(5, callback=duplicate_callback)
        duplicate_mic_failed = False
    except RuntimeError as error:
        duplicate_mic_failed = str(error) == "Windows callback start failed"
    _check("reordered same-name host aliases are never guessed",
           duplicate_mic_failed and duplicate_sd.attempts == [(5, duplicate_callback)])
    _check("stale index among same-name duplicate mics is unavailable",
           audio.resolve_mic("Twin USB Microphone", 99, strict_hint=True) is None)
class _FakeAmbiguousMicOpen(_FakeAudioOpen):
    devices = [
        {"name": "Microphone (Twin USB Microphone)", "hostapi": 2, "max_input_channels": 1},
        {"name": "Microphone (Twin USB Microphone)", "hostapi": 2, "max_input_channels": 1},
        {"name": "Microphone (Twin USB Microphone)", "hostapi": 0, "max_input_channels": 1},
    ]

    def __init__(self):
        super().__init__()
        self.fail_devices = {1}


ambiguous_sd = _FakeAmbiguousMicOpen()
ambiguous_callback = lambda *_args: None
with patch("sys.platform", "win32"), patch.dict(
        sys.modules, {"sounddevice": ambiguous_sd}):
    try:
        audio.open_input_stream(1, callback=ambiguous_callback)
        failed_as_unavailable = False
    except RuntimeError as error:
        failed_as_unavailable = str(error) == "Windows callback start failed"
    _check("ambiguous alias counts do not switch to another same-name mic",
           failed_as_unavailable and
           ambiguous_sd.attempts == [(1, ambiguous_callback)])


open_sd = _FakeAudioOpen()
callback = lambda *_args: None
with patch("sys.platform", "win32"), patch.dict(sys.modules, {"sounddevice": open_sd}):
    stream, selected = audio.open_input_stream(3, callback=callback)
    _check("callback start fails over only to same-mic backend alias",
           selected == 1 and open_sd.attempts == [
               (3, callback), (2, callback), (1, callback)])
    stream.close()

open_sd.attempts.clear()
with patch("sys.platform", "win32"), patch.dict(sys.modules, {"sounddevice": open_sd}):
    _check("mic probe uses callback start and same-mic fallback",
           audio.probe(3, seconds=0) and
           [device for device, _callback in open_sd.attempts] == [3, 2, 1] and
           all(callback_ is not None for _device, callback_ in open_sd.attempts))
# setup: no-interactive configuration flags include context profiles.
from instant_app.setup import _parse_args
o = _parse_args(["--yes", "--no-probe"])
_check("setup yes noprobe", o.yes and o.no_probe)
o = _parse_args(["--yes", "--mic", "3", "--key", "f9", "--threads", "4", "--no-sound"])
_check("setup flags", o.mic == 3 and o.key == "f9" and o.threads == 4 and o.no_sound)
o = _parse_args([
    "--context-profile", "Trabajo",
    "--context-term", "Instant=instante|in stand",
    "--context-remove-term", "Parakeet",
    "--context-delete-profile",
])
_check("setup context management flags",
       o.context_profile == "Trabajo"
       and o.context_term == ["Instant=instante|in stand"]
       and o.context_remove_term == ["Parakeet"]
       and o.context_delete_profile)

# Setup can remove exact terms from a selected profile without changing others.
from instant_app import setup as setup_module
_setup_cfg = {
    **config.DEFAULTS,
    "active_context": "Trabajo",
    "context_profiles": {
        "General": [],
        "Trabajo": [{"term": "Instant", "aliases": ["instante"]},
                    {"term": "Parakeet", "aliases": ["para kit"]}],
    },
}
_saved_setup = {}
with patch("instant_app.setup.config.load", return_value=_setup_cfg), \
        patch("instant_app.setup.config.save",
              side_effect=lambda value: (_saved_setup.update(value) or "config.json")), \
        patch("instant_app.deps.check", return_value={
            "sherpa_onnx": {"ok": True}, "sounddevice": {"ok": True}}), \
        patch("instant_app.deps.report", return_value=""), \
        patch("instant_app.models.check",
              return_value={"parakeet": True, "vad": True}), \
        patch("instant_app.setup._real_inputs", return_value=[]), \
        patch("instant_app.autostart.is_enabled", return_value=False), \
        patch("instant_app.autostart.describe", return_value="disabled"):
    setup_module.cmd_setup([
        "--yes", "--no-probe", "--context-profile", "Trabajo",
        "--context-remove-term", "Instant",
    ])
_check("setup removes a vocabulary term from only the selected profile",
       _saved_setup["active_context"] == "Trabajo"
       and _saved_setup["context_profiles"]["General"] == []
       and _saved_setup["context_profiles"]["Trabajo"] == [
           {"term": "Parakeet", "aliases": ["para kit"]}])

# modelos: descarga conjunta Parakeet + VAD en un solo paso con progreso claro.
from instant_app import models
with tempfile.TemporaryDirectory() as d:
    import os as _os
    mdir = _os.path.join(d, "parakeet-v3-int8")
    vdir = _os.path.join(d, "silero-vad")
    _os.makedirs(mdir)
    _os.makedirs(vdir)
    for f in models.PARAKEET_FILES:
        open(_os.path.join(mdir, f), "wb").close()
    open(_os.path.join(vdir, "silero_vad.onnx"), "wb").close()
    seen = []
    models.download_models(d, progress=lambda step, done, total: seen.append(step))
    _check("joint parakeet+vad", "parakeet" in seen and "vad" in seen)

class _FakeResponse:
    headers = {"Content-Length": "3"}

    def __init__(self):
        self.done = False

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, size):
        if self.done:
            return b""
        self.done = True
        return b"vad"


def _snapshot_download(repo_id, *, local_dir, allow_patterns):
    os.makedirs(local_dir, exist_ok=True)
    for filename in allow_patterns:
        with open(os.path.join(local_dir, filename), "wb") as model_file:
            model_file.write(b"model")


fake_hub = type("FakeHub", (), {"snapshot_download": staticmethod(_snapshot_download)})
with tempfile.TemporaryDirectory() as d:
    with patch.dict(sys.modules, {"huggingface_hub": fake_hub}):
        with patch("urllib.request.urlopen", return_value=_FakeResponse()):
            models.download_models(d)
    _check("descarga usa la API actual de Hugging Face", all(models.check(d).values()))

print("OK: regresion minima verde.")
