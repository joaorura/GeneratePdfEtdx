import json
import os
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, A3, letter
from reportlab.lib.units import inch, mm
from reportlab.lib.colors import white
from PIL import Image
import math
import sys
import zipfile
import tempfile
import shutil

class PDFGenerator:
    def __init__(self, ref_path):
        self.ref_path = Path(ref_path)
        self.project_info = {}
        self.page_list = []
        self.master_template = {}
        self.pages_data = {}
        
    def load_project_info(self):
        """Carrega informações gerais do projeto"""
        project_file = self.ref_path / "projectInfo.json"
        if project_file.exists():
            with open(project_file, 'r', encoding='utf-8') as f:
                self.project_info = json.load(f)
                print(f"Projeto carregado - Versão: {self.project_info.get('appVersion', 'N/A')}")
    
    def load_page_list(self):
        """Carrega a lista de páginas"""
        page_file = self.ref_path / "page.json"
        if page_file.exists():
            with open(page_file, 'r', encoding='utf-8') as f:
                self.page_list = json.load(f)
                print(f"Páginas encontradas: {self.page_list}")
    
    def load_master_template(self):
        """Carrega o template mestre"""
        template_file = self.ref_path / "MasterTemplate" / "_info.json"
        if template_file.exists():
            with open(template_file, 'r', encoding='utf-8') as f:
                self.master_template = json.load(f)
                print(f"Template mestre carregado - ID: {self.master_template.get('id', 'N/A')}")
    
    def load_page_data(self, page_id):
        """Carrega dados de uma página específica"""
        page_dir = self.ref_path / page_id
        if not page_dir.exists():
            return None
            
        info_file = page_dir / "_info.json"
        if info_file.exists():
            with open(info_file, 'r', encoding='utf-8') as f:
                page_data = json.load(f)
                self.pages_data[page_id] = page_data
                print(f"Página {page_id} carregada")
                return page_data
        return None
    
    def get_paper_size(self, paper_size_id):
        """Converte ID do tamanho de papel para dimensões em pontos"""
        size_mapping = {
            'A4': (595, 842),  # A4 em pontos
            'A3': (842, 1191), # A3 em pontos
            'A5': (420, 595),  # A5 em pontos
            'LB': (400, 574),  # Aproximação baseada no JSON
            '2L': (562, 790),  # Aproximação baseada no JSON
            'HG': (447, 663),  # Aproximação baseada no JSON
            'KG': (454, 682),  # Aproximação baseada no JSON
            'S2': (562, 574),  # Aproximação baseada no JSON
        }
        return size_mapping.get(paper_size_id, size_mapping['A4'])

    def get_json_paper_size(self, edited_paper):
        """Obtém o tamanho do papel conforme definido no JSON (em pixels)"""
        return tuple(edited_paper.get('size', [3048, 4321]))

    def convert_coordinates(self, center, scale, original_size, json_page_size, pdf_page_size):
        """Converte coordenadas do JSON para coordenadas do PDF, ajustando escala"""
        x, y = center
        # Fator de escala entre o tamanho do JSON e o tamanho do PDF
        scale_x = pdf_page_size[0] / json_page_size[0]
        scale_y = pdf_page_size[1] / json_page_size[1]
        # Aplica o fator de escala nas coordenadas
        pdf_x = (json_page_size[0] / 2 + x) * scale_x
        pdf_y = (json_page_size[1] / 2 - y) * scale_y
        return pdf_x, pdf_y, scale_x, scale_y

    def add_image_to_page(self, c, image_path, photo_data, page_size, json_page_size):
        """Adiciona uma imagem à página do PDF, ajustando escala e posição"""
        try:
            # Caminho completo da imagem - precisa incluir a pasta da página
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
            img = Image.open(full_image_path)
            original_width, original_height = photo_data['originalsize']
            center = photo_data['center']
            scale = photo_data['scale']
            # Converte coordenadas e obtém fatores de escala
            x, y, scale_x, scale_y = self.convert_coordinates(center, scale, (original_width, original_height), json_page_size, page_size)
            # Ajusta a escala da imagem para o tamanho do PDF
            img_width = original_width * scale * scale_x
            img_height = original_height * scale * scale_y
            # Adiciona a imagem ao PDF
            c.drawImage(str(full_image_path), x - img_width/2, y - img_height/2, width=img_width, height=img_height)
            print(f"Imagem adicionada: {image_path} em ({x:.1f}, {y:.1f}) tam: {img_width:.1f}x{img_height:.1f}")
        except Exception as e:
            print(f"Erro ao adicionar imagem {image_path}: {e}")

    def create_pdf(self, output_filename="output.pdf"):
        """Cria o PDF final"""
        print(f"\nCriando PDF: {output_filename}")
        self.load_project_info()
        self.load_page_list()
        self.load_master_template()
        for page_id in self.page_list:
            self.load_page_data(page_id)
        c = canvas.Canvas(output_filename)
        for page_id in self.page_list:
            if page_id not in self.pages_data:
                continue
            page_data = self.pages_data[page_id]
            edited_paper = page_data.get('editedPaperSize', {})
            paper_size_id = edited_paper.get('paperSizeId', 'A4')
            page_size = self.get_paper_size(paper_size_id)
            json_page_size = self.get_json_paper_size(edited_paper)
            c.setPageSize(page_size)
            c.setFillColor(white)
            c.rect(0, 0, page_size[0], page_size[1], fill=1)
            print(f"\nProcessando página {page_id} - Tamanho: {paper_size_id} ({page_size[0]}x{page_size[1]})")
            photos = edited_paper.get('photos', [])
            for photo in photos:
                image_path = photo['imagepath']
                self.add_image_to_page(c, image_path, photo, page_size, json_page_size)
            if page_id != self.page_list[-1]:
                c.showPage()
        c.save()
        print(f"\nPDF criado com sucesso: {output_filename}")
        print(f"Total de páginas: {len(self.page_list)}")
    
    def print_summary(self):
        """Imprime um resumo dos dados carregados"""
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

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Gera PDF a partir de um arquivo .etdx (zip disfarçado)")
    parser.add_argument('etdx_path', type=str, help='Caminho para o arquivo .etdx')
    parser.add_argument('--output', type=str, default='documento_gerado.pdf', help='Nome do PDF de saída')
    args = parser.parse_args()

    etdx_path = Path(args.etdx_path)
    # Aceita apenas .etdx (t antes do d)
    if not etdx_path.exists() or etdx_path.suffix.lower() != '.etdx':
        print('Erro: Forneça um arquivo .etdx válido!')
        sys.exit(1)

    # Extrai o .etdx (zip) para uma pasta temporária
    with tempfile.TemporaryDirectory() as tmpdirname:
        with zipfile.ZipFile(etdx_path, 'r') as zip_ref:
            zip_ref.extractall(tmpdirname)
        print(f'Arquivo .etdx extraído para {tmpdirname}')
        # Cria o gerador usando a pasta temporária
        generator = PDFGenerator(tmpdirname)
        generator.create_pdf(args.output)
        generator.print_summary()
        print(f'PDF gerado: {args.output}')

if __name__ == "__main__":
    main()
