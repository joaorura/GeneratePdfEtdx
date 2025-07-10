@echo off
echo ========================================
echo    Gerador de PDF - Build Otimizado
echo ========================================
echo.
echo Removendo builds anteriores...
if exist "build" rmdir /s /q "build"
if exist "dist" rmdir /s /q "dist"
if exist "*.spec" del "*.spec"

echo.
echo Instalando dependencias...
pip install -r requirements.txt

echo.
echo Criando executavel otimizado (sem IA)...
pyinstaller --clean --onefile --windowed --icon=icons/pdf_gear.ico --name=GeradorPDF gui.py

echo.
echo Build concluido!
echo Executavel criado em: dist/GeradorPDF.exe
echo.
echo Nota: Este build nao inclui funcionalidades de IA para reduzir o tamanho.
echo Para usar IA, execute diretamente com Python: python gui.py
pause 