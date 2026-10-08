"""Qt Quick overlay hook, tested against and pinned to PyInstaller 6.22.3."""
from pathlib import Path, PurePath

from PyInstaller.utils.hooks.qt import add_qt6_dependencies, pyside6_library_info

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)

# PyInstaller's default QtQml hook scans every installed QML plugin; that
# added about 120 MB to Instant. This pinned private helper preserves its
# plugin dependency validation while restricting collection to our imports.
_QML_MODULES = (
    # Los hosts web (overlay y panel) solo necesitan Window, el canal
    # QWebChannel y WebEngineView.
    "QtQuick",
    "QtQuick/Window",
    "QtWebChannel",
    "QtWebEngine",
)
_qml_root = Path(pyside6_library_info.location["QmlImportsPath"]).resolve()
_qml_dest = PurePath(pyside6_library_info.qt_rel_dir) / "qml"

for _module in _QML_MODULES:
    _qmldir = _qml_root.joinpath(*_module.split("/"), "qmldir")
    if not _qmldir.is_file():
        raise FileNotFoundError(f"Missing required Qt Quick QML module: {_qmldir}")
    _module_binaries, _module_datas = pyside6_library_info._process_qml_plugin(_qmldir)
    for _source in _module_binaries:
        _relative = Path(_source).resolve().relative_to(_qml_root)
        binaries.append((str(_source), str(_qml_dest / _relative.parent)))
    for _source in _module_datas:
        _source = Path(_source).resolve()
        _relative = _source.relative_to(_qml_root)
        _destination = _qml_dest / (_relative if _source.is_dir() else _relative.parent)
        datas.append((str(_source), str(_destination)))
