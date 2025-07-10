# Gerador de PDF (.etdx)

Aplicação para gerar PDFs a partir de arquivos .etdx (arquivos ZIP disfarçados) com suporte a upscale inteligente de imagens.

## Funcionalidades

- ✅ Geração de PDF a partir de arquivos .etdx
- ✅ Suporte a múltiplos tamanhos de papel (A4, A3, A5, etc.)
- ✅ Upscale inteligente de imagens usando RealESRGAN (apenas execução direta)
- ✅ Interface gráfica amigável
- ✅ Processamento paralelo de imagens (quando disponível)
- ✅ Configurações de qualidade (DPI, formato de imagem, qualidade JPEG)
- ✅ Build otimizado sem dependências de IA (executáveis mais leves)

## Modos de Execução

### 🐍 Execução Direta (Python)
- **Funcionalidades completas**: Inclui upscale inteligente com RealESRGAN
- **Tamanho**: Maior devido às dependências de IA
- **Performance**: Melhor para imagens pequenas com upscale

### 📦 Executável Compilado
- **Funcionalidades básicas**: Apenas redimensionamento simples
- **Tamanho**: Muito menor (sem dependências de IA)
- **Performance**: Rápido para imagens normais

## Instalação

### Dependências Básicas (obrigatórias)
```bash
pip install -r requirements.txt
```

### Dependências de IA (opcional - apenas para execução direta)
```bash
pip install -r requirements-ai.txt
```

## Uso

### Interface Gráfica
```bash
python gui.py
```

### Linha de Comando
```bash
# Gerar PDF a partir de arquivo .etdx
python main.py arquivo.etdx --output saida.pdf

# Com configurações personalizadas
python main.py arquivo.etdx --output saida.pdf --dpi 600 --format png --quality 95

# Usar upscale inteligente (apenas execução direta)
python main.py arquivo.etdx --upscale
```

## Compilação

Para criar um executável otimizado (sem IA):

```bash
# Windows
build.bat

# Linux/Mac
pyinstaller --clean --onefile --windowed --icon=icons/pdf_gear.ico --name=GeradorPDF gui.py
```

**Nota**: O executável compilado não inclui funcionalidades de IA para reduzir o tamanho. Para usar IA, execute diretamente com Python.

## Diferenças entre Modos

| Funcionalidade | Execução Direta | Executável Compilado |
|----------------|-----------------|---------------------|
| Upscale Inteligente | ✅ RealESRGAN | ❌ Redimensionamento simples |
| Cache de Imagens | ✅ Completo | ❌ Desabilitado |
| Multiprocessing | ✅ Ativo | ⚠️ Limitado |
| Tamanho do Build | Grande (~500MB+) | Pequeno (~50MB) |
| Dependências | Todas | Apenas básicas |

## Solução de Problemas

### Upscale Inteligente Não Disponível

**Executável Compilado:**
- O upscale inteligente é intencionalmente desabilitado em executáveis compilados
- Use redimensionamento simples ou execute diretamente com Python

**Execução Direta:**
- Verifique se instalou as dependências de IA: `pip install -r requirements-ai.txt`
- Verifique se o arquivo `weights/RealESRGAN_x4.pth` existe
- O aplicativo automaticamente usa upscale simples como fallback

### Erro de Multiprocessing

Se você encontrar erros relacionados ao multiprocessing:

**Executável Compilado:**
- O multiprocessing é automaticamente desabilitado para evitar problemas
- O processamento será sequencial (mais lento, mas estável)

**Execução Direta:**
- O multiprocessing é habilitado por padrão
- Se houver problemas, o aplicativo automaticamente faz fallback para processamento sequencial

## Estrutura do Projeto

```
teste/
├── pdf_generator/
│   ├── __init__.py
│   └── core.py          # Lógica principal de geração de PDF
├── icons/               # Ícones da aplicação
├── weights/             # Pesos do modelo RealESRGAN
├── gui.py              # Interface gráfica
├── main.py             # Interface de linha de comando
├── build.bat           # Script de compilação para Windows
├── runtime_hook.py     # Hook para PyInstaller
├── requirements.txt    # Dependências básicas
├── requirements-ai.txt # Dependências de IA (opcional)
└── GeradorPDF.spec    # Especificação do PyInstaller
```

## Configurações

### DPI (Dots Per Inch)
- **300 DPI**: Padrão, boa qualidade
- **600 DPI**: Alta qualidade, arquivos maiores

### Formato de Imagem
- **JPEG**: Menor tamanho, boa qualidade
- **PNG**: Maior tamanho, qualidade máxima

### Qualidade JPEG
- **80-100**: Quanto maior, melhor a qualidade e maior o arquivo

### Upscale Inteligente
- **Execução Direta**: Usa RealESRGAN para melhorar imagens pequenas
- **Executável Compilado**: Usa redimensionamento simples

## Dependências

### Básicas (obrigatórias)
- `reportlab`: Geração de PDF
- `Pillow`: Processamento de imagens
- `pyinstaller`: Compilação (apenas para build)

### IA (opcional)
- `torch`: Framework de machine learning
- `py-real-esrgan`: Upscale inteligente
- `numpy`: Computação numérica
- `huggingface_hub`: Modelos pré-treinados

## Licença

Este projeto está sob a licença MIT. 