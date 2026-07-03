# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path

from PyInstaller.utils.hooks import collect_all


selenium_datas, selenium_binaries, selenium_hiddenimports = collect_all("selenium")
datas = [("assets", "assets")] + selenium_datas

if Path("drivers").exists():
    datas.append(("drivers", "drivers"))

block_cipher = None

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=selenium_binaries,
    datas=datas,
    hiddenimports=selenium_hiddenimports
    + [
        "selenium.webdriver",
        "selenium.webdriver.chrome",
        "selenium.webdriver.chrome.webdriver",
        "selenium.webdriver.chrome.options",
        "selenium.webdriver.chrome.service",
        "selenium.webdriver.edge",
        "selenium.webdriver.edge.webdriver",
        "selenium.webdriver.edge.options",
        "selenium.webdriver.edge.service",
        "selenium.webdriver.common.by",
        "selenium.webdriver.common.keys",
        "selenium.webdriver.support",
        "selenium.webdriver.support.ui",
        "selenium.webdriver.support.expected_conditions",
        "PIL",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["win32clipboard", "win32con", "pythoncom", "pywintypes"],
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Difusion Legion",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="assets/icon.icns",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="Difusion Legion",
)

app = BUNDLE(
    coll,
    name="Difusion Legion.app",
    icon="assets/icon.icns",
    bundle_identifier="org.edicionescristorey.difusionlegion",
    info_plist={
        "CFBundleDisplayName": "Difusion Legion",
        "CFBundleName": "Difusion Legion",
        "CFBundleShortVersionString": "1.0.0",
        "CFBundleVersion": "1.0.0",
        "NSHighResolutionCapable": True,
    },
)
