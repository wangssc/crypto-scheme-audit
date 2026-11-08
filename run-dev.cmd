@echo off
chcp 65001 >nul
cd /d "%~dp0"

rem ---------------------------------------------------------------------
rem 开发用启动：直接跑源码版，不打包。
rem 改完 ui/index.html 只要刷新浏览器（Ctrl+R）就能看到效果，
rem 不用每次等 PyInstaller 打三十秒。
rem
rem 只有改了 .py 才需要停掉窗口重开。
rem ---------------------------------------------------------------------

set "PY="
if exist "C:\Users\32719\.workbuddy\binaries\python\versions\3.13.12\python.exe" (
    set "PY=C:\Users\32719\.workbuddy\binaries\python\versions\3.13.12\python.exe"
)
if not defined PY (
    for /f "delims=" %%i in ('where python 2^>nul') do (
        set "PY=%%i"
        goto :got_py
    )
)
:got_py
if not defined PY (
    echo.
    echo   找不到 python。
    echo   请先装 Python 3.10 以上，并执行：pip install python-docx
    echo.
    pause
    exit /b 2
)

echo 解释器：%PY%
echo 启动中，浏览器会自动打开。关掉这个窗口就退出。
echo.

"%PY%" app.py
set "CODE=%ERRORLEVEL%"

echo.
if not "%CODE%"=="0" echo 退出码 %CODE% —— 上面有报错信息。
echo 服务已退出。
pause
