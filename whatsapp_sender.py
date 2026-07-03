"""
Funciones de bajo nivel para enviar mensajes con WhatsApp Web.

Parche v9: abre el chat real, maneja flyers de forma estable, salta
automaticamente los numeros que WhatsApp informa como no registrados,
usa un envio robusto para la vista previa de imagenes, intenta enviar
el mensaje como caption/pie del flyer y fuerza el adjunto como foto
normal, no como sticker.
"""

import os
import io
import re
import time
import tempfile
import unicodedata
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.parse import quote

from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys

from paths import ensure_data_dir


MENSAJES_CAJA = (
    "message",
    "mensaje",
    "mensagem",
    "nachricht",
    "messaggio",
    "bericht",
    "type a message",
    "escribe un mensaje",
    "escribir mensaje",
    "escribi un mensaje",
    "escribí un mensaje",
    "digite uma mensagem",
)

MENSAJES_BUSQUEDA = (
    "search",
    "buscar",
    "pesquisar",
    "rechercher",
    "cerca",
)


class WhatsAppNumeroNoDisponibleError(Exception):
    """WhatsApp Web indico que el numero no esta registrado o no es contactable."""


def _convertir_numero_excel_si_corresponde(texto):
    """
    Algunos CSV exportados desde Excel pueden traer telefonos como 54911...0,
    5.4911E+12 o 5491112345678.0. Antes de sacar caracteres, intentamos
    convertir esos casos a un entero en texto para no perder digitos.
    """

    texto = str(texto or "").strip()

    if not texto:
        return ""

    candidato = texto.replace(" ", "").replace(",", ".")

    if not re.fullmatch(r"\+?\d+(?:\.\d+)?(?:e[+-]?\d+)?", candidato, re.I):
        return texto

    try:
        valor = Decimal(candidato.lstrip("+"))
    except (InvalidOperation, ValueError):
        return texto

    try:
        if valor == valor.to_integral_value():
            return format(valor.quantize(Decimal(1)), "f")
    except (InvalidOperation, ValueError):
        pass

    return texto


def _solo_digitos(numero):
    texto = _convertir_numero_excel_si_corresponde(numero)
    return re.sub(r"\D", "", texto)


def _quitar_quince_local(numero_nacional):
    """
    Convierte formatos argentinos locales con 15 al formato nacional movil.

    Ejemplos:
    111512345678  -> 1112345678
    351151234567  -> 3511234567
    221156123456  -> 2216123456
    """

    numero_nacional = str(numero_nacional or "").strip()

    while numero_nacional.startswith("0"):
        numero_nacional = numero_nacional[1:]

    if len(numero_nacional) == 12:
        if numero_nacional.startswith("11") and numero_nacional[2:4] == "15":
            return numero_nacional[:2] + numero_nacional[4:]

        if numero_nacional[3:5] == "15":
            return numero_nacional[:3] + numero_nacional[5:]

        if numero_nacional[4:6] == "15":
            return numero_nacional[:4] + numero_nacional[6:]

    return numero_nacional


def normalizar_numero_argentina(numero, area_por_defecto="11"):
    """
    Normaliza numeros para WhatsApp Web usando Argentina como pais por defecto.

    Acepta formatos como:
    - 54911XXXXXXXX
    - +54 9 11 XXXX-XXXX
    - 54 11 XXXX-XXXX
    - 011 15 XXXX-XXXX
    - 11 15 XXXX-XXXX
    - 15 XXXX-XXXX (usa area_por_defecto=11)
    - XXXX-XXXX (usa area_por_defecto=11)
    """

    digitos = _solo_digitos(numero)

    if not digitos:
        raise Exception("El numero de WhatsApp esta vacio o no es valido")

    while digitos.startswith("00"):
        digitos = digitos[2:]

    if digitos.startswith("549"):
        return digitos

    if digitos.startswith("54"):
        nacional = digitos[2:]

        while nacional.startswith("0"):
            nacional = nacional[1:]

        if nacional.startswith("9"):
            nacional = nacional[1:]

        nacional = _quitar_quince_local(nacional)

        if nacional.startswith("15") and len(nacional) == 10:
            nacional = area_por_defecto + nacional[2:]

        if len(nacional) == 8:
            nacional = area_por_defecto + nacional

        return "549" + nacional

    while digitos.startswith("0"):
        digitos = digitos[1:]

    if digitos.startswith("9") and len(digitos) >= 11:
        digitos = digitos[1:]

    if digitos.startswith("15") and len(digitos) == 10:
        digitos = area_por_defecto + digitos[2:]
    else:
        digitos = _quitar_quince_local(digitos)

    if len(digitos) == 8:
        digitos = area_por_defecto + digitos

    if len(digitos) < 10:
        raise Exception(
            "El numero de WhatsApp parece incompleto. "
            "Revisa el CSV o escribilo con codigo de area."
        )

    return "549" + digitos


def limpiar_numero(numero):
    return normalizar_numero_argentina(numero)


def _ruta_logs():
    return ensure_data_dir("logs")


def _guardar_diagnostico(driver, contexto):
    try:
        carpeta = _ruta_logs()
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        base = carpeta / f"whatsapp_error_{contexto}_{timestamp}"

        try:
            driver.save_screenshot(str(base.with_suffix(".png")))
        except Exception:
            pass

        try:
            base.with_suffix(".html").write_text(
                driver.page_source,
                encoding="utf-8",
                errors="ignore",
            )
        except Exception:
            pass

        return str(base.with_suffix(".png"))
    except Exception:
        return None


def _texto_pagina(driver):
    try:
        return driver.execute_script(
            "return document.body ? document.body.innerText : '';"
        ) or ""
    except Exception:
        return ""


def _normalizar_texto_busqueda(texto):
    texto = str(texto or "")
    texto = unicodedata.normalize("NFKD", texto)
    texto = "".join(
        caracter
        for caracter in texto
        if not unicodedata.combining(caracter)
    )
    return texto.lower()


def _cerrar_dialogo_whatsapp(driver):
    """Cierra modales de WhatsApp como "el numero no esta en WhatsApp"."""

    xpaths = (
        '//button[normalize-space()="OK" or normalize-space()="Ok" or normalize-space()="Aceptar" or normalize-space()="ACEPTAR"]',
        '//*[@role="button" and (normalize-space()="OK" or normalize-space()="Ok" or normalize-space()="Aceptar" or normalize-space()="ACEPTAR")]',
        '//*[normalize-space()="OK" or normalize-space()="Ok" or normalize-space()="Aceptar" or normalize-space()="ACEPTAR"]/ancestor::*[@role="button" or self::button][1]',
    )

    for xpath in xpaths:
        try:
            elementos = driver.find_elements(By.XPATH, xpath)
            for elemento in elementos:
                try:
                    if elemento.is_displayed() and elemento.is_enabled():
                        try:
                            elemento.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", elemento)
                        time.sleep(0.5)
                        return True
                except Exception:
                    continue
        except Exception:
            continue

    try:
        ActionChains(driver).send_keys(Keys.ESCAPE).perform()
        time.sleep(0.5)
        return True
    except Exception:
        return False


def _detectar_estado_bloqueante(driver):
    texto_original = _texto_pagina(driver)
    texto = texto_original.lower()
    texto_simple = _normalizar_texto_busqueda(texto_original)
    url = ""

    try:
        url = driver.current_url
    except Exception:
        pass

    patrones_numero_no_whatsapp = (
        "no esta en whatsapp",
        "no esta en whats app",
        "isn't on whatsapp",
        "is not on whatsapp",
        "not on whatsapp",
        "not registered on whatsapp",
        "no es usuario de whatsapp",
        "no esta registrado en whatsapp",
        "phone number shared via url is invalid",
        "phone number shared via link is invalid",
        "numero de telefono compartido a traves de la url no es valido",
        "numero de telefono compartido a traves del enlace no es valido",
        "numero de telefone compartilhado via url e invalido",
        "numero de telefone compartilhado via link e invalido",
    )

    if any(patron in texto_simple for patron in patrones_numero_no_whatsapp):
        _cerrar_dialogo_whatsapp(driver)
        raise WhatsAppNumeroNoDisponibleError(
            "WhatsApp informa que este numero no esta registrado o no permite abrir chat directo. Se omitio este contacto."
        )

    patrones_numero_invalido = (
        "phone number shared via url is invalid",
        "phone number shared via link is invalid",
        "número de teléfono compartido a través de la url no es válido",
        "numero de telefono compartido a traves de la url no es valido",
        "número de teléfono compartido a través del enlace no es válido",
        "numero de telefono compartido a traves del enlace no es valido",
        "número de telefone compartilhado via url é inválido",
        "numero de telefone compartilhado via url e invalido",
    )

    if any(patron in texto for patron in patrones_numero_invalido):
        _cerrar_dialogo_whatsapp(driver)
        raise WhatsAppNumeroNoDisponibleError(
            "WhatsApp Web indica que el numero no es valido o no esta registrado. Se omitio este contacto."
        )

    patrones_sesion = (
        "use whatsapp on your computer",
        "para usar whatsapp en tu computadora",
        "usa whatsapp en tu computadora",
        "link with phone number",
        "vincular con el número de teléfono",
        "vincular con el numero de telefono",
        "scan the qr code",
        "escanea el código qr",
        "escanea el codigo qr",
        "escaneá el código qr",
    )

    if any(patron in texto for patron in patrones_sesion):
        return (
            "WhatsApp Web todavia no esta conectado en esta ventana. "
            "Escanea el QR o termina de vincular la sesion y volve a probar."
        )

    if "web.whatsapp.com" not in url.lower():
        return (
            "El navegador no esta en WhatsApp Web. "
            "Volve a conectar WhatsApp desde la app y proba otra vez."
        )

    return None

def _esperar_carga_basica(driver, timeout=30):
    fin = time.time() + timeout

    while time.time() < fin:
        try:
            estado = driver.execute_script("return document.readyState")
            if estado in ("interactive", "complete"):
                return
        except Exception:
            pass
        time.sleep(0.25)


def _es_visible_y_habilitado(elemento):
    try:
        return elemento.is_displayed() and elemento.is_enabled()
    except Exception:
        return False


def _esta_en_footer(driver, elemento):
    try:
        return bool(
            driver.execute_script(
                "return !!arguments[0].closest('footer');",
                elemento,
            )
        )
    except Exception:
        return False


def _texto_atributos(elemento):
    partes = []
    for atributo in (
        "aria-label",
        "aria-placeholder",
        "placeholder",
        "title",
        "role",
        "data-tab",
    ):
        try:
            partes.append(elemento.get_attribute(atributo) or "")
        except Exception:
            pass
    return " ".join(partes).lower()


def _es_caja_mensaje(driver, elemento):
    attrs = _texto_atributos(elemento)

    if any(palabra in attrs for palabra in MENSAJES_BUSQUEDA):
        return False

    # La caja correcta de WhatsApp esta en el footer del chat. En la pantalla
    # principal solo existe el buscador; ese no sirve para enviar.
    if _esta_en_footer(driver, elemento):
        return True

    if any(palabra in attrs for palabra in MENSAJES_CAJA):
        return True

    return False


def _contenido_caja(driver, caja):
    try:
        texto = driver.execute_script(
            "return arguments[0].innerText || arguments[0].textContent || '';",
            caja,
        )
        return (texto or "").strip()
    except Exception:
        try:
            return (caja.text or "").strip()
        except Exception:
            return ""


def _buscar_caja_mensaje(driver, timeout=60):
    fin = time.time() + timeout
    ultimo_estado = None

    while time.time() < fin:
        estado = _detectar_estado_bloqueante(driver)
        if estado:
            ultimo_estado = estado

        try:
            elementos = driver.find_elements(By.CSS_SELECTOR, '[contenteditable="true"]')
            candidatos = []
            for elemento in elementos:
                if not _es_visible_y_habilitado(elemento):
                    continue
                if _es_caja_mensaje(driver, elemento):
                    score = 100 if _esta_en_footer(driver, elemento) else 10
                    candidatos.append((score, elemento))
            if candidatos:
                candidatos.sort(key=lambda item: item[0], reverse=True)
                return candidatos[0][1]
        except Exception:
            pass

        time.sleep(0.5)

    captura = _guardar_diagnostico(driver, "chat_no_abierto")
    detalle = ultimo_estado or (
        "No se abrio el chat del destinatario. WhatsApp Web quedo en la pantalla principal "
        "o todavia esta cargando. Revisa que el numero tenga codigo de pais y que WhatsApp "
        "este conectado."
    )

    if captura:
        detalle += f"\n\nCaptura guardada en:\n{captura}"

    raise Exception(detalle)


def _buscar_visible(driver, localizadores, timeout=30):
    fin = time.time() + timeout

    while time.time() < fin:
        for by, selector in localizadores:
            try:
                elementos = driver.find_elements(by, selector)
                for elemento in elementos:
                    if _es_visible_y_habilitado(elemento):
                        return elemento
            except Exception:
                pass
        time.sleep(0.4)

    return None


def _elemento_clickable(driver, elemento):
    try:
        return driver.execute_script(
            """
            let e = arguments[0];
            while (e && e !== document.body) {
                const tag = (e.tagName || '').toLowerCase();
                const role = e.getAttribute && e.getAttribute('role');
                if (tag === 'button' || role === 'button') return e;
                e = e.parentElement;
            }
            return arguments[0];
            """,
            elemento,
        )
    except Exception:
        return elemento


def _click(driver, elemento):
    elemento = _elemento_clickable(driver, elemento)
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
            elemento,
        )
        time.sleep(0.1)
    except Exception:
        pass

    try:
        ActionChains(driver).move_to_element(elemento).pause(0.05).click().perform()
        return
    except Exception:
        pass

    try:
        elemento.click()
        return
    except Exception:
        pass

    driver.execute_script("arguments[0].click();", elemento)


def _buscar_boton_enviar_por_js(driver):
    # WhatsApp Web cambia seguido los selectores del boton Enviar, sobre todo
    # en la vista previa de imagenes. Esta busqueda mira atributos visibles
    # como aria-label, title, data-icon y data-testid.
    try:
        return driver.execute_script(
            r'''
            const candidatos = [];
            const palabrasEnviar = [
                'send', 'enviar', 'mandar', 'envoyer', 'invia', 'senden',
                'enviar mensaje', 'send message'
            ];
            const palabrasEvitar = [
                'reenviar', 'forward', 'resend', 'reply', 'responder',
                'documento', 'document', 'archivo', 'file', 'buscar', 'search',
                'descargar', 'download'
            ];

            function visible(el) {
                if (!el) return false;
                const rect = el.getBoundingClientRect();
                if (!rect || rect.width <= 0 || rect.height <= 0) return false;
                const style = window.getComputedStyle(el);
                if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
                if (parseFloat(style.opacity || '1') === 0) return false;
                if (rect.bottom < 0 || rect.right < 0) return false;
                if (rect.top > window.innerHeight || rect.left > window.innerWidth) return false;
                return true;
            }

            function clickable(el) {
                let actual = el;
                for (let i = 0; actual && i < 6; i++) {
                    const tag = (actual.tagName || '').toLowerCase();
                    const role = (actual.getAttribute('role') || '').toLowerCase();
                    if (tag === 'button' || role === 'button') return actual;
                    actual = actual.parentElement;
                }
                return el;
            }

            function textoAtributos(el) {
                const attrs = [
                    'aria-label', 'title', 'data-icon', 'data-testid',
                    'aria-description', 'name', 'class'
                ];
                let texto = '';
                for (const attr of attrs) {
                    texto += ' ' + (el.getAttribute(attr) || '');
                }
                texto += ' ' + (el.innerText || '');
                return texto.toLowerCase();
            }

            const elementos = document.querySelectorAll(
                'button, [role="button"], span[data-icon], div[data-icon], ' +
                '[data-testid], [aria-label], [title]'
            );

            for (const el of elementos) {
                const texto = textoAtributos(el);
                const tieneEnviar = palabrasEnviar.some(p => texto.includes(p));
                const iconoEnviar = /(^|\s|_|-)(send|send-filled|wds-ic-send-filled|send-message)(\s|_|-|$)/.test(texto);

                if (!tieneEnviar && !iconoEnviar) continue;
                if (palabrasEvitar.some(p => texto.includes(p)) && !iconoEnviar) continue;

                const boton = clickable(el);
                if (!visible(boton)) continue;

                const rect = boton.getBoundingClientRect();
                let score = 0;

                // En la vista previa de imagenes, el boton suele estar abajo a la derecha.
                score += rect.left / 10;
                score += rect.top / 20;

                if (iconoEnviar) score += 1000;
                if ((boton.getAttribute('aria-label') || '').toLowerCase().includes('enviar')) score += 300;
                if ((boton.getAttribute('aria-label') || '').toLowerCase().includes('send')) score += 300;
                if (boton.closest('footer')) score += 200;
                if (boton.closest('[role="dialog"]')) score += 200;

                candidatos.push({boton, score});
            }

            candidatos.sort((a, b) => b.score - a.score);
            return candidatos.length ? candidatos[0].boton : null;
            '''
        )
    except Exception:
        return None


def _buscar_boton_enviar(driver, timeout=20):
    localizadores = (
        (By.XPATH, '//button[.//*[contains(@data-icon, "send")]]'),
        (By.XPATH, '//*[@role="button" and .//*[contains(@data-icon, "send")]]'),
        (By.XPATH, '//*[contains(@data-icon, "send")]/ancestor::*[@role="button" or self::button][1]'),
        (By.XPATH, '//*[contains(@data-testid, "send")]/ancestor::*[@role="button" or self::button][1]'),
        (By.CSS_SELECTOR, 'button[aria-label="Send"]'),
        (By.CSS_SELECTOR, 'button[aria-label="Enviar"]'),
        (By.CSS_SELECTOR, 'div[aria-label="Send"]'),
        (By.CSS_SELECTOR, 'div[aria-label="Enviar"]'),
        (By.CSS_SELECTOR, '[aria-label*="Send"]'),
        (By.CSS_SELECTOR, '[aria-label*="Enviar"]'),
        (By.CSS_SELECTOR, 'span[data-icon*="send"]'),
        (By.CSS_SELECTOR, 'div[data-icon*="send"]'),
        (By.CSS_SELECTOR, '[data-testid*="send"]'),
    )

    fin = time.time() + timeout

    while time.time() < fin:
        try:
            estado = _detectar_estado_bloqueante(driver)
            if estado:
                time.sleep(0.5)
                continue
        except WhatsAppNumeroNoDisponibleError:
            raise
        except Exception:
            pass

        for by, selector in localizadores:
            try:
                elementos = driver.find_elements(by, selector)
                for elemento in elementos:
                    candidato = _elemento_clickable(driver, elemento)
                    if _es_visible_y_habilitado(candidato):
                        return candidato
                    if _es_visible_y_habilitado(elemento):
                        return elemento
            except Exception:
                pass

        candidato_js = _buscar_boton_enviar_por_js(driver)
        if candidato_js is not None:
            return candidato_js

        time.sleep(0.4)

    return None


def _enviar_con_enter(driver, caja=None):
    try:
        if caja is not None:
            try:
                caja.click()
            except Exception:
                pass
            try:
                caja.send_keys(Keys.ENTER)
                return True
            except Exception:
                pass

        ActionChains(driver).send_keys(Keys.ENTER).perform()
        return True
    except Exception:
        return False


def _pulsar_enviar(driver, caja=None, timeout=20, permitir_enter=True):
    boton = _buscar_boton_enviar(driver, timeout=timeout)
    if boton is not None:
        _click(driver, boton)
        time.sleep(2)
        return

    # En la vista previa de imagenes de WhatsApp, a veces el boton no expone
    # selector estable pero Enter envia el adjunto seleccionado. Lo usamos como
    # respaldo para no frenar la campaña.
    if permitir_enter and _enviar_con_enter(driver, caja=caja):
        time.sleep(3)
        return

    captura = _guardar_diagnostico(driver, "no_boton_enviar")
    detalle = "No se encontro el boton de enviar de WhatsApp Web."
    if captura:
        detalle += f"\n\nCaptura guardada en:\n{captura}"
    raise Exception(detalle)


def _hay_caja_footer_visible(driver):
    try:
        elementos = driver.find_elements(By.CSS_SELECTOR, '[contenteditable="true"]')
        for elemento in elementos:
            if _es_visible_y_habilitado(elemento) and _esta_en_footer(driver, elemento):
                return True
    except Exception:
        pass
    return False


def _esperar_fin_preview_adjunto(driver, timeout=35):
    fin = time.time() + timeout
    while time.time() < fin:
        try:
            estado = _detectar_estado_bloqueante(driver)
            if estado:
                time.sleep(0.5)
                continue
        except WhatsAppNumeroNoDisponibleError:
            raise
        except Exception:
            pass

        if _hay_caja_footer_visible(driver):
            return True

        time.sleep(0.5)

    return False


def _hacer_foco_seguro(driver, elemento):
    try:
        driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center', inline: 'center'});",
            elemento,
        )
        time.sleep(0.1)
    except Exception:
        pass

    try:
        ActionChains(driver).move_to_element(elemento).pause(0.05).click().perform()
        return True
    except Exception:
        pass

    try:
        elemento.click()
        return True
    except Exception:
        pass

    try:
        driver.execute_script("arguments[0].focus();", elemento)
        return True
    except Exception:
        return False


def _enviar_teclas_a_caja(driver, caja, texto):
    try:
        caja.send_keys(texto)
        return True
    except Exception:
        pass

    try:
        ActionChains(driver).send_keys(texto).perform()
        return True
    except Exception:
        return False


def _escribir_mensaje_seguro(driver, caja, mensaje):
    _hacer_foco_seguro(driver, caja)
    time.sleep(0.2)

    lineas = str(mensaje).split("\n")
    for indice, linea in enumerate(lineas):
        if indice > 0:
            try:
                ActionChains(driver).key_down(Keys.SHIFT).send_keys(
                    Keys.ENTER
                ).key_up(Keys.SHIFT).perform()
            except Exception:
                caja.send_keys(Keys.SHIFT, Keys.ENTER)
            time.sleep(0.05)

        if linea:
            if not _enviar_teclas_a_caja(driver, caja, linea):
                raise Exception("No se pudo escribir el texto en WhatsApp Web.")
            time.sleep(0.03)


def _escribir_mensaje(driver, caja, mensaje):
    _escribir_mensaje_seguro(driver, caja, mensaje)


def _buscar_caja_caption(driver, timeout=25):
    """Busca la caja de caption/pie de imagen en la vista previa del flyer.

    WhatsApp Web cambia seguido los atributos de esta caja. Por eso no usamos
    un unico selector: filtramos cajas contenteditable visibles, descartamos el
    buscador y evitamos la caja normal del chat cuando queda tapada por la
    vista previa del adjunto.
    """

    fin = time.time() + timeout

    while time.time() < fin:
        try:
            estado = _detectar_estado_bloqueante(driver)
            if estado:
                time.sleep(0.4)
                continue
        except WhatsAppNumeroNoDisponibleError:
            raise
        except Exception:
            pass

        try:
            caja = driver.execute_script(
                r"""
                const candidatos = [];
                const positivos = [
                    'caption', 'add a caption', 'comentario', 'comentario opcional',
                    'agrega un comentario', 'agregar un comentario',
                    'anade un comentario', 'añade un comentario',
                    'leyenda', 'pie de foto', 'type a message',
                    'escribe un mensaje', 'escribir un mensaje', 'digite uma mensagem'
                ];
                const negativos = [
                    'search', 'buscar', 'pesquisar', 'rechercher', 'cerca',
                    'filtrar', 'filter'
                ];

                function norm(s) {
                    return (s || '')
                        .normalize('NFD')
                        .replace(/[\u0300-\u036f]/g, '')
                        .toLowerCase();
                }

                function visible(el) {
                    if (!el) return false;
                    const rect = el.getBoundingClientRect();
                    if (!rect || rect.width <= 0 || rect.height <= 0) return false;
                    const style = window.getComputedStyle(el);
                    if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
                    if (parseFloat(style.opacity || '1') === 0) return false;
                    if (rect.bottom < 0 || rect.right < 0) return false;
                    if (rect.top > window.innerHeight || rect.left > window.innerWidth) return false;
                    return true;
                }

                function alFrente(el) {
                    const rect = el.getBoundingClientRect();
                    const x = Math.max(0, Math.min(window.innerWidth - 1, rect.left + rect.width / 2));
                    const y = Math.max(0, Math.min(window.innerHeight - 1, rect.top + rect.height / 2));
                    let top = document.elementFromPoint(x, y);
                    if (!top) return false;
                    return top === el || el.contains(top) || top.contains(el);
                }

                function attrs(el) {
                    const nombres = [
                        'aria-label', 'aria-placeholder', 'placeholder', 'title',
                        'role', 'data-tab', 'data-lexical-editor', 'class'
                    ];
                    let texto = '';
                    for (const n of nombres) texto += ' ' + (el.getAttribute(n) || '');
                    texto += ' ' + (el.innerText || '');
                    texto += ' ' + (el.textContent || '');
                    return norm(texto);
                }

                const elementos = document.querySelectorAll('[contenteditable="true"], textarea');

                for (const el of elementos) {
                    if (!visible(el)) continue;
                    if (!alFrente(el)) continue;

                    const texto = attrs(el);
                    if (negativos.some(p => texto.includes(p))) continue;

                    const rect = el.getBoundingClientRect();
                    let score = 0;

                    if (positivos.some(p => texto.includes(norm(p)))) score += 1000;
                    if (!el.closest('footer')) score += 400;
                    if (el.closest('[role="dialog"]')) score += 300;
                    if (texto.includes('data-lexical-editor') || texto.includes('true')) score += 50;
                    if (rect.top > window.innerHeight * 0.45) score += 100;
                    if (rect.left > window.innerWidth * 0.25) score += 50;

                    // La caja normal del chat vive en footer. En preview de imagen
                    // preferimos una caja fuera del footer. Si solo existe footer,
                    // probablemente todavia no cargo la vista previa.
                    if (el.closest('footer')) score -= 600;

                    candidatos.push({el, score});
                }

                candidatos.sort((a, b) => b.score - a.score);
                if (!candidatos.length) return null;
                return candidatos[0].score > 0 ? candidatos[0].el : null;
                """
            )
            if caja is not None:
                return caja
        except Exception:
            pass

        time.sleep(0.4)

    return None


def _intentar_escribir_caption(driver, mensaje):
    if not mensaje:
        return None, False

    caja = _buscar_caja_caption(driver, timeout=25)
    if caja is None:
        return None, False

    try:
        _escribir_mensaje_seguro(driver, caja, mensaje)
        time.sleep(0.5)
        return caja, True
    except Exception:
        return caja, False


def _urls_chat(numero, mensaje=None):
    numero = limpiar_numero(numero)
    texto = ""
    if mensaje is not None:
        texto = quote(str(mensaje), safe="")

    urls = []
    if mensaje is None:
        urls.append(f"https://web.whatsapp.com/send?phone={numero}&app_absent=0")
        urls.append(f"https://web.whatsapp.com/send/?phone={numero}&type=phone_number&app_absent=0")
    else:
        urls.append(f"https://web.whatsapp.com/send?phone={numero}&text={texto}&app_absent=0")
        urls.append(f"https://web.whatsapp.com/send/?phone={numero}&text={texto}&type=phone_number&app_absent=0")
    return urls


def _abrir_chat(driver, numero, mensaje=None):
    ultimo_error = None

    for url in _urls_chat(numero, mensaje=mensaje):
        driver.get(url)
        _esperar_carga_basica(driver, timeout=30)

        try:
            return _buscar_caja_mensaje(driver, timeout=45)
        except WhatsAppNumeroNoDisponibleError:
            raise
        except Exception as e:
            ultimo_error = e
            # Segundo intento con cambio de location dentro de la misma pestana.
            try:
                driver.execute_script("window.location.href = arguments[0];", url)
                _esperar_carga_basica(driver, timeout=30)
                return _buscar_caja_mensaje(driver, timeout=45)
            except WhatsAppNumeroNoDisponibleError:
                raise
            except Exception as e2:
                ultimo_error = e2

    if ultimo_error:
        raise ultimo_error

    raise Exception("No se pudo abrir el chat de WhatsApp Web.")


def abrir_chat(driver, numero):
    _abrir_chat(driver, numero, mensaje=None)


def enviar_texto(driver, mensaje):
    caja = _buscar_caja_mensaje(driver, timeout=60)
    if not _contenido_caja(driver, caja):
        _escribir_mensaje(driver, caja, mensaje)
    _pulsar_enviar(driver, caja=caja, timeout=20)


def enviar_texto_a_numero(driver, numero, mensaje):
    caja = _abrir_chat(driver, numero, mensaje=mensaje)
    if not _contenido_caja(driver, caja):
        _escribir_mensaje(driver, caja, mensaje)
    _pulsar_enviar(driver, caja=caja, timeout=20)


def _click_boton_adjuntar(driver, timeout=30):
    localizadores = (
        (By.CSS_SELECTOR, 'button[aria-label="Attach"]'),
        (By.CSS_SELECTOR, 'button[aria-label="Adjuntar"]'),
        (By.CSS_SELECTOR, 'div[aria-label="Attach"]'),
        (By.CSS_SELECTOR, 'div[aria-label="Adjuntar"]'),
        (By.CSS_SELECTOR, 'span[data-testid="plus-rounded"]'),
        (By.CSS_SELECTOR, 'span[data-icon="attach-menu-plus"]'),
        (By.CSS_SELECTOR, 'span[data-icon="plus"]'),
        (By.CSS_SELECTOR, 'span[data-icon="clip"]'),
        (By.XPATH, '//*[@title="Attach" or @title="Adjuntar"]'),
        (By.XPATH, '//*[@data-icon="attach-menu-plus" or @data-icon="plus" or @data-icon="clip"]/ancestor::*[@role="button" or self::button][1]'),
    )

    boton = _buscar_visible(driver, localizadores, timeout=timeout)
    if boton is None:
        captura = _guardar_diagnostico(driver, "adjuntar")
        detalle = "No se encontro el boton para adjuntar archivos dentro del chat."
        if captura:
            detalle += f"\n\nCaptura guardada en:\n{captura}"
        raise Exception(detalle)

    _click(driver, boton)
    time.sleep(1)



def _seleccionar_input_archivo(driver, timeout=30):
    """Selecciona el input de Fotos/Videos y evita stickers/documentos.

    WhatsApp Web suele dejar varios <input type="file"> en el DOM. Para que el
    flyer salga como imagen normal necesitamos el input de multimedia. El input
    correcto generalmente acepta imagenes y videos; el de stickers suele
    mencionar sticker/webp y el de documentos suele aceptar cualquier archivo.
    """

    fin = time.time() + timeout

    while time.time() < fin:
        try:
            inputs = driver.find_elements(By.CSS_SELECTOR, 'input[type="file"]')
            candidatos = []

            for indice, input_archivo in enumerate(inputs):
                try:
                    accept = (input_archivo.get_attribute("accept") or "").lower()
                    aria = (input_archivo.get_attribute("aria-label") or "").lower()
                    title = (input_archivo.get_attribute("title") or "").lower()
                    outer = (input_archivo.get_attribute("outerHTML") or "").lower()

                    contexto = ""
                    try:
                        contexto = driver.execute_script(
                            r"""
                            let e = arguments[0];
                            let texto = '';
                            for (let i = 0; e && i < 8; i++) {
                                texto += ' ' + (e.innerText || '');
                                texto += ' ' + (e.getAttribute && (e.getAttribute('aria-label') || ''));
                                texto += ' ' + (e.getAttribute && (e.getAttribute('title') || ''));
                                texto += ' ' + (e.getAttribute && (e.getAttribute('data-testid') || ''));
                                texto += ' ' + (e.className || '');
                                e = e.parentElement;
                            }
                            return texto.toLowerCase();
                            """,
                            input_archivo,
                        ) or ""
                    except Exception:
                        contexto = ""

                    texto = " ".join([accept, aria, title, outer, contexto])
                    texto_simple = _normalizar_texto_busqueda(texto)
                    score = 0

                    positivos_media = (
                        "foto", "fotos", "photo", "photos", "imagen", "image",
                        "video", "videos", "camara", "camera", "galeria", "gallery",
                    )
                    if any(p in texto_simple for p in positivos_media):
                        score += 350

                    if "image/*" in accept:
                        score += 450
                    if "video" in accept:
                        score += 700
                    if "image/jpeg" in accept or "image/jpg" in accept or "image/png" in accept:
                        score += 250
                    if accept.strip() in ("*", "*/*"):
                        score -= 500

                    negativos = (
                        "sticker", "stickers", "pegatina", "pegatinas",
                        "figurinha", "figurinhas", "document", "documento",
                        "archivo", "file", "contact", "contacto", "poll", "encuesta",
                    )
                    if any(p in texto_simple for p in negativos):
                        score -= 2500

                    if "webp" in accept and "video" not in accept:
                        score -= 900
                    if accept.strip() in ("image/webp", ".webp"):
                        score -= 1500

                    candidatos.append((score, -indice, input_archivo, accept, texto_simple[:250]))
                except Exception:
                    continue

            if candidatos:
                candidatos.sort(key=lambda item: (item[0], item[1]), reverse=True)
                mejor = candidatos[0]
                if mejor[0] > 0:
                    return mejor[2]

                try:
                    carpeta = _ruta_logs()
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    diag = carpeta / f"whatsapp_inputs_archivo_{timestamp}.txt"
                    lineas = []
                    for score, neg_indice, _, accept, contexto in candidatos:
                        lineas.append(f"score={score} indice={-neg_indice} accept={accept} contexto={contexto}")
                    diag.write_text("\n".join(lineas), encoding="utf-8", errors="ignore")
                except Exception:
                    pass
                return candidatos[0][2]
        except Exception:
            pass
        time.sleep(0.4)

    captura = _guardar_diagnostico(driver, "input_archivo")
    detalle = "No se encontro el selector de archivos de WhatsApp Web."
    if captura:
        detalle += f"\n\nCaptura guardada en:\n{captura}"
    raise Exception(detalle)


def _preparar_flyer_como_jpg(archivo):
    """Crea una copia JPG temporal para evitar que WhatsApp lo trate como sticker.

    En v8 solo se convertia WEBP. En algunos equipos WhatsApp tambien toma
    ciertas imagenes cuadradas, transparentes o comprimidas como sticker. Por
    eso en v9 normalizamos siempre a JPG RGB, con fondo blanco y nombre .jpg.
    """

    archivo = os.path.abspath(archivo)

    try:
        from PIL import Image, ImageOps
    except Exception as exc:
        raise Exception(
            "Para enviar el flyer como imagen normal hace falta Pillow. "
            "Ejecuta: python -m pip install -r requirements.txt"
        ) from exc

    carpeta_tmp = Path(tempfile.gettempdir()) / "DifusionLegion"
    carpeta_tmp.mkdir(parents=True, exist_ok=True)
    salida = carpeta_tmp / f"flyer_whatsapp_imagen_{int(time.time() * 1000)}.jpg"

    with Image.open(archivo) as imagen:
        try:
            imagen.seek(0)
        except Exception:
            pass

        imagen.load()
        imagen = ImageOps.exif_transpose(imagen)

        if imagen.mode in ("RGBA", "LA") or (imagen.mode == "P" and "transparency" in imagen.info):
            if imagen.mode != "RGBA":
                imagen = imagen.convert("RGBA")
            fondo = Image.new("RGB", imagen.size, (255, 255, 255))
            fondo.paste(imagen, mask=imagen.getchannel("A"))
            imagen = fondo
        else:
            imagen = imagen.convert("RGB")

        max_lado = 2200
        ancho, alto = imagen.size
        if max(ancho, alto) > max_lado:
            proporcion = max_lado / float(max(ancho, alto))
            nuevo = (max(1, int(ancho * proporcion)), max(1, int(alto * proporcion)))
            imagen = imagen.resize(nuevo)

        imagen.save(str(salida), "JPEG", quality=94, optimize=True)

    return str(salida)


def _copiar_imagen_al_portapapeles_windows(archivo_jpg):
    """Copia la imagen al portapapeles como bitmap de Windows."""

    if os.name != "nt":
        return False

    try:
        import win32clipboard
        import win32con
        from PIL import Image
    except Exception:
        return False

    with Image.open(archivo_jpg) as imagen:
        imagen = imagen.convert("RGB")
        salida = io.BytesIO()
        imagen.save(salida, "BMP")
        datos = salida.getvalue()[14:]

    abierto = False
    try:
        win32clipboard.OpenClipboard()
        abierto = True
        win32clipboard.EmptyClipboard()
        win32clipboard.SetClipboardData(win32con.CF_DIB, datos)
        return True
    except Exception:
        return False
    finally:
        if abierto:
            try:
                win32clipboard.CloseClipboard()
            except Exception:
                pass


def _hay_preview_imagen(driver):
    try:
        return bool(
            driver.execute_script(
                r"""
                function visible(el) {
                    if (!el) return false;
                    const rect = el.getBoundingClientRect();
                    if (!rect || rect.width <= 0 || rect.height <= 0) return false;
                    const style = window.getComputedStyle(el);
                    if (!style || style.display === 'none' || style.visibility === 'hidden') return false;
                    if (parseFloat(style.opacity || '1') === 0) return false;
                    if (rect.bottom < 0 || rect.right < 0) return false;
                    if (rect.top > window.innerHeight || rect.left > window.innerWidth) return false;
                    return true;
                }

                const cajas = Array.from(document.querySelectorAll('[contenteditable="true"], textarea'))
                    .filter(el => visible(el) && !el.closest('footer'));
                if (cajas.length) return true;

                const botones = Array.from(document.querySelectorAll('button, [role="button"], span[data-icon], [data-testid]'));
                for (const el of botones) {
                    if (!visible(el)) continue;
                    const texto = ((el.getAttribute('aria-label') || '') + ' ' +
                                  (el.getAttribute('title') || '') + ' ' +
                                  (el.getAttribute('data-icon') || '') + ' ' +
                                  (el.getAttribute('data-testid') || '')).toLowerCase();
                    if ((texto.includes('send') || texto.includes('enviar')) && !el.closest('footer')) {
                        return true;
                    }
                }

                const imagenes = Array.from(document.querySelectorAll('img, canvas, video'));
                for (const el of imagenes) {
                    if (!visible(el)) continue;
                    const rect = el.getBoundingClientRect();
                    if (rect.width < 120 || rect.height < 120) continue;
                    if (el.closest('[role="dialog"]')) return true;
                    if (rect.left > window.innerWidth * 0.25 && rect.top > 80 && rect.bottom < window.innerHeight - 40) return true;
                }
                return false;
                """
            )
        )
    except Exception:
        return False


def _pegar_flyer_desde_portapapeles(driver, archivo_jpg, timeout=25):
    if not _copiar_imagen_al_portapapeles_windows(archivo_jpg):
        return False

    caja = _buscar_caja_mensaje(driver, timeout=60)
    _hacer_foco_seguro(driver, caja)
    time.sleep(0.3)

    try:
        ActionChains(driver).key_down(Keys.CONTROL).send_keys('v').key_up(Keys.CONTROL).perform()
    except Exception:
        try:
            caja.send_keys(Keys.CONTROL, 'v')
        except Exception:
            return False

    fin = time.time() + timeout
    while time.time() < fin:
        try:
            estado = _detectar_estado_bloqueante(driver)
            if estado:
                time.sleep(0.4)
                continue
        except WhatsAppNumeroNoDisponibleError:
            raise
        except Exception:
            pass

        if _hay_preview_imagen(driver):
            return True

        time.sleep(0.5)

    return False


def _enviar_preview_flyer(driver, mensaje):
    caja_caption = None
    caption_escrito = False

    if mensaje:
        caja_caption, caption_escrito = _intentar_escribir_caption(driver, mensaje)

    _pulsar_enviar(
        driver,
        caja=caja_caption if caption_escrito else None,
        timeout=60,
        permitir_enter=True,
    )

    if not _esperar_fin_preview_adjunto(driver, timeout=45):
        captura = _guardar_diagnostico(driver, "flyer_no_confirmado")
        detalle = (
            "No pude confirmar que WhatsApp haya cerrado la vista previa del flyer. "
            "Puede que la imagen todavia este cargando o que WhatsApp Web haya cambiado "
            "el boton de envio. Proba con una imagen JPG mas liviana."
        )
        if captura:
            detalle += f"\n\nCaptura guardada en:\n{captura}"
        raise Exception(detalle)

    time.sleep(2)

    if mensaje and not caption_escrito:
        enviar_texto(driver, mensaje)


def enviar_flyer(driver, ruta_imagen, mensaje=""):
    archivo = os.path.abspath(ruta_imagen)
    if not os.path.exists(archivo):
        raise Exception(f"No se encontro el flyer: {archivo}")

    _buscar_caja_mensaje(driver, timeout=60)

    archivo_para_enviar = _preparar_flyer_como_jpg(archivo)

    if _pegar_flyer_desde_portapapeles(driver, archivo_para_enviar, timeout=25):
        _enviar_preview_flyer(driver, mensaje)
        return

    _click_boton_adjuntar(driver, timeout=30)
    input_archivo = _seleccionar_input_archivo(driver, timeout=30)
    input_archivo.send_keys(archivo_para_enviar)
    time.sleep(5)
    _enviar_preview_flyer(driver, mensaje)


def enviar_flyer_a_numero(driver, numero, ruta_imagen, mensaje=""):
    _abrir_chat(driver, numero, mensaje=None)
    enviar_flyer(driver, ruta_imagen, mensaje=mensaje)
