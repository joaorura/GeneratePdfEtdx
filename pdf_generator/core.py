import json
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.colors import white
from PIL import Image
import zipfile
import tempfile
import io
import multiprocessing
from multiprocessing import Pool, cpu_count, Lock
import sys
import os

# Suporte para PyInstaller
if getattr(sys, 'frozen', False):
    # Executando como executável compilado
    multiprocessing.freeze_support()

# Lock global para RealESRGAN - deve ser multiprocessing.Lock() para funcionar com Pool
realesrgan_lock = Lock()

# Flag para controlar se o multiprocessing está funcionando
# Em executáveis compilados, desabilita por padrão para evitar problemas
MULTIPROCESSING_AVAILABLE = not getattr(sys, 'frozen', False)

class PDFGenerator:
    def __init__(self, ref_path):
        self.ref_path = Path(ref_path)
        self.project_info = {}
        self.page_list = []
        self.master_template = {}
        self.pages_data = {}

    @staticmethod
    def _preprocess_image_no_upscale_worker(args):
        """Worker function para processamento paralelo SEM upscale"""
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
            # Upscale inteligente se necessário
            if upscale and (img.width < target_px_width or img.height < target_px_height):
                scale_factor = max(target_px_width / img.width, target_px_height / img.height)
                # RealESRGAN suporta apenas 2x, 4x, 8x
                if scale_factor > 1.5:
                    if scale_factor <= 2:
                        scale_factor = 2
                    elif scale_factor <= 4:
                        scale_factor = 4
                    else:
                        scale_factor = 4  # Máximo 4x para evitar problemas
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
        # Tamanhos em mm (A4, A3, etc)
        mm_sizes = {
            'A4': (210, 297),
            'A3': (297, 420),
            'A5': (148, 210),
            'LB': (89, 127),
            '2L': (127, 178),
            'HG': (102, 152),
            'KG': (102, 152),
            'S2': (127, 127),
        }
        size_mm = mm_sizes.get(paper_size_id, mm_sizes['A4'])
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

    def upscale_realesrgan(self, img, scale=2):
        """Tenta usar RealESRGAN com lock para evitar problemas de múltiplas threads"""
        with realesrgan_lock:  # Garante que apenas uma thread use RealESRGAN por vez
            try:
                from py_real_esrgan.model import RealESRGAN
                import torch
                device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
                model = RealESRGAN(device, scale=scale)
                model.load_weights(f"weights/RealESRGAN_x{scale}.pth", download=True)
                img_up = model.predict(img)
                return img_up
            except ImportError:
                print("RealESRGAN não disponível, usando upscale simples")
                return self.upscale_simple(img, scale)
            except Exception as e:
                print(f"Erro no RealESRGAN: {e}, usando upscale simples")
                return self.upscale_simple(img, scale)

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
            # Upscale inteligente se necessário
            if img.width < target_px_width or img.height < target_px_height:
                scale_factor = max(target_px_width / img.width, target_px_height / img.height)
                # RealESRGAN suporta apenas 2x, 4x, 8x
                if scale_factor > 1.5:
                    if scale_factor <= 2:
                        scale_factor = 2
                    elif scale_factor <= 4:
                        scale_factor = 4
                    else:
                        scale_factor = 4  # Máximo 4x para evitar problemas
                    img = self.upscale_realesrgan(img, scale=scale_factor)
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
        self.load_project_info()
        self.load_page_list()
        self.load_master_template()
        for page_id in self.page_list:
            self.load_page_data(page_id)
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
                for args in images_with_upscale:
                    result = self.preprocess_image_with_upscale(args)
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