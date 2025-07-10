"""
Runtime hook para PyInstaller - resolve problemas de multiprocessing
"""
import sys
import multiprocessing

# Configuração para multiprocessing com PyInstaller
if getattr(sys, 'frozen', False):
    # Executando como executável compilado
    multiprocessing.freeze_support()
    
    # Configurar o método de start para multiprocessing
    if sys.platform.startswith('win'):
        # No Windows, usar 'spawn' para compatibilidade com PyInstaller
        multiprocessing.set_start_method('spawn', force=True)
    else:
        # Em outros sistemas, usar 'fork' se disponível
        try:
            multiprocessing.set_start_method('fork', force=True)
        except RuntimeError:
            multiprocessing.set_start_method('spawn', force=True)

# Garantir que os módulos necessários sejam importados
try:
    import PIL
    import PIL.Image
    import reportlab
    import reportlab.pdfgen
    import reportlab.lib.colors
    import zipfile
    import tempfile
    import io
    import json
    import pathlib
    import tkinter
    import tkinter.filedialog
    import tkinter.messagebox
    import tkinter.ttk
    import threading
    import shutil
    import os
except ImportError as e:
    print(f"Aviso: Módulo não encontrado durante inicialização: {e}") 