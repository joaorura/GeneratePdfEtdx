import json
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import white
from PIL import Image
from PIL.Image import DecompressionBombError

# Desativa o limite de pixels do Pillow
Image.MAX_IMAGE_PIXELS = None
import zipfile
import tempfile
import io
import multiprocessing
from multiprocessing import Pool, cpu_count, Lock
import sys
import os
import time
import threading
import hashlib
import pickle
import atexit
import shutil

# Suporte para PyInstaller
if getattr(sys, 'frozen', False):
    # Executando como executável compilado
    multiprocessing.freeze_support()

# Lock global para upscaling - deve ser multiprocessing.Lock() para funcionar com Pool
upscale_lock = Lock()

# Flag para controlar se o multiprocessing está funcionando
# Em executáveis compilados, desabilita por padrão para evitar problemas
MULTIPROCESSING_AVAILABLE = not getattr(sys, 'frozen', False)



# Diretórios de cache em disco (apenas para execução direta em Python)
if not getattr(sys, 'frozen', False):
    CACHE_DIR = 'upscale_cache'
    MODEL_CACHE_DIR = os.path.join(CACHE_DIR, 'model')
    FINAL_CACHE_DIR = os.path.join(CACHE_DIR, 'final')
    # Criação protegida dos diretórios de cache
    for d in [CACHE_DIR, MODEL_CACHE_DIR, FINAL_CACHE_DIR]:
        try:
            os.makedirs(d, exist_ok=True)
        except PermissionError:
            print(f"[Aviso] Sem permissão para criar o diretório de cache: {d}")
        except Exception as e:
            print(f"[Aviso] Erro ao criar diretório de cache {d}: {e}")
else:
    # Em executáveis compilados, não usar cache para economizar espaço
    CACHE_DIR = None
    MODEL_CACHE_DIR = None
    FINAL_CACHE_DIR = None

# Funções utilitárias para salvar/carregar/remover imagens do cache em disco
def _save_image_to_cache(img, cache_path):
    # Salva uma imagem PIL como pickle (usando BytesIO)
    with open(cache_path, 'wb') as f:
        with io.BytesIO() as buf:
            img.save(buf, format='PNG')
            pickle.dump(buf.getvalue(), f)

def _load_image_from_cache(cache_path):
    # Carrega uma imagem PIL de um arquivo pickle
    try:
        with open(cache_path, 'rb') as f:
            img_bytes = pickle.load(f)
            img = Image.open(io.BytesIO(img_bytes))
            if img is None:
                raise ValueError('Imagem carregada do cache é None')
            return img
    except Exception as e:
        print(f'[Cache] Erro ao carregar imagem do cache {cache_path}: {e}. Apagando arquivo corrompido.')
        try:
            os.remove(cache_path)
        except Exception:
            pass
        return None

def _remove_cache_dir(path):
    # Remove o diretório de cache, ignorando erros se estiver em uso ou não existir
    shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path, exist_ok=True)

# Funções de cache para modelo e final
def get_model_cache_path(model_cache_hash):
    if MODEL_CACHE_DIR is None:
        return None
    return os.path.join(MODEL_CACHE_DIR, f'{model_cache_hash}.pkl')

def get_final_cache_path(final_cache_hash):
    if FINAL_CACHE_DIR is None:
        return None
    return os.path.join(FINAL_CACHE_DIR, f'{final_cache_hash}.pkl')

# Busca no cache do modelo (em disco)
def get_model_cache(model_cache_hash):
    if getattr(sys, 'frozen', False):
        return None
    path = get_model_cache_path(model_cache_hash)
    if path and os.path.exists(path):
        img = _load_image_from_cache(path)
        if img is None:
            print(f'[Cache] Cache do modelo corrompido em {path}, removido.')
        return img
    return None

def set_model_cache(model_cache_hash, img):
    if getattr(sys, 'frozen', False):
        return
    if img is None or not hasattr(img, 'save'):
        print(f"[Cache] Tentativa de salvar None ou objeto inválido no cache do modelo: {model_cache_hash}")
        return
    path = get_model_cache_path(model_cache_hash)
    if path:
        try:
            _save_image_to_cache(img, path)
        except Exception as e:
            print(f'Erro ao salvar cache do modelo: {e}')

# Busca no cache final (em disco)
def get_final_cache(final_cache_hash):
    if getattr(sys, 'frozen', False):
        return None
    path = get_final_cache_path(final_cache_hash)
    if path and os.path.exists(path):
        img = _load_image_from_cache(path)
        if img is None:
            print(f'[Cache] Cache final corrompido em {path}, removido.')
        return img
    return None

def set_final_cache(final_cache_hash, img):
    if getattr(sys, 'frozen', False):
        return
    if img is None or not hasattr(img, 'save'):
        print(f"[Cache] Tentativa de salvar None ou objeto inválido no cache final: {final_cache_hash}")
        return
    path = get_final_cache_path(final_cache_hash)
    if path:
        try:
            _save_image_to_cache(img, path)
        except Exception as e:
            print(f'Erro ao salvar cache final: {e}')

# Limpa ambos os caches (em disco)
def clear_upscale_cache():
    if getattr(sys, 'frozen', False):
        print("Cache não disponível em executável compilado")
        return
    if MODEL_CACHE_DIR and FINAL_CACHE_DIR:
        _remove_cache_dir(MODEL_CACHE_DIR)
        _remove_cache_dir(FINAL_CACHE_DIR)
        print('Cache de upscale limpo (em disco)')

# Limpa o cache apenas se for o processo principal
def safe_clear_upscale_cache():
    if getattr(sys, 'frozen', False):
        return
    if multiprocessing.current_process().name == 'MainProcess':
        clear_upscale_cache()

# Limpa o cache ao sair do programa (apenas no processo principal)
def _cleanup_cache_on_exit():
    safe_clear_upscale_cache()

if not getattr(sys, 'frozen', False):
    atexit.register(_cleanup_cache_on_exit)

def get_image_hash(img_path, scale_factor, target_size=None):
    """Gera um hash único para a imagem baseado no caminho e fator de escala"""
    try:
        # Para páginas processadas (que não são arquivos reais), usar um hash baseado no conteúdo
        if isinstance(img_path, str) and img_path.startswith('page_'):
            # Hash baseado no nome da página e parâmetros
            content_hash = hashlib.md5(f"{img_path}_{scale_factor}".encode()).hexdigest()
            return content_hash
        
        # Hash do caminho do arquivo
        path_hash = hashlib.md5(str(img_path).encode()).hexdigest()
        
        # Verificar se o arquivo existe antes de tentar acessar seus metadados
        if not os.path.exists(img_path):
            # Se o arquivo não existe, usar apenas o caminho e escala
            scale_hash = hashlib.md5(f"{scale_factor}".encode()).hexdigest()
            final_hash = hashlib.md5(f"{path_hash}_{scale_hash}".encode()).hexdigest()
            return final_hash
        
        # Hash dos metadados da imagem (tamanho, data de modificação)
        stat = os.stat(img_path)
        metadata = f"{stat.st_size}_{stat.st_mtime}"
        metadata_hash = hashlib.md5(metadata.encode()).hexdigest()
        
        # Hash do fator de escala (sem considerar target_size para melhor cache)
        scale_hash = hashlib.md5(f"{scale_factor}".encode()).hexdigest()
        
        # Hash final combinando todos os elementos
        final_hash = hashlib.md5(f"{path_hash}_{metadata_hash}_{scale_hash}".encode()).hexdigest()
        
        return final_hash
    except Exception as e:
        print(f"Erro ao gerar hash da imagem {img_path}: {e}")
        return None

def get_model_cache_hash(img_path, scale_factor):
    """Hash para o cache do resultado do modelo (sem target_size)"""
    try:
        # Para páginas processadas, usar hash baseado no conteúdo
        if isinstance(img_path, str) and img_path.startswith('page_'):
            content_hash = hashlib.md5(f"{img_path}_{scale_factor}".encode()).hexdigest()
            return content_hash
        
        path_hash = hashlib.md5(str(img_path).encode()).hexdigest()
        
        # Verificar se o arquivo existe
        if not os.path.exists(img_path):
            scale_hash = hashlib.md5(f"{scale_factor}".encode()).hexdigest()
            final_hash = hashlib.md5(f"{path_hash}_{scale_hash}".encode()).hexdigest()
            return final_hash
        
        stat = os.stat(img_path)
        metadata = f"{stat.st_size}_{stat.st_mtime}"
        metadata_hash = hashlib.md5(metadata.encode()).hexdigest()
        scale_hash = hashlib.md5(f"{scale_factor}".encode()).hexdigest()
        final_hash = hashlib.md5(f"{path_hash}_{metadata_hash}_{scale_hash}".encode()).hexdigest()
        return final_hash
    except Exception as e:
        print(f"Erro ao gerar hash do modelo para {img_path}: {e}")
        return None

def get_final_cache_hash(img_path, scale_factor, target_size):
    """Hash para o cache do resultado final (inclui target_size)"""
    try:
        # Para páginas processadas, usar hash baseado no conteúdo
        if isinstance(img_path, str) and img_path.startswith('page_'):
            size_hash = hashlib.md5(f"{target_size[0]}_{target_size[1]}".encode()).hexdigest()
            content_hash = hashlib.md5(f"{img_path}_{scale_factor}_{size_hash}".encode()).hexdigest()
            return content_hash
        
        path_hash = hashlib.md5(str(img_path).encode()).hexdigest()
        
        # Verificar se o arquivo existe
        if not os.path.exists(img_path):
            scale_hash = hashlib.md5(f"{scale_factor}".encode()).hexdigest()
            size_hash = hashlib.md5(f"{target_size[0]}_{target_size[1]}".encode()).hexdigest()
            final_hash = hashlib.md5(f"{path_hash}_{scale_hash}_{size_hash}".encode()).hexdigest()
            return final_hash
        
        stat = os.stat(img_path)
        metadata = f"{stat.st_size}_{stat.st_mtime}"
        metadata_hash = hashlib.md5(metadata.encode()).hexdigest()
        scale_hash = hashlib.md5(f"{scale_factor}".encode()).hexdigest()
        size_hash = hashlib.md5(f"{target_size[0]}_{target_size[1]}".encode()).hexdigest()
        final_hash = hashlib.md5(f"{path_hash}_{metadata_hash}_{scale_hash}_{size_hash}".encode()).hexdigest()
        return final_hash
    except Exception as e:
        print(f"Erro ao gerar hash final para {img_path}: {e}")
        return None

# Cache para modelos de upscaling (evita recarregar os objetos dos modelos)
_upscale_model_cache = {}
_upscale_cache_lock = Lock()

# Importar módulo de upscaling com IA
try:
    from .ai_upscaler import upscale_image, is_ai_upscaling_available, get_available_devices
    AI_UPSCALE_AVAILABLE = is_ai_upscaling_available()
except ImportError:
    AI_UPSCALE_AVAILABLE = False
    def upscale_image(img, scale_factor=4, model_name="RealESRGAN_x4", device="auto", target_size=None):
        # Fallback para upscale simples
        if target_size:
            return img.resize(target_size, Image.Resampling.LANCZOS)
        else:
            new_width = img.width * scale_factor
            new_height = img.height * scale_factor
            return img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    def get_available_devices():
        return ["cpu"]

class PDFGenerator:
    def __init__(self, ref_path):
        self.ref_path = Path(ref_path)
        self.project_info = {}
        self.page_list = []
        self.master_template = {}
        self.pages_data = {}

    @staticmethod
    def _preprocess_image_no_upscale_worker(args):
        """Worker function para processamento paralelo SEM upscale, agora usando o final_cache em disco"""
        (img_path, photo_data, page_size, json_page_size, dpi, img_format, jpeg_quality) = args
        try:
            # Calcular o tamanho alvo
            original_width, original_height = photo_data['originalsize']
            scale = photo_data['scale']
            scale_x = page_size[0] / json_page_size[0]
            scale_y = page_size[1] / json_page_size[1]
            img_width_pt = original_width * scale * scale_x
            img_height_pt = original_height * scale * scale_y
            img_width_inch = img_width_pt / 72
            img_height_inch = img_height_pt / 72
            target_px_width = int(img_width_inch * dpi)
            target_px_height = int(img_height_inch * dpi)
            target_size = (target_px_width, target_px_height)
            
            # Cache apenas para execução direta em Python
            if not getattr(sys, 'frozen', False):
                final_cache_hash = get_final_cache_hash(img_path, 1, target_size)
                img_cache = get_final_cache(final_cache_hash)
                if img_cache is not None:
                    print(f"[Cache] Cache final hit (resize simples) para {img_path.name} size={target_size}")
                    img_bytes = io.BytesIO()
                    if img_format == 'jpeg':
                        img_cache.save(img_bytes, format='JPEG', quality=jpeg_quality, optimize=True)
                    else:
                        img_cache.save(img_bytes, format='PNG', optimize=True)
                    img_bytes.seek(0)
                    return (photo_data, img_bytes, img_width_pt, img_height_pt)
            
            # Processamento normal
            img = Image.open(img_path).convert('RGB')
            if target_px_width > 0 and target_px_height > 0:
                img = img.resize((target_px_width, target_px_height), Image.Resampling.LANCZOS)
            img_bytes = io.BytesIO()
            if img_format == 'jpeg':
                img.save(img_bytes, format='JPEG', quality=jpeg_quality, optimize=True)
            else:
                img.save(img_bytes, format='PNG', optimize=True)
            img_bytes.seek(0)
            
            # Salva no cache final (apenas para execução direta em Python)
            if not getattr(sys, 'frozen', False):
                set_final_cache(final_cache_hash, img)
                print(f"[Cache] Cache final salvo (resize simples) para {img_path.name} size={target_size}")
            
            return (photo_data, img_bytes, img_width_pt, img_height_pt)
        except Exception as e:
            print(f"Erro ao processar imagem {img_path}: {e}")
            return (photo_data, None, 0, 0)

    @staticmethod
    def _preprocess_image_worker(args):
        """Worker function para processamento paralelo (compatibilidade)"""
        (img_path, photo_data, page_size, json_page_size, dpi, img_format, jpeg_quality, upscale) = args
        try:
            img = Image.open(img_path).convert('RGB')
            original_width, original_height = photo_data['originalsize']
            center = photo_data['center']
            scale = photo_data['scale']
            # Espaço visual da imagem no PDF (em pontos)
            scale_x = page_size[0] / json_page_size[0]
            scale_y = page_size[1] / json_page_size[1]
            img_width_pt = original_width * scale * scale_x
            img_height_pt = original_height * scale * scale_y
            img_width_inch = img_width_pt / 72
            img_height_inch = img_height_pt / 72
            target_px_width = int(img_width_inch * dpi)
            target_px_height = int(img_height_inch * dpi)
            
            # Upscale com IA quando necessário
            if upscale and (img.width < target_px_width or img.height < target_px_height):
                scale_factor = max(target_px_width / img.width, target_px_height / img.height)
                if scale_factor > 1.5:
                    if scale_factor <= 2:
                        scale_factor = 2
                    elif scale_factor <= 4:
                        scale_factor = 4
                    else:
                        scale_factor = 4  # Máximo 4x para evitar problemas
                    
                    # Usar upscaling com IA se disponível
                    if AI_UPSCALE_AVAILABLE and not getattr(sys, 'frozen', False):
                        try:
                            print(f"Aplicando upscale com IA x{scale_factor} em {img_path.name}")
                            # Usar lock para evitar múltiplas chamadas simultâneas de upscale_image
                            with upscale_lock:
                                img = upscale_image(img, scale_factor=scale_factor, target_size=(target_px_width, target_px_height))
                        except Exception as e:
                            print(f"Erro no upscale com IA: {e}, usando upscale simples")
                            # Fallback para upscale simples
                            new_width = int(img.width * scale_factor)
                            new_height = int(img.height * scale_factor)
                            img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                    else:
                        # Upscale simples
                        new_width = int(img.width * scale_factor)
                        new_height = int(img.height * scale_factor)
                        img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Redimensionar para o tamanho final
            if target_px_width > 0 and target_px_height > 0:
                img = img.resize((target_px_width, target_px_height), Image.Resampling.LANCZOS)
            img_bytes = io.BytesIO()
            if img_format == 'jpeg':
                img.save(img_bytes, format='JPEG', quality=jpeg_quality, optimize=True)
            else:
                img.save(img_bytes, format='PNG', optimize=True)
            img_bytes.seek(0)
            return (photo_data, img_bytes, img_width_pt, img_height_pt)
        except Exception as e:
            print(f"Erro ao processar imagem {img_path}: {e}")
            return (photo_data, None, 0, 0)

    def load_project_info(self):
        project_file = self.ref_path / "projectInfo.json"
        if project_file.exists():
            with open(project_file, 'r', encoding='utf-8') as f:
                self.project_info = json.load(f)

    def load_page_list(self):
        page_file = self.ref_path / "page.json"
        if page_file.exists():
            with open(page_file, 'r', encoding='utf-8') as f:
                self.page_list = json.load(f)

    def load_master_template(self):
        template_file = self.ref_path / "MasterTemplate" / "_info.json"
        if template_file.exists():
            with open(template_file, 'r', encoding='utf-8') as f:
                self.master_template = json.load(f)

    def load_page_data(self, page_id):
        page_dir = self.ref_path / page_id
        if not page_dir.exists():
            return None
        info_file = page_dir / "_info.json"
        if info_file.exists():
            with open(info_file, 'r', encoding='utf-8') as f:
                page_data = json.load(f)
                self.pages_data[page_id] = page_data
                return page_data
        return None

    def get_paper_size(self, paper_size_id, dpi=300):
        # Mapeamento completo de paperSizeId para tamanhos em mm
        mm_sizes = {
            # Tamanhos padrão
            '3.5x5': (89, 127),           # 3,5 x 5 pol. (89 x 127 mm)
            '5x7': (127, 178),            # 5 x 7 pol. (127 x 178 mm)
            '4x6': (102, 152),            # 4 x 6 pol. (102 x 152 mm)
            'A4': (210, 297),             # A4 (210 x 297 mm)
            '8x10': (203, 254),           # 8 x 10 pol. (203 x 254 mm)
            'Carta': (216, 279),          # Carta (216 x 279 mm)
            'Oficio': (216, 356),         # Oficio (216 x 356 mm)
            # Mapeamento de paperSizeId para tamanhos
            'LB': (89, 127),              # 3,5 x 5 pol.
            '2L': (127, 178),             # 5 x 7 pol.
            'KG': (102, 152),             # 4 x 6 pol.
            '6G': (203, 254),             # 8 x 10 pol.
            'LT': (216, 279),             # Carta
            'LG': (216, 356),             # Oficio
            'HG': (148, 221),             # 5 x 7 pol. (altura)
            'S2': (187, 191),             # 7 x 7 pol.
            'A5': (148, 210),             # A5
            'S1': (210, 210),             # A4 quadrado
            'A3': (297, 420),             # A3
            'A2': (420, 594),             # A2
            'HV': (102, 178),             # 4 x 7 pol.
            '5A': (148, 210),             # A5
            'CA': (33, 52),               # Cartão
            'MS': (34, 55),               # Mini cartão
            '3A': (297, 420),             # A3
            '4G': (144, 174),             # 5 x 7 pol. (largura)
        }
        if paper_size_id not in mm_sizes:
            raise ValueError(f"Tamanho de papel não permitido: {paper_size_id}. Tamanhos aceitos: {list(mm_sizes.keys())}")
        size_mm = mm_sizes[paper_size_id]
        # 1 polegada = 25.4 mm
        width_pt = size_mm[0] / 25.4 * dpi
        height_pt = size_mm[1] / 25.4 * dpi
        return (width_pt, height_pt)

    def get_json_paper_size(self, edited_paper):
        return tuple(edited_paper.get('size', [3048, 4321]))

    def convert_coordinates(self, center, scale, original_size, json_page_size, pdf_page_size):
        x, y = center
        scale_x = pdf_page_size[0] / json_page_size[0]
        scale_y = pdf_page_size[1] / json_page_size[1]
        pdf_x = (json_page_size[0] / 2 + x) * scale_x
        pdf_y = (json_page_size[1] / 2 - y) * scale_y
        return pdf_x, pdf_y, scale_x, scale_y

    def add_image_to_page(self, c, image_path, photo_data, page_size, json_page_size, dpi=300, img_format='jpeg', jpeg_quality=90):
        try:
            page_id = None
            for pid in self.page_list:
                if pid in self.pages_data and 'photos' in self.pages_data[pid].get('editedPaperSize', {}):
                    for photo in self.pages_data[pid]['editedPaperSize']['photos']:
                        if photo['imagepath'] == image_path:
                            page_id = pid
                            break
                    if page_id:
                        break
            if page_id:
                full_image_path = self.ref_path / page_id / photo_data['imagepath']
            else:
                full_image_path = self.ref_path / photo_data['imagepath']
            if not full_image_path.exists():
                print(f"Imagem não encontrada: {full_image_path}")
                return
            img = Image.open(full_image_path).convert('RGB')
            original_width, original_height = photo_data['originalsize']
            center = photo_data['center']
            scale = photo_data['scale']
            x, y, scale_x, scale_y = self.convert_coordinates(center, scale, (original_width, original_height), json_page_size, page_size)
            # Espaço visual da imagem no PDF (em pontos)
            img_width_pt = original_width * scale * scale_x
            img_height_pt = original_height * scale * scale_y
            # Espaço visual em polegadas
            img_width_inch = img_width_pt / 72
            img_height_inch = img_height_pt / 72
            # Redimensionar imagem para o número de pixels correspondente ao espaço físico no DPI desejado
            target_px_width = int(img_width_inch * dpi)
            target_px_height = int(img_height_inch * dpi)
            if target_px_width > 0 and target_px_height > 0:
                img = img.resize((target_px_width, target_px_height), Image.Resampling.LANCZOS)
            # Salvar imagem temporária no formato desejado
            import io
            img_bytes = io.BytesIO()
            if img_format == 'jpeg':
                img.save(img_bytes, format='JPEG', quality=jpeg_quality, optimize=True)
            else:
                img.save(img_bytes, format='PNG', optimize=True)
            img_bytes.seek(0)
            # Inserir imagem no PDF no espaço visual correto
            c.drawInlineImage(Image.open(img_bytes), x - img_width_pt/2, y - img_height_pt/2, width=img_width_pt, height=img_height_pt)
        except Exception as e:
            print(f"Erro ao adicionar imagem {image_path}: {e}")





    def create_pdf(self, output_filename="output.pdf", dpi=300, img_format='jpeg', jpeg_quality=90, upscale=True, progress_callback=None):
        try:
            try:
                print(f"Iniciando geração de PDF: {output_filename}")
                print(f"Configurações: DPI={dpi}, formato={img_format}, qualidade={jpeg_quality}")
                self.load_project_info()
                self.load_page_list()
                self.load_master_template()
                for page_id in self.page_list:
                    self.load_page_data(page_id)
                print(f"Projeto carregado: {len(self.page_list)} páginas")
                c = canvas.Canvas(output_filename)
                total_pages = len(self.page_list)
                for idx, page_id in enumerate(self.page_list):
                    if page_id not in self.pages_data:
                        continue
                    page_data = self.pages_data[page_id]
                    edited_paper = page_data.get('editedPaperSize', {})
                    paper_size_id = edited_paper.get('paperSizeId', 'A4')
                    page_size = self.get_paper_size(paper_size_id, dpi)
                    json_page_size = self.get_json_paper_size(edited_paper)
                    c.setPageSize(page_size)
                    c.setFillColor(white)
                    c.rect(0, 0, page_size[0], page_size[1], fill=1)
                    photos = edited_paper.get('photos', [])
                    print(f"Processando página {idx+1}/{total_pages} ({page_id}): {len(photos)} imagens")
                    # Processamento normal
                    args_list = []
                    for photo in photos:
                        image_path = photo['imagepath']
                        page_dir = self.ref_path / page_id
                        full_image_path = page_dir / image_path
                        args_list.append((full_image_path, photo, page_size, json_page_size, dpi, img_format, jpeg_quality, upscale))
                    if MULTIPROCESSING_AVAILABLE and len(args_list) > 1:
                        try:
                            with Pool(processes=min(cpu_count(), len(args_list))) as pool:
                                results = pool.map(self._preprocess_image_worker, args_list)
                        except Exception as e:
                            print(f"Erro no multiprocessing, usando processamento sequencial: {e}")
                            # Fallback para processamento sequencial
                            results = []
                            for args in args_list:
                                result = self._preprocess_image_worker(args)
                                results.append(result)
                    else:
                        # Processamento sequencial
                        results = []
                        for args in args_list:
                            result = self._preprocess_image_worker(args)
                            results.append(result)
                    for (photo, img_bytes, img_width_pt, img_height_pt) in results:
                        if img_bytes is not None:
                            center = photo['center']
                            scale = photo['scale']
                            scale_x = page_size[0] / json_page_size[0]
                            scale_y = page_size[1] / json_page_size[1]
                            x = (json_page_size[0] / 2 + center[0]) * scale_x
                            y = (json_page_size[1] / 2 - center[1]) * scale_y
                            c.drawInlineImage(Image.open(img_bytes), x - img_width_pt/2, y - img_height_pt/2, width=img_width_pt, height=img_height_pt)
                    if page_id != self.page_list[-1]:
                        c.showPage()
                    if progress_callback:
                        progress_callback(idx + 1, total_pages)
                c.save()
                print(f"PDF gerado com sucesso: {output_filename}")
            except DecompressionBombError as e:
                print(f"Erro de imagem gigante: {e}. Gerando PDF automaticamente em 300 DPI.")
                if dpi != 300:
                    self.create_pdf(output_filename, dpi=300, img_format=img_format, jpeg_quality=jpeg_quality, progress_callback=progress_callback)
                else:
                    raise
        finally:
            safe_clear_upscale_cache()  # Garante limpeza dos caches mesmo em caso de erro

    def print_summary(self):
        print("\n=== RESUMO DO PROJETO ===")
        print(f"Versão do App: {self.project_info.get('appVersion', 'N/A')}")
        print(f"Template ID: {self.master_template.get('id', 'N/A')}")
        print(f"Páginas: {self.page_list}")
        for page_id in self.page_list:
            if page_id in self.pages_data:
                page_data = self.pages_data[page_id]
                edited_paper = page_data.get('editedPaperSize', {})
                photos = edited_paper.get('photos', [])
                print(f"  {page_id}: {len(photos)} imagens, tamanho: {edited_paper.get('paperSizeId', 'N/A')}")

def extract_etdx(etdx_path):
    tmpdirname = tempfile.mkdtemp()
    with zipfile.ZipFile(etdx_path, 'r') as zip_ref:
        zip_ref.extractall(tmpdirname)
    return tmpdirname 