# Upscaling com IA - Real-ESRGAN

Este módulo implementa upscaling de imagens usando **Real-ESRGAN** com **ONNX Runtime**, oferecendo suporte a CUDA e CPU com compatibilidade total com PyInstaller.

## 🚀 Características

- ✅ **Compatível com PyInstaller** - Modelos ONNX são estáticos
- ✅ **Suporte a CUDA** - Aceleração por GPU NVIDIA
- ✅ **Suporte a CPU** - Fallback automático
- ✅ **Múltiplos modelos** - x2, x4, anime
- ✅ **Download automático** - Modelos baixados automaticamente
- ✅ **Fallback inteligente** - Upscale simples quando IA falha

## 📦 Instalação

### Windows (Recomendado)
```bash
# Execute o instalador automatizado
install_ai_deps.bat
```

### Manual
```bash
# Dependências básicas
pip install -r requirements.txt

# Dependências para IA
pip install -r requirements-ai.txt
```

### Verificação
```bash
python test_ai_upscale.py
```

## 🎯 Uso

### Interface Gráfica
```bash
python etdx_gui.py
# Marque a opção "Upscale com IA"
```

### Linha de Comando
```bash
# Gerar PDF com upscaling
python etdx_cli.py arquivo.etdx --upscale

# Gerar ETDX com upscaling
python etdx_cli.py arquivo.pdf --upscale
```

### Programático
```python
from pdf_generator.ai_upscaler import upscale_image
from PIL import Image

# Carregar imagem
img = Image.open("imagem.jpg")

# Upscaling 4x com IA
result = upscale_image(img, scale_factor=4, device="auto")

# Salvar resultado
result.save("imagem_upscaled.png")
```

## 🧠 Modelos Disponíveis

| Modelo | Escala | Uso Recomendado |
|--------|--------|-----------------|
| `RealESRGAN_x2plus` | 2x | Imagens pequenas, velocidade |
| `RealESRGAN_x4plus` | 4x | Qualidade geral (padrão) |
| `RealESRGAN_x4plus_anime_6B` | 4x | Imagens de anime/manga |

## ⚙️ Configuração

### Dispositivos
- **`auto`** (padrão): Detecta automaticamente o melhor dispositivo
- **`cuda`**: Força uso de GPU NVIDIA
- **`cpu`**: Força uso de CPU
- **`dml`**: DirectML para AMD (Windows)

### Verificar Dispositivos Disponíveis
```python
from pdf_generator.ai_upscaler import get_available_devices

devices = get_available_devices()
print(f"Dispositivos: {devices}")
```

## 🔧 Compilação com PyInstaller

### Configuração Automática
O arquivo `GeradorPDF.spec` já está configurado para incluir:
- Modelos ONNX
- Dependências necessárias
- Módulo ai_upscaler

### Compilar
```bash
pyinstaller GeradorPDF.spec
```

### Incluir Modelos Manualmente
Se precisar incluir modelos específicos:
```python
# No arquivo .spec
datas=[
    ('pdf_generator/models/RealESRGAN_x4plus.onnx', 'pdf_generator/models'),
    ('pdf_generator/models/RealESRGAN_x2plus.onnx', 'pdf_generator/models'),
],
```

## 📊 Performance

### Tempos Médios (imagem 512x512)

| Dispositivo | x2 | x4 |
|-------------|----|----|
| **CUDA** | ~0.5s | ~1.2s |
| **CPU** | ~3s | ~8s |
| **Lanczos** | ~0.1s | ~0.2s |

### Requisitos de Sistema

#### Mínimo
- **RAM**: 4GB
- **GPU**: Qualquer (CPU fallback)
- **Espaço**: 500MB (modelos)

#### Recomendado
- **RAM**: 8GB+
- **GPU**: NVIDIA GTX 1060+ (6GB VRAM)
- **Espaço**: 1GB

## 🐛 Solução de Problemas

### Erro: "ONNX Runtime não disponível"
```bash
pip install onnxruntime-gpu
```

### Erro: "CUDA out of memory"
- Reduza o tamanho das imagens
- Use modelo x2 em vez de x4
- Feche outros programas que usam GPU

### Erro: "Modelo não encontrado"
- Os modelos são baixados automaticamente na primeira execução
- Verifique conexão com internet
- Execute manualmente: `python test_ai_upscale.py`

### Erro: "Fallback para CPU"
- Normal quando GPU não está disponível
- Performance será menor, mas funcional

## 🔄 Cache e Otimização

### Cache de Modelos
- Modelos são carregados uma vez e reutilizados
- Cache automático em memória
- Limpeza automática ao finalizar

### Otimizações
- **Batch processing**: Processa múltiplas imagens
- **Memory management**: Limpeza automática de VRAM
- **Fallback inteligente**: Lanczos quando IA falha

## 📁 Estrutura de Arquivos

```
pdf_generator/
├── ai_upscaler.py          # Módulo principal
├── models/                 # Modelos ONNX
│   ├── RealESRGAN_x2plus.onnx
│   ├── RealESRGAN_x4plus.onnx
│   └── RealESRGAN_x4plus_anime_6B.onnx
└── core.py                 # Integração

requirements-ai.txt         # Dependências IA
test_ai_upscale.py         # Script de teste
install_ai_deps.bat        # Instalador Windows
```

## 🔗 Links Úteis

- [Real-ESRGAN GitHub](https://github.com/xinntao/Real-ESRGAN)
- [ONNX Runtime](https://onnxruntime.ai/)
- [PyInstaller](https://pyinstaller.org/)

## 📄 Licença

Este módulo usa modelos Real-ESRGAN sob licença Apache 2.0. 