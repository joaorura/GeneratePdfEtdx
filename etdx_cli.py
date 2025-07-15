#!/usr/bin/env python3
"""
Gerador de ETDX a partir de arquivos PDF
Ponto de entrada principal para execução via linha de comando
"""

import sys
import argparse
from pathlib import Path
from pdf_generator.etdx_generator import ETDXGenerator

def main():
    parser = argparse.ArgumentParser(description="Gera arquivo .etdx a partir de um PDF")
    parser.add_argument('pdf_path', type=str, help='Caminho para o arquivo PDF')
    parser.add_argument('--output', type=str, default='documento_gerado.etdx', help='Nome do arquivo .etdx de saída')
    parser.add_argument('--dpi', type=int, default=300, help='DPI para as imagens (300 ou 600)')
    parser.add_argument('--format', type=str, default='jpeg', choices=['jpeg', 'png'], help='Formato das imagens')
    parser.add_argument('--quality', type=int, default=90, help='Qualidade JPEG (80-100)')
    parser.add_argument('--upscale', action='store_true', default=True, help='Ativar upscaling (padrão: habilitado)')
    parser.add_argument('--no-upscale', action='store_true', help='Desabilitar upscaling')

    
    args = parser.parse_args()
    
    # Ajustar upscale baseado nos argumentos
    if args.no_upscale:
        args.upscale = False

    pdf_path = Path(args.pdf_path)
    if not pdf_path.exists() or pdf_path.suffix.lower() != '.pdf':
        print('Erro: Forneça um arquivo PDF válido!')
        sys.exit(1)

    try:
        # Cria o gerador
        generator = ETDXGenerator(pdf_path)
        
        # Upscale sempre disponível (simples)
        
        generator.create_etdx(
            output_filename=args.output,
            dpi=args.dpi,
            img_format=args.format,
            upscale=args.upscale
        )
        generator.print_summary()
        print(f'ETDX gerado: {args.output}')
        
    except Exception as e:
        print(f'Erro ao gerar ETDX: {e}')
        sys.exit(1)

if __name__ == "__main__":
    main() 