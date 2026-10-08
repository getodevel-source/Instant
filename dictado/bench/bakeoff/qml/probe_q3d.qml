import QtQuick
import QtQuick3D
import QtQuick3D.Helpers

/* Sonda Quick3D: esfera emissive + ExtendedSceneEnvironment con glow (el
   post-proceso de Quick3D). Fondo transparente. Si el glow funciona, hay halo
   fuera de la silueta de la esfera. */
Window {
    id: probe
    width: 240
    height: 240
    color: "transparent"
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
    visible: true

    View3D {
        anchors.fill: parent
        environment: ExtendedSceneEnvironment {
            backgroundMode: SceneEnvironment.Color
            clearColor: "#0d1a1e"
            antialiasingMode: SceneEnvironment.MSAA
            antialiasingQuality: SceneEnvironment.High
            tonemapMode: SceneEnvironment.TonemapModeFilmic
            glowEnabled: true
            glowStrength: 2.0
            glowIntensity: 1.5
            glowBloom: 0.6
            glowLevel: ExtendedSceneEnvironment.GlowLevel.One
            glowUseBicubicUpscale: true
            ditheringEnabled: true
        }
        PerspectiveCamera {
            position: Qt.vector3d(0, 0, 420)
        }
        DirectionalLight {
            eulerRotation.x: -20
            eulerRotation.y: 30
            brightness: 1.2
        }
        Model {
            source: "#Sphere"
            scale: Qt.vector3d(0.5, 0.5, 0.5)
            materials: PrincipledMaterial {
                baseColor: "#55d5c8"
                roughness: 0.25
                metalness: 0.0
                emissiveFactor: Qt.vector3d(0.8, 3.0, 2.8)
            }
        }
    }
}
