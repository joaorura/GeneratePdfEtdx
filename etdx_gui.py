import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import threading
from pdf_generator.etdx_generator import ETDXGenerator, REALESRGAN_AVAILABLE, clear_etdx_upscale_cache
import shutil
import os
import sys
import time
import io
from pdf_generator.etdx_sizes import ETDX_SIZES

class LogRedirector:
    """Classe para redirecionar stdout para o arquivo de log"""
    def __init__(self, log_file="etdx_app.log"):
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

def clear_log_file(log_file="etdx_app.log"):
    """Limpa o arquivo de log ao iniciar o aplicativo"""
    try:
        with open(log_file, 'w', encoding='utf-8') as f:
            f.write(f"=== LOG INICIADO EM {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
    except Exception as e:
        print(f"Erro ao limpar arquivo de log: {e}")

class ETDXApp:
    def __init__(self, root):
        self.root = root
        self.root.title('Gerador de ETDX (.pdf → .etdx)')
        self.root.geometry('520x380')
        self.root.minsize(400, 300)
        self.root.resizable(True, True)
        
        # Inicializar sistema de log
        clear_log_file()
        self.log_redirector = LogRedirector()
        sys.stdout = self.log_redirector
        
        self.pdf_path = tk.StringVar()
        self.output_path = tk.StringVar(value='documento_gerado.etdx')
        self.status = tk.StringVar(value='Aguardando seleção do arquivo...')
        self.progress = tk.DoubleVar(value=0)
        self.dpi = tk.IntVar(value=300)
        self.upscale = tk.BooleanVar(value=True)
        self.fit_mode = tk.StringVar(value='fit')
        self.create_widgets()

    def create_widgets(self):
        frm = ttk.Frame(self.root, padding=20)
        frm.pack(fill='both', expand=True)

        # Bloco vertical para seleção do arquivo PDF
        file_frame = ttk.Frame(frm)
        file_frame.pack(fill='x', pady=5)
        ttk.Label(file_frame, text='Arquivo PDF:').pack(anchor='w')
        file_entry_frame = ttk.Frame(file_frame)
        file_entry_frame.pack(fill='x')
        entry = ttk.Entry(file_entry_frame, textvariable=self.pdf_path)
        entry.pack(side='left', fill='x', expand=True)
        ttk.Button(file_entry_frame, text='Selecionar', command=self.select_file).pack(side='left', padx=5)

        # Bloco vertical para ETDX de saída
        output_frame = ttk.Frame(frm)
        output_frame.pack(fill='x', pady=5)
        ttk.Label(output_frame, text='Arquivo .etdx de saída:').pack(anchor='w')
        output_entry_frame = ttk.Frame(output_frame)
        output_entry_frame.pack(fill='x')
        out_entry = ttk.Entry(output_entry_frame, textvariable=self.output_path)
        out_entry.pack(side='left', fill='x', expand=True)
        ttk.Button(output_entry_frame, text='Gerar ETDX', command=self.start_process).pack(side='left', padx=5)

        # Bloco para escolha de DPI
        dpi_frame = ttk.Frame(frm)
        dpi_frame.pack(fill='x', pady=5)
        ttk.Label(dpi_frame, text='Qualidade (DPI):').pack(side='left')
        ttk.Radiobutton(dpi_frame, text='300 (padrão)', variable=self.dpi, value=300).pack(side='left', padx=5)
        ttk.Radiobutton(dpi_frame, text='600 (alta)', variable=self.dpi, value=600).pack(side='left', padx=5)

        # Bloco para escolha do tamanho final do ETDX
        size_frame = ttk.Frame(frm)
        size_frame.pack(fill='x', pady=5)
        ttk.Label(size_frame, text='Tamanho final do ETDX:').pack(side='left')
        self.paper_size = tk.StringVar(value='auto')
        self.allowed_sizes = [('auto', 'Automático (default)')] + [(s['id'], s['label']) for s in ETDX_SIZES]
        self.size_combobox = ttk.Combobox(size_frame, textvariable=self.paper_size, state='readonly',
            values=[label for _, label in self.allowed_sizes])
        self.size_combobox.current(0)
        self.size_combobox.pack(side='left', padx=5)

        # Bloco para modo de ajuste da imagem
        fit_frame = ttk.Frame(frm)
        fit_frame.pack(fill='x', pady=5)
        ttk.Label(fit_frame, text='Modo de ajuste da imagem:').pack(side='left')
        self.fit_combobox = ttk.Combobox(fit_frame, textvariable=self.fit_mode, state='readonly',
            values=['Ajustar (caber na página)', 'Preencher (preencher a página)'])
        self.fit_combobox.current(0)
        self.fit_combobox.pack(side='left', padx=5)

        # Checkbox para upscale inteligente com status
        upscale_frame = ttk.Frame(frm)
        upscale_frame.pack(fill='x', pady=5)
        
        # Status do RealESRGAN
        if getattr(sys, 'frozen', False):
            status_text = "🚫 Upscale inteligente desabilitado (executável compilado)"
            status_color = "red"
            self.upscale.set(False)  # Desabilitar por padrão em executáveis compilados
        elif REALESRGAN_AVAILABLE:
            status_text = "✅ Upscale inteligente (RealESRGAN) disponível"
            status_color = "green"
        else:
            status_text = "⚠️ Upscale inteligente não disponível (usando redimensionamento simples)"
            status_color = "orange"
            self.upscale.set(False)  # Desabilitar por padrão se não disponível
        
        ttk.Label(upscale_frame, text=status_text, foreground=status_color).pack(anchor='w')
        
        # Checkbox
        self.upscale_checkbox = ttk.Checkbutton(
            upscale_frame, 
            text='Usar upscale inteligente para melhorar imagens pequenas', 
            variable=self.upscale,
            state='disabled' if getattr(sys, 'frozen', False) else ('normal' if REALESRGAN_AVAILABLE else 'disabled')
        )
        self.upscale_checkbox.pack(anchor='w')

        # Barra de progresso
        ttk.Progressbar(frm, variable=self.progress, maximum=100).pack(fill='x', pady=10)
        # Status
        ttk.Label(frm, textvariable=self.status, foreground='blue').pack(fill='x', pady=5)

    def select_file(self):
        clear_etdx_upscale_cache()  # Limpa ambos os caches ao selecionar novo arquivo
        path = filedialog.askopenfilename(filetypes=[('Arquivos PDF', '*.pdf')])
        if path:
            self.pdf_path.set(path)
            # Atualizar nome do arquivo de saída baseado no PDF selecionado
            pdf_name = os.path.splitext(os.path.basename(path))[0]
            self.output_path.set(f"{pdf_name}.etdx")

    def start_process(self):
        if not self.pdf_path.get().lower().endswith('.pdf'):
            messagebox.showerror('Erro', 'Selecione um arquivo PDF válido!')
            return
        
        # Verificar se upscale foi solicitado mas não está disponível
        if getattr(sys, 'frozen', False) and self.upscale.get():
            messagebox.showinfo(
                'Upscale desabilitado', 
                'O upscale inteligente está desabilitado em executáveis compilados.\n\n'
                'O processamento será feito com redimensionamento simples.'
            )
            self.upscale.set(False)
        elif self.upscale.get() and not REALESRGAN_AVAILABLE:
            result = messagebox.askyesno(
                'Upscale não disponível', 
                'O upscale inteligente (RealESRGAN) não está disponível.\n\n'
                'Deseja continuar com processamento normal (sem upscale)?'
            )
            if not result:
                return
            self.upscale.set(False)
        
        self.status.set('Processando...')
        self.progress.set(0)
        threading.Thread(target=self.process_etdx, daemon=True).start()

    def process_etdx(self):
        try:
            generator = ETDXGenerator(self.pdf_path.get())
            
            def progress_callback(atual, total):
                self.progress.set(100 * atual / total)
                self.status.set(f'Processando página {atual} de {total}...')
            
            # Mostrar informações sobre o processamento
            if self.upscale.get():
                self.status.set('Iniciando processamento com upscale inteligente...')
            else:
                self.status.set('Iniciando processamento normal...')
            
            # Determinar tamanho selecionado
            selected_label = self.size_combobox.get()
            selected_key = next((key for key, label in self.allowed_sizes if label == selected_label), 'auto')
            
            # Determinar modo de ajuste
            fit_label = self.fit_combobox.get()
            fit_mode = 'fit' if 'Ajustar' in fit_label else 'fill'
            
            # Chamar create_etdx com o parâmetro correto
            generator.create_etdx(
                self.output_path.get(),
                dpi=self.dpi.get(),
                img_format='png', # Sempre PNG
                progress_callback=progress_callback,
                upscale=self.upscale.get(),
                paper_size_id=selected_key,  # Passa o id correto
                fit_mode=fit_mode  # Passa o modo de ajuste
            )
            generator.print_summary()
            self.status.set('ETDX gerado com sucesso!')
            messagebox.showinfo('Sucesso', f'ETDX gerado: {os.path.abspath(self.output_path.get())}')
        except Exception as e:
            self.status.set('Erro ao gerar ETDX!')
            messagebox.showerror('Erro', str(e))
        finally:
            self.progress.set(0)

if __name__ == '__main__':
    root = tk.Tk()
    app = ETDXApp(root)
    root.mainloop() 