import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
from pdf_generator.core import PDFGenerator, extract_etdx, clear_upscale_cache
import shutil
import os
import sys
import time
import io

class LogRedirector:
    """Classe para redirecionar stdout para o arquivo de log"""
    def __init__(self, log_file="app.log"):
        self.log_file = log_file
        self.original_stdout = sys.stdout
        self.buffer = io.StringIO()
        
    def write(self, text):
        # Escrever no buffer original (console)
        self.original_stdout.write(text)
        # Escrever no arquivo de log
        try:
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write(f"[{timestamp}] {text}")
        except Exception as e:
            self.original_stdout.write(f"Erro ao escrever no log: {e}\n")
    
    def flush(self):
        self.original_stdout.flush()
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.flush()
        except:
            pass

def clear_log_file(log_file="app.log"):
    """Limpa o arquivo de log ao iniciar o aplicativo"""
    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"=== LOG INICIADO EM {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    except Exception as e:
        print(f"Erro ao limpar arquivo de log: {e}")

class PDFApp:
    def __init__(self, root):
        self.root = root
        self.root.title('Gerador de PDF (.etdx)')
        self.root.geometry('520x380')
        self.root.minsize(400, 300)
        self.root.resizable(True, True)
        
        # Inicializar sistema de log
        clear_log_file()
        self.log_redirector = LogRedirector()
        sys.stdout = self.log_redirector
        
        self.etdx_path = tk.StringVar()
        self.output_path = tk.StringVar(value='documento_gerado.pdf')
        self.status = tk.StringVar(value='Aguardando seleção do arquivo...')
        self.progress = tk.DoubleVar(value=0)
        self.dpi = tk.IntVar(value=300)
        self.img_format = tk.StringVar(value='jpeg')
        self.jpeg_quality = tk.IntVar(value=90)
        self.upscale = tk.BooleanVar(value=True)  # Padrão: habilitado

        self.create_widgets()

    def create_widgets(self):
        frm = ttk.Frame(self.root, padding=20)
        frm.pack(fill='both', expand=True)

        # Bloco vertical para seleção do arquivo .etdx
        file_frame = ttk.Frame(frm)
        file_frame.pack(fill='x', pady=5)
        ttk.Label(file_frame, text='Arquivo .etdx:').pack(anchor='w')
        file_entry_frame = ttk.Frame(file_frame)
        file_entry_frame.pack(fill='x')
        entry = ttk.Entry(file_entry_frame, textvariable=self.etdx_path)
        entry.pack(side='left', fill='x', expand=True)
        ttk.Button(file_entry_frame, text='Selecionar', command=self.select_file).pack(side='left', padx=5)

        # Bloco vertical para PDF de saída
        output_frame = ttk.Frame(frm)
        output_frame.pack(fill='x', pady=5)
        ttk.Label(output_frame, text='PDF de saída:').pack(anchor='w')
        output_entry_frame = ttk.Frame(output_frame)
        output_entry_frame.pack(fill='x')
        out_entry = ttk.Entry(output_entry_frame, textvariable=self.output_path)
        out_entry.pack(side='left', fill='x', expand=True)
        ttk.Button(output_entry_frame, text='Gerar PDF', command=self.start_process).pack(side='left', padx=5)

        # Bloco para escolha de DPI
        dpi_frame = ttk.Frame(frm)
        dpi_frame.pack(fill='x', pady=5)
        ttk.Label(dpi_frame, text='Qualidade (DPI):').pack(side='left')
        ttk.Radiobutton(dpi_frame, text='300 (padrão)', variable=self.dpi, value=300).pack(side='left', padx=5)
        ttk.Radiobutton(dpi_frame, text='600 (alta)', variable=self.dpi, value=600).pack(side='left', padx=5)

        # Bloco para formato de imagem
        fmt_frame = ttk.Frame(frm)
        fmt_frame.pack(fill='x', pady=5)
        ttk.Label(fmt_frame, text='Formato das imagens:').pack(side='left')
        ttk.Radiobutton(fmt_frame, text='JPEG', variable=self.img_format, value='jpeg', command=self.toggle_jpeg_quality).pack(side='left', padx=5)
        ttk.Radiobutton(fmt_frame, text='PNG', variable=self.img_format, value='png', command=self.toggle_jpeg_quality).pack(side='left', padx=5)

        # Bloco para qualidade JPEG
        self.jpeg_frame = ttk.Frame(frm)
        self.jpeg_frame.pack(fill='x', pady=5)
        ttk.Label(self.jpeg_frame, text='Qualidade JPEG:').pack(side='left')
        self.quality_slider = ttk.Scale(self.jpeg_frame, from_=80, to=100, variable=self.jpeg_quality, orient='horizontal')
        self.quality_slider.pack(side='left', fill='x', expand=True, padx=5)
        self.quality_entry = ttk.Entry(self.jpeg_frame, textvariable=self.jpeg_quality, width=4)
        self.quality_entry.pack(side='left', padx=5)
        self.toggle_jpeg_quality()

        # Bloco para upscaling
        upscale_frame = ttk.Frame(frm)
        upscale_frame.pack(fill='x', pady=5)
        ttk.Checkbutton(upscale_frame, text='Upscaling com IA (melhora qualidade)', variable=self.upscale).pack(side='left')

        # Barra de progresso
        ttk.Progressbar(frm, variable=self.progress, maximum=100).pack(fill='x', pady=10)
        # Status
        ttk.Label(frm, textvariable=self.status, foreground='blue').pack(fill='x', pady=5)

    def toggle_jpeg_quality(self):
        if self.img_format.get() == 'jpeg':
            self.jpeg_frame.pack(fill='x', pady=5)
        else:
            self.jpeg_frame.pack_forget()

    def select_file(self):
        clear_upscale_cache()  # Limpa ambos os caches ao selecionar novo arquivo
        path = filedialog.askopenfilename(filetypes=[('Arquivos EDTX', '*.etdx')])
        if path:
            self.etdx_path.set(path)

    def start_process(self):
        if not self.etdx_path.get().lower().endswith('.etdx'):
            messagebox.showerror('Erro', 'Selecione um arquivo .etdx válido!')
            return
        
        self.status.set('Processando...')
        self.progress.set(0)
        threading.Thread(target=self.process_pdf, daemon=True).start()

    def process_pdf(self):
        tmpdirname = extract_etdx(self.etdx_path.get())
        try:
            generator = PDFGenerator(tmpdirname)
            def progress_callback(atual, total):
                self.progress.set(100 * atual / total)
                self.status.set(f'Processando página {atual} de {total}...')
            
            # Mostrar informações sobre o processamento
            self.status.set('Iniciando processamento...')
            
            generator.create_pdf(
                self.output_path.get(),
                dpi=self.dpi.get(),
                img_format=self.img_format.get(),
                jpeg_quality=self.jpeg_quality.get(),
                upscale=self.upscale.get(),
                progress_callback=progress_callback
            )
            generator.print_summary()
            self.status.set('PDF gerado com sucesso!')
            messagebox.showinfo('Sucesso', f'PDF gerado: {os.path.abspath(self.output_path.get())}')
        except Exception as e:
            self.status.set('Erro ao gerar PDF!')
            messagebox.showerror('Erro', str(e))
        finally:
            shutil.rmtree(tmpdirname)
            self.progress.set(0)

if __name__ == '__main__':
    root = tk.Tk()
    app = PDFApp(root)
    root.mainloop() 