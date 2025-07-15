
#!/usr/bin/env python3
"""
Gerador de arquivos .etdx a partir de PDFs
Módulo para converter PDFs em arquivos .etdx editáveis
"""

import json
from pathlib import Path
from PIL import Image
import fitz  # PyMuPDF
import tempfile
import zipfile
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
import uuid
from datetime import datetime
from typing import Optional, Tuple, Any, Callable

from .etdx_sizes import ETDX_SIZES, get_etdx_size_by_id, find_closest_etdx_size, calculate_image_scale_and_position_exact, get_etdx_label_by_paperSizeId

# Suporte para PyInstaller
if getattr(sys, 'frozen', False):
    multiprocessing.freeze_support()

# Lock global para upscaling
upscale_lock = Lock()

# Flag para controlar se o multiprocessing está funcionando
MULTIPROCESSING_AVAILABLE = not getattr(sys, 'frozen', False)



# Diretórios de cache em disco (apenas para execução direta em Python)
if not getattr(sys, 'frozen', False):
    CACHE_DIR = 'etdx_upscale_cache'
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
    CACHE_DIR = None
    MODEL_CACHE_DIR = None
    FINAL_CACHE_DIR = None

# Funções utilitárias para cache (reutilizadas do core.py)
def _save_image_to_cache(img, cache_path):
    with open(cache_path, 'wb') as f:
        with io.BytesIO() as buf:
            img.save(buf, format='PNG')
            pickle.dump(buf.getvalue(), f)

def _load_image_from_cache(cache_path):
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
    shutil.rmtree(path, ignore_errors=True)
    os.makedirs(path, exist_ok=True)

def get_model_cache_path(model_cache_hash):
    if MODEL_CACHE_DIR is None:
        return None
    return os.path.join(MODEL_CACHE_DIR, f'{model_cache_hash}.pkl')

def get_final_cache_path(final_cache_hash):
    if FINAL_CACHE_DIR is None:
        return None
    return os.path.join(FINAL_CACHE_DIR, f'{final_cache_hash}.pkl')

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

def clear_etdx_upscale_cache():
    if getattr(sys, 'frozen', False):
        print("Cache não disponível em executável compilado")
        return
    if MODEL_CACHE_DIR and FINAL_CACHE_DIR:
        _remove_cache_dir(MODEL_CACHE_DIR)
        _remove_cache_dir(FINAL_CACHE_DIR)
        print('Cache de upscale ETDX limpo (em disco)')

def safe_clear_etdx_upscale_cache():
    if getattr(sys, 'frozen', False):
        return
    if multiprocessing.current_process().name == 'MainProcess':
        clear_etdx_upscale_cache()

def _cleanup_cache_on_exit():
    safe_clear_etdx_upscale_cache()

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
        
        path_hash = hashlib.md5(str(img_path).encode()).hexdigest()
        
        # Verificar se o arquivo existe antes de tentar acessar seus metadados
        if not os.path.exists(img_path):
            # Se o arquivo não existe, usar apenas o caminho e escala
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

# Cache para modelos de upscaling
_upscale_model_cache = {}
_upscale_cache_lock = Lock()

# A disponibilidade do HF_UPSCALE_AVAILABLE é testada no módulo hf_upscaler

class ETDXGenerator:
    """Gerador de arquivos .etdx a partir de PDFs"""
    
    def __init__(self, pdf_path):
        self.pdf_path = Path(pdf_path)
        self.temp_dir = None
        self.project_id = str(uuid.uuid4())
        self.created_at = datetime.now().isoformat()
        
        # Verificar se o arquivo PDF existe
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"Arquivo PDF não encontrado: {pdf_path}")
        
        # Abrir o PDF para análise
        self.pdf_document = fitz.Document(str(self.pdf_path))
        
    def get_paper_size_from_pdf(self, page_num=0) -> Tuple[str, Tuple[float, float]]:
        """Extrai o tamanho do papel do PDF e retorna o identificador do tamanho permitido mais próximo"""
        if page_num >= len(self.pdf_document):
            page_num = 0
        page = self.pdf_document[page_num]
        rect = page.rect
        # Converter pontos para mm (1 ponto = 0.3528 mm)
        width_mm = rect.width * 0.3528
        height_mm = rect.height * 0.3528
        
        # Usar a função find_closest_etdx_size para detectar o tamanho mais próximo
        etdx_size = find_closest_etdx_size(width_mm, height_mm)
        if etdx_size:
            return etdx_size["id"], (width_mm, height_mm)
        else:
            # Fallback para A4 se não encontrar nenhum tamanho
            return "A4", (width_mm, height_mm)
    
    def get_paper_size_pts(self, paper_size_id: str, dpi: int = 300) -> Tuple[int, int]:
        """Retorna o tamanho do papel em pontos"""
        paper_sizes = {
            'A4': (595, 842),
            'A3': (842, 1191),
            'A5': (420, 595),
            'A6': (298, 420),
            'Letter': (612, 792),
            'Legal': (612, 1008)
        }
        return paper_sizes.get(paper_size_id, (595, 842))
    
    @staticmethod
    def _process_page_worker(args: Tuple[int, str, int, str, bool]) -> Tuple[int, Optional[io.BytesIO], int, int]:
        """Worker para processamento de página com multiprocessing"""
        (page_num, pdf_path, dpi, img_format, upscale) = args
        
        try:
            # Abrir o PDF com tratamento de erro mais robusto
            try:
                pdf_doc = fitz.Document(str(pdf_path))  # type: ignore
                if page_num >= len(pdf_doc):
                    print(f"Página {page_num} não existe no PDF")
                    return (page_num, None, 0, 0)
                page = pdf_doc[page_num]
            except Exception as e:
                print(f"Erro ao abrir PDF ou acessar página {page_num}: {e}")
                return (page_num, None, 0, 0)
            
            try:
                # Renderizar página como imagem
                mat = fitz.Matrix(dpi/72, dpi/72)
                pix = page.get_pixmap(matrix=mat)  # type: ignore
                img_data = pix.tobytes("png")
                
                # Converter para PIL Image
                img = Image.open(io.BytesIO(img_data)).convert('RGB')
                
                # Aplicar upscale se necessário
                if upscale and not getattr(sys, 'frozen', False):
                    # Verificar se precisa de upscale
                    target_dpi = dpi * 2  # Upscale para 2x DPI
                    target_width = int(page.rect.width * target_dpi / 72)
                    target_height = int(page.rect.height * target_dpi / 72)
                    target_size = (target_width, target_height)
                    
                    if img.width < target_width or img.height < target_height:
                        scale_factor = max(target_width / img.width, target_height / img.height)
                        if scale_factor > 1.5:
                            if scale_factor <= 2:
                                scale_factor = 2
                            elif scale_factor <= 4:
                                scale_factor = 4
                            else:
                                scale_factor = 4  # Máximo 4x para evitar problemas
                            
                            print(f"Aplicando upscale x{scale_factor} na página {page_num + 1}")
                            
                            # Em workers, usar upscale simples
                            img_path = f"page_{page_num + 1}"  # Identificador único para cache
                            
                            # Verificar cache final primeiro
                            final_cache_hash = get_final_cache_hash(img_path, scale_factor, target_size)
                            if final_cache_hash:
                                cached_img = get_final_cache(final_cache_hash)
                                if cached_img is not None:
                                    print(f"[Cache] Cache final hit para página {page_num + 1}")
                                    img = cached_img
                                else:
                                    # Aplicar upscale simples e salvar no cache
                                    img = img.resize((int(img.width * scale_factor), int(img.height * scale_factor)), Image.Resampling.LANCZOS)
                                    if target_size:
                                        img = img.resize(target_size, Image.Resampling.LANCZOS)
                                    set_final_cache(final_cache_hash, img)
                            else:
                                # Aplicar upscale simples
                                img = img.resize((int(img.width * scale_factor), int(img.height * scale_factor)), Image.Resampling.LANCZOS)
                
                # Salvar imagem
                img_bytes = io.BytesIO()
                img.save(img_bytes, format='PNG', optimize=True)
                
                img_bytes.seek(0)
                
                # Obter dimensões da página antes de fechar
                page_width = page.rect.width
                page_height = page.rect.height
                
                # Fechar o documento PDF
                pdf_doc.close()
                
                return (page_num, img_bytes, page_width, page_height)
                
            except Exception as e:
                print(f"Erro ao processar página {page_num}: {e}")
                try:
                    pdf_doc.close()
                except:
                    pass
                return (page_num, None, 0, 0)
                
        except Exception as e:
            print(f"Erro geral ao processar página {page_num}: {e}")
            return (page_num, None, 0, 0)
    
    def create_etdx(self, output_filename: str = "documento_gerado.etdx", dpi: int = 300, img_format: str = 'png', upscale: bool = True, progress_callback: Optional[Callable[[int, int], None]] = None, paper_size_id: Optional[str] = None, fit_mode: str = "fit") -> None:
        """Cria um arquivo .etdx a partir do PDF"""
        try:
            print(f"Iniciando geração de ETDX: {output_filename}")
            print(f"Configurações: DPI={dpi}, formato={img_format}, modo={fit_mode}")
            
            # Obter informações do PDF
            num_pages = len(self.pdf_document)
            
            # Seleção de tamanho ETDX
            if paper_size_id is None or paper_size_id == 'auto':
                # Detectar tamanho mais próximo
                _, (width_mm, height_mm) = self.get_paper_size_from_pdf()
                etdx_size = find_closest_etdx_size(width_mm, height_mm)
                if etdx_size is None:
                    raise ValueError("Não foi possível determinar o tamanho ETDX mais próximo.")
            else:
                etdx_size = get_etdx_size_by_id(paper_size_id)
                if etdx_size is None:
                    raise ValueError(f"Tamanho de papel não permitido: {paper_size_id}")
            paperSizeId = etdx_size["paperSizeId"]
            size_px = etdx_size["size"]
            label = get_etdx_label_by_paperSizeId(paperSizeId)
            print(f"PDF analisado: {num_pages} páginas, tamanho: {label} (paperSizeId={paperSizeId}, size={size_px})")
            # Sugerir nome do arquivo de saída se for o padrão
            if output_filename == "documento_gerado.etdx":
                output_filename = f"{self.pdf_path.stem}_{paperSizeId}.etdx"
            
            # Criar diretório temporário
            self.temp_dir = tempfile.mkdtemp()
            
            # Estrutura do projeto ETDX seguindo o formato correto
            project_info = {
                "appVersion": "4.0.2.0",
                "editInfo": {
                    "pageEditInfo": {
                        "canAddPage": True,
                        "canCopyPage": True,
                        "canRemovePage": True
                    }
                },
                "formatInfo": {
                    "saveFormat": 0
                }
            }
            
            # Gerar IDs únicos para páginas
            page_ids = []
            for i in range(num_pages):
                page_ids.append(str(uuid.uuid4()).replace('-', '')[:8].upper())
            
            # Processar páginas
            args_list = []
            for page_num in range(num_pages):
                args_list.append((page_num, self.pdf_path, dpi, 'png', upscale))
            
            # Processamento normal
            if MULTIPROCESSING_AVAILABLE and len(args_list) > 1:
                try:
                    with Pool(processes=min(cpu_count(), len(args_list))) as pool:
                        results = pool.map(self._process_page_worker, args_list)
                except Exception as e:
                    print(f"Erro no multiprocessing, usando processamento sequencial: {e}")
                    results = []
                    for args in args_list:
                        result = self._process_page_worker(args)
                        results.append(result)
            else:
                # Processamento sequencial
                results = []
                for args in args_list:
                    result = self._process_page_worker(args)
                    results.append(result)
            
            # Organizar resultados por página
            for page_num, img_bytes, page_width, page_height in results:
                if img_bytes is None:
                    continue
                
                page_id = page_ids[page_num]
                
                # Criar estrutura de diretórios da página
                page_dir = Path(self.temp_dir) / page_id
                page_dir.mkdir(exist_ok=True)
                
                # Criar pasta para imagens (usando ID único)
                image_folder_id = str(uuid.uuid4()).replace('-', '')[:8].upper()
                image_dir = page_dir / image_folder_id
                image_dir.mkdir(exist_ok=True)
                
                # Salvar imagem da página
                img_filename = f"{self.pdf_path.stem}_{page_num + 1}.png"
                img_path = image_dir / img_filename
                
                with open(img_path, 'wb') as f:
                    f.write(img_bytes.getvalue())
                
                # Calcular escala e posição da imagem usando valores corretos
                # Converter dimensões da página de pontos para pixels (assumindo 72 DPI)
                page_width_px = int(page_width * dpi / 72)
                page_height_px = int(page_height * dpi / 72)
                image_size = [page_width_px, page_height_px]
                scale_info = calculate_image_scale_and_position_exact(size_px, image_size, fit_mode)
                
                # Criar dados da página seguindo o formato correto
                page_info = {
                    "version": 3,
                    "id": "LA_FL",
                    "thumbnail": "LA_FL.png",
                    "update": True,
                    "function": "LA",
                    "mediaTypeIdList": [],
                    "editedPaperSize": {
                        "paperSizeId": paperSizeId,
                        "size": size_px,
                        "topleft": [-36, -42],
                        "defaultAddTextFontSize": 48.0,
                        "backgroundData": {
                            "backgroundImage": "",
                            "backgroundPattern": {
                                "type": "C",
                                "size": "L",
                                "patternColor": [255, 255, 255, 255],
                                "patternName": "",
                                "layout": "T",
                                "scale": 1.0,
                                "density": 50
                            }
                        },
                        "vergeData": {
                            "borderType": "BL",
                            "defaultWidth": 42,
                            "maxWidth": 297,
                            "width": 42
                        },
                        "imageFrames": [],
                        "photos": [
                            {
                                "imagepath": f"{image_folder_id}\\{img_filename}",
                                "originalsize": image_size,
                                "center": scale_info["center"],
                                "scale": scale_info["scale"],
                                "crop": scale_info["crop"],
                                "apfInfo": {
                                    "mode": "standard",
                                    "level": 5
                                },
                                "workSpaceNumber": 1,
                                "zindex": 1000
                            }
                        ],
                        "cliparts": [],
                        "messages": [],
                        "sender": {
                            "show": True,
                            "zindex": 1001
                        },
                        "workData": {
                            "maxWorkSpaceCount": 1
                        }
                    },
                    "paperSizeList": [
                        {
                            "paperSizeId": "LB",
                            "size": [1332, 1912],
                            "topleft": [-36, -42],
                            "defaultAddTextFontSize": 20.0,
                            "backgroundData": {
                                "backgroundImage": "",
                                "backgroundPattern": {
                                    "type": "C",
                                    "size": "S",
                                    "patternColor": [255, 255, 255, 255],
                                    "patternName": "",
                                    "layout": "T",
                                    "scale": 1.0,
                                    "density": 50
                                }
                            },
                            "vergeData": {
                                "borderType": "BL",
                                "defaultWidth": 42,
                                "maxWidth": 126,
                                "width": 42
                            },
                            "imageFrames": [],
                            "cliparts": [],
                            "messages": [],
                            "sender": {"show": True},
                            "workData": {"maxWorkSpaceCount": 1}
                        },
                        {
                            "paperSizeId": "2L",
                            "size": [1872, 2634],
                            "topleft": [-36, -42],
                            "defaultAddTextFontSize": 29.0,
                            "backgroundData": {
                                "backgroundImage": "",
                                "backgroundPattern": {
                                    "type": "C",
                                    "size": "L",
                                    "patternColor": [255, 255, 255, 255],
                                    "patternName": "",
                                    "layout": "T",
                                    "scale": 1.0,
                                    "density": 50
                                }
                            },
                            "vergeData": {
                                "borderType": "BL",
                                "defaultWidth": 42,
                                "maxWidth": 180,
                                "width": 42
                            },
                            "imageFrames": [],
                            "cliparts": [],
                            "messages": [],
                            "sender": {"show": True, "zindex": 1001},
                            "workData": {"maxWorkSpaceCount": 1}
                        },
                        {
                            "paperSizeId": "HG",
                            "size": [1489, 2210],
                            "topleft": [-36, -42],
                            "defaultAddTextFontSize": 24.0,
                            "backgroundData": {
                                "backgroundImage": "",
                                "backgroundPattern": {
                                    "type": "C",
                                    "size": "S",
                                    "patternColor": [255, 255, 255, 255],
                                    "patternName": "",
                                    "layout": "T",
                                    "scale": 1.0,
                                    "density": 50
                                }
                            },
                            "vergeData": {
                                "borderType": "BL",
                                "defaultWidth": 42,
                                "maxWidth": 141,
                                "width": 42
                            },
                            "imageFrames": [],
                            "cliparts": [],
                            "messages": [],
                            "sender": {"show": True},
                            "workData": {"maxWorkSpaceCount": 1}
                        },
                        {
                            "paperSizeId": "KG",
                            "size": [1512, 2272],
                            "topleft": [-36, -42],
                            "defaultAddTextFontSize": 25.0,
                            "backgroundData": {
                                "backgroundImage": "",
                                "backgroundPattern": {
                                    "type": "C",
                                    "size": "S",
                                    "patternColor": [255, 255, 255, 255],
                                    "patternName": "",
                                    "layout": "T",
                                    "scale": 1.0,
                                    "density": 50
                                }
                            },
                            "vergeData": {
                                "borderType": "BL",
                                "defaultWidth": 42,
                                "maxWidth": 144,
                                "width": 42
                            },
                            "imageFrames": [],
                            "cliparts": [],
                            "messages": [],
                            "sender": {"show": True},
                            "workData": {"maxWorkSpaceCount": 1}
                        },
                        {
                            "paperSizeId": "S2",
                            "size": [1872, 1912],
                            "topleft": [-36, -42],
                            "defaultAddTextFontSize": 48.0,
                            "backgroundData": {
                                "backgroundImage": "",
                                "backgroundPattern": {
                                    "type": "C",
                                    "size": "L",
                                    "patternColor": [255, 255, 255, 255],
                                    "patternName": "",
                                    "layout": "T",
                                    "scale": 1.0,
                                    "density": 50
                                }
                            },
                            "vergeData": {
                                "borderType": "BL",
                                "defaultWidth": 42,
                                "maxWidth": 180,
                                "width": 42
                            },
                            "imageFrames": [],
                            "cliparts": [],
                            "messages": [],
                            "sender": {"show": True},
                            "workData": {"maxWorkSpaceCount": 1}
                        },
                        {
                            "paperSizeId": "A5",
                            "size": [2170, 3088],
                            "topleft": [-36, -42],
                            "defaultAddTextFontSize": 48.0,
                            "backgroundData": {
                                "backgroundImage": "",
                                "backgroundPattern": {
                                    "type": "C",
                                    "size": "L",
                                    "patternColor": [255, 255, 255, 255],
                                    "patternName": "",
                                    "layout": "T",
                                    "scale": 1.0,
                                    "density": 50
                                }
                            },
                            "vergeData": {
                                "borderType": "BL",
                                "defaultWidth": 42,
                                "maxWidth": 209,
                                "width": 42
                            },
                            "imageFrames": [],
                            "cliparts": [],
                            "messages": [],
                            "sender": {"show": True},
                            "workData": {"maxWorkSpaceCount": 1}
                        },
                        {
                            "paperSizeId": "A4",
                            "size": [3048, 4321],
                            "topleft": [-36, -42],
                            "defaultAddTextFontSize": 48.0,
                            "backgroundData": {
                                "backgroundImage": "",
                                "backgroundPattern": {
                                    "type": "C",
                                    "size": "L",
                                    "patternColor": [255, 255, 255, 255],
                                    "patternName": "",
                                    "layout": "T",
                                    "scale": 1.0,
                                    "density": 50
                                }
                            },
                            "vergeData": {
                                "borderType": "BL",
                                "defaultWidth": 42,
                                "maxWidth": 297,
                                "width": 42
                            },
                            "imageFrames": [],
                            "cliparts": [],
                            "messages": [],
                            "sender": {"show": True},
                            "workData": {"maxWorkSpaceCount": 1}
                        },
                        {
                            "paperSizeId": "A3",
                            "size": [4281, 6065],
                            "topleft": [-36, -42],
                            "defaultAddTextFontSize": 68.0,
                            "backgroundData": {
                                "backgroundImage": "",
                                "backgroundPattern": {
                                    "type": "C",
                                    "size": "L",
                                    "patternColor": [255, 255, 255, 255],
                                    "patternName": "",
                                    "layout": "T",
                                    "scale": 1.0,
                                    "density": 50
                                }
                            },
                            "vergeData": {
                                "borderType": "BL",
                                "defaultWidth": 42,
                                "maxWidth": 420,
                                "width": 42
                            },
                            "imageFrames": [],
                            "cliparts": [],
                            "messages": [],
                            "sender": {"show": True},
                            "workData": {"maxWorkSpaceCount": 1}
                        },
                        {
                            "paperSizeId": "6G",
                            "size": [2952, 3712],
                            "topleft": [-36, -42],
                            "defaultAddTextFontSize": 48.0,
                            "backgroundData": {
                                "backgroundImage": "",
                                "backgroundPattern": {
                                    "type": "C",
                                    "size": "L",
                                    "patternColor": [255, 255, 255, 255],
                                    "patternName": "",
                                    "layout": "T",
                                    "scale": 1.0,
                                    "density": 50
                                }
                            },
                            "vergeData": {
                                "borderType": "BL",
                                "defaultWidth": 42,
                                "maxWidth": 288,
                                "width": 42
                            },
                            "imageFrames": [],
                            "cliparts": [],
                            "messages": [],
                            "sender": {"show": True},
                            "workData": {"maxWorkSpaceCount": 1}
                        },
                        {
                            "paperSizeId": "S1",
                            "size": [3048, 3088],
                            "topleft": [-36, -42],
                            "defaultAddTextFontSize": 48.0,
                            "backgroundData": {
                                "backgroundImage": "",
                                "backgroundPattern": {
                                    "type": "C",
                                    "size": "L",
                                    "patternColor": [255, 255, 255, 255],
                                    "patternName": "",
                                    "layout": "T",
                                    "scale": 1.0,
                                    "density": 50
                                }
                            },
                            "vergeData": {
                                "borderType": "BL",
                                "defaultWidth": 42,
                                "maxWidth": 297,
                                "width": 42
                            },
                            "imageFrames": [],
                            "cliparts": [],
                            "messages": [],
                            "sender": {"show": True},
                            "workData": {"maxWorkSpaceCount": 1}
                        },
                        {
                            "paperSizeId": "A2",
                            "size": [6025, 8531],
                            "topleft": [-36, -42],
                            "defaultAddTextFontSize": 48.0,
                            "backgroundData": {
                                "backgroundImage": "",
                                "backgroundPattern": {
                                    "type": "C",
                                    "size": "L",
                                    "patternColor": [255, 255, 255, 255],
                                    "patternName": "",
                                    "layout": "T",
                                    "scale": 1.0,
                                    "density": 50
                                }
                            },
                            "vergeData": {
                                "borderType": "BL",
                                "defaultWidth": 42,
                                "maxWidth": 595,
                                "width": 42
                            },
                            "imageFrames": [],
                            "cliparts": [],
                            "messages": [],
                            "sender": {"show": True},
                            "workData": {"maxWorkSpaceCount": 1}
                        },
                        {
                            "paperSizeId": "HV",
                            "size": [1512, 2672],
                            "topleft": [-36, -42],
                            "defaultAddTextFontSize": 48.0,
                            "backgroundData": {
                                "backgroundImage": "",
                                "backgroundPattern": {
                                    "type": "C",
                                    "size": "S",
                                    "patternColor": [255, 255, 255, 255],
                                    "patternName": "",
                                    "layout": "T",
                                    "scale": 1.0,
                                    "density": 50
                                }
                            },
                            "vergeData": {
                                "borderType": "BL",
                                "defaultWidth": 42,
                                "maxWidth": 144,
                                "width": 42
                            },
                            "imageFrames": [],
                            "cliparts": [],
                            "messages": [],
                            "sender": {"show": True},
                            "workData": {"maxWorkSpaceCount": 1}
                        },
                        {
                            "paperSizeId": "5A",
                            "size": [2170, 3088],
                            "topleft": [-36, -42],
                            "defaultAddTextFontSize": 48.0,
                            "backgroundData": {
                                "backgroundImage": "",
                                "backgroundPattern": {
                                    "type": "C",
                                    "size": "L",
                                    "patternColor": [255, 255, 255, 255],
                                    "patternName": "",
                                    "layout": "T",
                                    "scale": 1.0,
                                    "density": 50
                                }
                            },
                            "vergeData": {
                                "borderType": "BL",
                                "defaultWidth": 42,
                                "maxWidth": 209,
                                "width": 42
                            },
                            "imageFrames": [],
                            "cliparts": [],
                            "messages": [],
                            "sender": {"show": True},
                            "workData": {"maxWorkSpaceCount": 1}
                        },
                        {
                            "paperSizeId": "CA",
                            "size": [837, 1331],
                            "topleft": [-36, -42],
                            "defaultAddTextFontSize": 15.0,
                            "backgroundData": {
                                "backgroundImage": "",
                                "backgroundPattern": {
                                    "type": "C",
                                    "size": "S",
                                    "patternColor": [255, 255, 255, 255],
                                    "patternName": "",
                                    "layout": "T",
                                    "scale": 1.0,
                                    "density": 50
                                }
                            },
                            "vergeData": {
                                "borderType": "BL",
                                "defaultWidth": 42,
                                "maxWidth": 76,
                                "width": 42
                            },
                            "imageFrames": [],
                            "cliparts": [],
                            "messages": [],
                            "sender": {"show": True},
                            "workData": {"maxWorkSpaceCount": 1}
                        },
                        {
                            "paperSizeId": "MS",
                            "size": [852, 1402],
                            "topleft": [-36, -42],
                            "defaultAddTextFontSize": 15.0,
                            "backgroundData": {
                                "backgroundImage": "",
                                "backgroundPattern": {
                                    "type": "C",
                                    "size": "S",
                                    "patternColor": [255, 255, 255, 255],
                                    "patternName": "",
                                    "layout": "T",
                                    "scale": 1.0,
                                    "density": 50
                                }
                            },
                            "vergeData": {
                                "borderType": "BL",
                                "defaultWidth": 42,
                                "maxWidth": 78,
                                "width": 42
                            },
                            "imageFrames": [],
                            "cliparts": [],
                            "messages": [],
                            "sender": {"show": True},
                            "workData": {"maxWorkSpaceCount": 1}
                        },
                        {
                            "paperSizeId": "3A",
                            "size": [4735, 6958],
                            "topleft": [-36, -42],
                            "defaultAddTextFontSize": 68.0,
                            "backgroundData": {
                                "backgroundImage": "",
                                "backgroundPattern": {
                                    "type": "C",
                                    "size": "L",
                                    "patternColor": [255, 255, 255, 255],
                                    "patternName": "",
                                    "layout": "T",
                                    "scale": 1.0,
                                    "density": 50
                                }
                            },
                            "vergeData": {
                                "borderType": "BL",
                                "defaultWidth": 42,
                                "maxWidth": 466,
                                "width": 42
                            },
                            "imageFrames": [],
                            "cliparts": [],
                            "messages": [],
                            "sender": {"show": True},
                            "workData": {"maxWorkSpaceCount": 1}
                        },
                        {
                            "paperSizeId": "4G",
                            "size": [3672, 4432],
                            "topleft": [-36, -42],
                            "defaultAddTextFontSize": 48.0,
                            "backgroundData": {
                                "backgroundImage": "",
                                "backgroundPattern": {
                                    "type": "C",
                                    "size": "L",
                                    "patternColor": [255, 255, 255, 255],
                                    "patternName": "",
                                    "layout": "T",
                                    "scale": 1.0,
                                    "density": 50
                                }
                            },
                            "vergeData": {
                                "borderType": "BL",
                                "defaultWidth": 42,
                                "maxWidth": 360,
                                "width": 42
                            },
                            "imageFrames": [],
                            "cliparts": [],
                            "messages": [],
                            "sender": {"show": True},
                            "workData": {"maxWorkSpaceCount": 1}
                        },
                        {
                            "paperSizeId": "LT",
                            "size": [3132, 4072],
                            "topleft": [-36, -42],
                            "defaultAddTextFontSize": 45.0,
                            "backgroundData": {
                                "backgroundImage": "",
                                "backgroundPattern": {
                                    "type": "C",
                                    "size": "L",
                                    "patternColor": [255, 255, 255, 255],
                                    "patternName": "",
                                    "layout": "T",
                                    "scale": 1.0,
                                    "density": 50
                                }
                            },
                            "vergeData": {
                                "borderType": "BL",
                                "defaultWidth": 42,
                                "maxWidth": 306,
                                "width": 42
                            },
                            "imageFrames": [],
                            "cliparts": [],
                            "messages": [],
                            "sender": {"show": True},
                            "workData": {"maxWorkSpaceCount": 1}
                        },
                        {
                            "paperSizeId": "LG",
                            "size": [3132, 5152],
                            "topleft": [-36, -42],
                            "defaultAddTextFontSize": 48.0,
                            "backgroundData": {
                                "backgroundImage": "",
                                "backgroundPattern": {
                                    "type": "C",
                                    "size": "L",
                                    "patternColor": [255, 255, 255, 255],
                                    "patternName": "",
                                    "layout": "T",
                                    "scale": 1.0,
                                    "density": 50
                                }
                            },
                            "vergeData": {
                                "borderType": "BL",
                                "defaultWidth": 42,
                                "maxWidth": 306,
                                "width": 42
                            },
                            "imageFrames": [],
                            "cliparts": [],
                            "messages": [],
                            "sender": {"show": True},
                            "workData": {"maxWorkSpaceCount": 1}
                        }
                    ]
                }
                
                # Salvar _info.json da página
                with open(page_dir / "_info.json", 'w', encoding='utf-8') as f:
                    json.dump(page_info, f, ensure_ascii=False)
                
                if progress_callback:
                    progress_callback(page_num + 1, num_pages)
            
            # Criar MasterTemplate
            master_template_dir = Path(self.temp_dir) / "MasterTemplate"
            master_template_dir.mkdir(exist_ok=True)
            
            # Template mestre com todos os tamanhos disponíveis (como nos exemplos)
            master_template_info = {
                "id": "LA_FL",
                "version": 3,
                "thumbnail": "LA_FL.png",
                "update": True,
                "function": "LA",
                "mediaTypeIdList": [],
                "borderType": 0,
                "paperSizeList": [
                    {
                        "paperSizeId": "LB",
                        "size": [1332, 1912],
                        "orientation": 0,
                        "topleft": [-36, -42],
                        "defaultAddTextFontSize": 20.0,
                        "backgroundData": {
                            "backgroundImage": "",
                            "backgroundPattern": {
                                "type": "C",
                                "size": "S",
                                "patternColor": [255, 255, 255, 255],
                                "patternName": "",
                                "layout": "T",
                                "angle": 0.0,
                                "scale": 1.0,
                                "density": 50
                            }
                        },
                        "vergeData": {
                            "borderType": "BL",
                            "isEquablePhotoSize": True,
                            "defaultWidth": 42,
                            "maxWidth": 126,
                            "width": 42
                        },
                        "imageFrames": [],
                        "cliparts": [],
                        "messages": [],
                        "sender": {}
                    },
                    {
                        "paperSizeId": "2L",
                        "size": [1872, 2634],
                        "orientation": 0,
                        "topleft": [-36, -42],
                        "defaultAddTextFontSize": 29.0,
                        "backgroundData": {
                            "backgroundImage": "",
                            "backgroundPattern": {
                                "type": "C",
                                "size": "L",
                                "patternColor": [255, 255, 255, 255],
                                "patternName": "",
                                "layout": "T",
                                "angle": 0.0,
                                "scale": 1.0,
                                "density": 50
                            }
                        },
                        "vergeData": {
                            "borderType": "BL",
                            "isEquablePhotoSize": True,
                            "defaultWidth": 42,
                            "maxWidth": 180,
                            "width": 42
                        },
                        "imageFrames": [],
                        "cliparts": [],
                        "messages": [],
                        "sender": {}
                    },
                    {
                        "paperSizeId": "HG",
                        "size": [1489, 2210],
                        "orientation": 0,
                        "topleft": [-36, -42],
                        "defaultAddTextFontSize": 24.0,
                        "backgroundData": {
                            "backgroundImage": "",
                            "backgroundPattern": {
                                "type": "C",
                                "size": "S",
                                "patternColor": [255, 255, 255, 255],
                                "patternName": "",
                                "layout": "T",
                                "angle": 0.0,
                                "scale": 1.0,
                                "density": 50
                            }
                        },
                        "vergeData": {
                            "borderType": "BL",
                            "isEquablePhotoSize": True,
                            "defaultWidth": 42,
                            "maxWidth": 141,
                            "width": 42
                        },
                        "imageFrames": [],
                        "cliparts": [],
                        "messages": [],
                        "sender": {}
                    },
                    {
                        "paperSizeId": "KG",
                        "size": [1512, 2272],
                        "orientation": 0,
                        "topleft": [-36, -42],
                        "defaultAddTextFontSize": 25.0,
                        "backgroundData": {
                            "backgroundImage": "",
                            "backgroundPattern": {
                                "type": "C",
                                "size": "S",
                                "patternColor": [255, 255, 255, 255],
                                "patternName": "",
                                "layout": "T",
                                "angle": 0.0,
                                "scale": 1.0,
                                "density": 50
                            }
                        },
                        "vergeData": {
                            "borderType": "BL",
                            "isEquablePhotoSize": True,
                            "defaultWidth": 42,
                            "maxWidth": 144,
                            "width": 42
                        },
                        "imageFrames": [],
                        "cliparts": [],
                        "messages": [],
                        "sender": {}
                    },
                    {
                        "paperSizeId": "S2",
                        "size": [1872, 1912],
                        "orientation": 0,
                        "topleft": [-36, -42],
                        "defaultAddTextFontSize": 48.0,
                        "backgroundData": {
                            "backgroundImage": "",
                            "backgroundPattern": {
                                "type": "C",
                                "size": "L",
                                "patternColor": [255, 255, 255, 255],
                                "patternName": "",
                                "layout": "T",
                                "angle": 0.0,
                                "scale": 1.0,
                                "density": 50
                            }
                        },
                        "vergeData": {
                            "borderType": "BL",
                            "isEquablePhotoSize": True,
                            "defaultWidth": 42,
                            "maxWidth": 180,
                            "width": 42
                        },
                        "imageFrames": [],
                        "cliparts": [],
                        "messages": [],
                        "sender": {}
                    },
                    {
                        "paperSizeId": "A5",
                        "size": [2170, 3088],
                        "orientation": 0,
                        "topleft": [-36, -42],
                        "defaultAddTextFontSize": 48.0,
                        "backgroundData": {
                            "backgroundImage": "",
                            "backgroundPattern": {
                                "type": "C",
                                "size": "L",
                                "patternColor": [255, 255, 255, 255],
                                "patternName": "",
                                "layout": "T",
                                "angle": 0.0,
                                "scale": 1.0,
                                "density": 50
                            }
                        },
                        "vergeData": {
                            "borderType": "BL",
                            "isEquablePhotoSize": True,
                            "defaultWidth": 42,
                            "maxWidth": 209,
                            "width": 42
                        },
                        "imageFrames": [],
                        "cliparts": [],
                        "messages": [],
                        "sender": {}
                    },
                    {
                        "paperSizeId": "A4",
                        "size": [3048, 4321],
                        "orientation": 0,
                        "topleft": [-36, -42],
                        "defaultAddTextFontSize": 48.0,
                        "backgroundData": {
                            "backgroundImage": "",
                            "backgroundPattern": {
                                "type": "C",
                                "size": "L",
                                "patternColor": [255, 255, 255, 255],
                                "patternName": "",
                                "layout": "T",
                                "angle": 0.0,
                                "scale": 1.0,
                                "density": 50
                            }
                        },
                        "vergeData": {
                            "borderType": "BL",
                            "isEquablePhotoSize": True,
                            "defaultWidth": 42,
                            "maxWidth": 297,
                            "width": 42
                        },
                        "imageFrames": [],
                        "cliparts": [],
                        "messages": [],
                        "sender": {}
                    },
                    {
                        "paperSizeId": "A3",
                        "size": [4281, 6065],
                        "orientation": 0,
                        "topleft": [-36, -42],
                        "defaultAddTextFontSize": 68.0,
                        "backgroundData": {
                            "backgroundImage": "",
                            "backgroundPattern": {
                                "type": "C",
                                "size": "L",
                                "patternColor": [255, 255, 255, 255],
                                "patternName": "",
                                "layout": "T",
                                "angle": 0.0,
                                "scale": 1.0,
                                "density": 50
                            }
                        },
                        "vergeData": {
                            "borderType": "BL",
                            "isEquablePhotoSize": True,
                            "defaultWidth": 42,
                            "maxWidth": 420,
                            "width": 42
                        },
                        "imageFrames": [],
                        "cliparts": [],
                        "messages": [],
                        "sender": {}
                    },
                    {
                        "paperSizeId": "6G",
                        "size": [2952, 3712],
                        "orientation": 0,
                        "topleft": [-36, -42],
                        "defaultAddTextFontSize": 48.0,
                        "backgroundData": {
                            "backgroundImage": "",
                            "backgroundPattern": {
                                "type": "C",
                                "size": "L",
                                "patternColor": [255, 255, 255, 255],
                                "patternName": "",
                                "layout": "T",
                                "angle": 0.0,
                                "scale": 1.0,
                                "density": 50
                            }
                        },
                        "vergeData": {
                            "borderType": "BL",
                            "isEquablePhotoSize": True,
                            "defaultWidth": 42,
                            "maxWidth": 288,
                            "width": 42
                        },
                        "imageFrames": [],
                        "cliparts": [],
                        "messages": [],
                        "sender": {}
                    },
                    {
                        "paperSizeId": "S1",
                        "size": [3048, 3088],
                        "orientation": 0,
                        "topleft": [-36, -42],
                        "defaultAddTextFontSize": 48.0,
                        "backgroundData": {
                            "backgroundImage": "",
                            "backgroundPattern": {
                                "type": "C",
                                "size": "L",
                                "patternColor": [255, 255, 255, 255],
                                "patternName": "",
                                "layout": "T",
                                "angle": 0.0,
                                "scale": 1.0,
                                "density": 50
                            }
                        },
                        "vergeData": {
                            "borderType": "BL",
                            "isEquablePhotoSize": True,
                            "defaultWidth": 42,
                            "maxWidth": 297,
                            "width": 42
                        },
                        "imageFrames": [],
                        "cliparts": [],
                        "messages": [],
                        "sender": {}
                    },
                    {
                        "paperSizeId": "A2",
                        "size": [6025, 8531],
                        "orientation": 0,
                        "topleft": [-36, -42],
                        "defaultAddTextFontSize": 48.0,
                        "backgroundData": {
                            "backgroundImage": "",
                            "backgroundPattern": {
                                "type": "C",
                                "size": "L",
                                "patternColor": [255, 255, 255, 255],
                                "patternName": "",
                                "layout": "T",
                                "angle": 0.0,
                                "scale": 1.0,
                                "density": 50
                            }
                        },
                        "vergeData": {
                            "borderType": "BL",
                            "isEquablePhotoSize": True,
                            "defaultWidth": 42,
                            "maxWidth": 595,
                            "width": 42
                        },
                        "imageFrames": [],
                        "cliparts": [],
                        "messages": [],
                        "sender": {}
                    },
                    {
                        "paperSizeId": "HV",
                        "size": [1512, 2672],
                        "orientation": 0,
                        "topleft": [-36, -42],
                        "defaultAddTextFontSize": 48.0,
                        "backgroundData": {
                            "backgroundImage": "",
                            "backgroundPattern": {
                                "type": "C",
                                "size": "S",
                                "patternColor": [255, 255, 255, 255],
                                "patternName": "",
                                "layout": "T",
                                "angle": 0.0,
                                "scale": 1.0,
                                "density": 50
                            }
                        },
                        "vergeData": {
                            "borderType": "BL",
                            "isEquablePhotoSize": True,
                            "defaultWidth": 42,
                            "maxWidth": 144,
                            "width": 42
                        },
                        "imageFrames": [],
                        "cliparts": [],
                        "messages": [],
                        "sender": {}
                    },
                    {
                        "paperSizeId": "5A",
                        "size": [2170, 3088],
                        "orientation": 0,
                        "topleft": [-36, -42],
                        "defaultAddTextFontSize": 48.0,
                        "backgroundData": {
                            "backgroundImage": "",
                            "backgroundPattern": {
                                "type": "C",
                                "size": "L",
                                "patternColor": [255, 255, 255, 255],
                                "patternName": "",
                                "layout": "T",
                                "angle": 0.0,
                                "scale": 1.0,
                                "density": 50
                            }
                        },
                        "vergeData": {
                            "borderType": "BL",
                            "isEquablePhotoSize": True,
                            "defaultWidth": 42,
                            "maxWidth": 209,
                            "width": 42
                        },
                        "imageFrames": [],
                        "cliparts": [],
                        "messages": [],
                        "sender": {}
                    },
                    {
                        "paperSizeId": "CA",
                        "size": [837, 1331],
                        "orientation": 0,
                        "topleft": [-36, -42],
                        "defaultAddTextFontSize": 15.0,
                        "backgroundData": {
                            "backgroundImage": "",
                            "backgroundPattern": {
                                "type": "C",
                                "size": "S",
                                "patternColor": [255, 255, 255, 255],
                                "patternName": "",
                                "layout": "T",
                                "angle": 0.0,
                                "scale": 1.0,
                                "density": 50
                            }
                        },
                        "vergeData": {
                            "borderType": "BL",
                            "isEquablePhotoSize": True,
                            "defaultWidth": 42,
                            "maxWidth": 76,
                            "width": 42
                        },
                        "imageFrames": [],
                        "cliparts": [],
                        "messages": [],
                        "sender": {}
                    },
                    {
                        "paperSizeId": "MS",
                        "size": [852, 1402],
                        "orientation": 0,
                        "topleft": [-36, -42],
                        "defaultAddTextFontSize": 15.0,
                        "backgroundData": {
                            "backgroundImage": "",
                            "backgroundPattern": {
                                "type": "C",
                                "size": "S",
                                "patternColor": [255, 255, 255, 255],
                                "patternName": "",
                                "layout": "T",
                                "angle": 0.0,
                                "scale": 1.0,
                                "density": 50
                            }
                        },
                        "vergeData": {
                            "borderType": "BL",
                            "isEquablePhotoSize": True,
                            "defaultWidth": 42,
                            "maxWidth": 78,
                            "width": 42
                        },
                        "imageFrames": [],
                        "cliparts": [],
                        "messages": [],
                        "sender": {}
                    },
                    {
                        "paperSizeId": "3A",
                        "size": [4735, 6958],
                        "orientation": 0,
                        "topleft": [-36, -42],
                        "defaultAddTextFontSize": 68.0,
                        "backgroundData": {
                            "backgroundImage": "",
                            "backgroundPattern": {
                                "type": "C",
                                "size": "L",
                                "patternColor": [255, 255, 255, 255],
                                "patternName": "",
                                "layout": "T",
                                "angle": 0.0,
                                "scale": 1.0,
                                "density": 50
                            }
                        },
                        "vergeData": {
                            "borderType": "BL",
                            "isEquablePhotoSize": True,
                            "defaultWidth": 42,
                            "maxWidth": 466,
                            "width": 42
                        },
                        "imageFrames": [],
                        "cliparts": [],
                        "messages": [],
                        "sender": {}
                    },
                    {
                        "paperSizeId": "4G",
                        "size": [3672, 4432],
                        "orientation": 0,
                        "topleft": [-36, -42],
                        "defaultAddTextFontSize": 48.0,
                        "backgroundData": {
                            "backgroundImage": "",
                            "backgroundPattern": {
                                "type": "C",
                                "size": "L",
                                "patternColor": [255, 255, 255, 255],
                                "patternName": "",
                                "layout": "T",
                                "angle": 0.0,
                                "scale": 1.0,
                                "density": 50
                            }
                        },
                        "vergeData": {
                            "borderType": "BL",
                            "isEquablePhotoSize": True,
                            "defaultWidth": 42,
                            "maxWidth": 360,
                            "width": 42
                        },
                        "imageFrames": [],
                        "cliparts": [],
                        "messages": [],
                        "sender": {}
                    },
                    {
                        "paperSizeId": "LT",
                        "size": [3132, 4072],
                        "orientation": 0,
                        "topleft": [-36, -42],
                        "defaultAddTextFontSize": 45.0,
                        "backgroundData": {
                            "backgroundImage": "",
                            "backgroundPattern": {
                                "type": "C",
                                "size": "L",
                                "patternColor": [255, 255, 255, 255],
                                "patternName": "",
                                "layout": "T",
                                "angle": 0.0,
                                "scale": 1.0,
                                "density": 50
                            }
                        },
                        "vergeData": {
                            "borderType": "BL",
                            "isEquablePhotoSize": True,
                            "defaultWidth": 42,
                            "maxWidth": 306,
                            "width": 42
                        },
                        "imageFrames": [],
                        "cliparts": [],
                        "messages": [],
                        "sender": {}
                    },
                    {
                        "paperSizeId": "LG",
                        "size": [3132, 5152],
                        "orientation": 0,
                        "topleft": [-36, -42],
                        "defaultAddTextFontSize": 48.0,
                        "backgroundData": {
                            "backgroundImage": "",
                            "backgroundPattern": {
                                "type": "C",
                                "size": "L",
                                "patternColor": [255, 255, 255, 255],
                                "patternName": "",
                                "layout": "T",
                                "angle": 0.0,
                                "scale": 1.0,
                                "density": 50
                            }
                        },
                        "vergeData": {
                            "borderType": "BL",
                            "isEquablePhotoSize": True,
                            "defaultWidth": 42,
                            "maxWidth": 306,
                            "width": 42
                        },
                        "imageFrames": [],
                        "cliparts": [],
                        "messages": [],
                        "sender": {}
                    }
                ]
            }
            
            # Salvar MasterTemplate/_info.json
            with open(master_template_dir / "_info.json", 'w', encoding='utf-8') as f:
                json.dump(master_template_info, f, indent=2, ensure_ascii=False)
            
            # Salvar projectInfo.json
            with open(Path(self.temp_dir) / "projectInfo.json", 'w', encoding='utf-8') as f:
                json.dump(project_info, f, indent=2, ensure_ascii=False)
            
            # Salvar page.json (lista de IDs das páginas)
            with open(Path(self.temp_dir) / "page.json", 'w', encoding='utf-8') as f:
                json.dump(page_ids, f, ensure_ascii=False)
            
            # Criar arquivo .etdx (ZIP)
            with zipfile.ZipFile(output_filename, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for root, dirs, files in os.walk(self.temp_dir):
                    for file in files:
                        file_path = Path(root) / file
                        arcname = file_path.relative_to(self.temp_dir)
                        zipf.write(file_path, arcname)
            
            print(f"ETDX gerado com sucesso: {output_filename}")
            print(f"Páginas processadas: {len(page_ids)}")
            
        except Exception as e:
            print(f"Erro ao gerar ETDX: {e}")
            raise
        finally:
            # Limpar diretório temporário
            if self.temp_dir and os.path.exists(self.temp_dir):
                shutil.rmtree(self.temp_dir)
            safe_clear_etdx_upscale_cache()
    
    def print_summary(self):
        """Imprime resumo do processamento"""
        print("\n=== RESUMO DO PROCESSAMENTO ===")
        print(f"Arquivo PDF: {self.pdf_path}")
        print(f"Páginas: {len(self.pdf_document)}")
        paper_size_id, (width_mm, height_mm) = self.get_paper_size_from_pdf()
        print(f"Tamanho do papel: {paper_size_id} ({width_mm:.1f}x{height_mm:.1f}mm)")
        print(f"ID do projeto: {self.project_id}")
    
    def __del__(self):
        """Destrutor para limpeza"""
        if hasattr(self, 'pdf_document'):
            self.pdf_document.close()
        if hasattr(self, 'temp_dir') and self.temp_dir and os.path.exists(self.temp_dir):
            shutil.rmtree(self.temp_dir) 