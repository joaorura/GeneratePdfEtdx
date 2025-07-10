#!/usr/bin/env python3
"""
Script de teste para verificar se o multiprocessing está funcionando corretamente
"""

import sys
import multiprocessing
from multiprocessing import Pool, cpu_count

def test_worker(x):
    """Função worker simples para teste"""
    return x * 2

def test_multiprocessing():
    """Testa se o multiprocessing está funcionando"""
    print("=== Teste de Multiprocessing ===")
    print(f"Python version: {sys.version}")
    print(f"Platform: {sys.platform}")
    print(f"Frozen: {getattr(sys, 'frozen', False)}")
    print(f"CPU count: {cpu_count()}")
    
    try:
        # Teste básico de multiprocessing
        print("\n1. Testando Pool básico...")
        with Pool(processes=1) as pool:
            result = pool.map(test_worker, [1, 2, 3, 4, 5])
            expected = [2, 4, 6, 8, 10]
            if result == expected:
                print("✅ Pool básico funcionando!")
            else:
                print(f"❌ Pool básico falhou! Esperado: {expected}, Obtido: {result}")
                return False
        
        # Teste com múltiplos processos
        print("\n2. Testando múltiplos processos...")
        with Pool(processes=min(2, cpu_count())) as pool:
            result = pool.map(test_worker, range(10))
            expected = [i * 2 for i in range(10)]
            if result == expected:
                print("✅ Múltiplos processos funcionando!")
            else:
                print(f"❌ Múltiplos processos falharam! Esperado: {expected}, Obtido: {result}")
                return False
        
        print("\n✅ Todos os testes de multiprocessing passaram!")
        return True
        
    except Exception as e:
        print(f"\n❌ Erro no multiprocessing: {e}")
        return False

def test_pdf_generator_import():
    """Testa se o PDFGenerator pode ser importado"""
    print("\n=== Teste de Importação do PDFGenerator ===")
    try:
        from pdf_generator.core import PDFGenerator, MULTIPROCESSING_AVAILABLE
        print("✅ PDFGenerator importado com sucesso!")
        print(f"Multiprocessing disponível: {MULTIPROCESSING_AVAILABLE}")
        return True
    except Exception as e:
        print(f"❌ Erro ao importar PDFGenerator: {e}")
        return False

if __name__ == "__main__":
    print("Iniciando testes...")
    
    # Teste de importação
    import_ok = test_pdf_generator_import()
    
    # Teste de multiprocessing
    multiprocessing_ok = test_multiprocessing()
    
    print("\n=== Resumo ===")
    print(f"Importação: {'✅ OK' if import_ok else '❌ FALHOU'}")
    print(f"Multiprocessing: {'✅ OK' if multiprocessing_ok else '❌ FALHOU'}")
    
    if import_ok and multiprocessing_ok:
        print("\n🎉 Todos os testes passaram!")
        sys.exit(0)
    else:
        print("\n⚠️  Alguns testes falharam!")
        sys.exit(1) 