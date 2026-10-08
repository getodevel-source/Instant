import QtQuick
import QtQuick3D

/* Sonda de la cadena v4 por etapas:
   stage 0: View3D directo (control positivo).
   stage 2: View3D oculto (hideSource) + passthrough de la captura.
   stage 3: View3D oculto + cadena de bloom completa. */
Window {
    id: probe
    width: 224
    height: 224
    color: "transparent"
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
    visible: true

    property int stage: 0
    property real timeS: 0

    FrameAnimation { running: probe.visible; onTriggered: probe.timeS = Date.now() / 1000 }

    View3D {
        id: view
        anchors.fill: parent
        // Siempre visible: el ocultamiento lo hace hideSource del
        // ShaderEffectSource (visible:false suprime tambien la captura).
        environment: SceneEnvironment {
            backgroundMode: SceneEnvironment.Transparent
            clearColor: "transparent"
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.High
        }
        PerspectiveCamera { position: Qt.vector3d(0, 0, 520); fieldOfView: 60 }
        DirectionalLight { eulerRotation.x: -25; eulerRotation.y: 35; brightness: 1.1 }
        Model {
            source: "#Sphere"
            scale: Qt.vector3d(0.6, 0.6, 0.6)
            materials: PrincipledMaterial {
                baseColor: "#55d5c8"
                roughness: 0.3
                emissiveFactor: Qt.vector3d(0.4, 1.2, 1.1)
            }
        }
    }

    ShaderEffectSource {
        id: sceneTex
        sourceItem: view
        live: true
        hideSource: probe.stage >= 2
        textureSize: Qt.size(224, 224)
    }

    ShaderEffect {
        id: passThrough
        anchors.fill: parent
        visible: probe.stage === 2
        property var src: sceneTex
        fragmentShader: "debug_pass.frag.qsb"
    }

    ShaderEffect {
        id: bloomH
        width: 112
        height: 112
        visible: false
        property var src: sceneTex
        property real threshold: 0.45
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
        visible: probe.stage === 3
        property var scene: sceneTex
        property var bloom: bloomTex
        property real strength: 1.25
        property real exposure: 1.1
        property vector2d texel: Qt.vector2d(1.0 / 112.0, 1.0 / 112.0)
        fragmentShader: "bloom_v.frag.qsb"
    }
}
