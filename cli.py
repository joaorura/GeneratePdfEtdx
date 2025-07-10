import sys
import argparse
from pathlib import Path
from pdf_generator.core import PDFGenerator, extract_etdx
import shutil

def main():
    parser = argparse.ArgumentParser(description="Gera PDF a partir de um arquivo .etdx ou pasta com dados")
    parser.add_argument('input_path', type=str, help='Caminho para o arquivo .etdx ou pasta com dados')
    parser.add_argument('--output', type=str, default='documento_gerado.pdf', help='Nome do PDF de saída')
    parser.add_argument('--dpi', type=int, choices=[300, 600], default=300, help='DPI do PDF gerado (300 ou 600, padrão 300)')
    parser.add_argument('--img-format', type=str, choices=['jpeg', 'png'], default='jpeg', help='Formato das imagens no PDF (jpeg ou png, padrão jpeg)')
    parser.add_argument('--jpeg-quality', type=int, default=90, help='Qualidade do JPEG (80-100, padrão 90, só para jpeg)')
    parser.add_argument('--no-upscale', action='store_true', help='Desativa o upscale inteligente (RealESRGAN) para imagens pequenas')
    args = parser.parse_args()

    input_path = Path(args.input_path)
    tmpdirname = None
    
    try:
        if input_path.suffix.lower() == '.etdx':
            # É um arquivo .etdx
            if not input_path.exists():
                print(f'Erro: Arquivo {input_path} não encontrado!')
                sys.exit(1)
            tmpdirname = extract_etdx(input_path)
            ref_path = tmpdirname
        else:
            # É uma pasta
            if not input_path.exists() or not input_path.is_dir():
                print(f'Erro: Pasta {input_path} não encontrada!')
                sys.exit(1)
            ref_path = input_path

        generator = PDFGenerator(ref_path)
        generator.create_pdf(
            args.output,
            dpi=args.dpi,
            img_format=args.img_format,
            jpeg_quality=args.jpeg_quality,
            upscale=not args.no_upscale
        )
        generator.print_summary()
        print(f'PDF gerado: {args.output}')
    finally:
        if tmpdirname:
            shutil.rmtree(tmpdirname)

if __name__ == "__main__":
    main() 