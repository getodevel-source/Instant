# SRS de mejoras — Instant (hold-to-talk offline ES)

Dictado local por voz en Windows: mantenés la tecla, hablás, soltás y el texto se pega. Este SRS fija qué se mejora, con qué criterio medible se da por hecho, y qué sigue sin evidencia propia.

## Lectura rápida

1. Si venís a implementar: andá a §3 (funcionales) y §7 (roadmap) — cada requisito tiene aceptación medible.
2. Si venís a verificar: §2 te dice qué está confirmado en código y qué trae [A CONFIRMAR].
3. Si venís a medir: §4 NFR-3 y §5 te dan el protocolo pendiente y los experimentos para cerrar cada incertidumbre.

> Convención: todo número que este worker no leyó él mismo en archivo o log va marcado **[A CONFIRMAR]** con su motivo. IDs de requisito `INST-R01…R11` (sin saltos); incertidumbres `INST-U01…U10` (sin saltos). `FR-`/`NFR-`/`U-` son alias cortos al mismo ID y se muestran entre paréntesis.

## 1. Alcance y contexto

Instant es dictado hold-to-talk 100% offline en español. Pipeline (ver `dictado/src/instant_app/`): mic 16 kHz (`audio.py`) → Silero VAD que corta frases (`engine.py: segment`) → Parakeet TDT v3 int8 por segmento en paralelo vía `sherpa-onnx` con `provider="cpu"` (`engine.py`) → portapapeles + Ctrl+V (`paste.py`). Config en JSON por usuario + override por env (`config.py`, `paths.py`). Comandos: `instant setup` (TUI), `instant run` (daemon `daemon.py`), `instant check` (boot rápido en `daemon.py: cmd_check`). Paquete `instant` 0.1.0 (`dictado/pyproject.toml`, entry point `instant = instant_app.__main__:main`).

Qué Instant NO es (fuera de alcance de este SRS):

| Tema | Límite |
|------|--------|
| Nube | Ningún requisito puede pedir red salvo LLM opt-in local (§4 NFR-5). `engine.py` y `audio.py` no tienen código de red. |
| GPU | `provider="cpu"` fijo en `engine.py`; CUDA no existe en el proyecto. |
| Streaming | Transcripción al soltar la tecla, no en tiempo real durante la pulsación (`daemon.py: on_release` → `_job`). |
| Multi-idioma | Solo ES; el modelo es Parakeet y el prompt LLM es ES (`llm.py: DEFAULT_SYSTEM`). |

## 2. Estado verificado vs supuesto

Leído directamente por este worker: `dictado/src/instant_app/*.py` (12 módulos), `dictado/pyproject.toml`, ambos `README.md`, los tres `.bat`, `.github/workflows/release.yml`, `dictado/tests/test_regression.py`, ambos `.gitignore`, listado de `models/` y `git status`/`ls-files` del repo. Además el director leyó `C:/Users/juans/AppData/Roaming/instant/config.json` e `instant.log` (líneas 1-37 y cola de 25) el 2026-09-25: lo que sigue [A CONFIRMAR] en esta tabla es solo filas 9, 10 y el fenómeno ES de fila 11.

| # | Afirmación | Evidencia / archivo | Estado |
|---|-----------|---------------------|--------|
| 1 | Pipeline mic→VAD→Parakeet→clipboard+Ctrl+V, CPU-only | `engine.py` (`provider="cpu"`), `audio.py`, `paste.py`, `daemon.py` | Verificado en código |
| 2 | Paquete `instant` 0.1.0, entry point `instant` | `dictado/pyproject.toml` (leído) | Verificado |
| 3 | Comandos `setup`, `run`, `check` + flags `--yes --mic --key --threads --sound/--no-sound --llm-url --no-meter --no-probe` | `__main__.py`, `setup.py: _parse_args` (leídos) | Verificado |
| 4 | `DICTADO_DATA` > `./models` (solo si tiene `parakeet-v3-int8/`) > dir por SO; env `DICTADO_*` pisa config | `paths.py: resolve_data_dir`, `config.py: load` (leídos) | Verificado en código |
| 5 | Lanzadores fijan `DICTADO_DATA` al repo solo si no viene definida; `instant-status.bat` solo diagnostica | `instant-run.bat`, `instant-setup.bat`, `instant-status.bat` (leídos) | Verificado |
| 6 | Modelos presentes en disco, fuera de git | `models/parakeet-v3-int8/` (4 archivos) + `models/silero-vad/silero_vad.onnx` (listados por este worker); `models/` en `.gitignore` raíz | Verificado |
| 7 | Daemon vivo con F9, config mic 3 / key f9 / threads 4 / sound false / max_seg 20.0 / llm_url `""` | `C:/Users/juans/AppData/Roaming/instant/config.json` (leído por director 2026-09-25: mic_index 3, key f9, threads 4, sound false, max_seg 20.0, llm_url "") | Config verificada en config.json; solo el "vivo ahora" es time-sensitive (log muestra heartbeat `vivo, esperando F9...` hasta 06:24:47 + wmic pid 19588 con instant.exe run según worker evidencia) |
| 8 | Bench 14.7 s audio → 0.64 s, RTF 0.04x | `%APPDATA%/instant/instant.log` líneas 8-15 (leído por director 2026-09-25: soltado 14.7 s, 2 segmentos, decode 0.58 s, `[14.7s audio -> 0.64s, RTF=0.04x]` 2026-09-25 05:45:03) | Verificado verbatim en log; lo no confirmado es si la voz era ES nativa (ver INST-U01) |
| 9 | `check` boot 2.4 s < 5 s | `README.md` raíz (cita corrida con fix `DICTADO_DATA`, no releída) | **[A CONFIRMAR]** — ver INST-U02 |
| 10 | Stress sintético 71.2 s → 1.03 s RTF 0.014x sin truncado por código | Misión (sin archivo leído por este worker; `dictado/tests/_stress/` está borrado del worktree, ver §6) | **[A CONFIRMAR]** — ver INST-U01 |
| 11 | Errores conocidos del modelo: nombres propios/siglas por fonética (`Instant` → `instante`) | `dictado/README.md` (leído; es documentación, sin corpus medido) | Verificado como documentación; el fenómeno en ES es [A CONFIRMAR] — ver INST-U04 |
| 12 | Workflow PyInstaller win/linux/mac sin empaquetar modelos | `.github/workflows/release.yml` (leído; comentado en el propio yml) | Verificado en archivo; build nunca corrido → INST-U07 |
| 13 | `instant.exe` existe pero no está en PATH (ruta absoluta en los `.bat`) | Existencia: worker evidencia (ls 108351 bytes + `--help` exit 0 listando setup/run/check); ausencia en PATH: `instant-run.bat` / `instant-setup.bat` (ruta `...\Python314\Scripts\instant.exe`, leída) + `README.md` troubleshooting | Existencia verificada en otra sesión; PATH-ausencia verificada en `.bat` |
| 14 | Default `%LOCALAPPDATA%/instant/models` vacío en esta máquina | `%APPDATA%/instant/instant.log` línea 37 (leída por director 2026-09-25, 06:13:23: `modelo parakeet incompleto ... %LOCALAPPDATA%/instant/models/...encoder.int8.onnx`) + `paths.py: user_data_dir` (lógica) | Verificado en log línea 37 |

## 3. Requisitos funcionales de mejora

| ID | Alias | Descripción | Criterio de aceptación medible | Prioridad |
|----|-------|-------------|--------------------------------|-----------|
| INST-R01 | FR-1 | Dictado largo 60–120 s sin truncado. El corte por `max_seg` (`engine.py: segment`) parte por energía mínima y el fallback junta todo hasta 120 s; `transcribe` une con `join_texts`. | Corpus ES de 60, 90 y 120 s: 100% de las sesiones devuelven texto no vacío, 0 sesiones cortadas por límite de código (log `segmentando...` muestra N segmentos y el texto final los cubre), RTF ≤ 0.1x en CPU referencia. Baseline actual [A CONFIRMAR] (ver INST-U01). | Alta |
| INST-R02 | FR-2 | TUI `setup` completa: descarga lo que falte (~670 MB Parakeet + ~1 MB VAD), elige mic con medidor, tecla, hilos, URL LLM, y cierra con probe + warmup (`setup.py: cmd_setup`). | `instant setup --yes --no-probe` con modelos presentes sale 0 y guarda `config.json`; sin modelos sale 2 avisando y sin traceback; sin mic sale 2 sin crashear; `--mic` inválido cae al default con aviso (comportamiento ya codificado en `setup.py`, a fijar con test de humo). | Alta |
| INST-R03 | FR-3 | Comando `check`: valida tecla + mic probe + warmup de modelos e informa boot (`daemon.py: cmd_check`). | `instant check` sale 0 e imprime `boot mic+warmup: Xs (OK <5s)` con X < 5 en máquina referencia; sin modelos sale 2 con `SIN MODELOS`. Valor 2.4 s citado [A CONFIRMAR] (ver INST-U02). | Alta |
| INST-R04 | FR-4 | Pulido LLM opt-in: corrige tildes/puntuación vía `llama-server` local; apagado por defecto (`llm_url: ""`); si falla, devuelve el crudo (`llm.py: maybe_polish`). | `llm_url` vacío → byte-idéntico (ya cubierto en `dictado/tests/test_regression.py`); server caído (`http://127.0.0.1:9`) → crudo sin excepción (ya cubierto); server real → mejora tildes/puntuación en corpus ES sin cambiar palabras (protocolo pendiente, ver INST-U08). Sin regresión de latencia cuando está off. | Media |
| INST-R05 | FR-5 | Lanzadores Windows con `DICTADO_DATA`: `instant-run.bat` / `instant-setup.bat` fijan la var al repo solo si no viene definida, con fallback a `python -m instant_app` (`instant-status.bat` diagnostica sin levantar nada). | Con `DICTADO_DATA` indefinida, el `.bat` la fija y `instant-run.bat check` sale 0; con var predefinida la respeta (no la pisa); `instant-status.bat` reporta proceso/var/log/config sin levantar el daemon. Rutas absolutas actuales son de una máquina (`C:/PROYECTOS/Instant`, `C:\Users\juans\...`): hacerlas relativas al repo antes de distribuir. | Alta |
| INST-R06 | FR-6 | Release por SO: workflow build PyInstaller win/linux/mac al pushear tag `v*`, sin empaquetar modelos (se descargan en primer `setup`) (`.github/workflows/release.yml`). | Workflow verde en CI en los 3 SO y cada artefacto corre su `check --help` con exit 0. Hoy nunca corrió ([A CONFIRMAR] ver INST-U07); hasta entonces distribuir es solo `pip install -e dictado`. | Baja |

## 4. Requisitos no funcionales

| ID | Alias | Descripción | Criterio medible |
|----|-------|-------------|------------------|
| INST-R07 | NFR-1 | CPU-only siempre. | `grep provider` en `engine.py` muestra solo `cpu`; el daemon corre en máquina sin GPU ni CUDA y transcribe; ningún requisito futuro puede pedir GPU. |
| INST-R08 | NFR-2 | Latencia: RTF ≤ 0.1x en dictado real, boot < 5 s. | RTF = tiempo decode / duración audio en log (`daemon.py: _job` lo imprime como `RTF=`); 5 dictados reales ES ≥ 30 s con RTF ≤ 0.1x; `instant check` < 5 s. Baselines citados (0.04x, 0.014x, 2.4 s) [A CONFIRMAR] (INST-U01/U02). |
| INST-R09 | NFR-3 | Precisión ES sin WER formal aún: definir protocolo de medición con corpus ES nativo. | Protocolo: corpus ≥ 20 muestras ES rioplatense (varias voces, con nombres propios y siglas), referencia transcripta a mano, WER = (S+D+I)/N con `jiwer` o script propio versionado en `dictado/tests/`; objetivo inicial: WER mediano ≤ 15% en habla limpia (umbral a ajustar tras primera medición). Hasta medirlo, toda cifra de precisión va [A CONFIRMAR]. |
| INST-R10 | NFR-4 | Robustez: sin modelos o sin mic no crashea. | `setup` sin red/mic: exit 2 con aviso, 0 tracebacks (`setup.py` ya lo implementa); `run` sin modelos: exit 2 con `corre instant setup primero` (`__main__.py`); `check` sin modelos: exit 2. Fijar con corrida de humo en cada fase (§7). |
| INST-R11 | NFR-5 | Privacidad: 100% local salvo LLM opt-in documentado. | Con `llm_url` vacío, `maybe_polish` retorna idéntico sin abrir socket (early-return en `llm.py:59-61`, cubierto en `dictado/tests/test_regression.py`); con URL caída devuelve crudo con warning. Con LLM configurado, el único destino es el host documentado en `dictado/README.md` §Pulido LLM. `models.py` solo descarga en `setup`, nunca en `run`. |

## 5. Incertidumbres abiertas

| ID | Alias | Incertidumbre | Impacto | Experimento para cerrarla | Dueño sugerido |
|----|-------|---------------|---------|---------------------------|----------------|
| INST-U01 | U-1 | Bench confirmado en log pero voz sin caracterizar: el 14.7 s → 0.64 s RTF 0.04x SÍ está verificado verbatim en `instant.log` líneas 8-15 (el texto es ES pero la voz no está caracterizada: podría ser SAPI EN u otra fuente); el stress sintético 71.2 s → 1.03 s RTF 0.014x sigue [A CONFIRMAR] (sin archivo). | Sin baseline de voz ES nativa no se puede afirmar RTF ni calidad en el idioma real. | Grabar 5 dictados ES con voz nativa (10/30/60/90/120 s, mic DGM20), correr `instant-run.bat`, extraer `RTF=` del log `%APPDATA%/instant/instant.log` y tabular contra el bench 14.7 s ya confirmado. | Usuario (graba) + worker (tabula) |
| INST-U02 | U-2 | Pulsación física F9 sostenida real: el boot 2.4 s citado es `check`, no una sesión hold-to-talk completa con grabación + VAD + pegado. | El path real (polling `GetAsyncKeyState` + `sounddevice` callback + `_job`) puede tener latencias que `check` no ve. | Sesión real: mantener F9 60 s dictando, soltar, medir tiempo hasta pegado y confirmar texto en la app foco; repetir 3 veces. | Usuario |
| INST-U03 | U-3 | WER formal con corpus: no existe medición. | Toda afirmación de precisión es anecdótica. | Aplicar protocolo de INST-R09: armar corpus, transcribir referencias, correr y publicar WER. | Worker (scripts) + usuario (voces) |
| INST-U04 | U-4 | Nombres propios/siglas (`Instant`→`instante`, anglicismos por fonética). | Afecta nombres de producto, clientes y siglas en dictado laboral. | Corpus de 20 frases con nombres/siglas ES + EN; medir tasa de acierto antes/después del pulido LLM; decidir lista de reemplazos solo si el LLM no lo resuelve. | Worker |
| INST-U05 | U-5 | Concurrencia con IA local (RAM/CPU al 100%): Parakeet + otra IA local peleando hilos. | Degrada RTF y puede entrecortar captura. | Correr dictado 60 s con carga sintética (`threads` al máximo en otra tarea) y comparar RTF vs baseline; probar `threads` 2/4/8. | Worker |
| INST-U06 | U-6 | Wayland/macOS/Linux sin verificar: pegado (`xdotool` no anda en Wayland) y hotkey (`pynput` requiere X) solo documentados. | FR-6 promete 3 SO sin evidencia en 2 de ellos. | En cada SO: `pip install -e dictado` + `instant check` + sesión real de 30 s; registrar pass/fail de hotkey y pegado. | Usuario (tiene las máquinas) |
| INST-U07 | U-7 | Build PyInstaller nunca corrido: el workflow existe pero jamás tuvo run verde. | El release puede fallar por hidden-imports o tamaño. | Pushear tag de prueba (el workflow dispara solo con tags `v*`, p.ej. `v0.0.0-test`) y ver los 3 artefactos; si falla, iterar `--hidden-import`/`--collect-all`. | Worker |
| INST-U08 | U-8 | `llm_url` sin server real probado: solo hay test con server caído (devuelve crudo). | FR-4 promete mejora de tildes sin evidencia. | Levantar `llama-server` local, configurar URL, dictar 10 frases sin tildes y comparar antes/después. | Usuario (server) + worker (corpus) |
| INST-U09 | U-9 | ✅ CERRADA 2026-09-25: remote configurado — `origin https://github.com/getodevel-source/Instant.git`, `main` pusheado hasta `e7d4ba4` (verificado con `git remote -v` + `git log --oneline`). | Era bloqueo de FR-6; ya no bloquea. | PENDIENTE restante: pushear tag `v*` de prueba y verificar Actions + 3 artefactos (ver U-07). | Worker (tag) |
| INST-U10 | U-10 | Resolvedor `DICTADO_DATA` vs cwd `./models`: si el cwd tiene `models/parakeet-v3-int8/` lo prefiere sobre el user dir (`paths.py: resolve_data_dir`). | Correr `instant` desde un cwd ajeno con `models/` parcial puede resolver modelos inesperados. | Test: cwd con `models/` vacío vs completo, con y sin `DICTADO_DATA`; documentar precedencia efectiva en `dictado/README.md`. | Worker |

## 6. Deuda técnica conocida

| Ítem | Detalle | Acción |
|------|---------|--------|
| `__pycache__/` | `dictado/src/instant_app/__pycache__/` con 13 `.pyc` (listado por este worker). Ignorado en ambos `.gitignore`, no trackeado. | Nada en git; borrar local si molesta (`__pycache__/` se regenera). |
| `egg-info` | `dictado/src/instant.egg-info/` (6 archivos, visto por este worker; viene de `pip install -e dictado`). Ignorado por `.gitignore`, no trackeado. | Nada; no commitear. |
| `_stress` residual | `dictado/tests/_stress/` (8 archivos p1–p4 `.ps1`/`.wav`) sigue trackeado en git pero fue borrado del worktree (`git status` muestra 8 `D`). | Decidir: `git rm` si era material descartable, o restaurar si es el corpus del stress citado [A CONFIRMAR]. |
| `models/` fuera de git | `models/` ignorado raíz; ~640 MB + VAD solo en disco local. | Mantener; el release los descarga en `setup` (`models.py`). Riesgo: máquina nueva sin red no anda. |
| `instant.exe` fuera de PATH | Existencia verificada en otra sesión (ls 108351 bytes + `--help` exit 0); los `.bat` usan ruta absoluta de una máquina (`C:\Users\juans\AppData\Roaming\Python\Python314\Scripts\instant.exe`). | Hacer los `.bat` relativos al repo o documentar PATH; hoy solo andan en la máquina original. |
| Default `%LOCALAPPDATA%` vacío | Verificado en log línea 37 (06:13:23: el exe buscó `%LOCALAPPDATA%/instant/models/...encoder.int8.onnx` sin `DICTADO_DATA`); lógica en `paths.py: user_data_dir`. | Lo cubre FR-5 (los `.bat` fijan la var); a largo plazo, que `setup` instale ahí por defecto. |

## 7. Roadmap propuesto en 3 fases

**Fase 1 — Estabilizar** (cierra FR-2, FR-3, FR-5 + NFR-4).

- Hacer relativos los `.bat` al repo; humo: `check` sale 0 con y sin `DICTADO_DATA` predefinida.
- Humo robustez: `setup` sin mic / sin modelos → exit 2, 0 tracebacks.
- Resolver `_stress`: `git rm` o restaurar + documentar.
- Exit: `instant check` < 5 s, `setup --yes` 0, `git status` limpio, sin paths absolutos de una máquina en los `.bat`.

**Fase 2 — Medir** (cierra U-01…U-05, U-08, U-10 + NFR-2, NFR-3, FR-1, FR-4).

- Benches ES nativos 10–120 s + tabla RTF real (U-01, U-02).
- Corpus ES + primera medición WER y nombres propios, con/sin LLM (U-03, U-04, U-08).
- Prueba bajo carga CPU + matriz `threads` (U-05); test de precedencia `DICTADO_DATA` vs cwd (U-10).
- Exit: RTF ≤ 0.1x demostrado en ES, WER mediano publicado, FR-1 aceptado en 120 s, FR-4 aceptado o recortado a “no mejora, se documenta”.

**Fase 3 — Distribuir** (cierra FR-6 + U-06, U-07, U-09).

- Remote + push LISTOS (U-09 cerrada: `origin` + `main` hasta `e7d4ba4`); correr workflow en tag de prueba (U-07).
- Verificar `check` + sesión 30 s en Linux X11, Wayland (documentar límite), macOS (U-06).
- Exit: 3 artefactos verdes que corren `check`, matriz SO con pass/fail de hotkey+pegado, release `v0.1.0` publicado sin modelos empaquetados.

## 8. Trazabilidad: requisito → archivo(s)

| Requisito | Archivo(s) que lo implementan |
|-----------|-------------------------------|
| INST-R01 (FR-1) | `dictado/src/instant_app/engine.py` (`segment`, `transcribe`, `join_texts`, `merge_short_bounds`), `dictado/src/instant_app/daemon.py` (`_job`, `_record`) |
| INST-R02 (FR-2) | `dictado/src/instant_app/setup.py` (`cmd_setup`), `dictado/src/instant_app/models.py` (`download_models`, `check`), `dictado/src/instant_app/audio.py` (`peak_meter`, `probe`), `dictado/src/instant_app/__main__.py` (forward de flags) |
| INST-R03 (FR-3) | `dictado/src/instant_app/daemon.py` (`cmd_check`), `dictado/src/instant_app/__main__.py` (subparser `check`) |
| INST-R04 (FR-4) | `dictado/src/instant_app/llm.py` (`maybe_polish`, `polish`, `resolve_url`), `dictado/src/instant_app/daemon.py` (`_job` lo llama), `dictado/src/instant_app/config.py` (`llm_url`), `dictado/tests/test_regression.py` (off/caído) |
| INST-R05 (FR-5) | `instant-run.bat`, `instant-setup.bat`, `instant-status.bat`, `dictado/src/instant_app/paths.py` (`resolve_data_dir`) |
| INST-R06 (FR-6) | `.github/workflows/release.yml`, `dictado/pyproject.toml`, `dictado/src/instant_app/models.py` (descarga en primer arranque) |
| INST-R07 (NFR-1) | `dictado/src/instant_app/engine.py` (`provider="cpu"`) |
| INST-R08 (NFR-2) | `dictado/src/instant_app/daemon.py` (log `RTF=`), `dictado/src/instant_app/daemon.py: cmd_check` (boot) |
| INST-R09 (NFR-3) | Pendiente: corpus + script en `dictado/tests/` (hoy solo `test_regression.py` sin WER) |
| INST-R10 (NFR-4) | `dictado/src/instant_app/setup.py` (avisa y sigue), `dictado/src/instant_app/__main__.py` (exit 2), `dictado/src/instant_app/daemon.py: cmd_check` |
| INST-R11 (NFR-5) | `dictado/src/instant_app/llm.py` (off por defecto), `dictado/src/instant_app/config.py` (`llm_url: ""`), `dictado/README.md` (§Pulido LLM), `dictado/src/instant_app/models.py` (red solo en `setup`) |
