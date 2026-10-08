import QtQuick
import QtWebChannel
import QtWebEngine

/* Host del prototipo web: la MISMA ventana (224x224, transparente, sin foco)
   que el lado QML, con el canvas corriendo en QtWebEngine.
   El QWebChannel se crea aca (la propiedad webChannel del view es
   QQmlWebChannel y no tiene binding PySide): el bridge Python entra con
   registerBridge() desde el runner. */
Window {
    id: host
    title: "Instant bakeoff overlay v2 (web)"
    width: 224
    height: 224
    color: "transparent"
    flags: Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowDoesNotAcceptFocus
    visible: true

    property url page

    WebChannel {
        id: channel
    }

    WebEngineView {
        id: view
        objectName: "view"
        anchors.fill: parent
        url: host.page
        webChannel: channel
        backgroundColor: "transparent"
    }

    function registerBridge(obj) {
        channel.registerObject("bridge", obj)
    }
}
