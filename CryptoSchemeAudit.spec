# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

为什么用 spec 文件而不是一串命令行参数：

1. `audit.py` 里是 `__import__("checks." + name)` 动态导入，PyInstaller 的静态
   分析看不到这些模块，不显式收集的话打出来的 exe 一跑就报 ModuleNotFoundError。
   这里用 collect_submodules("checks") 兜住，以后 checks/ 里再加文件也不用改配置。
2. console=False：双击运行时不能弹黑框。
3. onefile：用户只需要一个 exe，不用管 _internal 目录往哪放。
4. excludes 里排掉的是体积大头，本项目一个都用不到（docx 只依赖 lxml）。
"""

from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("checks")

a = Analysis(
    ["app.py"],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "numpy",
        "pandas",
        "matplotlib",
        "scipy",
        "PIL",
        "PyQt5",
        "PySide2",
        "PySide6",
        "IPython",
        "pytest",
        "setuptools",
        "pip",
        "wheel",
    ],
    noarchive=False,
    optimize=0,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="密码应用方案自检",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="D:/aa/密评Copilot/tools/app.ico",
)
