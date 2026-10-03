import QtQuick
import QtQuick.Shapes
import QtQuick.Window

Window {
    id: overlay
    title: "Instant overlay"
    width: feedback ? 430 : 316
    height: feedback ? Math.max(88, messageText.implicitHeight + 38) : 86
    color: "transparent"
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
    visible: false
    opacity: mode === "idle" ? 0 : 1

    property string mode: "idle"
    property string message: ""
    property color messageColor: "#f2c36a"
    property string keyLabel: "F9"
    readonly property bool feedback: mode === "error" || mode === "notice"
    readonly property color accent: mode === "processing" ? "#b7a3ff"
                                  : mode === "error" ? "#ff908b"
                                  : mode === "notice" ? "#f2c36a"
                                  : mode === "success" ? "#7cdda6" : "#55d5c8"

    Behavior on width { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
    Behavior on height { NumberAnimation { duration: 260; easing.type: Easing.OutCubic } }
    Behavior on opacity { NumberAnimation { duration: 170; easing.type: Easing.OutCubic } }

    onModeChanged: {
        if (mode === "idle") {
            delayedHide.start()
        } else {
            visible = true
            delayedHide.stop()
        }
    }

    Timer {
        id: delayedHide
        interval: 190
        onTriggered: if (overlay.mode === "idle") overlay.visible = false
    }

    Item {
        id: content
        anchors.fill: parent

        Rectangle {
            anchors.fill: shell
            anchors.topMargin: 5
            radius: shell.radius
            color: "#05090d"
            opacity: 0.38
        }

        Rectangle {
            id: shell
            anchors.fill: parent
            radius: feedback ? 20 : 27
            border.width: 1
            border.color: Qt.rgba(overlay.accent.r, overlay.accent.g, overlay.accent.b, 0.48)
            gradient: Gradient {
                GradientStop { position: 0.0; color: "#24353d" }
                GradientStop { position: 0.46; color: "#17262e" }
                GradientStop { position: 1.0; color: "#111c23" }
            }

            Rectangle {
                x: 1; y: 1; width: parent.width - 2; height: 1
                radius: 1; color: "#ffffff"; opacity: 0.12
            }

            Item {
                id: iconWell
                x: 18
                anchors.verticalCenter: parent.verticalCenter
                width: 52; height: 52

                Rectangle {
                    id: aura
                    anchors.centerIn: parent
                    width: overlay.mode === "starting" || overlay.mode === "listening" ? 58 : 48
                    height: width
                    radius: width / 2
                    color: Qt.rgba(overlay.accent.r, overlay.accent.g, overlay.accent.b, 0.13)
                    border.width: 1
                    border.color: Qt.rgba(overlay.accent.r, overlay.accent.g, overlay.accent.b, 0.42)
                    Behavior on width { NumberAnimation { duration: 280; easing.type: Easing.OutCubic } }
                    Behavior on color { ColorAnimation { duration: 220 } }
                    SequentialAnimation on scale {
                        running: overlay.mode === "starting"
                        loops: Animation.Infinite
                        NumberAnimation { to: 1.13; duration: 420; easing.type: Easing.OutSine }
                        NumberAnimation { to: 0.96; duration: 520; easing.type: Easing.InOutSine }
                    }
                    Behavior on opacity { NumberAnimation { duration: 180 } }
                    opacity: overlay.mode === "idle" ? 0 : 1
                }

                Rectangle {
                    id: iconDisk
                    anchors.centerIn: parent
                    width: 38; height: 38; radius: 19
                    gradient: Gradient {
                        GradientStop { position: 0; color: Qt.lighter(overlay.accent, 1.2) }
                        GradientStop { position: 1; color: Qt.darker(overlay.accent, 1.6) }
                    }
                    opacity: overlay.mode === "error" || overlay.mode === "notice" ? 1 : 0.94
                    Behavior on opacity { NumberAnimation { duration: 160 } }

                    Shape {
                        id: micCup
                        anchors.centerIn: parent
                        width: 36; height: 36
                        visible: micBody.visible
                        ShapePath {
                            strokeColor: "#f5fbfb"
                            strokeWidth: 1.7
                            fillColor: "transparent"
                            capStyle: ShapePath.RoundCap
                            joinStyle: ShapePath.RoundJoin
                            startX: 7; startY: 15
                            PathCubic { control1X: 7; control1Y: 21; control2X: 12; control2Y: 25; x: 18; y: 25 }
                            PathCubic { control1X: 24; control1Y: 25; control2X: 29; control2Y: 21; x: 29; y: 15 }
                            PathMove { x: 18; y: 25 }
                            PathLine { x: 18; y: 31 }
                            PathMove { x: 13; y: 31 }
                            PathLine { x: 23; y: 31 }
                        }
                    }
                    Rectangle {
                        id: micBody
                        anchors.horizontalCenter: parent.horizontalCenter
                        y: 5; width: 8; height: 18; radius: 4
                        color: "#f5fbfb"
                        visible: overlay.mode === "starting" || overlay.mode === "listening" || overlay.mode === "processing"
                        opacity: overlay.mode === "processing" ? 0.76 : 1
                    }
                    Text {
                        anchors.centerIn: parent
                        text: overlay.mode === "success" ? "✓" : "!"
                        color: "#10191f"
                        font.pixelSize: 23; font.bold: true
                        visible: overlay.mode === "success" || overlay.mode === "error" || overlay.mode === "notice"
                    }
                }
            }

            Item {
                id: activity
                x: 102; width: 112; height: 54
                anchors.verticalCenter: parent.verticalCenter
                visible: !overlay.feedback && overlay.mode !== "success"
                opacity: visible ? 1 : 0
                Behavior on opacity { NumberAnimation { duration: 140 } }

                Item {
                    id: startDots
                    anchors.centerIn: parent
                    width: 58; height: 18
                    visible: overlay.mode === "starting"
                    Repeater {
                        model: 3
                        delegate: Rectangle {
                            id: pulseDot
                            x: 5 + index * 19; y: 6
                            width: 6; height: 6; radius: 3
                            color: overlay.accent
                            opacity: 0.45
                            SequentialAnimation {
                                running: overlay.mode === "starting"
                                loops: Animation.Infinite
                                PauseAnimation { duration: index * 130 }
                                NumberAnimation { target: pulseDot; property: "scale"; to: 1.45; duration: 280; easing.type: Easing.OutCubic }
                                NumberAnimation { target: pulseDot; property: "opacity"; to: 1; duration: 180 }
                                NumberAnimation { target: pulseDot; property: "scale"; to: 0.82; duration: 380; easing.type: Easing.InOutSine }
                                NumberAnimation { target: pulseDot; property: "opacity"; to: 0.42; duration: 260 }
                            }
                        }
                    }
                }

                Repeater {
                    model: 7
                    delegate: Rectangle {
                        id: bar
                        property real lowHeight: [7, 13, 9, 18, 11, 15, 8][index]
                        property real highHeight: [16, 24, 19, 30, 21, 26, 15][index]
                        x: 10 + index * 14
                        anchors.verticalCenter: parent.verticalCenter
                        width: 4; height: lowHeight; radius: 2
                        color: overlay.accent
                        opacity: 0.62 + (1 - Math.abs(index - 3) / 4) * 0.36
                        visible: overlay.mode === "listening"
                        SequentialAnimation {
                            running: overlay.mode === "listening"
                            loops: Animation.Infinite
                            PauseAnimation { duration: index * 74 }
                            NumberAnimation { target: bar; property: "height"; to: bar.highHeight; duration: 320; easing.type: Easing.OutCubic }
                            NumberAnimation { target: bar; property: "height"; to: bar.lowHeight; duration: 500; easing.type: Easing.InOutSine }
                        }
                        Behavior on color { ColorAnimation { duration: 240 } }
                    }
                }

                Item {
                    id: spinner
                    anchors.centerIn: parent
                    width: 46; height: 46
                    visible: overlay.mode === "processing"
                    Rectangle {
                        anchors.centerIn: parent
                        width: 29; height: 29; radius: 15
                        color: "transparent"
                        border.width: 1
                        border.color: Qt.rgba(overlay.accent.r, overlay.accent.g, overlay.accent.b, 0.32)
                    }
                    RotationAnimation on rotation {
                        from: 0; to: 360; duration: 1450; loops: Animation.Infinite
                        running: overlay.mode === "processing"
                    }
                    Repeater {
                        model: 8
                        delegate: Rectangle {
                            width: index === 0 ? 7 : 5
                            height: width; radius: width / 2
                            x: 20.5 + 17 * Math.cos(index * Math.PI / 4)
                            y: 20.5 + 17 * Math.sin(index * Math.PI / 4)
                            color: overlay.accent
                            opacity: 1 - index * 0.08
                        }
                    }
                }
            }

            Text {
                id: successText
                objectName: "successText"
                x: 102; width: 112; height: 54
                anchors.verticalCenter: parent.verticalCenter
                text: "Copiado"
                color: "#dff8e9"
                font.pixelSize: 15; font.weight: Font.DemiBold
                verticalAlignment: Text.AlignVCenter
                visible: overlay.mode === "success"
            }

            Rectangle {
                id: shortcut
                anchors.right: parent.right; anchors.rightMargin: 18
                anchors.verticalCenter: parent.verticalCenter
                width: 38; height: 27; radius: 8
                color: "#2a4149"
                border.width: 1; border.color: "#3b5961"
                visible: !overlay.feedback && overlay.mode !== "success"
                Text {
                    anchors.centerIn: parent
                    text: overlay.keyLabel
                    color: "#d6e6e9"
                    font.pixelSize: 10; font.weight: Font.DemiBold
                }
            }

            Text {
                id: messageText
                x: 84; y: 14
                width: parent.width - 102
                height: parent.height - 28
                text: overlay.message
                color: overlay.messageColor
                font.pixelSize: 13; font.weight: Font.DemiBold
                wrapMode: Text.WordWrap
                verticalAlignment: Text.AlignVCenter
                visible: overlay.feedback
            }
        }
    }
}
