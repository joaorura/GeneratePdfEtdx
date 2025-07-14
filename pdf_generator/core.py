import json
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import white
from PIL import Image
from PIL.Image import DecompressionBombError
from .robust_realesrgan import create_robust_realesrgan
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

# Lock global para RealESRGAN - deve ser multiprocessing.Lock() para funcionar com Pool
realesrgan_lock = Lock()

# Flag para controlar se o multiprocessing está funcionando
# Em executáveis compilados, desabilita por padrão para evitar problemas
MULTIPROCESSING_AVAILABLE = not getattr(sys, 'frozen', False)

# Flag para controlar se o RealESRGAN está disponível
# Em executáveis compilados, sempre False para reduzir o tamanho do build
if getattr(sys, 'frozen', False):
    REALESRGAN_AVAILABLE = False
    print("Executável compilado detectado - IA desabilitada para reduzir tamanho do build")
else:
    REALESRGAN_AVAILABLE = True

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
        # Hash do caminho do arquivo
        path_hash = hashlib.md5(str(img_path).encode()).hexdigest()
        
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
        path_hash = hashlib.md5(str(img_path).encode()).hexdigest()
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
        path_hash = hashlib.md5(str(img_path).encode()).hexdigest()
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

# Cache para o modelo RealESRGAN (evita recarregar o objeto do modelo, não as imagens)
_realesrgan_model_cache = {}
_realesrgan_cache_lock = Lock()

def test_realesrgan_availability():
    """Testa se o RealESRGAN está disponível e funcionando"""
    global REALESRGAN_AVAILABLE
    try:
        # Teste básico de importação
        from py_real_esrgan.model import RealESRGAN
        import torch
        
        # Teste básico de dispositivo
        device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
        print(f"RealESRGAN disponível - usando dispositivo: {device}")
        REALESRGAN_AVAILABLE = True
        return True
        
    except ImportError:
        print("RealESRGAN não disponível (módulo não encontrado)")
        REALESRGAN_AVAILABLE = False
        return False
    except Exception as e:
        print(f"Erro ao testar RealESRGAN: {e}")
        REALESRGAN_AVAILABLE = False
        return False

# Testa disponibilidade do RealESRGAN na inicialização (apenas para execução direta em Python)
if not getattr(sys, 'frozen', False):
    test_realesrgan_availability()

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
            
            # Upscale inteligente apenas para execução direta em Python
            if upscale and not getattr(sys, 'frozen', False) and (img.width < target_px_width or img.height < target_px_height):
                scale_factor = max(target_px_width / img.width, target_px_height / img.height)
                # RealESRGAN suporta apenas 2x, 4x, 8x
                if scale_factor > 1.5:
                    if scale_factor <= 2:
                        scale_factor = 2
                    elif scale_factor <= 4:
                        scale_factor = 4
                    elif scale_factor <= 8:
                        scale_factor = 8
                    else:
                        scale_factor = 8  # Máximo 8x para evitar problemas
                    # Upscale simples em workers (sem RealESRGAN)
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
        # Tamanhos permitidos (apenas os da imagem fornecida)
        mm_sizes = {
            '3.5x5': (89, 127),           # 3,5 x 5 pol. (89 x 127 mm)
            '5x7': (127, 178),            # 5 x 7 pol. (127 x 178 mm)
            '4x6': (102, 152),            # 4 x 6 pol. (102 x 152 mm)
            'A4': (210, 297),             # A4 (210 x 297 mm)
            '8x10': (203, 254),           # 8 x 10 pol. (203 x 254 mm)
            'Carta': (216, 279),          # Carta (216 x 279 mm)
            'Oficio': (216, 356),         # Oficio (216 x 356 mm)
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

    def upscale_simple(self, img, scale=2):
        """Upscale simples usando LANCZOS - fallback quando RealESRGAN não está disponível"""
        new_width = int(img.width * scale)
        new_height = int(img.height * scale)
        return img.resize((new_width, new_height), Image.Resampling.LANCZOS)

    def upscale_realesrgan(self, img, scale=2, timeout=300, img_path=None, target_size=None):
        """Upscale usando RealESRGAN robusto com fallback automático"""
        # Em executáveis compilados, sempre usar upscale simples
        if getattr(sys, 'frozen', False):
            print("Executável compilado detectado - usando upscale simples")
            return self.upscale_simple(img, scale)
        
        if not REALESRGAN_AVAILABLE:
            print("RealESRGAN não disponível, usando upscale simples")
            return self.upscale_simple(img, scale)

        # 1. Verificar cache final primeiro (imagem já no tamanho desejado)
        final_cache_hash = None
        if img_path and target_size:
            final_cache_hash = get_final_cache_hash(img_path, scale, target_size)
            if final_cache_hash:
                img_cache = get_final_cache(final_cache_hash)
                if img_cache is not None:
                    print(f"Cache final hit para {img_path} (escala x{scale}, size={target_size})")
                    return img_cache

        # 2. Verificar cache do modelo
        model_cache_hash = get_model_cache_hash(img_path, scale) if img_path else None
        upscale_img = None
        if model_cache_hash:
            upscale_img = get_model_cache(model_cache_hash)
            if upscale_img is not None:
                print(f"Cache do modelo hit para {img_path} (escala x{scale})")
                if target_size:
                    upscale_img = upscale_img.resize(target_size, Image.Resampling.LANCZOS)
                    # Salva no cache final
                    if final_cache_hash:
                        set_final_cache(final_cache_hash, upscale_img)
                return upscale_img

        # 3. Usar RealESRGAN robusto com fallback automático
        if upscale_img is None:
            with realesrgan_lock:
                try:
                    cache_key = f"robust_model_{scale}"
                    model = None
                    if cache_key in _realesrgan_model_cache:
                        model = _realesrgan_model_cache[cache_key]
                    else:
                        print(f"Carregando RealESRGAN robusto x{scale}...")
                        
                        # Usar RealESRGAN robusto
                        try:
                            from robust_realesrgan import create_robust_realesrgan
                            preferred_device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
                            model = create_robust_realesrgan(preferred_device, scale=scale)
                        except ImportError:
                            # Fallback para RealESRGAN original
                            from py_real_esrgan.model import RealESRGAN
                            device = torch.device('cpu')  # Usar CPU por segurança
                            model = RealESRGAN(device, scale=scale)
                            weights_path = f"weights/RealESRGAN_x{scale}.pth"
                            if os.path.exists(weights_path):
                                model.load_weights(weights_path, download=False)
                            else:
                                model.load_weights(weights_path, download=True)
                        
                        _realesrgan_model_cache[cache_key] = model
                        print(f"RealESRGAN robusto x{scale} carregado com sucesso")
                    
                    upscale_result = None
                    upscale_error = None
                    def upscale_worker():
                        nonlocal upscale_result, upscale_error
                        try:
                            # Usar método predict do modelo robusto
                            if hasattr(model, 'predict'):
                                upscale_result = model.predict(img)
                            else:
                                # Fallback para método original
                                upscale_result = model.predict(img)
                        except Exception as e:
                            upscale_error = str(e)
                    
                    thread = threading.Thread(target=upscale_worker)
                    thread.daemon = True
                    thread.start()
                    thread.join(timeout=timeout)
                    if thread.is_alive():
                        print(f"Timeout ao processar imagem com RealESRGAN (>{timeout}s), usando upscale simples")
                        return self.upscale_simple(img, scale)
                    if upscale_error:
                        print(f"Erro no RealESRGAN: {upscale_error}, usando upscale simples")
                        return self.upscale_simple(img, scale)
                    if upscale_result is None or not hasattr(upscale_result, 'width'):
                        print(f"Erro inesperado no RealESRGAN: resultado inválido para {img_path if img_path else 'imagem desconhecida'}: {type(upscale_result)}. Usando upscale simples.")
                        # Limpa o cache corrompido se existir
                        if model_cache_hash:
                            try:
                                cache_path = get_model_cache_path(model_cache_hash)
                                if cache_path:
                                    os.remove(cache_path)
                            except Exception:
                                pass
                        return self.upscale_simple(img, scale)
                    upscale_img = upscale_result
                    # Salva no cache do modelo
                    if model_cache_hash:
                        set_model_cache(model_cache_hash, upscale_img)
                except ImportError:
                    print("RealESRGAN não disponível (módulo não encontrado), usando upscale simples")
                    return self.upscale_simple(img, scale)
                except Exception as e:
                    print(f"Erro inesperado no RealESRGAN: {e}, usando upscale simples")
                    return self.upscale_simple(img, scale)

        # 4. Redimensiona para o tamanho final, se necessário
        if upscale_img is not None and target_size:
            if not hasattr(upscale_img, 'resize') or not hasattr(upscale_img, 'width'):
                print(f"[Erro] Objeto inesperado no upscale_img: {type(upscale_img)}. Usando upscale simples.")
                return self.upscale_simple(img, scale)
            resized_img = upscale_img.resize(target_size, Image.Resampling.LANCZOS)
            # Salva no cache final
            if final_cache_hash:
                set_final_cache(final_cache_hash, resized_img)
            return resized_img
        # fallback
        return upscale_img if upscale_img is not None else self.upscale_simple(img, scale)def upscale_worker():
                        nonlocal upscale_result, upscale_error
                        try:
                            # CORREÇÃO: Garantir que a imagem está em float32
                            if isinstance(img, Image.Image):
                                img_array = np.array(img).astype(np.float32) / 255.0
                                img_tensor = torch.from_numpy(img_array).to(device).float()
                            elif isinstance(img, np.ndarray):
                                if img.dtype != np.float32:
                                    img = img.astype(np.float32)
                                img_tensor = torch.from_numpy(img).to(device).float()
                            elif isinstance(img, torch.Tensor):
                                if img.dtype != torch.float32:
                                    img_tensor = img.to(device).float()
                                else:
                                    img_tensor = img.to(device)
                            else:
                                # Fallback para PIL Image
                                img_array = np.array(img).astype(np.float32) / 255.0
                                img_tensor = torch.from_numpy(img_array).to(device).float()
                            
                            # Garantir que é float32
                            if img_tensor.dtype != torch.float32:
                                img_tensor = img_tensor.float()
                            
                            upscale_result = model.predict(img_tensor)
                        except Exception as e:
                            upscale_error = str(e)
                    
                    thread = threading.Thread(target=upscale_worker)
                    thread.daemon = True
                    thread.start()
                    thread.join(timeout=timeout)
                    if thread.is_alive():
                        print(f"Timeout ao processar imagem com RealESRGAN (>{timeout}s), usando upscale simples")
                        return self.upscale_simple(img, scale)
                    if upscale_error:
                        print(f"Erro no RealESRGAN: {upscale_error}, usando upscale simples")
                        return self.upscale_simple(img, scale)
                    if upscale_result is None or not hasattr(upscale_result, 'width'):
                        print(f"Erro inesperado no RealESRGAN: resultado inválido para {img_path if img_path else 'imagem desconhecida'}: {type(upscale_result)}. Usando upscale simples.")
                        # Limpa o cache corrompido se existir
                        if model_cache_hash:
                            try:
                                cache_path = get_model_cache_path(model_cache_hash)
                                if cache_path:
                                    os.remove(cache_path)
                            except Exception:
                                pass
                        return self.upscale_simple(img, scale)
                    upscale_img = upscale_result
                    # Salva no cache do modelo
                    if model_cache_hash:
                        set_model_cache(model_cache_hash, upscale_img)
                except ImportError:
                    print("RealESRGAN não disponível (módulo não encontrado), usando upscale simples")
                    return self.upscale_simple(img, scale)
                except Exception as e:
                    print(f"Erro inesperado no RealESRGAN: {e}, usando upscale simples")
                    return self.upscale_simple(img, scale)

        # 4. Redimensiona para o tamanho final, se necessário
        if upscale_img is not None and target_size:
            if not hasattr(upscale_img, 'resize') or not hasattr(upscale_img, 'width'):
                print(f"[Erro] Objeto inesperado no upscale_img: {type(upscale_img)}. Usando upscale simples.")
                return self.upscale_simple(img, scale)
            resized_img = upscale_img.resize(target_size, Image.Resampling.LANCZOS)
            # Salva no cache final
            if final_cache_hash:
                set_final_cache(final_cache_hash, resized_img)
            return resized_img
        # fallback
        return upscale_img if upscale_img is not None else self.upscale_simple(img, scale)

    def preprocess_image_with_upscale(self, args):
        # Função para processamento SEQUENCIAL COM upscale (usando RealESRGAN)
        (img_path, photo_data, page_size, json_page_size, dpi, img_format, jpeg_quality) = args
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
            target_size = (target_px_width, target_px_height)
            
            # Upscale inteligente apenas para execução direta em Python
            if not getattr(sys, 'frozen', False) and img.width < target_px_width or img.height < target_px_height:
                scale_factor = max(target_px_width / img.width, target_px_height / img.height)
                # RealESRGAN suporta apenas 2x, 4x, 8x
                if scale_factor > 1.5:
                    if scale_factor <= 2:
                        scale_factor = 2
                    elif scale_factor <= 4:
                        scale_factor = 4
                    elif scale_factor <= 8:
                        scale_factor = 8
                    else:
                        scale_factor = 8  # Máximo 8x para evitar problemas
                    print(f"Aplicando upscale x{scale_factor} na imagem {img_path.name}")
                    img = self.upscale_realesrgan(img, scale=scale_factor, img_path=img_path, target_size=target_size)
            
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

    def create_pdf(self, output_filename="output.pdf", dpi=300, img_format='jpeg', jpeg_quality=90, progress_callback=None, upscale=False):
        try:
            try:
                # Em executáveis compilados, sempre desabilitar upscale
                if getattr(sys, 'frozen', False):
                    if upscale:
                        print("Executável compilado detectado - upscale inteligente desabilitado")
                    upscale = False
                # Verificar se o upscale está disponível
                elif upscale and not REALESRGAN_AVAILABLE:
                    print("⚠️  Upscale inteligente solicitado mas RealESRGAN não está disponível")
                    print("   Usando processamento normal sem upscale")
                    upscale = False
                print(f"Iniciando geração de PDF: {output_filename}")
                print(f"Configurações: DPI={dpi}, formato={img_format}, qualidade={jpeg_quality}, upscale={upscale}")
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
                    if upscale:
                        # Separar imagens que precisam de upscale das que não precisam
                        images_no_upscale = []
                        images_with_upscale = []
                        for photo in photos:
                            image_path = photo['imagepath']
                            page_dir = self.ref_path / page_id
                            full_image_path = page_dir / image_path
                            # Verificar se a imagem precisa de upscale
                            img = Image.open(full_image_path).convert('RGB')
                            original_width, original_height = photo['originalsize']
                            center = photo['center']
                            scale = photo['scale']
                            scale_x = page_size[0] / json_page_size[0]
                            scale_y = page_size[1] / json_page_size[1]
                            img_width_pt = original_width * scale * scale_x
                            img_height_pt = original_height * scale * scale_y
                            img_width_inch = img_width_pt / 72
                            img_height_inch = img_height_pt / 72
                            target_px_width = int(img_width_inch * dpi)
                            target_px_height = int(img_height_inch * dpi)
                            if img.width < target_px_width or img.height < target_px_height:
                                scale_factor = max(target_px_width / img.width, target_px_height / img.height)
                                if scale_factor > 1.5:
                                    images_with_upscale.append((full_image_path, photo, page_size, json_page_size, dpi, img_format, jpeg_quality))
                                else:
                                    images_no_upscale.append((full_image_path, photo, page_size, json_page_size, dpi, img_format, jpeg_quality))
                            else:
                                images_no_upscale.append((full_image_path, photo, page_size, json_page_size, dpi, img_format, jpeg_quality))
                        # Processar imagens sem upscale
                        results_no_upscale = []
                        if images_no_upscale:
                            if MULTIPROCESSING_AVAILABLE and len(images_no_upscale) > 1:
                                try:
                                    with Pool(processes=min(cpu_count(), len(images_no_upscale))) as pool:
                                        results_no_upscale = pool.map(self._preprocess_image_no_upscale_worker, images_no_upscale)
                                except Exception as e:
                                    print(f"Erro no multiprocessing, usando processamento sequencial: {e}")
                                    # Fallback para processamento sequencial
                                    results_no_upscale = []
                                    for args in images_no_upscale:
                                        result = self._preprocess_image_no_upscale_worker(args)
                                        results_no_upscale.append(result)
                            else:
                                # Processamento sequencial
                                for args in images_no_upscale:
                                    result = self._preprocess_image_no_upscale_worker(args)
                                    results_no_upscale.append(result)
                        # Processar imagens com upscale sequencialmente (uma por vez)
                        results_with_upscale = []
                        for i, args in enumerate(images_with_upscale):
                            print(f"Processando imagem {i+1}/{len(images_with_upscale)} com upscale...")
                            try:
                                result = self.preprocess_image_with_upscale(args)
                            except Exception as e:
                                print(f"Erro ao fazer upscale da imagem: {e}")
                                result = (args[1], None, 0, 0)
                            results_with_upscale.append(result)
                        # Combinar resultados
                        results = results_no_upscale + results_with_upscale
                    else:
                        # Processamento normal sem upscale
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
                    self.create_pdf(output_filename, dpi=300, img_format=img_format, jpeg_quality=jpeg_quality, progress_callback=progress_callback, upscale=upscale)
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