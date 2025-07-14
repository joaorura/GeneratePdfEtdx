#!/usr/bin/env python3
"""
Gerador de PDF a partir de arquivos .etdx
Ponto de entrada principal para execução via linha de comando
"""

import sys
import argparse
from pathlib import Path
from pdf_generator.core import PDFGenerator, extract_etdx

def main():
    parser = argparse.ArgumentParser(description="Gera PDF a partir de um arquivo .etdx")
    parser.add_argument('etdx_path', type=str, help='Caminho para o arquivo .etdx')
    parser.add_argument('--output', type=str, default='documento_gerado.pdf', help='Nome do PDF de saída')
    parser.add_argument('--dpi', type=int, default=300, help='DPI para as imagens (300 ou 600)')
    parser.add_argument('--format', type=str, default='jpeg', choices=['jpeg', 'png'], help='Formato das imagens')
    parser.add_argument('--quality', type=int, default=90, help='Qualidade JPEG (80-100)')
    parser.add_argument('--upscale', action='store_true', help='Usar upscale inteligente (apenas em execução direta)')
    
    args = parser.parse_args()

    etdx_path = Path(args.etdx_path)
    if not etdx_path.exists() or etdx_path.suffix.lower() != '.etdx':
        print('Erro: Forneça um arquivo .etdx válido!')
        sys.exit(1)

    # Extrai o .etdx para uma pasta temporária
    tmpdirname = extract_etdx(etdx_path)
    
    try:
        # Cria o gerador usando a pasta temporária
        generator = PDFGenerator(tmpdirname)
        
        # Verifica se está compilado e ajusta upscale
        if getattr(sys, 'frozen', False) and args.upscale:
            print("Executável compilado detectado - upscale inteligente desabilitado")
            args.upscale = False
        
        generator.create_pdf(
            output_filename=args.output,
            dpi=args.dpi,
            img_format=args.format,
            jpeg_quality=args.quality,
            upscale=args.upscale
        )
        generator.print_summary()
        print(f'PDF gerado: {args.output}')
        
    except Exception as e:
        print(f'Erro ao gerar PDF: {e}')
        sys.exit(1)
    finally:
        # Limpa a pasta temporária
        import shutil
        shutil.rmtree(tmpdirname)

if __name__ == "__main__":
    main()
