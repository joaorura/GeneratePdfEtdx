#!/usr/bin/env python3
"""
Script de teste para upscaling com IA
Testa a funcionalidade do módulo ai_upscaler
"""

import sys
import os
from pathlib import Path
from PIL import Image
import time

def test_ai_upscaling():
    """Testa o upscaling com IA"""
    print("=== Teste de Upscaling com IA ===")
    
    # Verificar se o módulo está disponível
    try:
        from pdf_generator.ai_upscaler import (
            AIUpscaler, 
            upscale_image, 
            is_ai_upscaling_available, 
            get_available_devices
        )
        print("✅ Módulo ai_upscaler importado com sucesso")
    except ImportError as e:
        print(f"❌ Erro ao importar módulo: {e}")
        print("Instale as dependências com: pip install -r requirements-ai.txt")
        return False
    
    # Verificar disponibilidade
    if not is_ai_upscaling_available():
        print("❌ ONNX Runtime não está disponível")
        print("Instale com: pip install onnxruntime-gpu")
        return False
    
    print("✅ ONNX Runtime disponível")
    
    # Verificar dispositivos
    devices = get_available_devices()
    print(f"📱 Dispositivos disponíveis: {devices}")
    
    # Criar imagem de teste
    test_img = Image.new('RGB', (100, 100), color='red')
    test_img_path = "test_image.png"
    test_img.save(test_img_path)
    print(f"🖼️ Imagem de teste criada: {test_img_path}")
    
    try:
        # Teste 1: Upscaling básico
        print("\n--- Teste 1: Upscaling básico ---")
        start_time = time.time()
        
        result = upscale_image(test_img, scale_factor=2, device="auto")
        
        end_time = time.time()
        print(f"⏱️ Tempo de processamento: {end_time - start_time:.2f}s")
        print(f"📏 Tamanho original: {test_img.size}")
        print(f"📏 Tamanho resultado: {result.size}")
        
        # Salvar resultado
        result_path = "test_result_2x.png"
        result.save(result_path)
        print(f"💾 Resultado salvo: {result_path}")
        
        # Teste 2: Upscaling 4x
        print("\n--- Teste 2: Upscaling 4x ---")
        start_time = time.time()
        
        result_4x = upscale_image(test_img, scale_factor=4, device="auto")
        
        end_time = time.time()
        print(f"⏱️ Tempo de processamento: {end_time - start_time:.2f}s")
        print(f"📏 Tamanho resultado: {result_4x.size}")
        
        # Salvar resultado
        result_4x_path = "test_result_4x.png"
        result_4x.save(result_4x_path)
        print(f"💾 Resultado salvo: {result_4x_path}")
        
        # Teste 3: Upscaling com tamanho específico
        print("\n--- Teste 3: Upscaling com tamanho específico ---")
        target_size = (300, 300)
        start_time = time.time()
        
        result_target = upscale_image(test_img, scale_factor=4, target_size=target_size, device="auto")
        
        end_time = time.time()
        print(f"⏱️ Tempo de processamento: {end_time - start_time:.2f}s")
        print(f"📏 Tamanho alvo: {target_size}")
        print(f"📏 Tamanho resultado: {result_target.size}")
        
        # Salvar resultado
        result_target_path = "test_result_target.png"
        result_target.save(result_target_path)
        print(f"💾 Resultado salvo: {result_target_path}")
        
        # Teste 4: Diferentes modelos
        print("\n--- Teste 4: Teste de diferentes modelos ---")
        models = ["RealESRGAN_x2", "RealESRGAN_x4", "RealESRGAN_x8"]
        
        for model in models:
            try:
                print(f"🧠 Testando modelo: {model}")
                start_time = time.time()
                
                result_model = upscale_image(test_img, scale_factor=2, model_name=model, device="auto")
                
                end_time = time.time()
                print(f"⏱️ Tempo: {end_time - start_time:.2f}s")
                print(f"📏 Tamanho: {result_model.size}")
                
                # Salvar resultado
                model_path = f"test_result_{model}.png"
                result_model.save(model_path)
                print(f"💾 Salvo: {model_path}")
                
            except Exception as e:
                print(f"❌ Erro com modelo {model}: {e}")
        
        print("\n✅ Todos os testes concluídos com sucesso!")
        return True
        
    except Exception as e:
        print(f"❌ Erro durante os testes: {e}")
        return False
    
    finally:
        # Limpar arquivos de teste
        try:
            test_files = [
                test_img_path,
                "test_result_2x.png",
                "test_result_4x.png", 
                "test_result_target.png",
                "test_result_RealESRGAN_x2.png",
                "test_result_RealESRGAN_x4.png",
                "test_result_RealESRGAN_x8.png"
            ]
            
            for file_path in test_files:
                if os.path.exists(file_path):
                    os.remove(file_path)
                    
            print("🧹 Arquivos de teste limpos")
        except Exception as e:
            print(f"⚠️ Erro ao limpar arquivos: {e}")

def test_integration():
    """Testa a integração com o módulo core"""
    print("\n=== Teste de Integração ===")
    
    try:
        from pdf_generator.core import AI_UPSCALE_AVAILABLE, upscale_image
        print(f"✅ Integração com core: AI_UPSCALE_AVAILABLE = {AI_UPSCALE_AVAILABLE}")
        
        if AI_UPSCALE_AVAILABLE:
            # Teste simples
            test_img = Image.new('RGB', (50, 50), color='blue')
            result = upscale_image(test_img, scale_factor=2)
            print(f"✅ Teste de integração: {test_img.size} -> {result.size}")
            return True
        else:
            print("⚠️ Upscaling com IA não disponível no core")
            return False
            
    except Exception as e:
        print(f"❌ Erro na integração: {e}")
        return False

def main():
    """Função principal"""
    print("🚀 Iniciando testes de upscaling com IA")
    print("=" * 50)
    
    # Teste básico
    success1 = test_ai_upscaling()
    
    # Teste de integração
    success2 = test_integration()
    
    print("\n" + "=" * 50)
    print("📊 RESUMO DOS TESTES:")
    print(f"Upscaling básico: {'✅ PASSOU' if success1 else '❌ FALHOU'}")
    print(f"Integração: {'✅ PASSOU' if success2 else '❌ FALHOU'}")
    
    if success1 and success2:
        print("\n🎉 Todos os testes passaram! O upscaling com IA está funcionando.")
        print("\n📋 PRÓXIMOS PASSOS:")
        print("1. Execute o programa principal para testar")
        print("2. Use a opção --upscale para ativar o upscaling com IA")
        print("3. Verifique os arquivos gerados para qualidade")
    else:
        print("\n⚠️ Alguns testes falharam. Verifique as dependências:")
        print("pip install -r requirements-ai.txt")

if __name__ == "__main__":
    main()
    
    # Limpeza final - remover qualquer arquivo de teste que possa ter ficado
    try:
        import glob
        test_files = glob.glob("test_*.png")
        for file_path in test_files:
            if os.path.exists(file_path):
                os.remove(file_path)
    except:
        pass 