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

# Importar módulo de upscaling com IA
try:
    from .ai_upscaler import upscale_image, is_ai_upscaling_available, get_available_devices
    AI_UPSCALE_AVAILABLE = is_ai_upscaling_available()
except ImportError:
    AI_UPSCALE_AVAILABLE = False
    def upscale_image(img, scale_factor=4, device="auto", target_size=None):
        # Fallback para upscale simples
        if target_size:
            return img.resize(target_size, Image.Resampling.LANCZOS)
        else:
            new_width = img.width * scale_factor
            new_height = img.height * scale_factor
            return img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    def get_available_devices():
        return ["cpu"]

# Suporte para PyInstaller
if getattr(sys, 'frozen', False):
    multiprocessing.freeze_support()

# Lock global para upscaling - evita múltiplas chamadas simultâneas de upscale_image
# que podem causar problemas de memória e performance em multiprocessing
upscale_lock = Lock()

# Flag para controlar se o multiprocessing está funcionando
MULTIPROCESSING_AVAILABLE = not getattr(sys, 'frozen', False)


class ETDXGenerator:
    """Gerador de arquivos .etdx a partir de PDFs"""
    
    def __init__(self, pdf_path):
        self.pdf_path = Path(pdf_path)
        self.temp_dir = None
        self.project_id = str(uuid.uuid4())
        self.created_at = datetime.now().isoformat()
        self.detected_paper_size = None  # Armazenar o tamanho detectado
        
        # Verificar se o arquivo PDF existe
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"Arquivo PDF não encontrado: {pdf_path}")
        
        # Abrir o PDF para análise
        self.pdf_document = fitz.Document(str(self.pdf_path))
        
    def get_paper_size_from_pdf(self, page_num=0) -> Tuple[str, Tuple[float, float]]:
        """Extrai o tamanho do papel do PDF e retorna o identificador do tamanho permitido mais próximo"""
        if not self.pdf_document:
            raise ValueError("Documento PDF não está aberto")
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
    

    def calculate_optimal_render_dpi(self, page_num: int = 0) -> float:
        """Calcula o DPI ótimo para renderizar uma página específica baseado nas imagens contidas"""
        if not self.pdf_document or page_num >= len(self.pdf_document):
            return 300.0
            
        print(f"Calculando DPI ótimo para renderização da página {page_num + 1}...")
        
        page = self.pdf_document[page_num]
        image_list = page.get_images(full=True)
        
        if not image_list:
            print(f"Página {page_num + 1}: nenhuma imagem encontrada, usando DPI padrão: 300")
            return 300.0
        
        # Lista para armazenar todos os DPIs das imagens da página
        page_dpi_values = []
        total_images = 0
        
        for img_index, img in enumerate(image_list):
            try:
                is_mask = img[7]
                if is_mask:
                    continue  # pula máscaras
                    
                # Obter informações da imagem
                xref = img[0]  # Referência da imagem no PDF
                pix = fitz.Pixmap(self.pdf_document, xref)
                
                # Calcular DPI real da imagem baseado no tamanho físico
                img_rect = page.get_image_bbox(xref)
                if img_rect:
                    # img_rect é uma tupla (Rect, Matrix), pegar apenas o Rect
                    rect = img_rect[0] if isinstance(img_rect, tuple) else img_rect
                    # Converter pontos para polegadas (1 ponto = 1/72 polegada)
                    img_width_inches = rect.width / 72.0
                    img_height_inches = rect.height / 72.0
                    
                    # Calcular DPI real
                    dpi_width = pix.width / img_width_inches if img_width_inches > 0 else 0
                    dpi_height = pix.height / img_height_inches if img_height_inches > 0 else 0
                    
                    # Usar o menor DPI (mais conservador)
                    img_dpi = min(dpi_width, dpi_height)
                    
                    if img_dpi > 0:
                        page_dpi_values.append(img_dpi)
                        total_images += 1
                        print(f"  Imagem {img_index + 1}: {pix.width}x{pix.height} @ {img_dpi:.1f} DPI")
                
                pix = None  # Liberar memória
                
            except Exception as e:
                print(f"Erro ao calcular DPI da imagem {img_index} na página {page_num + 1}: {e}")
                continue
        
        # Calcular DPI médio da página
        if page_dpi_values:
            # Usar o DPI médio das imagens da página
            optimal_dpi = sum(page_dpi_values) / len(page_dpi_values)
            
            # Limitar o DPI máximo para evitar problemas de memória
            max_dpi = 600  # DPI máximo razoável
            if optimal_dpi > max_dpi:
                print(f"  DPI calculado ({optimal_dpi:.1f}) muito alto, limitando a {max_dpi}")
                optimal_dpi = max_dpi
            
            print(f"Página {page_num + 1}: {total_images} imagens, DPI ótimo para renderização: {optimal_dpi:.1f}")
            return optimal_dpi
        else:
            print(f"Página {page_num + 1}: nenhuma imagem válida encontrada, usando DPI padrão: 300")
            return 300.0

    def render_page_at_optimal_dpi(self, page_num: int = 0) -> Optional[Image.Image]:
        """Renderiza uma página específica com o DPI ótimo baseado nas imagens contidas"""
        if not self.pdf_document or page_num >= len(self.pdf_document):
            return None
            
        try:
            page = self.pdf_document[page_num]
            
            # Calcular DPI ótimo para esta página
            optimal_dpi = self.calculate_optimal_render_dpi(page_num)
            
            # Calcular fator de escala baseado no DPI ótimo
            # DPI padrão do PDF é 72, então o fator de escala é optimal_dpi / 72
            scale_factor = optimal_dpi / 72.0
            
            print(f"Renderizando página {page_num + 1} com fator de escala: {scale_factor:.3f} (DPI: {optimal_dpi:.1f})")
            
            # Criar matriz de transformação com o fator de escala
            mat = fitz.Matrix(scale_factor, scale_factor)
            
            # Renderizar página como imagem
            pix = page.get_pixmap(matrix=mat)  # type: ignore
            img_data = pix.tobytes("png")
            
            # Converter para PIL Image
            img = Image.open(io.BytesIO(img_data)).convert('RGB')
            
            print(f"Página {page_num + 1} renderizada: {img.width}x{img.height} pixels")
            
            return img
            
        except Exception as e:
            print(f"Erro ao renderizar página {page_num + 1} com DPI ótimo: {e}")
            return None



    @staticmethod
    def _process_page_worker(args: Tuple[int, str, bool, Tuple[int, int]]) -> Tuple[int, Optional[io.BytesIO]]:
        """Worker para processamento de página com multiprocessing"""
        (page_num, pdf_path, upscale, target_size_px) = args
        
        try:
            # Abrir o PDF com tratamento de erro mais robusto
            try:
                pdf_doc = fitz.Document(str(pdf_path))  # type: ignore
                if page_num >= len(pdf_doc):
                    print(f"Página {page_num} não existe no PDF")
                    return (page_num, None)
                page = pdf_doc[page_num]
            except Exception as e:
                print(f"Erro ao abrir PDF ou acessar página {page_num}: {e}")
                return (page_num, None)
            
            try:
                # Calcular DPI ótimo para esta página específica
                print(f"Calculando DPI ótimo para página {page_num + 1}...")
                
                # Obter lista de imagens da página
                image_list = page.get_images(full=True)
                page_dpi_values = []
                
                if image_list:
                    for img_index, img_info in enumerate(image_list):
                        try:
                            is_mask = img_info[7]
                            if is_mask:
                                continue  # pula máscaras
                                
                            # Obter informações da imagem
                            xref = img_info[0]  # Referência da imagem no PDF
                            pix = fitz.Pixmap(pdf_doc, xref)  # type: ignore
                            
                            # Calcular DPI real da imagem baseado no tamanho físico
                            img_rect = page.get_image_bbox(xref)
                            if img_rect:
                                # img_rect é uma tupla (Rect, Matrix), pegar apenas o Rect
                                rect = img_rect[0] if isinstance(img_rect, tuple) else img_rect
                                # Converter pontos para polegadas (1 ponto = 1/72 polegada)
                                img_width_inches = rect.width / 72.0
                                img_height_inches = rect.height / 72.0
                                
                                # Calcular DPI real
                                dpi_width = pix.width / img_width_inches if img_width_inches > 0 else 0
                                dpi_height = pix.height / img_height_inches if img_height_inches > 0 else 0
                                
                                # Usar o menor DPI (mais conservador)
                                img_dpi = min(dpi_width, dpi_height)
                                
                                if img_dpi > 0:
                                    page_dpi_values.append(img_dpi)
                                    print(f"  Imagem {img_index + 1}: {pix.width}x{pix.height} @ {img_dpi:.1f} DPI")
                            
                            pix = None  # Liberar memória
                            
                        except Exception as e:
                            print(f"Erro ao calcular DPI da imagem {img_index} na página {page_num + 1}: {e}")
                            continue
                
                # Calcular DPI ótimo para renderização
                if page_dpi_values:
                    optimal_dpi = sum(page_dpi_values) / len(page_dpi_values)
                    # Limitar o DPI máximo para evitar problemas de memória
                    max_dpi = 600
                    if optimal_dpi > max_dpi:
                        print(f"  DPI calculado ({optimal_dpi:.1f}) muito alto, limitando a {max_dpi}")
                        optimal_dpi = max_dpi
                    print(f"Página {page_num + 1}: {len(page_dpi_values)} imagens, DPI ótimo: {optimal_dpi:.1f}")
                else:
                    optimal_dpi = 300.0
                    print(f"Página {page_num + 1}: nenhuma imagem encontrada, usando DPI padrão: {optimal_dpi}")
                
                # Calcular fator de escala baseado no DPI ótimo
                # DPI padrão do PDF é 72, então o fator de escala é optimal_dpi / 72
                scale_factor = optimal_dpi / 72.0
                
                print(f"Renderizando página {page_num + 1} com fator de escala: {scale_factor:.3f} (DPI: {optimal_dpi:.1f})")
                
                # Criar matriz de transformação com o fator de escala
                mat = fitz.Matrix(scale_factor, scale_factor)
                pix = page.get_pixmap(matrix=mat)  # type: ignore
                img_data = pix.tobytes("png")
                
                # Converter para PIL Image
                img = Image.open(io.BytesIO(img_data)).convert('RGB')
                
                # Calcular o tamanho alvo respeitando a proporção da imagem
                # Usar a função calculate_image_scale_and_position_exact para determinar a escala correta
                scale_info = calculate_image_scale_and_position_exact(target_size_px, [img.width, img.height], "fit")
                scale = scale_info["scale"]
                    
                # Calcular o tamanho da imagem escalada mantendo a proporção
                scaled_width = int(img.width * scale)
                scaled_height = int(img.height * scale)
                    
                print(f"Página {page_num + 1}: imagem={img.width}x{img.height}, escala={scale:.3f}, tamanho escalado={scaled_width}x{scaled_height}")
                    
                # Calcular fator de escala baseado no tamanho mínimo desejado
                scale_factor = scale
                    
                # Limitar o fator de escala
                if scale_factor <= 2:
                    scale_factor = 2
                elif scale_factor <= 4:
                    scale_factor = 4
                elif scale_factor <= 8:
                    scale_factor = 8
                else:
                    scale_factor = 8  # Máximo 8x para evitar problemas
                    
                print(f"Página {page_num + 1}: precisa upscale, fator={scale_factor:.2f}")
                    
                # Em workers, usar upscale simples
                img_path = f"page_{page_num + 1}"  # Identificador único para cache
                    
                # Calcular tamanho após upscale (mantendo proporção)
                upscaled_width = int(img.width * scale_factor)
                upscaled_height = int(img.height * scale_factor)
                upscaled_size = (upscaled_width, upscaled_height)

                # Aplicar upscale se necessário
                if AI_UPSCALE_AVAILABLE and upscale:
                    # Usar upscaling com IA se disponível e não for executável compilado
                    if AI_UPSCALE_AVAILABLE and not getattr(sys, 'frozen', False):
                        try:
                            print(f"Aplicando upscale com IA x{scale_factor} na página {page_num + 1}")
                                # Usar lock para evitar múltiplas chamadas simultâneas de upscale_image
                            with upscale_lock:
                                img = upscale_image(img, scale_factor=scale_factor)
                        except Exception as e:
                            print(f"Erro no upscale com IA: {e}, usando upscale simples")
                            # Fallback para upscale simples
                            img = img.resize(upscaled_size, Image.Resampling.LANCZOS)
                    else:
                        # Upscale simples (para executável compilado ou quando IA não está disponível)
                        if getattr(sys, 'frozen', False):
                            print(f"Aplicando upscale simples x{scale_factor} na página {page_num + 1} (executável compilado)")
                        else:
                            print(f"Aplicando upscale simples x{scale_factor} na página {page_num + 1}")
                        img = img.resize(upscaled_size, Image.Resampling.LANCZOS)
                else:
                    print(f"Página {page_num + 1}: upscale desabilitado, seguindo com upscale simples")
                
                img = img.resize(upscaled_size, Image.Resampling.LANCZOS)

                
                # Salvar imagem
                img_bytes = io.BytesIO()
                img.save(img_bytes, format='PNG', optimize=True)
                
                img_bytes.seek(0)
                
                # Fechar o documento PDF
                pdf_doc.close()
                
                return (page_num, img_bytes)
                
            except Exception as e:
                print(f"Erro ao processar página {page_num}: {e}")
                try:
                    pdf_doc.close()
                except:
                    pass
                return (page_num, None)
                
        except Exception as e:
            print(f"Erro geral ao processar página {page_num}: {e}")
            return (page_num, None)
    
    def create_etdx(self, output_filename: str = "documento_gerado.etdx", dpi: int = 300, 
        img_format: str = 'png', upscale: bool = True, 
        progress_callback: Optional[Callable[[int, int], None]] = None, 
        paper_size_id: Optional[str] = None, fit_mode: str = "fit") -> None:
        """Cria um arquivo .etdx a partir do PDF"""

        try:
            print(f"Iniciando geração de ETDX: {output_filename}")
            print(f"Configurações: DPI={dpi}, formato={img_format}, modo={fit_mode}")
                
            
            # Obter informações do PDF
            if not self.pdf_document:
                raise ValueError("Documento PDF não está aberto")
            num_pages = len(self.pdf_document)
            
            # Seleção de tamanho ETDX
            if paper_size_id is None or paper_size_id == 'auto':
                # Detectar tamanho mais próximo
                detected_id, (width_mm, height_mm) = self.get_paper_size_from_pdf()
                etdx_size = find_closest_etdx_size(width_mm, height_mm)
                if etdx_size is None:
                    raise ValueError("Não foi possível determinar o tamanho ETDX mais próximo.")
                # Armazenar o tamanho detectado para uso no resumo
                self.detected_paper_size = (detected_id, width_mm, height_mm)
            else:
                etdx_size = get_etdx_size_by_id(paper_size_id)
                if etdx_size is None:
                    raise ValueError(f"Tamanho de papel não permitido: {paper_size_id}")
                # Armazenar o tamanho especificado para uso no resumo
                self.detected_paper_size = (paper_size_id, etdx_size["size"][0]/14.5, etdx_size["size"][1]/14.5)
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
                args_list.append((page_num, self.pdf_path, upscale, size_px))
            
            # Processamento normal
            if MULTIPROCESSING_AVAILABLE and len(args_list) > 1 and not upscale:
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
            for page_num, img_bytes in results:
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
                # Usar as dimensões reais da imagem processada
                img = Image.open(img_bytes)
                image_size = [img.width, img.height]
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
    
    def print_summary(self):
        """Imprime resumo do processamento"""
        print("\n=== RESUMO DO PROCESSAMENTO ===")
        print(f"Arquivo PDF: {self.pdf_path}")
        if not self.pdf_document:
            print("Páginas: Documento não disponível")
        else:
            print(f"Páginas: {len(self.pdf_document)}")
        
        # Usar o tamanho detectado durante a criação do ETDX
        if self.detected_paper_size:
            paper_size_id, width_mm, height_mm = self.detected_paper_size
            print(f"Tamanho do papel: {paper_size_id} ({width_mm:.1f}x{height_mm:.1f}mm)")
        else:
            # Fallback para detecção se não foi armazenado
            paper_size_id, (width_mm, height_mm) = self.get_paper_size_from_pdf()
            print(f"Tamanho do papel: {paper_size_id} ({width_mm:.1f}x{height_mm:.1f}mm)")
        
        print(f"ID do projeto: {self.project_id}")
    
    def close(self):
        """Fecha o documento PDF de forma segura"""
        try:
            if hasattr(self, 'pdf_document') and self.pdf_document:
                try:
                    self.pdf_document.close()
                    self.pdf_document = None
                except (ValueError, AttributeError):
                    # Documento já foi fechado
                    pass
        except Exception as e:
            print(f"Erro ao fechar documento PDF: {e}")

    def __del__(self):
        """Destrutor para limpeza"""
        try:
            if hasattr(self, 'pdf_document') and self.pdf_document:
                try:
                    self.pdf_document.close()
                except (ValueError, AttributeError):
                    # Documento já foi fechado ou não existe
                    pass
        except Exception:
            pass 