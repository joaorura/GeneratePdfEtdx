@echo off
echo ========================================
echo INSTALADOR DE DEPENDENCIAS PARA IA
echo ========================================
echo.

echo Verificando Python...
python --version
if errorlevel 1 (
    echo ERRO: Python nao encontrado!
    echo Instale o Python primeiro: https://python.org
    pause
    exit /b 1
)

echo.
echo Instalando dependencias basicas...
pip install -r requirements.txt

echo.
echo Instalando dependencias para IA...
pip install -r requirements-ai.txt

echo.
echo ========================================
echo BAIXANDO MODELOS ONNX
echo ========================================
echo.

setlocal enabledelayedexpansion

REM Baixar o arquivo zip dos modelos ONNX
set ZIP_URL=https://github.com/instant-high/real-esrgan-onnx/releases/download/RealESRGAN-ONNX/RealEsrganONNX.zip
set ZIP_FILE=RealEsrganONNX.zip
set MODELS_DIR=models

REM Criar diretório de modelos se não existir
if not exist %MODELS_DIR% (
    echo Criando diretorio %MODELS_DIR%...
    mkdir %MODELS_DIR%
)

REM Baixar o zip se não existir
if not exist %ZIP_FILE% (
    echo Baixando modelos ONNX...
    powershell -Command "Invoke-WebRequest -Uri %ZIP_URL% -OutFile %ZIP_FILE%"
    if errorlevel 1 (
        echo ERRO: Falha ao baixar o arquivo!
        pause
        exit /b 1
    )
)

REM Extrair o zip
echo Extraindo arquivos...
powershell -Command "Expand-Archive -Path %ZIP_FILE% -DestinationPath temp_models -Force"
if errorlevel 1 (
    echo ERRO: Falha ao extrair o arquivo!
    pause
    exit /b 1
)

REM Listar arquivos extraídos para debug
echo.
echo Arquivos encontrados no zip:
dir temp_models\*.onnx /b

REM Copiar apenas os modelos específicos (2x, 4x, 8x) para a pasta de modelos
echo.
echo Copiando modelos ONNX especificos...
for %%F in (2 4 8) do (
    set MODEL_FILE=RealESRGAN_x%%F.onnx
    echo Verificando: !MODEL_FILE!
    if exist "temp_models\!MODEL_FILE!" (
        echo Copiando: !MODEL_FILE!
        copy /Y "temp_models\!MODEL_FILE!" "%MODELS_DIR%\" >nul
        if errorlevel 1 (
            echo ERRO ao copiar: !MODEL_FILE!
        ) else (
            echo OK: !MODEL_FILE! copiado
        )
    ) else (
        echo AVISO: !MODEL_FILE! nao encontrado no zip
    )
)

REM Verificar se os arquivos foram copiados
echo.
echo Verificando arquivos copiados:
dir %MODELS_DIR%\*.onnx /b

REM Limpar arquivos temporários
echo.
echo Limpando arquivos temporarios...
rd /S /Q temp_models

REM Deletar o arquivo zip baixado
if exist %ZIP_FILE% del /F /Q %ZIP_FILE%

echo.
echo Modelos ONNX prontos em %MODELS_DIR%!

echo.
echo Verificando instalacao...
python test_ai_upscale.py

echo.
echo ========================================
echo INSTALACAO CONCLUIDA!
echo ========================================
echo.
echo Para testar o upscaling com IA:
echo 1. Execute: python test_ai_upscale.py
echo 2. Use a opcao --upscale no programa principal
echo.
pause
endlocal 