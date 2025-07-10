@echo off
echo Compilando aplicacao...

REM Limpar builds anteriores
if exist "dist" rmdir /s /q "dist"
if exist "build" rmdir /s /q "build"
if exist "*.spec" del "*.spec"

REM Compilar com PyInstaller
pyinstaller --onefile ^
    --windowed ^
    --name "GeradorPDF" ^
    --icon "icons/pdf_gear.ico" ^
    --add-data "icons;icons" ^
    --add-data "weights;weights" ^
    --hidden-import "multiprocessing" ^
    --hidden-import "multiprocessing.pool" ^
    --hidden-import "multiprocessing.managers" ^
    --hidden-import "multiprocessing.synchronize" ^
    --hidden-import "PIL" ^
    --hidden-import "PIL.Image" ^
    --hidden-import "reportlab" ^
    --hidden-import "reportlab.pdfgen" ^
    --hidden-import "reportlab.lib.colors" ^
    --hidden-import "zipfile" ^
    --hidden-import "tempfile" ^
    --hidden-import "io" ^
    --hidden-import "json" ^
    --hidden-import "pathlib" ^
    --hidden-import "tkinter" ^
    --hidden-import "tkinter.filedialog" ^
    --hidden-import "tkinter.messagebox" ^
    --hidden-import "tkinter.ttk" ^
    --hidden-import "threading" ^
    --hidden-import "shutil" ^
    --hidden-import "os" ^
    --hidden-import "sys" ^
    --collect-all "pdf_generator" ^
    --runtime-hook "runtime_hook.py" ^
    gui.py

echo Compilacao concluida!
pause 