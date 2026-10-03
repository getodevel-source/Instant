import QtQuick
import QtQuick.Shapes
import QtQuick.Window

/* Orbital: alternativa al pastilla flotante, diseñada desde cero.
   Lenguaje distinto (orbe circular concéntrico en vez de pastilla con
   barras), mismo contrato con el daemon: mode, message, messageColor,
   keyLabel, level, bandLevels, pitch. La paleta repite
   instant_app/branding.py como overlay.qml (tests/test_overlay_palette.py
   cubre ambos archivos). */
Window {
    id: orbital
    title: "Instant overlay"

    readonly property int shadowMargin: 12

    property string mode: "idle"
    property string message: ""
    property color messageColor: "#f2c36a"
    property string keyLabel: "F9"
    property string previousMode: ""

    // Voz real del daemon: nivel global, espectro y tono. Gesto contenido y
    // sedoso: el nivel se suaviza en 90 ms y los anillos/núcleo acompañan
    // sin saltos.
    property real level: 0
    Behavior on level { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
    property var bandLevels: [0, 0, 0, 0, 0, 0, 0, 0, 0]
    property real pitch: 0.5
    Behavior on pitch { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }

    readonly property bool feedback: mode === "error" || mode === "notice"
    // Modos con animación viva: anillos y núcleo solo existen acá. En idle
    // (incluida la despedida) se ocultan para que el éxito no "rebote" a la
    // animación por unos frames al expirar.
    readonly property bool active: mode === "starting" || mode === "listening"
        || mode === "processing"
    // Escala global de la composición (1 = tamaño original). La ventana sigue
    // igual; todo el orbe se dibuja más chico y centrado. Un solo número
    // para ajustar el tamaño sin romper proporciones.
    readonly property real compositionScale: 0.56
    readonly property int orbSize: feedback ? 0 : 200
    width: (feedback ? 384 : 200) + shadowMargin * 2
    height: (feedback ? 150 : 200) + shadowMargin * 2
    color: "transparent"
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
    visible: false
    opacity: 1

    // Tokens de marca (espejo de branding.PALETTE).
    readonly property color brandAccent: "#55d5c8"
    readonly property color brandWorking: "#8fd7e8"
    readonly property color brandGreen: "#7cdda6"
    readonly property color brandAmber: "#f2c36a"
    readonly property color brandRed: "#ff908b"
    readonly property color ink: "#eaf3f4"
    readonly property color inkDim: "#9db0b6"
    readonly property color glassTop: "#1b2b34"
    readonly property color glassBottom: "#0f1c23"

    readonly property color accent: mode === "processing" ? brandWorking
                                  : mode === "error" ? brandRed
                                  : mode === "notice" ? brandAmber
                                  : mode === "success" ? brandGreen : brandAccent

    readonly property color voiceHi: Qt.hsla(0.47 + pitch * 0.07, 0.50, 0.74, 1)
    readonly property color voiceLo: Qt.hsla(0.47 + pitch * 0.07, 0.62, 0.58, 1)

    function tint(color, alpha) {
        return Qt.rgba(color.r, color.g, color.b, alpha)
    }

    function bandAvg(from, to) {
        if (bandLevels.length < 9 || to <= from)
            return 0
        var sum = 0
        for (var i = from; i < to && i < bandLevels.length; i++)
            sum += Math.min(1, Math.max(0, bandLevels[i]))
        return sum / (to - from)
    }

    Behavior on width { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }
    Behavior on height { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }

    onModeChanged: {
        if (mode === "idle") {
            departure.restart()
            delayedHide.restart()
        } else {
            visible = true
            delayedHide.stop()
            departure.stop()
            if (previousMode === "idle" || previousMode === "")
                entrance.restart()
            if (mode === "success")
                checkPop.restart()
        }
        previousMode = mode
    }

    Timer {
        id: delayedHide
        interval: 300
        onTriggered: if (orbital.mode === "idle") orbital.visible = false
    }

    // Entrada: UN solo gesto con la bezier de la casa.
    ParallelAnimation {
        id: entrance
        NumberAnimation {
            target: stage; property: "scale"
            from: orbital.compositionScale * 0.92; to: orbital.compositionScale; duration: 380
            easing.type: Easing.BezierSpline
            easing.bezierCurve: [0.32, 0.72, 0, 1]
        }
        NumberAnimation {
            target: stage; property: "opacity"
            from: 0; to: 1; duration: 240; easing.type: Easing.OutCubic
        }
        NumberAnimation {
            target: stage; property: "y"
            from: 24; to: 0; duration: 380
            easing.type: Easing.BezierSpline
            easing.bezierCurve: [0.32, 0.72, 0, 1]
        }
    }

    // Salida en espejo.
    ParallelAnimation {
        id: departure
        NumberAnimation {
            target: stage; property: "scale"
            to: orbital.compositionScale * 0.94; duration: 260; easing.type: Easing.InCubic
        }
        NumberAnimation {
            target: stage; property: "opacity"
            to: 0; duration: 220; easing.type: Easing.InCubic
        }
        NumberAnimation {
            target: stage; property: "y"
            to: 24; duration: 260; easing.type: Easing.InCubic
        }
    }

    // Pop del tilde con la curva de la casa. Sin texto de confirmación:
    // el tilde ES la confirmación (minimalismo: nada decorativo escrito).
    ParallelAnimation {
        id: checkPop
        NumberAnimation {
            target: checkGlyph; property: "scale"
            from: 0.85; to: 1; duration: 260
            easing.type: Easing.BezierSpline
            easing.bezierCurve: [0.32, 0.72, 0, 1]
        }
        NumberAnimation {
            target: checkGlyph; property: "opacity"
            from: 0; to: 1; duration: 200; easing.type: Easing.OutCubic
        }
    }

    Item {
        id: stage
        anchors.fill: parent
        transformOrigin: Item.Center
        scale: orbital.compositionScale

        // Velo de fondo: halo apenas más grande que la composición, con el
        // vidrio de la marca a baja alfa. Sin el velo a sangre completa: la
        // huella se achica y un glitch de composición se lee como sombra.
        Rectangle {
            anchors.fill: parent
            anchors.margins: 26
            radius: 24
            antialiasing: true
            color: orbital.tint(orbital.glassBottom, 0.38)
        }

        // Sombra suave del orbe.
        Rectangle {
            anchors.centerIn: parent
            width: 120; height: 120
            radius: 60
            color: Qt.rgba(0, 0, 0, 0.25)
            visible: !orbital.feedback
        }

        // Escenario: fondito traslúcido detrás de los anillos. Les da
        // contraste en cualquier fondo, también en los oscuros.
        Rectangle {
            anchors.centerIn: parent
            width: 170; height: 170
            radius: 85
            antialiasing: true
            color: orbital.tint(orbital.glassTop, 0.35)
            border.width: 1
            border.color: orbital.tint(orbital.ink, 0.05)
            visible: !orbital.feedback
        }

        // Tres anillos: graves, medios y agudos de verdad.
        Repeater {
            model: [
                { base: 30, alpha: 0.55, lo: 0, hi: 3 },
                { base: 44, alpha: 0.38, lo: 3, hi: 6 },
                { base: 58, alpha: 0.24, lo: 6, hi: 9 }
            ]
            delegate: Rectangle {
                anchors.centerIn: parent
                width: (modelData.base + orbital.bandAvg(modelData.lo, modelData.hi) * 15) * 2
                height: width
                radius: width / 2
                antialiasing: true
                visible: orbital.active
                color: "transparent"
                border.width: index === 0 ? 2 : 1.5
                border.color: orbital.tint(orbital.accent, modelData.alpha + orbital.level * 0.15)
            }
        }

        // Núcleo: la voz hecha punto. Más chico y contenido: crece con el
        // nivel sin exagerar y respira en reposo.
        Rectangle {
            id: core
            anchors.centerIn: parent
            width: 11 + orbital.level * 12; height: width
            radius: width / 2
            antialiasing: true
            visible: orbital.active
            color: orbital.voiceLo
            opacity: 0.85
            SequentialAnimation on opacity {
                running: orbital.mode === "listening" || orbital.mode === "starting"
                loops: Animation.Infinite
                NumberAnimation { from: 0.65; to: 1.0; duration: 1600; easing.type: Easing.InOutSine }
                NumberAnimation { from: 1.0; to: 0.65; duration: 1600; easing.type: Easing.InOutSine }
            }
        }

        // Transcribir: arco único girando sobre la guía del anillo medio.
        Item {
            anchors.centerIn: parent
            width: 96; height: 96
            visible: orbital.mode === "processing"
            Rectangle {
                anchors.centerIn: parent
                width: 88; height: 88; radius: 44
                antialiasing: true
                color: "transparent"
                border.width: 1
                border.color: orbital.tint(orbital.accent, 0.18)
            }
            Item {
                anchors.fill: parent
                Shape {
                    anchors.fill: parent
                    antialiasing: true
                    layer.enabled: true
                    layer.smooth: true
                    layer.samples: 4
                    ShapePath {
                        strokeColor: orbital.accent
                        strokeWidth: 3.5
                        fillColor: "transparent"
                        capStyle: ShapePath.RoundCap
                        PathAngleArc {
                            centerX: 48; centerY: 48; radiusX: 44; radiusY: 44
                            startAngle: 90; sweepAngle: 90
                        }
                    }
                }
                RotationAnimation on rotation {
                    from: 0; to: 360; duration: 900
                    loops: Animation.Infinite
                    running: orbital.mode === "processing"
                }
            }
        }

        // Éxito: solo el tilde dibujado. Sin "Copiado", sin tecla: el gesto
        // confirma, no hace falta escribirlo.
        Shape {
            id: checkGlyph
            anchors.centerIn: parent
            width: 40; height: 40
            antialiasing: true
            transformOrigin: Item.Center
            layer.enabled: true
            layer.smooth: true
            layer.samples: 4
            visible: orbital.mode === "success"
            ShapePath {
                strokeColor: orbital.brandGreen
                strokeWidth: 3
                fillColor: "transparent"
                capStyle: ShapePath.RoundCap
                joinStyle: ShapePath.RoundJoin
                startX: 12
                startY: 21
                PathLine { x: 18; y: 27 }
                PathLine { x: 28; y: 13 }
            }
        }

        // Avisos: el único texto del diseño, y solo cuando algo falla o
        // avisa. Sin texto de tecla ni de confirmación: minimalismo total en
        // el camino feliz.
        Text {
            id: messageText
            anchors.centerIn: parent
            width: parent.width - 48
            horizontalAlignment: Text.AlignHCenter
            text: orbital.message
            color: orbital.messageColor
            font.pixelSize: 13
            font.weight: Font.DemiBold
            lineHeight: 1.2
            wrapMode: Text.WordWrap
            renderType: Text.NativeRendering
            visible: orbital.feedback
        }
    }
}
