# Difusion Legion para macOS

Esta carpeta esta preparada para generar una app de macOS sin requerir Python en la computadora del usuario final.

## Importante

El archivo `.app` de macOS debe construirse desde una Mac. PyInstaller no genera binarios de macOS desde Windows.

La Mac del usuario final no necesita Python, pero si necesita tener instalado Google Chrome o Microsoft Edge. En macOS la app intenta abrir Chrome primero y Edge como respaldo.

La primera ejecucion puede necesitar internet para que Selenium obtenga el driver compatible con el navegador. Si queres evitar eso, podes incluir `chromedriver` o `msedgedriver` dentro de una carpeta `drivers/` antes de construir la app.

## Construir la app

En una Mac, abre Terminal dentro de esta carpeta y ejecuta:

```bash
chmod +x build_macos.sh
./build_macos.sh
```

El resultado queda en:

```text
dist/Difusion Legion.app
dist/Difusion Legion-macOS.zip
```

## Apple Silicon e Intel

El build normalmente queda para la arquitectura de la Mac donde se compila. Para cubrir Apple Silicon e Intel de forma prolija, conviene generar un build en cada arquitectura o usar un Python universal2 y ajustar PyInstaller para universal2.

## Aviso de seguridad de macOS

El script aplica una firma local ad-hoc si `codesign` esta disponible. Para distribuir la app fuera de tu equipo, Apple puede mostrar advertencias si no esta firmada y notarizada con una cuenta Apple Developer.

Para pruebas internas, si macOS bloquea la app descargada, prueba abrirla con clic derecho > Abrir.
