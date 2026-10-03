"""Genera el audio del corpus etiquetado con voces neuronales y ffmpeg.

Uso (desde la raiz del repo, con el .venv del proyecto):

    python dictado/tests/corpus/generate_corpus.py
    python dictado/tests/corpus/generate_corpus.py --only es01,en05
    python dictado/tests/corpus/generate_corpus.py --voice es-ES-AlvaroNeural

El audio NO se versiona: se regenera. Los WAV quedan a 16 kHz mono, que es lo
que esperan Silero VAD y Parakeet.

Limitacion conocida: es voz sintetica. Sirve para comparar motores entre si y
para ver donde falla cada uno, pero no reemplaza una grabacion humana.
"""
import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
import wave

HERE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(HERE, "manifest.json")
AUDIO_DIR = os.path.join(HERE, "audio")
SAMPLE_RATE = 16000


def load_manifest(path=MANIFEST):
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def find_ffmpeg():
    found = shutil.which("ffmpeg")
    if not found:
        raise SystemExit(
            "ffmpeg no esta en PATH; hace falta para pasar el audio a 16 kHz mono.")
    return found


async def _synthesize(text, voice, destination, rate=None):
    import edge_tts

    options = {}
    if rate:
        options["rate"] = rate
    await edge_tts.Communicate(text, voice, **options).save(destination)


def synthesize(text, voice, destination, rate=None):
    asyncio.run(_synthesize(text, voice, destination, rate))


def to_wav(source, destination, ffmpeg):
    subprocess.run(
        [ffmpeg, "-y", "-loglevel", "error", "-i", source,
         "-ac", "1", "-ar", str(SAMPLE_RATE), "-acodec", "pcm_s16le", destination],
        check=True)


def wav_stats(path):
    with wave.open(path, "rb") as handle:
        frames, rate = handle.getnframes(), handle.getframerate()
        width, channels = handle.getsampwidth(), handle.getnchannels()
        raw = handle.readframes(frames)
    import numpy as np

    if width != 2:
        raise SystemExit(f"{path}: se esperaba PCM de 16 bits, hay {width * 8}.")
    samples = np.frombuffer(raw, dtype="<i2").astype("float32") / 32768.0
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    return {"seconds": frames / float(rate), "rate": rate, "channels": channels,
            "peak": peak}


def main(argv=None):
    parser = argparse.ArgumentParser(description="Genera el audio del corpus.")
    parser.add_argument("--manifest", default=MANIFEST)
    parser.add_argument("--out", default=AUDIO_DIR)
    parser.add_argument("--only", default="",
                        help="ids separados por coma (default: todas)")
    parser.add_argument("--voice", default="",
                        help="fuerza una voz; default: alterna las del manifiesto")
    parser.add_argument("--voice-set", default="voices",
                        help="clave del manifiesto con la lista de voces "
                             "(default: voices; usa voices_pass_b para la pasada B)")
    parser.add_argument("--rate", default="",
                        help="ritmo de la voz, p.ej. -15%% (default: el normal)")
    parser.add_argument("--keep-mp3", action="store_true",
                        help="conserva el mp3 intermedio")
    args = parser.parse_args(argv)

    manifest = load_manifest(args.manifest)
    voices = manifest.get(args.voice_set) or manifest.get("voices") or ["es-AR-TomasNeural"]
    phrases = manifest["phrases"]
    wanted = {value.strip() for value in args.only.split(",") if value.strip()}
    if wanted:
        phrases = [item for item in phrases if item["id"] in wanted]
        missing = wanted - {item["id"] for item in phrases}
        if missing:
            raise SystemExit("ids desconocidos: " + ", ".join(sorted(missing)))

    ffmpeg = find_ffmpeg()
    os.makedirs(args.out, exist_ok=True)
    report = []
    for position, phrase in enumerate(phrases):
        voice = args.voice or voices[position % len(voices)]
        wav_path = os.path.join(args.out, phrase["id"] + ".wav")
        mp3_path = os.path.join(args.out, phrase["id"] + ".mp3")
        synthesize(phrase["text"], voice, mp3_path, args.rate or None)
        to_wav(mp3_path, wav_path, ffmpeg)
        if not args.keep_mp3:
            os.remove(mp3_path)
        stats = wav_stats(wav_path)
        report.append((phrase["id"], voice, stats))
        print(f"  {phrase['id']:<6} {voice:<22} {stats['seconds']:5.2f}s "
              f"pico {stats['peak']:.3f}")

    total = sum(item[2]["seconds"] for item in report)
    quiet = [item[0] for item in report if item[2]["peak"] < 0.05]
    print(f"\n{len(report)} frases, {total:.1f}s de audio en {args.out}")
    if quiet:
        print("AVISO: pico muy bajo en " + ", ".join(quiet))
    return 0


if __name__ == "__main__":
    sys.exit(main())
