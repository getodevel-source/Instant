# Changelog

Formato basado en [Keep a Changelog](https://keepachangelog.com/es-ES/1.1.0/).
El proyecto usa [versionado semántico](https://semver.org/lang/es/).

## [Sin publicar]

Todavía no hay una versión publicada. El primer release será `0.1.0` y se
publica tageando `v0.1.0`: el workflow construye los binarios de los tres
sistemas y los adjunta al release, pero solo después de que la suite pase en
Windows, Linux y macOS.

### Cambiado

- **Interfaz más minimalista y prolija.** Los colores pasan a una sola fuente de
  verdad (`branding.PALETTE`) y las medidas, la tipografía y los tiempos de
  animación a `theme.py`, que arma la hoja de estilo: un cambio de marca ya no
  hay que perseguirlo por los archivos. La ventana gana marca en la barra
  lateral, encabezado con el nombre de la página, tarjetas y controles más
  aireados, y cada página tiene scroll, así que nada queda cortado al achicar.
- **La pastilla flotante sigue a la marca.** La transcripción deja el violeta
  por un cian de la misma familia que el verde agua; escuchar se anima con una
  onda fina y transcribir con un arco que barre sobre una guía tenue, en lugar
  de los ocho puntos. La pastilla es más chica, tiene sombra suave, entrada
  animada y los avisos se ajustan al largo del texto.
- El overlay Tk de Linux/macOS usa la misma paleta que el resto de la aplicación
  y el giro se apaga hacia el fondo en vez de cambiar de color.
- **Segunda pasada minimalista iOS.** La barra lateral se afina, los botones
  pierden el borde lateral y quedan en pastilla, los pesos tipográficos bajan
  de 700 a 500/600, la portada y las tarjetas respiran con más aire y el Inicio
  cambia la segunda tarjeta por una línea de estado tenue: era mucho cromo
  para dos datos.
- **La animación del dictado respira con tu voz y se ve nítida.** La onda del
  overlay pasa de 7 a 9 barras y el daemon le manda el nivel real del micrófono
  (~12 Hz): en silencio respira bajito, al hablar crece hasta ~1.6x, el anillo
  se expande y la pastilla vibra apenas. Además hay multisampleo (`layer
  samples 4`) en pastilla, micrófono, tilde y arcos, trazos un poco más
  gruesos, sombra de cinco pasos y textos en render nativo: se acabó lo
  pixelado en movimiento. El fallback Tk hace lo mismo a su escala.
- **Icono propio en la barra de tareas.** La ventana fijaba su icono pero
  Windows la agrupaba bajo Python (`pythonw.exe`); ahora declara su
  `AppUserModelID` y el icono de Instant aparece en la barra.
- **Ventana compacta de verdad.** Ancho total menor, barra de 188 px, portada
  fina (de ~210 a ~150 px) y las dos tarjetas de tecla/arranque fusionadas en
  una sola «General»: menos cajas para las mismas cuatro páginas.
- **El dictado aparece y se despide.** La pastilla nace creciendo con fade
  (escala + opacidad) y al terminar se achica con fade antes de esconderse, en
  espejo. Además vive **fija abajo al centro** de la pantalla, estilo asistente
  de voz: siempre en el mismo lugar, sin perseguir al cursor ni tapar el campo
  donde se escribe. El fallback Tk también centra abajo y funde entrada/salida
  con el alfa de la ventana.
- **Animación del dictado más expresiva.** La entrada nace con pop suave
  (escala desde 0.82 con leve sobreimpulso + fundido) y la salida se despide
  igual, en espejo. La onda en silencio apenas respira y al hablar se estira
  hasta ~1.7x con respuesta más rápida (nivel cada 60 ms, ganancia 5x); el
  anillo y la pastilla acompañan con más amplitud. El giro de transcripción
  gana trazo grueso, vuelta más rápida (900 ms) y un pulso central que marca
  que está pensando.
- **La pastilla respeta tu monitor de trabajo.** Sigue fija abajo al centro,
  pero del monitor donde está el cursor (el campo que dictás), no siempre del
  principal. Misma posición relativa, pantalla correcta.
- **Onda más sensible.** Nivel cada 50 ms con ganancia 6x: en silencio apenas
  respira (base 0.35x) y al hablar se estira hasta ~1.85x, con anillo,
  pastilla y brillo acompañando con más amplitud.
- **La onda ahora es un analizador de espectro real.** El daemon calcula por
  FFT la energía en 9 bandas logarítmicas (80 Hz..7.5 kHz) con techo
  adaptativo por banda: se autoajusta a tu mic y tu distancia, así hables
  bajito o fuerte la onda usa todo el rango. Cantá grave y se mueven las
  barras del centro; silbá agudo y saltan las de los bordes. Verificado con
  tonos sintéticos (150 Hz vs 4 kHz) y silencio en cero.
- **Fidelidad total.** Dos causas del movimiento raro, corregidas: en silencio
  se mandaban bandas normalizadas contra un techo colapsado (bailaba solo) —
  ahora por debajo del piso medido (0.006) se mandan ceros; y el reposo se
  aplana solo por barra (1-2 px) en vez de oscilar a 10 px. Además el espectro
  usa una ventana corrediza de ~60 ms (los bloques son de 10 ms y no resolvían
  graves) y la puerta de silencio se calibró contra el mic real.
- **Aparición con elevación.** La pastilla nace 14 px abajo y sube con el
  pop+fundido, y al terminar se va bajando 12 px mientras se achica y se
  funde. Mismo tratamiento en el fallback Tk (deslizamiento + alfa).
- **Transiciones que sí se ven.** Entrada más marcada (22 px en 500 ms con
  sobreimpulso estilo spring + fundido de 300 ms) y salida alargada a 300 ms
  con 18 px de recorrido: las salidas de 150-200 ms se sienten pero no se ven.
- **Gesto firma.** La entrada sube 34 px en 600 ms con un anillo que se
  expande una sola vez; la salida baja 26 px en 350 ms.
- **La despedida sí se ve ahora (dos bugs).** La ventana se fundía por su
  cuenta en 170 ms y tapaba la salida de 350 ms: parecía que desaparecía de
  golpe. Ahora solo la pastilla se funde. Además el ping nunca llegaba a
  mostrarse (un `PropertyAction` dentro de un paralelo se aplica al inicio):
  pasó a secuencia y se verificó con muestreo temporal — entrada y 34→0 con
  opacidad 0→1 y ping visible que se oculta; salida y 0→26 con fundido.
- **Cinco gestos premium.** Morph onda→tilde (la marca nace con sobreimpulso
  y el texto entra con fundido); ripple verde de confirmación al pegar;
  resplandor que respira con tu volumen; insignia de tecla que se aprieta
  mientras la mantenés; giro de transcripción con doble estela. Además el pop
  de la pastilla ahora crece desde el centro (origen de transformación).
  Criterio Apple HIG: entrar con ease-out, salir con ease-in, y que la
  despedida dure lo suficiente para registrarse.
- **Gesto firma: ping de aparición y despedida marcada.** La entrada sube
  34 px en 600 ms con un anillo que se expande una sola vez; la salida baja
  26 px en 350 ms. Recorridos y tiempos que no se pueden perder.
- **Criterio high-end: menos gestos, un solo lenguaje.** Se retiraron el ping,
  el ripple, el resplandor, las estelas, el squash de la tecla y los
  sobreimpulsos: juntos hacían ruido. Quedó un sistema coherente con curva
  bezier propia (0.32, 0.72, 0, 1) —entrada y tilde—, onda de voz como única
  protagonista, giro de un solo arco y salida en espejo. Origen de escala al
  centro.
- **Auditoría visual con capturas reales.** Se montó render offscreen de las
  4 páginas y se corrigió lo hallado: el texto de "Reiniciar con cambios" se
  recortaba (botón más alto con más padding y texto acortado a "Reiniciar"),
  se quitaron los subtítulos del encabezado (duplicaban la página), el
  subtítulo de la tarjeta de micrófono y se acortó "Probar 3 s" a "Probar".
  La portada creció a 160–196 px para que entren los dos botones sin
  apreturas. Se conserva todo texto funcional o exigido por tests.
- **Alternativa Orbital desde cero.** Segundo diseño del overlay con lenguaje
  propio (orbe concéntrico: tres anillos de graves/medios/agudos + núcleo que
  late, sin barras) sobre el mismo motor de voz real y la misma paleta
  (cubierta por tests). Se elige con `overlay_style: classic|orbital` en la
  config (o `DICTADO_OVERLAY`) y la actual queda intacta como default.
- **Orbital sin textos.** Fuera la insignia de tecla y el "Copiado": el gesto
  confirma, no hace falta escribirlo. Solo quedan los avisos de error, que
  son funcionales (sin ellos nunca sabrías por qué no se pegó nada).
- **Transiciones más ágiles.** Entrada 600→420 ms y salida 380→280 ms con el
  mismo idioma (bezier propia, recorridos intactos). El fallback Tk acompaña
  con pasos más grandes.
- **Calma premium.** Se retiró el pop por sílaba y se contuvieron todos los
  recorridos (entrada 24 px/380 ms, salida 24 px/260 ms, onda con tope 32 px,
  anillo y pastilla con gestos mínimos). La voz y el tono siguen reales, pero
  la pastilla susurra en vez de actuar.
- **La onda tiene tono.** El daemon estima tu tono por
  autocorrelación (verificado: 120 Hz→0.25, 220 Hz→0.63, 350 Hz→0.91) y tiñe
  la onda dentro de la familia de marca (verde agua→hielo). El micro-pop por
  sílaba se probó y se retiró en la pasada de calma.
- **Una sola pantalla.** Se eliminaron la barra lateral y las 4 páginas: todo
  (estado, micrófono, tecla, vocabulario, modelos, guardar) en una columna
  centrada con scroll. Los modelos quedaron en una línea sin sección y el
  Diagnóstico subió al encabezado. Navegar a una sección hace scroll.
- **Vocabulario en tabla.** Chau texto crudo con tabuladores: cada término es
  una fila con Término, Así se escucha (| separa variantes), Sonido ≈ y ✕,
  más botón de añadir. Misma semántica (incluido el `~` de sonido) y mismo
  guardado; el formato viejo sigue entendiéndose al cargar.
- **Robustez de tests Qt.** La tabla emite señales al destruirse: se
  desconecta en `closeEvent` y los tests destruyen ventanas con `del` +
  colecta explícita fuera de los pumps (el GC cíclico a mitad de pump
  abortaba Qt en offscreen).
- **Sin alturas fijas frágiles.** La portada ya no tiene altura máxima (a
  150 % de escala o ventana angosta el título ocupa dos líneas y nada se
  recorta), la insignia de tecla tampoco, y las filas de la tabla se
  autoajustan. Auditoría con capturas a 100 % y 150 %.
- **Apaisado de dos columnas.** La página ocupa todo el ancho: héroe arriba y
  dos columnas debajo (izquierda ajustes, derecha vocabulario ancho). Ventana
  inicial 1200×720, mínima 1000×640. Adiós columna chata.
- **Viewport que no se rompe al redimensionar.** El scroll es la ventana
  directo, sin envoltorios: antes el contenido quedaba en negro tras
  redimensionar. Verificado con stress de tamaños.
- **Vocabulario que no se rompe ni se pierde.** La tabla crece con las filas
  (hasta ~7 visibles), añadir enfoca y lleva a la fila nueva, y cada Guardar
  respalda la config anterior (`config.json.bak`).
- **Minimalismo pedido.** Diagnóstico fantasma abajo centrado; combos que no
  cambian con la rueda; interruptores pill; la voz sin nombres; sin campo LLM
  (vive en config/CLI); sin pastilla verde ni textos de estado; fila de
  modelos solo si falta descargar; ✕ circular con aire.
- **Sonido ≈ explícito.** La columna Sonido deja el pill sin perilla por un
  botón ≈: tenue apagado, teal encendido. Sin ambigüedad.
- **La ✕ con aire de verdad.** El margen interno del viewport recortaba el
  área pintable (él cortaba la cruz); se quitó y la columna tiene ancho fijo
  con aire. Verificado con zoom al píxel.
- **Columnas blindadas.** Sonido (78) y ✕ (62) con ancho fijo: ningún ajuste
  las puede apretar ni recortar, ni al mínimo de ventana.
- **Siete pedidos de minimalismo.** Diagnóstico fantasma sutil; la rueda ya no
  cambia los combos (scrollea la página); arranque y Sonido con interruptor
  pill; sin nombres de modelos en la UI ("la voz"); sin campo de LLM visible
  (vive en config/CLI); fuera la pastilla verde (solo un punto de estado); ✕
  circular para quitar términos.
- **Botones de vocabulario rehechos.** El pill `≈` y la `✕` se recortaban
  arriba/abajo (`resizeRowsToContents` dejaba filas más bajas que el botón y la
  fuente desbordaba) y la `✕` mostraba un cuadrado detrás (el envoltorio
  heredaba el fondo global de `QWidget`). Ahora: filas de 46 px mínimo
  garantizado, botones 30/28 px con fuentes contenidas, envoltorios
  transparentes y sin foco visible. Verificado con tests Qt y captura real.
- **Overlay Orbital afinado.** Velo y escenario traslúcidos (se notan también
  en fondos oscuros), voz contenida en dos pasadas, núcleo más chico, flash de
  despedida eliminado (mic/anillos/tilde ya no reaparecen en `idle`),
  composición global con `compositionScale` (0.56) y pastilla 16 px más abajo
  (`_OVERLAY_BOTTOM_GAP` 60). Arco de transcripción apenas más nítido; el
  movimiento (entrada/salida/tilde/giro) intacto.
- **`instant-run.bat` ya no confunde la ventana con el daemon.** Su chequeo de
  duplicados matcheaba cualquier `pythonw` con "instant" (incluida la ventana
  de ajustes) y se negaba a arrancar; ahora solo mira `instant_app run`.
- **Actualización desde GitHub sin hacerlo a mano.** `instant update`
  consulta el último release y compara versiones; con `--download` baja el
  asset y lo verifica por SHA256 (sidecar `.sha256` publicado por el
  release). `instant-update.bat` frena todo, respalda el exe anterior y lo
  cambia. La ventana trae «Buscar actualizaciones» al lado de Diagnóstico.
  Sin sidecar no hay instalación. El workflow valida versión==tag y publica
  los hashes.

### Corregido

- **Dictado más consistente ante cortes del VAD.** La inferencia sobre el
  recognizer compartido se serializa (el decode concurrente producía vacíos
  intermitentes), los segmentos de menos de 1.5 s se fusionan con su vecino
  y todo segmento vacío con audio fuerte se reintenta con ±1 s de contexto,
  con último intento sobre el audio completo. Solo actúa en la vía de fallo:
  sin vacíos no hay decodes extra.
- **Primeras palabras menos recortadas.** El VAD arranca con 0.20 s de voz
  (antes 0.25 s) y el padding por segmento sube a 0.3 s (ajustable con
  `vad_pad` en config). El log ahora muestra los cortes, el pico y la
  duración por segmento, y la latencia de apertura del micrófono.
- **Cola del dictado completa.** Al soltar la tecla se esperan hasta 0.3 s
  drenando la cola antes de cerrar el stream: lo que ya estaba en los buffers
  de audio se perdía aunque estuviera grabado.
- **Takes bajitos al mismo nivel.** Cada segmento con voz pero RMS menor a
  0.03 se normaliza hasta RMS 0.06 (tope 8x, solo boost, con `g=` en el log):
  hablar bajito o lejos ya no cambia la hipótesis.
- **El inicio ya no depende de abrir el micrófono.** Captura continua con
  pre-roll de ~0.45 s: un solo stream abierto toda la sesión, cada dictado
  arranca con lo ya grabado. Si el stream muere, cae al one-shot de siempre.
- **Fallos guardados para medir (opt-in).** Con `DICTADO_SAVE_WAVS=<carpeta>`,
  cada audio que el modelo deja vacío se guarda con su meta (duración, pico,
  cortes): corpus de voz real para dejar de suponer. Tope 50 archivos.
- **Vocabulario visible.** Cada sustitución del perfil queda en el log
  (`vocab: '...' -> '...'`), para armar el perfil con evidencia.

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
