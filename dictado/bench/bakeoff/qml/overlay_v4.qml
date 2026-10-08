import QtQuick
import QtQuick3D

/* Overlay v4 del bake-off (ronda 3, lado QML): techo con motor 3D.
   Escena QtQuick3D real (orbe PBR con luces, anillo de onda de 24 esferas,
   embers 3D) renderizada offscreen y post-procesada con una cadena de bloom
   PROPIA (bloom_h + bloom_v) que preserva el alfa: el glow del motor
   (ExtendedSceneEnvironment) no compone sobre ventana transparente
   (verificado en probe_q3d: spill visible solo con fondo opaco).
   Mismo contrato y mismas metricas que v2/v3. */
Window {
    id: root
    title: "Instant bakeoff overlay v4 (QML 3D)"
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

    readonly property bool isIdle: mode === "idle"
    readonly property bool isStarting: mode === "starting"
    readonly property bool isListening: mode === "listening"
    readonly property bool isProcessing: mode === "processing"
    readonly property bool isNotice: mode === "notice" || mode === "error"
    readonly property bool feedback: isNotice

    // --- Metricas (mismo metodo que los demas prototipos) ---
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

    // --- Helpers JS (misma matematica que el lado web) ---
    function fract(v) { return v - Math.floor(v) }

    function hash21(x, y) {
        var px = fract(x * 123.34)
        var py = fract(y * 456.21)
        var d = px * (px + 45.32) + py * (py + 45.32)
        px += d
        py += d
        return fract(px * py)
    }

    function bandAt(ang) {
        var b = bandLevels
        if (!b || b.length < 9)
            return 0
        var pos = (ang / (2 * Math.PI)) * 9
        var i0 = Math.floor(pos)
        var f = pos - i0
        var a = ((i0 % 9) + 9) % 9
        var c = ((i0 + 1) % 9 + 9) % 9
        var ff = f * f * (3 - 2 * f)
        return b[a] * (1 - ff) + b[c] * ff
    }

    function mixColor(c1, c2, t) {
        return Qt.rgba(c1.r + (c2.r - c1.r) * t, c1.g + (c2.g - c1.g) * t,
                       c1.b + (c2.b - c1.b) * t, 1)
    }

    readonly property color accentCol: "#55d5c8"
    readonly property color workingCol: "#8fd7e8"
    readonly property color amberCol: "#f2c36a"
    readonly property real breath: 0.5 + 0.5 * Math.sin(timeS * 2 * Math.PI / 2.8)
    readonly property real pulse: 0.5 + 0.5 * Math.sin(timeS * 2 * Math.PI / 0.45)
    readonly property color voiceCol: isNotice
        ? amberCol : mixColor(accentCol, workingCol, pitch)

    // Radio del nucleo en unidades de escena (1 unidad ~ 0.4 px aca).
    readonly property real nucUnits:
        (isIdle ? 40 + 4 * breath : 0)
        + (isStarting ? 45 + 10 * level : 0)
        + (isListening ? 60 + 20 * level : 0)
        + (isProcessing ? 55 + 8 * Math.sin(timeS * 2 * Math.PI / 0.9) : 0)
        + (isNotice ? 55 + 5 * pulse : 0)
    readonly property real nucEmissive:
        (isIdle ? 0.18 : 0) + (isStarting ? 0.5 : 0) + (isListening ? 0.45 + 0.45 * level : 0)
        + (isProcessing ? 0.55 : 0) + (isNotice ? 0.5 + 0.3 * pulse : 0)

    readonly property real ringBalls: 48
    readonly property real ringR: 205
    function ringPos(i) {
        var gate = (isStarting || isListening) ? 1 : 0
        var ang = (i / ringBalls) * 2 * Math.PI + timeS * (0.15 + 0.35 * level)
        var disp = gate * bandAt(ang - timeS * (0.15 + 0.35 * level)) * (0.02 + 0.08 * Math.max(level, 0.2))
        var rr = ringR * (1 + disp)
        return Qt.vector3d(Math.cos(ang) * rr, Math.sin(ang) * rr, 0)
    }
    readonly property real ringBallScale: (isIdle ? 0.008 : 0.075)

    // Embers: 10 esferas con la misma matematica de hash que los shaders v3.
    readonly property real emberCount: 10
    function emberPos(i) {
        if (isIdle || isNotice)
            return Qt.vector3d(0, 0, -900)
        var h1 = hash21(i, 1.7)
        var h2 = hash21(i, 9.3)
        var speed = 0.22 + 0.5 * h2
        var phase = fract(timeS * speed + h1)
        var rStart = nucUnits + 20
        var rEnd = 245
        var rr = isProcessing ? rEnd + (rStart - rEnd) * phase : rStart + (rEnd - rStart) * phase
        var ang = h1 * 2 * Math.PI + phase * (0.5 + h2)
        var z = (h1 - 0.5) * 120
        return Qt.vector3d(Math.cos(ang) * rr, Math.sin(ang) * rr, z)
    }
    readonly property real emberScale: {
        var h1 = 0.5
        return isListening ? (0.014 + 0.008 * level) : 0.012
    }

    // Barrido de processing: esfera brillante orbitando + eco.
    function sweepPos(phaseOffset) {
        var ang = timeS * (2 * Math.PI / 1.1) + phaseOffset
        return Qt.vector3d(Math.cos(ang) * ringR, Math.sin(ang) * ringR, 10)
    }

    // --- Escena 3D ---
    View3D {
        id: view
        anchors.fill: parent
        environment: SceneEnvironment {
            backgroundMode: SceneEnvironment.Transparent
            clearColor: "transparent"
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.High
        }
        PerspectiveCamera {
            position: Qt.vector3d(0, 0, 520)
            fieldOfView: 60
        }
        DirectionalLight {
            eulerRotation.x: -25
            eulerRotation.y: 35
            brightness: 0.9
        }
        DirectionalLight {
            eulerRotation.y: 150
            brightness: 0.35
        }

        Model {
            source: "#Sphere"
            scale: Qt.vector3d(root.nucUnits / 100, root.nucUnits / 100, root.nucUnits / 100)
            materials: PrincipledMaterial {
                baseColor: root.voiceCol
                roughness: 0.32
                metalness: 0.05
                emissiveFactor: Qt.vector3d(
                    root.voiceCol.r * root.nucEmissive,
                    root.voiceCol.g * root.nucEmissive,
                    root.voiceCol.b * root.nucEmissive)
            }
        }

        Repeater3D {
            model: root.ringBalls
            delegate: Model {
                source: "#Sphere"
                position: root.ringPos(index)
                scale: Qt.vector3d(root.ringBallScale, root.ringBallScale, root.ringBallScale)
                materials: PrincipledMaterial {
                    baseColor: root.voiceCol
                    roughness: 0.4
                    emissiveFactor: Qt.vector3d(
                        root.voiceCol.r * (root.isIdle ? 0.15 : 0.55),
                        root.voiceCol.g * (root.isIdle ? 0.15 : 0.55),
                        root.voiceCol.b * (root.isIdle ? 0.15 : 0.55))
                }
            }
        }

        Repeater3D {
            model: root.emberCount
            delegate: Model {
                source: "#Sphere"
                position: root.emberPos(index)
                scale: Qt.vector3d(root.emberScale, root.emberScale, root.emberScale)
                materials: PrincipledMaterial {
                    baseColor: root.voiceCol
                    roughness: 0.5
                    emissiveFactor: Qt.vector3d(root.voiceCol.r * 0.8, root.voiceCol.g * 0.8,
                                                root.voiceCol.b * 0.8)
                }
            }
        }

        Model {
            source: "#Sphere"
            position: root.sweepPos(0)
            visible: root.isProcessing
            scale: Qt.vector3d(0.11, 0.11, 0.11)
            materials: PrincipledMaterial {
                baseColor: root.workingCol
                roughness: 0.3
                emissiveFactor: Qt.vector3d(0.5, 0.8, 0.85)
            }
        }
        Model {
            source: "#Sphere"
            position: root.sweepPos(-0.55)
            visible: root.isProcessing
            scale: Qt.vector3d(0.06, 0.06, 0.06)
            materials: PrincipledMaterial {
                baseColor: root.workingCol
                roughness: 0.4
                emissiveFactor: Qt.vector3d(0.2, 0.3, 0.35)
            }
        }
    }

    // --- Post-proceso propio: bloom con alfa (2 pasadas + composicion) ---
    ShaderEffectSource {
        id: sceneTex
        sourceItem: view
        live: true
        hideSource: true
        textureSize: Qt.size(224, 224)
    }
    ShaderEffect {
        id: bloomH
        width: 112
        height: 112
        visible: false
        property var src: sceneTex
        property real threshold: 0.6
        property vector2d texel: Qt.vector2d(1.0 / 112.0, 1.0 / 112.0)
        fragmentShader: "bloom_h.frag.qsb"
    }
    ShaderEffectSource {
        id: bloomTex
        sourceItem: bloomH
        live: true
        hideSource: true
        textureSize: Qt.size(112, 112)
    }
    ShaderEffect {
        id: composite
        anchors.fill: parent
        property var scene: sceneTex
        property var bloom: bloomTex
        property real strength: 1.0
        property real exposure: 1.0
        property vector2d texel: Qt.vector2d(1.0 / 112.0, 1.0 / 112.0)
        fragmentShader: "bloom_v.frag.qsb"
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
