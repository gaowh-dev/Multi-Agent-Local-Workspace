@echo off
chcp 65001 >nul 2>&1
setlocal enabledelayedexpansion

REM ============================================================
REM  Multi-Agent-Local-Workspace 一键启动脚本 (Windows)
REM  所有数据/虚拟环境均存储在 D 盘项目目录内
REM  Python 版本要求: 3.10（Python 3.14 不推荐，存在依赖兼容问题）
REM ============================================================

set "PROJECT_DIR=D:\AI\Multi-Agent-Local-Workspace"
set "VENV_DIR=%PROJECT_DIR%\venv"
set "PIP_CACHE_DIR=%PROJECT_DIR%\.pip_cache"

REM Force UTF-8 mode to avoid GBK encoding issues on Chinese Windows
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM Bypass proxy for localhost to fix Gradio "localhost not accessible" error
set NO_PROXY=127.0.0.1,localhost,::1
set no_proxy=127.0.0.1,localhost,::1

echo.
echo ============================================================
echo   Multi-Agent-Local-Workspace 启动器
echo   项目路径: %PROJECT_DIR%
echo ============================================================
echo.

REM --- 检测 Python 3.10（优先使用 py launcher）---
echo [1/5] 检查 Python 3.10 环境...

set "PYTHON_CMD="

REM 优先尝试 py -3.10
py -3.10 --version >nul 2>&1
if not errorlevel 1 (
    set "PYTHON_CMD=py -3.10"
    for /f "tokens=2" %%v in ('py -3.10 --version 2^>^&1') do set "PY_VER=%%v"
    echo       找到 Python !PY_VER! (via py launcher)
)

REM 如果 py -3.10 不可用，尝试 python 命令并检查版本
if "!PYTHON_CMD!"=="" (
    python --version >nul 2>&1
    if not errorlevel 1 (
        for /f "tokens=2" %%v in ('python --version 2^>^&1') do set "PY_VER=%%v"
        echo !PY_VER! | findstr /b "3.10" >nul
        if not errorlevel 1 (
            set "PYTHON_CMD=python"
            echo       找到 Python !PY_VER! (via python command)
        )
    )
)

REM 如果仍未找到 Python 3.10，报错退出
if "!PYTHON_CMD!"=="" (
    echo.
    echo [错误] 未检测到 Python 3.10！
    echo.
    echo        当前系统可能安装了其他版本（如 3.14），但本项目要求 3.10。
    echo        Python 3.14 存在 Pillow / chromadb / langgraph 等依赖兼容问题，
    echo        无法正常安装，必须使用 Python 3.10。
    echo.
    echo        请安装 Python 3.10：
    echo        https://www.python.org/downloads/release/python-3100/
    echo.
    echo        安装后可通过以下命令验证：
    echo        py -3.10 --version
    echo.
    pause
    exit /b 1
)

REM 额外检查：如果检测到 3.14 直接拒绝
echo !PY_VER! | findstr /b "3.14" >nul
if not errorlevel 1 (
    echo.
    echo [错误] 检测到 Python !PY_VER!，本项目不支持 Python 3.14。
    echo        请安装 Python 3.10 后重试。
    echo        https://www.python.org/downloads/release/python-3100/
    pause
    exit /b 1
)

echo       使用 Python !PY_VER!

REM --- 创建/检查虚拟环境（存 D 盘项目内）---
echo.
echo [2/5] 检查虚拟环境（D 盘项目内）...
if not exist "%VENV_DIR%\Scripts\python.exe" (
    echo       正在用 Python !PY_VER! 创建虚拟环境到 %VENV_DIR% ...
    !PYTHON_CMD! -m venv "%VENV_DIR%"
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败
        pause
        exit /b 1
    )
    echo       虚拟环境创建成功
) else (
    echo       虚拟环境已存在，跳过创建
)

REM --- 验证虚拟环境内的 Python 版本 ---
"%VENV_DIR%\Scripts\python.exe" --version >nul 2>&1
for /f "tokens=2" %%v in ('"%VENV_DIR%\Scripts\python.exe" --version 2^>^&1') do set "VENV_PY_VER=%%v"
echo       虚拟环境 Python 版本: !VENV_PY_VER!

REM --- 激活虚拟环境 ---
call "%VENV_DIR%\Scripts\activate.bat"

REM --- 设置 pip 缓存到 D 盘，避免写入 C 盘 ---
if not exist "%PIP_CACHE_DIR%" mkdir "%PIP_CACHE_DIR%"

REM --- 安装依赖 ---
echo.
echo [3/5] 安装/更新项目依赖...
python -m pip install --upgrade pip --cache-dir "%PIP_CACHE_DIR%" >nul 2>&1
pip install -r "%PROJECT_DIR%\requirements.txt" --cache-dir "%PIP_CACHE_DIR%"
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络连接
    pause
    exit /b 1
)
echo       依赖安装完成

REM --- 检查 Ollama ---
echo.
echo [4/5] 检查 Ollama 服务...
where ollama >nul 2>&1
if errorlevel 1 (
    echo [警告] 未检测到 Ollama，本地 LLM 模式将不可用
    echo        安装 Ollama: https://ollama.com/download
    echo        拉取模型: ollama pull qwen2.5-7b-instruct
) else (
    echo       Ollama 已安装
    ollama list 2>nul | findstr "qwen2.5:7b-instruct" >nul
    if errorlevel 1 (
        echo [提示] 未检测到 qwen2.5:7b-instruct 模型，正在拉取...
        ollama pull qwen2.5:7b-instruct
    ) else (
        echo       qwen2.5-7b-instruct 模型已就绪
    )
)

REM --- 启动 WebUI (Streamlit) ---
echo.
echo [5/5] 启动 Streamlit WebUI ...
echo.
echo ============================================================
echo   WebUI 地址: http://localhost:8501
echo   按 Ctrl+C 停止服务
echo ============================================================
echo.

cd /d "%PROJECT_DIR%"
streamlit run app.py --server.headless true --server.port 8501

pause
