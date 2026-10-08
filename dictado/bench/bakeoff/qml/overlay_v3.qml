import QtQuick

/* Overlay v3 del bake-off (ronda 2, lado QML): mismo contrato, misma ventana
   y mismas metricas que v2; el dibujo del techo (blob fluido + anillo de onda
   + particulas) vive en overlay_v3.frag.qsb. */
Window {
    id: root
    title: "Instant bakeoff overlay v3 (QML)"
    width: 224
    height: 224
    color: "transparent"
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
    visible: true

    property string mode: "idle"
    property string message: ""
    property real level: 0
    Behavior on level { NumberAnimation { duration: 90; easing.type: Easing.OutCubic } }
    property real pitch: 0.5
    Behavior on pitch { NumberAnimation { duration: 140; easing.type: Easing.OutCubic } }
    property var bandLevels: [0, 0, 0, 0, 0, 0, 0, 0, 0]
    property real timeS: 0
    property double lastMs: 0

    readonly property real modeIndex:
        mode === "starting" ? 1
        : mode === "listening" ? 2
        : mode === "processing" ? 3
        : (mode === "notice" || mode === "error") ? 4
        : 0

    readonly property bool feedback: mode === "notice" || mode === "error"

    // --- Metricas (mismo metodo que el prototipo web) ---
    property int frames: 0
    property var frameTimes: []
    signal firstFrame()
    signal reportFps(real fps, real p95IntervalMs)

    FrameAnimation {
        running: root.visible
        onTriggered: {
            root.frames += 1
            var now = Date.now()
            if (root.lastMs > 0)
                root.timeS += (now - root.lastMs) / 1000
            root.lastMs = now
            var ft = root.frameTimes
            ft.push(now)
            if (ft.length > 4096)
                ft.shift()
            if (root.frames === 1)
                root.firstFrame()
        }
    }

    Timer {
        interval: 1000
        running: true
        repeat: true
        onTriggered: {
            var now = Date.now()
            var recent = []
            var ft = root.frameTimes
            for (var i = 0; i < ft.length; i++) {
                if (ft[i] >= now - 1000)
                    recent.push(ft[i])
            }
            var p95 = 0
            if (recent.length > 1) {
                var deltas = []
                for (var j = 1; j < recent.length; j++)
                    deltas.push(recent[j] - recent[j - 1])
                deltas.sort(function (a, b) { return a - b })
                p95 = deltas[Math.min(deltas.length - 1, Math.floor(deltas.length * 0.95))]
            }
            root.frameTimes = recent
            root.reportFps(recent.length, p95)
        }
    }

    // --- Dibujo: un solo fragment shader con todo el orbe v3 ---
    ShaderEffect {
        anchors.fill: parent
        property real level: root.level
        property real pitch: root.pitch
        property real timeS: root.timeS
        property real modeIndex: root.modeIndex
        property real band0: root.bandLevels.length > 0 ? root.bandLevels[0] : 0
        property real band1: root.bandLevels.length > 1 ? root.bandLevels[1] : 0
        property real band2: root.bandLevels.length > 2 ? root.bandLevels[2] : 0
        property real band3: root.bandLevels.length > 3 ? root.bandLevels[3] : 0
        property real band4: root.bandLevels.length > 4 ? root.bandLevels[4] : 0
        property real band5: root.bandLevels.length > 5 ? root.bandLevels[5] : 0
        property real band6: root.bandLevels.length > 6 ? root.bandLevels[6] : 0
        property real band7: root.bandLevels.length > 7 ? root.bandLevels[7] : 0
        property real band8: root.bandLevels.length > 8 ? root.bandLevels[8] : 0
        fragmentShader: "overlay_v3.frag.qsb"
    }

    Rectangle {
        visible: root.feedback && root.message.length > 0
        anchors.horizontalCenter: parent.horizontalCenter
        y: 200 - height + 6
        height: 26
        radius: 13
        width: Math.max(120, msgText.implicitWidth + 36)
        color: Qt.rgba(0.06, 0.13, 0.14, 0.85)
        border.width: 1
        border.color: Qt.rgba(0.949, 0.765, 0.416, 0.35)

        Text {
            id: msgText
            anchors.centerIn: parent
            text: root.message
            color: "#f2c36a"
            font.pixelSize: 13
        }
    }
}
