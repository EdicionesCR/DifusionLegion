"""
Rutas de recursos y datos para Difusion Legion.

- En desarrollo: usa la carpeta del proyecto.
- En .exe PyInstaller: usa la carpeta donde esta el ejecutable para datos
  persistentes, y la carpeta temporal de PyInstaller solo para recursos.
"""

from pathlib import Path
import os
import sys


APP_NAME = "Difusion Legion"


def app_base_dir():
    """Carpeta estable de la aplicacion."""

    if getattr(sys, "frozen", False):
        ejecutable = Path(sys.executable).resolve()

        if (
            sys.platform == "darwin"
            and ejecutable.parent.name == "MacOS"
            and ejecutable.parent.parent.name == "Contents"
        ):
            return ejecutable.parent.parent.parent

        return ejecutable.parent

    return Path(__file__).resolve().parent


def app_data_dir():
    """Carpeta escribible para sesiones, logs y datos persistentes."""

    if not getattr(sys, "frozen", False):
        return app_base_dir().joinpath("data")

    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / APP_NAME

    if os.name == "nt":
        return app_base_dir().joinpath("data")

    xdg_data_home = os.environ.get("XDG_DATA_HOME")
    if xdg_data_home:
        return Path(xdg_data_home) / APP_NAME

    return Path.home() / ".local" / "share" / APP_NAME


def resource_path(*parts):
    """Ruta a un recurso empaquetado, como assets/icon.ico."""

    pyinstaller_temp = getattr(sys, "_MEIPASS", None)

    if pyinstaller_temp:
        return Path(pyinstaller_temp).joinpath(*parts)

    return app_base_dir().joinpath(*parts)


def data_path(*parts):
    """Ruta a datos persistentes al lado del proyecto o del .exe."""

    return app_data_dir().joinpath(*parts)


def ensure_data_dir(*parts):
    """Crea y devuelve una carpeta dentro de data/."""

    carpeta = data_path(*parts)
    carpeta.mkdir(parents=True, exist_ok=True)
    return carpeta
