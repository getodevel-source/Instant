# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
El proyecto usa [versionado semántico](https://semver.org/lang/es/).

## [Sin publicar]

Todavía no hay una versión publicada. El primer release será `0.1.0` y se
publica tageando `v0.1.0`: el workflow construye los binarios de los tres
sistemas y los adjunta al release, pero solo después de que la suite pase en
Windows, Linux y macOS.

## [0.1.0] — 2026-10-03

Primera versión con la aplicación completa. Todo el reconocimiento corre local,
en CPU; el audio nunca sale del equipo.

### Agregado

- **Dictado hold-to-talk**: se mantiene F9 (o la tecla elegida), se habla y al
  soltar el texto se pega en el campo enfocado. Pipeline: micrófono a 16 kHz →
  Silero VAD que corta frases → Parakeet TDT v3 int8 por segmento en paralelo
  (`sherpa-onnx`, `provider=cpu`) → portapapeles + Ctrl+V.
- **Panel de control en Windows** (PySide6): estado del dictado y páginas de
  Audio, Preferencias, Modelos y Diagnóstico. Una sola ventana por sesión; al
  cerrarla, el dictado sigue en la bandeja.
- **Icono de bandeja**: abre la ventana, configura micrófono y tecla, abre el
  diagnóstico o sale de Instant cerrando también el dictado.
- **Overlay de progreso**: estados por sesión (escuchando, transcribiendo,
  copiado) con animación, en Qt Quick en Windows y Tk en Linux/macOS. Nunca
  muestra el texto dictado.
- **Perfiles de vocabulario local**: cada término tiene su grafía preferida y
  las variantes que el motor suele devolver distinto. Las sustituciones son
  locales y exactas; no hay corrección difusa.
- **Emparejamiento por sonido** (opt-in con `~`): cubre las variantes que el
  motor inventa sin enumerarlas, incluidas las palabras que parte o pega
  («O en Pi» → OpenAI). Con red de seguridad para no tocar palabras corrientes.
- **Pulido LLM opcional** (apagado por defecto): con un `llama-server` local
  corrige tildes, puntuación y los signos de apertura `¿`/`¡`. Recibe texto,
  nunca audio, y se rechaza toda salida que cambie la secuencia de palabras.
- **Verificación de integridad de los modelos**: los ~670 MB de Parakeet y el
  VAD se comprueban con SHA-256 al descargar; un archivo corrupto se vuelve a
  bajar y un archivo a medias no queda en su lugar.
- **Arranque con el sistema** opcional, y una sola instancia del dictado aunque
  se abra dos veces.
- **CLI** en Linux/macOS: `instant setup`, `run`, `check` y `diagnostics`, con
  gestión de perfiles de vocabulario por flags.
- **Suite de pruebas** (143 comprobaciones) que corre en Windows, Linux y macOS
  en cada push y antes de publicar.

### Limitaciones conocidas

- **Los ejecutables no están firmados.** Windows SmartScreen va a avisar al
  usuario la primera vez; es esperable hasta que haya un certificado de firma.
- **No existe un modelo de puntuación en español** para sherpa-onnx (solo
  inglés y chino). Los signos de apertura dependen del motor y, si faltan, del
  pulido LLM.
- **Los hotwords no funcionan con Parakeet v3**: sherpa-onnx los tokeniza con
  un `bpe.vocab` de sentencepiece que el paquete del modelo no trae. Por eso las
  marcas se corrigen después del reconocimiento, no antes. Ver
  [`docs/motores.md`](docs/motores.md).
- **El corpus de evaluación era de voz sintética** y se retiró junto con la
  comparación de motores; la decisión de motor quedó documentada en
  [`docs/motores.md`](docs/motores.md).
