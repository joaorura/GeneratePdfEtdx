# Gerador de PDF e ETDX

Aplicação para gerar PDFs a partir de arquivos .etdx e converter PDFs em arquivos .etdx editáveis, com suporte a upscale inteligente de imagens.

## Funcionalidades

### 📄 Gerador de PDF (.etdx → PDF)
- ✅ Geração de PDF a partir de arquivos .etdx
- ✅ Suporte a múltiplos tamanhos de papel (A4, A3, A5, etc.)
- ✅ Upscale inteligente de imagens usando RealESRGAN (apenas execução direta)
- ✅ Interface gráfica amigável
- ✅ Processamento paralelo de imagens (quando disponível)
- ✅ Configurações de qualidade (DPI, formato de imagem, qualidade JPEG)
- ✅ Build otimizado sem dependências de IA (executáveis mais leves)

### 🔄 Gerador de ETDX (.pdf → .etdx)
- ✅ Conversão de PDFs em arquivos .etdx editáveis
- ✅ Detecção automática de tamanho de papel
- ✅ Upscale inteligente para melhorar qualidade
- ✅ Interface gráfica dedicada
- ✅ Processamento paralelo otimizado
- ✅ Cache inteligente para melhor performance

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

### 📄 Gerador de PDF (.etdx → PDF)

#### Interface Gráfica
```bash
python gui.py
```

#### Linha de Comando
```bash
# Gerar PDF a partir de arquivo .etdx
python cli.py arquivo.etdx --output saida.pdf

# Com configurações personalizadas
python cli.py arquivo.etdx --output saida.pdf --dpi 600 --format png --quality 95

# Usar upscale inteligente (apenas execução direta)
python cli.py arquivo.etdx --upscale
```

### 🔄 Gerador de ETDX (.pdf → .etdx)

#### Interface Gráfica
```bash
python etdx_gui.py
```

#### Linha de Comando
```bash
# Converter PDF para .etdx
python etdx_cli.py documento.pdf --output documento.etdx

# Com configurações personalizadas
python etdx_cli.py documento.pdf --output documento.etdx --dpi 600 --format png --upscale

# Ajuda
python etdx_cli.py --help
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
GeneratePdfEtdx/
├── pdf_generator/
│   ├── __init__.py
│   ├── core.py              # Lógica principal de geração de PDF
│   └── etdx_generator.py    # Lógica de geração de ETDX
├── icons/                   # Ícones da aplicação
├── gui.py                   # Interface gráfica (PDF)
├── cli.py                   # Interface CLI (PDF)
├── etdx_gui.py             # Interface gráfica (ETDX)
├── etdx_cli.py             # Interface CLI (ETDX)
├── executar_gui.bat        # Script para executar GUI PDF
├── executar_etdx_gui.bat   # Script para executar GUI ETDX
├── build.bat               # Script de compilação para Windows
├── runtime_hook.py         # Hook para PyInstaller
├── requirements.txt        # Dependências básicas
├── requirements-ai.txt     # Dependências de IA (opcional)
├── README.md              # Documentação principal
└── README_ETDX.md         # Documentação específica do ETDX
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

## Documentação Adicional

Para informações detalhadas sobre o gerador de ETDX, consulte:
- [README_ETDX.md](README_ETDX.md) - Documentação específica do módulo ETDX

## Licença

Este projeto está sob a licença MIT. 