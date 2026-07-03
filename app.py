"""
Difusion Legion v1.0
Punto de entrada de la aplicacion.
"""

import sys
from tkinter import Tk, messagebox, PhotoImage

from paths import resource_path
from ui.login_window import LoginWindow


class DifusionLegionApp:

    def __init__(self):
        self.root = Tk()
        self.root.title("Difusión Legión")
        self.root.geometry("520x420")
        self.root.resizable(False, False)

        self.aplicar_icono()
        self.centrar_ventana(520, 420)
        LoginWindow(self.root)

    def aplicar_icono(self):
        icono_ico = resource_path("assets", "icon.ico")
        icono_png = resource_path("assets", "icon.png")

        if sys.platform == "darwin":
            try:
                if icono_png.exists() and icono_png.stat().st_size > 0:
                    imagen = PhotoImage(file=str(icono_png))
                    self.root.iconphoto(True, imagen)
                    self.root._icon_photo = imagen
            except Exception:
                pass
            return

        try:
            if icono_ico.exists() and icono_ico.stat().st_size > 0:
                self.root.iconbitmap(str(icono_ico))
        except Exception:
            pass

        try:
            if icono_png.exists() and icono_png.stat().st_size > 0:
                imagen = PhotoImage(file=str(icono_png))
                self.root.iconphoto(True, imagen)
                self.root._icon_photo = imagen
        except Exception:
            pass

    def centrar_ventana(self, ancho, alto):
        self.root.update_idletasks()
        pantalla_ancho = self.root.winfo_screenwidth()
        pantalla_alto = self.root.winfo_screenheight()
        x = int((pantalla_ancho / 2) - (ancho / 2))
        y = int((pantalla_alto / 2) - (alto / 2))
        self.root.geometry(f"{ancho}x{alto}+{x}+{y}")

    def ejecutar(self):
        self.root.mainloop()


if __name__ == "__main__":
    try:
        app = DifusionLegionApp()
        app.ejecutar()
    except Exception as e:
        messagebox.showerror("Error", str(e))
