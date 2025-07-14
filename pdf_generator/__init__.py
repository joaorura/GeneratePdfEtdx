"""
Package para geração de PDFs e ETDXs
"""

from .core import PDFGenerator, extract_etdx, clear_upscale_cache
from .etdx_generator import ETDXGenerator, clear_etdx_upscale_cache

__all__ = [
    'PDFGenerator',
    'ETDXGenerator', 
    'extract_etdx',
    'clear_upscale_cache',
    'clear_etdx_upscale_cache'
] 