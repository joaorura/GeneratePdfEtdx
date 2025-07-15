#!/usr/bin/env python3
"""
Módulo de upscaling com IA usando Real-ESRGAN e ONNX Runtime
Compatível com PyInstaller e suporte a CUDA/CPU
"""

import os
import sys
import io
import hashlib
import pickle
import tempfile
import threading
import multiprocessing
from pathlib import Path
from typing import Optional, Tuple, Union, Any
import numpy as np
from PIL import Image

# Detecção de disponibilidade de dependências
try:
    import onnxruntime as ort
    ONNX_AVAILABLE = True
except ImportError:
    ONNX_AVAILABLE = False

# Lock global para impedir execução paralela do upscaler
# Usar threading.Lock() para threads e multiprocessing.Lock() para processos
_upscaler_lock = None

def _get_upscaler_lock():
    """Retorna o lock apropriado baseado no contexto"""
    global _upscaler_lock
    
    if _upscaler_lock is None:
        # Se estamos em um processo filho do multiprocessing, usar threading.Lock()
        # Se estamos no processo principal, usar threading.Lock() para threads
        if multiprocessing.current_process().name != 'MainProcess':
            _upscaler_lock = threading.Lock()
        else:
            _upscaler_lock = threading.Lock()
    
    return _upscaler_lock

# Cache para modelos ONNX
_model_cache = {}

# Configurações
SUPPORTED_SCALES = [2, 4, 8]
DEFAULT_MODEL = "RealESRGAN_x4"

class AIUpscaler:
    """Upscaler com IA usando Real-ESRGAN e ONNX Runtime"""
    
    def __init__(self, model_name: str = DEFAULT_MODEL, device: str = "auto"):
        """
        Inicializa o upscaler
        
        Args:
            model_name: Nome do modelo ("RealESRGAN_x2", "RealESRGAN_x4", "RealESRGAN_x8")
            device: Dispositivo ("auto", "cuda", "cpu")
        """
        # Verificar se estamos compilados - upscaler não deve ser usado quando compilado
        if getattr(sys, 'frozen', False):
            raise RuntimeError("Upscaling com IA não é suportado quando compilado com PyInstaller")
        
        self.model_name = model_name
        self.device = self._detect_device(device)
        self.session = None
        self.scale_factor = self._get_scale_factor(model_name)
        
        if not ONNX_AVAILABLE:
            raise ImportError("ONNX Runtime não está disponível. Instale com: pip install onnxruntime-gpu")
        
        self._load_model()
    
    def _detect_device(self, device: str) -> str:
        """Detecta o melhor dispositivo disponível"""
        if device == "auto":
            if ONNX_AVAILABLE:
                providers = ort.get_available_providers()
                print(f"🔍 Providers disponíveis: {providers}")
                
                # Verificar se CUDA está realmente disponível
                if "CUDAExecutionProvider" in providers:
                    try:
                        # Testar se CUDA funciona realmente
                        test_session = ort.InferenceSession(
                            self._get_model_path(), 
                            providers=["CUDAExecutionProvider", "CPUExecutionProvider"]
                        )
                        print("✅ CUDA detectado e funcionando")
                        return "cuda"
                    except Exception as e:
                        print(f"⚠️ CUDA detectado mas não funciona: {e}")
                        print("🔄 Fallback para CPU")
                        return "cpu"
                elif "DmlExecutionProvider" in providers:  # DirectML para AMD
                    return "dml"
                else:
                    print("📱 Usando CPU (CUDA não disponível)")
                    return "cpu"
            else:
                return "cpu"
        return device
    
    def _get_scale_factor(self, model_name: str) -> int:
        """Extrai o fator de escala do nome do modelo"""
        if "x2" in model_name:
            return 2
        elif "x4" in model_name:
            return 4
        elif "x8" in model_name:
            return 8
        else:
            return 4  # Padrão
    
    def _get_model_path(self) -> str:
        """Obtém o caminho do modelo ONNX"""
        # Em PyInstaller, os modelos devem estar incluídos no executável
        if getattr(sys, 'frozen', False):
            # Executando como executável compilado
            base_path = getattr(sys, '_MEIPASS', os.path.dirname(sys.executable))
        else:
            # Executando em desenvolvimento - procurar na raiz do projeto
            base_path = os.path.dirname(os.path.dirname(__file__))
        
        model_dir = os.path.join(base_path, "models")
        model_path = os.path.join(model_dir, f"{self.model_name}_fp16.onnx")
        
        return model_path
    
    def _load_model(self):
        """Carrega o modelo ONNX"""
        model_path = self._get_model_path()
        
        # Verificar se o modelo existe
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Modelo não encontrado: {model_path}. Certifique-se de que os modelos foram baixados pelo script .bat")
        
        # Configurar providers baseado no dispositivo
        if self.device == "cuda":
            providers = ["CUDAExecutionProvider", "CPUExecutionProvider"]
        elif self.device == "dml":
            providers = ["DmlExecutionProvider", "CPUExecutionProvider"]
        else:
            providers = ["CPUExecutionProvider"]
        
        try:
            self.session = ort.InferenceSession(model_path, providers=providers)
            print(f"Modelo carregado: {self.model_name} em {self.device}")
        except Exception as e:
            print(f"Erro ao carregar modelo: {e}")
            # Fallback para CPU
            self.device = "cpu"
            providers = ["CPUExecutionProvider"]
            self.session = ort.InferenceSession(model_path, providers=providers)
            print(f"Modelo carregado em CPU (fallback)")
    
    def _preprocess_image(self, img: Image.Image) -> np.ndarray:
        """Pré-processa a imagem para o modelo"""
        # Converter para RGB se necessário
        if img.mode != "RGB":
            img = img.convert("RGB")
        
        # Converter para numpy array
        img_array = np.array(img).astype(np.float16) / 255.0
        
        # Adicionar dimensão de batch
        img_array = np.transpose(img_array, (2, 0, 1))
        img_array = np.expand_dims(img_array, axis=0)
        
        return img_array
    
    def _postprocess_image(self, output: Any) -> Image.Image:
        """Pós-processa a saída do modelo"""
        # Converter para numpy array se necessário
        if not isinstance(output, np.ndarray):
            output = np.array(output)
        
        # Remover dimensão de batch e transpor
        output = np.squeeze(output, axis=0)
        output = np.transpose(output, (1, 2, 0))
        
        # Clamp para [0, 1] e converter para uint8
        output = np.clip(output, 0, 1)
        output = (output * 255).astype(np.uint8)
        
        return Image.fromarray(output)
    
    def upscale(self, img: Image.Image, target_size: Optional[Tuple[int, int]] = None) -> Image.Image:
        """
        Aplica upscaling com IA
        
        Args:
            img: Imagem PIL para upscalar
            target_size: Tamanho final desejado (opcional)
        
        Returns:
            Imagem upscalada
        """
        # Usar lock para impedir execução paralela
        lock = _get_upscaler_lock()
        with lock:
            if self.session is None:
                raise RuntimeError("Modelo não carregado")
            
            # Verificar se a imagem é muito pequena
            if img.width < 32 or img.height < 32:
                print("Imagem muito pequena, usando upscale simples")
                return self._simple_upscale(img, target_size)
            
            try:
                # Pré-processar
                input_array = self._preprocess_image(img)
                
                # Executar inferência
                input_name = self.session.get_inputs()[0].name
                output_name = self.session.get_outputs()[0].name
                
                output_array = self.session.run([output_name], {input_name: input_array})[0]
                
                # Pós-processar
                result = self._postprocess_image(output_array)
                
                # Redimensionar para o tamanho final se especificado
                if target_size:
                    result = result.resize(target_size, Image.Resampling.LANCZOS)
                
                return result
                
            except Exception as e:
                print(f"Erro no upscaling com IA: {e}")
                print("Usando upscale simples como fallback")
                return self._simple_upscale(img, target_size)
    
    def _simple_upscale(self, img: Image.Image, target_size: Optional[Tuple[int, int]] = None) -> Image.Image:
        """Upscale simples usando Lanczos como fallback"""
        if target_size:
            return img.resize(target_size, Image.Resampling.LANCZOS)
        
        # Calcular novo tamanho baseado no fator de escala
        new_width = img.width * self.scale_factor
        new_height = img.height * self.scale_factor
        
        return img.resize((new_width, new_height), Image.Resampling.LANCZOS)

# Função de conveniência para upscaling
def upscale_image(img: Image.Image, 
                  scale_factor: int = 4, 
                  device: str = "auto",
                  target_size: Optional[Tuple[int, int]] = None) -> Image.Image:
    """
    Função de conveniência para upscaling de imagem
    
    Args:
        img: Imagem PIL
        scale_factor: Fator de escala (2, 4 ou 8)
        device: Dispositivo ("auto", "cuda", "cpu")
        target_size: Tamanho final desejado
    
    Returns:
        Imagem upscalada
    """
    # Verificar se estamos compilados - upscaler não deve ser usado quando compilado
    if getattr(sys, 'frozen', False):
        print("⚠️ Upscaling com IA desabilitado quando compilado, usando upscale simples")
        if target_size:
            return img.resize(target_size, Image.Resampling.LANCZOS)
        else:
            new_width = img.width * scale_factor
            new_height = img.height * scale_factor
            return img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    if scale_factor not in SUPPORTED_SCALES:
        raise ValueError(f"Fator de escala deve ser {SUPPORTED_SCALES}")
    
    # Definir modelo baseado no scale_factor
    if scale_factor == 2:
        model_name = "RealESRGAN_x2"
    elif scale_factor == 4:
        model_name = "RealESRGAN_x4"
    elif scale_factor == 8:
        model_name = "RealESRGAN_x8"
    else:
        model_name = DEFAULT_MODEL
    
    # Verificar se ONNX está disponível
    if not ONNX_AVAILABLE:
        print("ONNX Runtime não disponível, usando upscale simples")
        if target_size:
            return img.resize(target_size, Image.Resampling.LANCZOS)
        else:
            new_width = img.width * scale_factor
            new_height = img.height * scale_factor
            return img.resize((new_width, new_height), Image.Resampling.LANCZOS)
    
    try:
        # Criar upscaler
        upscaler = AIUpscaler(model_name=model_name, device=device)
        
        # Aplicar upscaling
        return upscaler.upscale(img, target_size)
        
    except Exception as e:
        print(f"Erro no upscaling com IA: {e}")
        print("Usando upscale simples como fallback")
        
        if target_size:
            return img.resize(target_size, Image.Resampling.LANCZOS)
        else:
            new_width = img.width * scale_factor
            new_height = img.height * scale_factor
            return img.resize((new_width, new_height), Image.Resampling.LANCZOS)

# Função para verificar disponibilidade
def is_ai_upscaling_available() -> bool:
    """Verifica se o upscaling com IA está disponível"""
    # Não disponível quando compilado
    if getattr(sys, 'frozen', False):
        return False
    return ONNX_AVAILABLE

# Função para obter dispositivos disponíveis
def get_available_devices() -> list:
    """Retorna lista de dispositivos disponíveis"""
    # Não disponível quando compilado
    if getattr(sys, 'frozen', False):
        return ["cpu"]
    
    if not ONNX_AVAILABLE:
        return ["cpu"]
    
    providers = ort.get_available_providers()
    devices = ["cpu"]
    
    if "CUDAExecutionProvider" in providers:
        devices.append("cuda")
    if "DmlExecutionProvider" in providers:
        devices.append("dml")
    
    return devices 