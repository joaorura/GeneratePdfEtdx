@echo off
chcp 65001 >nul
title Gerador de PDF (.etdx)

echo Iniciando Gerador de PDF...
echo.

REM Verifica se o Python está instalado
python --version >nul 2>&1
if errorlevel 1 (
    echo ERRO: Python não encontrado no sistema!
    echo Por favor, instale o Python 3.7+ e tente novamente.
    pause
    exit /b 1
)

REM Verifica se o arquivo gui.py existe
if not exist "gui.py" (
    echo ERRO: Arquivo gui.py não encontrado!
    echo Certifique-se de que este arquivo está na mesma pasta do executável.
    pause
    exit /b 1
)

REM Executa a interface gráfica
echo Executando interface gráfica...
D:\GitHub\teste\.conda\python.exe gui.py

REM Se houver erro, pausa para mostrar a mensagem
if errorlevel 1 (
    echo.
    echo Ocorreu um erro durante a execução.
    pause
) 