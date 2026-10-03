import QtQuick
import QtQuick.Shapes
import QtQuick.Window

/* Pastilla flotante de Instant.
   Escuchar se anima con una onda y transcribir con un arco que barre: las dos
   en la familia verde agua de la marca, con el mismo acento que la ventana.
   La paleta repite instant_app/branding.py a propósito (el QML se carga sin
   motor de plantillas); tests/test_overlay_palette.py falla si se despegan. */
Window {
    id: overlay
    title: "Instant overlay"

    // Margen transparente: le da lugar a la sombra dibujada en QML.
    readonly property int shadowMargin: 12

    property string mode: "idle"
    property string message: ""
    property color messageColor: "#f2c36a"
    property string keyLabel: "F9"
    property string previousMode: ""
    // Nivel de voz 0..1 que empuja el daemon ~20 veces por segundo mientras
    // se dicta: es tu micrófono de verdad, no un adorno. Con 0 la animación
    // apenas respira; al hablar, la onda se estira hasta ~1.85x, el anillo se
    // expande y la pastilla vibra. Suavizado en 60 ms para seguir a la voz.
    property real level: 0
    Behavior on level { NumberAnimation { duration: 60; easing.type: Easing.OutCubic } }
    // Espectro en 9 bandas (una por barra, 80 Hz..7.5 kHz): cada barra sigue
    // a su frecuencia de verdad. Cantá grave y se mueven las del centro;
    // silbá agudo y saltan las de los bordes.
    property var bandLevels: [0, 0, 0, 0, 0, 0, 0, 0, 0]
    // Tono 0..1 (grave->agudo) medido por autocorrelación: tiñe la onda
    // dentro de la familia de marca (verde agua -> hielo). 0.5 = neutro.
    property real pitch: 0.5
    Behavior on pitch { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
    readonly property color voiceHi: Qt.hsla(0.47 + pitch * 0.07, 0.50, 0.74, 1)
    readonly property color voiceLo: Qt.hsla(0.47 + pitch * 0.07, 0.62, 0.58, 1)

    readonly property bool feedback: mode === "error" || mode === "notice"
    // La pastilla de aviso se ajusta al texto: ni aire de más ni cortes raros.
    // Un poco más de píxeles que antes (300x78): las curvas finas necesitan
    // resolución para no verse pixeladas al escalar en pantallas HiDPI.
    readonly property int pillWidth: feedback
        ? Math.min(424, Math.max(300, messageMeasure.implicitWidth + 104))
        : 300
    readonly property int pillHeight: feedback ? Math.max(78, messageText.implicitHeight + 34) : 78

    width: pillWidth + shadowMargin * 2
    height: pillHeight + shadowMargin * 2
    color: "transparent"
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
    visible: false
    // La ventana no se funde por su cuenta: el fundido lo hace `shell` en la
    // entrada y en la salida. Si la ventana se apagara sola, taparía la
    // despedida y parecería que desaparece de golpe.
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

    function tint(color, alpha) {
        return Qt.rgba(color.r, color.g, color.b, alpha)
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
            if (previousMode === "idle" || previousMode === "") {
                entrance.restart()
            }
            if (mode === "success") {
                checkPop.restart()
            }
        }
        previousMode = mode
    }

    Timer {
        id: delayedHide
        interval: 300
        onTriggered: if (overlay.mode === "idle") overlay.visible = false
    }

    // Entrada: UN solo gesto — subir, aparecer, asentarse. Curva bezier
    // propia (0.32, 0.72, 0, 1): arranca decidida y aterriza suave. Recorrido
    // contenido (24 px): presencia sin teatro.
    ParallelAnimation {
        id: entrance
        NumberAnimation {
            target: shell; property: "scale"
            from: 0.95; to: 1; duration: 380
            easing.type: Easing.BezierSpline
            easing.bezierCurve: [0.32, 0.72, 0, 1]
        }
        NumberAnimation {
            target: shell; property: "opacity"
            from: 0; to: 1; duration: 240; easing.type: Easing.OutCubic
        }
        NumberAnimation {
            target: shell; property: "y"
            from: 24; to: 0; duration: 380
            easing.type: Easing.BezierSpline
            easing.bezierCurve: [0.32, 0.72, 0, 1]
        }
    }

    // Pop del tilde + fundido del texto: al confirmar, la marca aparece con
    // la misma curva de la casa, sin sobreimpulsos.
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
        NumberAnimation {
            target: successText; property: "opacity"
            from: 0; to: 1; duration: 260; easing.type: Easing.OutCubic
        }
    }

    // Salida: el mismo gesto en espejo, contenido y rápido.
    ParallelAnimation {
        id: departure
        NumberAnimation {
            target: shell; property: "scale"
            to: 0.96; duration: 260; easing.type: Easing.InCubic
        }
        NumberAnimation {
            target: shell; property: "opacity"
            to: 0; duration: 220; easing.type: Easing.InCubic
        }
        NumberAnimation {
            target: shell; property: "y"
            to: 24; duration: 260; easing.type: Easing.InCubic
        }
    }

    Item {
        id: content
        anchors.fill: parent

        // Sombra por capas: el overlay no usa shaders, así que se simula con
        // rectángulos de alfa decreciente. Cinco pasos se leen como un blur suave.
        Repeater {
            model: [
                { spread: 1, alpha: 0.20, drop: 1 },
                { spread: 3, alpha: 0.10, drop: 3 },
                { spread: 5, alpha: 0.05, drop: 5 },
                { spread: 8, alpha: 0.025, drop: 7 },
                { spread: 11, alpha: 0.012, drop: 9 }
            ]
            delegate: Rectangle {
                anchors.fill: shell
                anchors.margins: -modelData.spread
                anchors.topMargin: -modelData.spread + modelData.drop
                radius: shell.radius + modelData.spread
                color: Qt.rgba(0, 0, 0, modelData.alpha)
            }
        }

        Rectangle {
            id: shell
            objectName: "shell"
            // Origen al centro: el pop y la despedida crecen/colapsan
            // parejos, no desde la esquina.
            transformOrigin: Item.Center
            // Geometría explícita en vez de anchors.fill: así `y` queda libre
            // para animar la elevación. El tamaño sigue al padre por binding.
            x: overlay.shadowMargin
            y: 0
            width: parent.width - overlay.shadowMargin * 2
            height: parent.height - overlay.shadowMargin * 2
            radius: overlay.feedback ? 22 : 24
            border.width: 1
            antialiasing: true
            // Multisampleo en capa: los bordes redondeados y los arcos dejan
            // de verse aserrados sin cambiar ningún color ni forma.
            layer.enabled: true
            layer.smooth: true
            layer.samples: 4
            border.color: overlay.tint(overlay.accent, 0.30)
            gradient: Gradient {
                GradientStop { position: 0.0; color: overlay.glassTop }
                GradientStop { position: 1.0; color: overlay.glassBottom }
            }
            Behavior on border.color { ColorAnimation { duration: 260 } }
            Behavior on radius { NumberAnimation { duration: 240; easing.type: Easing.OutCubic } }

            // Luz de canto superior: separa la pastilla del fondo sin recargarla.
            Rectangle {
                x: shell.radius * 0.7
                y: 1
                width: parent.width - shell.radius * 1.4
                height: 1
                antialiasing: true
                color: "#ffffff"
                opacity: 0.09
            }

            Item {
                id: orb
                x: 16
                anchors.verticalCenter: parent.verticalCenter
                width: 44; height: 44
                // El anillo acompaña a la voz con un gesto mínimo.
                scale: 1 + overlay.level * 0.10
                Behavior on scale { NumberAnimation { duration: 100; easing.type: Easing.OutCubic } }

                // Anillo base: da el color del estado sin llenar el círculo.
                Rectangle {
                    id: halo
                    anchors.fill: parent
                    radius: width / 2
                    antialiasing: true
                    color: "transparent"
                    border.width: 1
                    border.color: overlay.tint(overlay.accent, 0.34 + overlay.level * 0.25)
                    Behavior on border.color { ColorAnimation { duration: 260 } }
                }

                // Aliento interior: late al escuchar, marcando que el micrófono vive.
                Rectangle {
                    id: breathe
                    anchors.fill: parent
                    anchors.margins: 3
                    radius: width / 2
                    antialiasing: true
                    color: overlay.tint(overlay.accent, 0.16 + overlay.level * 0.14)
                    opacity: 0.7 + overlay.level * 0.3
                    Behavior on color { ColorAnimation { duration: 260 } }
                    SequentialAnimation on opacity {
                        running: overlay.mode === "listening"
                        loops: Animation.Infinite
                        NumberAnimation { from: 0.55; to: 1.0; duration: 1200; easing.type: Easing.InOutSine }
                        NumberAnimation { from: 1.0; to: 0.55; duration: 1200; easing.type: Easing.InOutSine }
                    }
                }

                // Arranque: dos anillos que se abren escalonados mientras abre el mic.
                Repeater {
                    model: 2
                    delegate: Rectangle {
                        id: ring
                        anchors.fill: parent
                        radius: width / 2
                        color: "transparent"
                        border.width: 1
                        border.color: overlay.tint(overlay.accent, 0.55)
                        visible: overlay.mode === "starting"
                        SequentialAnimation {
                            running: overlay.mode === "starting"
                            loops: Animation.Infinite
                            PauseAnimation { duration: index * 700 }
                            ParallelAnimation {
                                NumberAnimation {
                                    target: ring; property: "scale"
                                    from: 0.88; to: 1.5; duration: 1500; easing.type: Easing.OutCubic
                                }
                                NumberAnimation {
                                    target: ring; property: "opacity"
                                    from: 0.6; to: 0; duration: 1500; easing.type: Easing.OutCubic
                                }
                            }
                        }
                    }
                }

                // Micrófono de trazo fino: la marca, sin el disco macizo de antes.
                Item {
                    id: micGlyph
                    anchors.centerIn: parent
                    width: 30; height: 30
                    transformOrigin: Item.Center
                    visible: !overlay.feedback && overlay.mode !== "success"
                    opacity: overlay.mode === "processing" ? 0.8 : 1
                    Behavior on opacity { NumberAnimation { duration: 220 } }

                    Rectangle {
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 4.5; width: 6.5; height: 14; radius: 3.25
                        antialiasing: true
                        color: overlay.ink
                    }
                    Shape {
                        anchors.fill: parent
                        antialiasing: true
                        layer.enabled: true
                        layer.smooth: true
                        layer.samples: 4
                        ShapePath {
                            strokeColor: overlay.ink
                            strokeWidth: 1.8
                            fillColor: "transparent"
                            capStyle: ShapePath.RoundCap
                            joinStyle: ShapePath.RoundJoin
                            startX: 5.5; startY: 11.5
                            PathCubic { control1X: 5.5; control1Y: 18; control2X: 9.5; control2Y: 21.5; x: 15; y: 21.5 }
                            PathCubic { control1X: 20.5; control1Y: 21.5; control2X: 24.5; control2Y: 18; x: 24.5; y: 11.5 }
                            PathMove { x: 15; y: 21.5 }
                            PathLine { x: 15; y: 26 }
                            PathMove { x: 10.5; y: 26 }
                            PathLine { x: 19.5; y: 26 }
                        }
                    }
                }

                // Listo: tilde dibujada (no depende de la tipografía del sistema).
                Shape {
                    id: checkGlyph
                    anchors.centerIn: parent
                    width: 30; height: 30
                    antialiasing: true
                    transformOrigin: Item.Center
                    layer.enabled: true
                    layer.smooth: true
                    layer.samples: 4
                    visible: overlay.mode === "success"
                    ShapePath {
                        strokeColor: overlay.brandGreen
                        strokeWidth: 2.6
                        fillColor: "transparent"
                        capStyle: ShapePath.RoundCap
                        joinStyle: ShapePath.RoundJoin
                        startX: 9.5
                        startY: 15.5
                        PathLine { x: 13.5; y: 19.5 }
                        PathLine { x: 21; y: 10.5 }
                    }
                }

                Text {
                    anchors.centerIn: parent
                    text: "!"
                    color: overlay.accent
                    font.pixelSize: 19
                    font.weight: Font.Bold
                    renderType: Text.NativeRendering
                    visible: overlay.feedback
                }
            }

            Item {
                id: activity
                x: orb.x + orb.width + (shortcut.x - orb.x - orb.width - width) / 2
                width: 124; height: 46
                anchors.verticalCenter: parent.verticalCenter
                visible: !overlay.feedback && overlay.mode !== "success"
                // La pastilla acompaña a la voz con un gesto mínimo.
                scale: 1 + overlay.level * 0.06
                Behavior on scale { NumberAnimation { duration: 100; easing.type: Easing.OutCubic } }

                // Arranque: tres puntos que respiran en secuencia.
                Item {
                    anchors.centerIn: parent
                    width: 37; height: 12
                    visible: overlay.mode === "starting"
                    Repeater {
                        model: 3
                        delegate: Rectangle {
                            id: dot
                            x: (parent.width - 37) / 2 + index * 16
                            anchors.verticalCenter: parent.verticalCenter
                            width: 5; height: 5; radius: 2.5
                            color: overlay.accent
                            opacity: 0.28
                            SequentialAnimation {
                                running: overlay.mode === "starting"
                                loops: Animation.Infinite
                                PauseAnimation { duration: index * 150 }
                                NumberAnimation { target: dot; property: "opacity"; to: 1; duration: 260; easing.type: Easing.OutCubic }
                                NumberAnimation { target: dot; property: "opacity"; to: 0.28; duration: 420; easing.type: Easing.InOutSine }
                            }
                        }
                    }
                }

                // Escuchar: 9 barras que siguen a su banda de frecuencia de
                // verdad (graves al centro, agudos a los bordes), con
                // recorrido contenido: elegancia contenida, no show. En
                // silencio quedan casi planas; con voz llegan al tope justo.
                Repeater {
                    model: 9
                    delegate: Rectangle {
                        id: bar
                        property real lowHeight: [4, 6, 8, 7, 10, 8, 9, 6, 5][index]
                        property real highHeight: [14, 22, 28, 24, 32, 26, 29, 20, 15][index]
                        property real centerWeight: 1 - Math.abs(index - 4) / 4.5
                        property real band: index < overlay.bandLevels.length ? Math.min(1, Math.max(0, overlay.bandLevels[index])) : 0
                        // Actividad 0..1 de ESTA barra: el reposo se aplana solo.
                        property real act: Math.max(overlay.level, bar.band)
                        x: (parent.width - 112) / 2 + index * 12.5
                        anchors.verticalCenter: parent.verticalCenter
                        width: 3
                        height: lowHeight
                        radius: 1.5
                        antialiasing: true
                        gradient: Gradient {
                            GradientStop { position: 0; color: overlay.voiceHi }
                            GradientStop { position: 1; color: overlay.voiceLo }
                        }
                        opacity: ((0.35 + (1 - Math.abs(index - 4) / 4.5) * 0.45) * (0.30 + 0.70 * bar.act)) + bar.act * 0.25
                        visible: overlay.mode === "listening"
                        SequentialAnimation {
                            running: overlay.mode === "listening"
                            loops: Animation.Infinite
                            PauseAnimation { duration: index * 55 }
                            NumberAnimation { target: bar; property: "height"; to: Math.min(32, bar.highHeight * (0.30 * (0.12 + 0.88 * bar.act) + bar.band * 1.4 + overlay.level * 0.2)); duration: 200; easing.type: Easing.OutCubic }
                            NumberAnimation { target: bar; property: "height"; to: bar.lowHeight * (0.25 + 0.45 * bar.act + overlay.level * 0.3); duration: 440; easing.type: Easing.InOutSine }
                        }
                    }
                }

                // Transcribir: arco grueso que barre sobre una guía tenue, con
                // pulso central que marca que está pensando. Trazos con
                // multisampleo: el giro no se pixela en movimiento.
                Item {
                    id: sweep
                    anchors.centerIn: parent
                    width: 52; height: 52
                    visible: overlay.mode === "processing"

                    Rectangle {
                        anchors.centerIn: parent
                        width: 40; height: 40; radius: 20
                        antialiasing: true
                        color: "transparent"
                        border.width: 1
                        border.color: overlay.tint(overlay.accent, 0.16)
                    }
                    Rectangle {
                        anchors.centerIn: parent
                        width: 6; height: 6; radius: 3
                        color: overlay.accent
                        opacity: 0.5
                        SequentialAnimation on opacity {
                            running: overlay.mode === "processing"
                            loops: Animation.Infinite
                            NumberAnimation { from: 0.25; to: 0.9; duration: 450; easing.type: Easing.InOutSine }
                            NumberAnimation { from: 0.9; to: 0.25; duration: 450; easing.type: Easing.InOutSine }
                        }
                    }
                    Item {
                        anchors.fill: parent
                        Shape {
                            anchors.fill: parent
                            antialiasing: true
                            layer.enabled: true
                            layer.smooth: true
                            layer.samples: 4
                            // Arco único: un solo trazo barriendo. Las estelas se
                            // retiraron por criterio high-end: un giro limpio
                            // se lee premium; tres se leen ruido.
                            ShapePath {
                                strokeColor: overlay.accent
                                strokeWidth: 3.2
                                fillColor: "transparent"
                                capStyle: ShapePath.RoundCap
                                PathAngleArc {
                                    centerX: 26; centerY: 26; radiusX: 20; radiusY: 20
                                    startAngle: 90; sweepAngle: 96
                                }
                            }
                        }
                        RotationAnimation on rotation {
                            from: 0; to: 360; duration: 900
                            loops: Animation.Infinite
                            running: overlay.mode === "processing"
                        }
                    }
                    Item {
                        anchors.fill: parent
                        opacity: 0.35
                        Shape {
                            anchors.fill: parent
                            antialiasing: true
                            layer.enabled: true
                            layer.smooth: true
                            layer.samples: 4
                            ShapePath {
                                strokeColor: overlay.accent
                                strokeWidth: 1.6
                                fillColor: "transparent"
                                capStyle: ShapePath.RoundCap
                                PathAngleArc {
                                    centerX: 26; centerY: 26; radiusX: 20; radiusY: 20
                                    startAngle: 0; sweepAngle: 210
                                }
                            }
                        }
                        RotationAnimation on rotation {
                            from: 360; to: 0; duration: 2600
                            loops: Animation.Infinite
                            running: overlay.mode === "processing"
                        }
                    }
                }
            }

            Text {
                id: successText
                objectName: "successText"
                anchors.horizontalCenter: activity.horizontalCenter
                anchors.verticalCenter: parent.verticalCenter
                text: "Copiado"
                color: Qt.lighter(overlay.brandGreen, 1.25)
                font.pixelSize: 14
                font.weight: Font.DemiBold
                renderType: Text.NativeRendering
                visible: overlay.mode === "success"
            }

            Rectangle {
                id: shortcut
                anchors.right: parent.right
                anchors.rightMargin: 16
                anchors.verticalCenter: parent.verticalCenter
                width: Math.max(34, keyText.implicitWidth + 18)
                height: 24
                radius: 8
                color: overlay.tint(overlay.ink, 0.05)
                border.width: 1
                border.color: overlay.tint(overlay.accent, 0.20)
                visible: !overlay.feedback && overlay.mode !== "success"
                Text {
                    id: keyText
                    anchors.centerIn: parent
                    text: overlay.keyLabel
                    color: overlay.inkDim
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                    renderType: Text.NativeRendering
                }
            }

            Text {
                id: messageText
                x: orb.x + orb.width + 16
                width: parent.width - x - 20
                anchors.verticalCenter: parent.verticalCenter
                text: overlay.message
                color: overlay.messageColor
                font.pixelSize: 13
                font.weight: Font.DemiBold
                lineHeight: 1.16
                wrapMode: Text.WordWrap
                renderType: Text.NativeRendering
                visible: overlay.feedback
            }

            // Medida sin wrap: define el ancho de la pastilla de aviso.
            Text {
                id: messageMeasure
                visible: false
                text: overlay.message
                font.pixelSize: 13
                font.weight: Font.DemiBold
            }
        }
    }
}
