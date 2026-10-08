import QtQuick
import QtQuick.Effects

/* Sonda de capacidades Qt Quick de este entorno: ShaderEffect GLSL inline,
   MultiEffect (glow/blur) y gradientes radiales. Ventana transparente,
   siempre encima, sin foco: mismas flags que el overlay de producción. */
Window {
    id: probe
    width: 240
    height: 120
    color: "transparent"
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
    visible: true

    property real level: 0.7

    // 1) Orbe por fragment shader compilado offline con qsb (el unico camino
    // de shaders propios en Qt 6: fragmentShader es una URL a .qsb).
    ShaderEffect {
        id: orb
        anchors.centerIn: parent
        width: 110
        height: 110
        property real level: probe.level
        property real pitch: 0.5
        fragmentShader: "orb_probe.frag.qsb"
    }

    // 2) Glow por MultiEffect sobre el orbe (blur + brillo de marca).
    // autoPadding dibuja el halo fuera de la geometría del orbe.
    MultiEffect {
        source: orb
        anchors.fill: orb
        blurEnabled: true
        blurMax: 48
        blur: 1.0
        brightness: 0.25
        opacity: 0.7
        autoPaddingEnabled: true
    }

    // 3) Gradiente lineal nativo (QtQuick core solo tiene Gradient lineal).
    Rectangle {
        x: 8
        y: 8
        width: 40
        height: 40
        radius: 20
        gradient: Gradient {
            orientation: Gradient.Vertical
            GradientStop { position: 0.0; color: "#55d5c8" }
            GradientStop { position: 1.0; color: "transparent" }
        }
    }
}
