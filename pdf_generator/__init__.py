"""
Package para geração de PDFs e ETDXs
"""

from .core import PDFGenerator, extract_etdx, clear_upscale_cache
from .etdx_generator import ETDXGenerator

__all__ = [
    'PDFGenerator',
    'ETDXGenerator', 
    'extract_etdx',
    'clear_upscale_cache',
] 