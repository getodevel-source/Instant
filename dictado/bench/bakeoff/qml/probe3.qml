import QtQuick
import Qt5Compat.GraphicalEffects

/* Sonda 3: que dialecto de fragmentShader inline acepta este Qt 6.11.
   Seis items en fila, mismo tamaño; los 4 primeros son variantes de sintaxis
   (los ultimos 2 son controles). Objetivo: encontrar la sintaxis que pinta. */
Window {
    id: probe3
    width: 500
    height: 160
    color: "transparent"
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
    visible: true

    Row {
        anchors.centerIn: parent
        spacing: 10

        // v1: legacy (control negativo conocido): varying + gl_FragColor
        ShaderEffect {
            width: 60; height: 60
            fragmentShader: "
                varying vec2 qt_TexCoord0;
                uniform lowp float qt_Opacity;
                void main() { gl_FragColor = vec4(1.0, 0.0, 1.0, 1.0) * qt_Opacity; }"
        }

        // v2: ES3 explicito con in/out
        ShaderEffect {
            width: 60; height: 60
            fragmentShader: "
                #version 300 es
                precision mediump float;
                in vec2 qt_TexCoord0;
                out vec4 fragColor;
                uniform float qt_Opacity;
                void main() { fragColor = vec4(1.0, 0.0, 1.0, 1.0) * qt_Opacity; }"
        }

        // v3: sin varyings, solo constantes + out explicito
        ShaderEffect {
            width: 60; height: 60
            fragmentShader: "
                #version 300 es
                precision mediump float;
                out vec4 fragColor;
                void main() { fragColor = vec4(1.0, 0.0, 1.0, 1.0); }"
        }

        // v4: macros Qt (VARYING/FRAGCOLOR) estilo Quick3D
        ShaderEffect {
            width: 60; height: 60
            fragmentShader: "
                VARYING vec2 qt_TexCoord0;
                void MAIN() { FRAGCOLOR = vec4(1.0, 0.0, 1.0, 1.0); }"
        }

        // v5: control positivo: Rectangle plano
        Rectangle { width: 60; height: 60; color: "#7cdda6" }

        // v6: control positivo: Qt5Compat RadialGradient
        Item {
            width: 60; height: 60
            RadialGradient {
                anchors.fill: parent
                gradient: Gradient {
                    GradientStop { position: 0.0; color: "#55d5c8" }
                    GradientStop { position: 1.0; color: "transparent" }
                }
            }
        }
    }
}
