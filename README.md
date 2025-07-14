# GeneratePdfEtdx

Gerador de PDFs e arquivos .etdx com suporte a upscaling simples.

## 🚀 Funcionalidades

- **Geração de PDFs** a partir de arquivos .etdx
- **Geração de arquivos .etdx** a partir de PDFs
- **Upscaling simples** usando redimensionamento LANCZOS
- **Suporte a múltiplas escalas**: x2, x4
- **Processamento otimizado** para melhor performance
- **Interface gráfica** intuitiva

## 📋 Requisitos

```bash
pip install -r requirements.txt
```

**Requisitos de sistema:**
- Python 3.8+
- Mínimo 2GB RAM

## 🛠️ Instalação

### Windows:
```bash
pip install -r requirements.txt
```

### Linux/Mac:
```bash
pip install -r requirements.txt
```

## 🎯 Como usar

### Interface Gráfica (Recomendado)
```bash
python etdx_gui.py
```

### Linha de Comando

#### Gerar PDF a partir de .etdx:
```bash
python etdx_cli.py --etdx arquivo.etdx --output saida.pdf --dpi 300 --upscale
```

#### Gerar .etdx a partir de PDF:
```bash
python etdx_cli.py --pdf arquivo.pdf --output saida.etdx --dpi 300 --upscale
```

### Parâmetros disponíveis:
- `--dpi`: Resolução (padrão: 300)
- `--upscale`: Ativar upscaling simples
- `--format`: Formato de imagem (jpeg/png)
- `--quality`: Qualidade JPEG (1-100)

## 🔧 Configurações Avançadas

### Processamento de Imagens

O sistema inclui processamento otimizado:
- **Fallback para CPU** quando GPU está sem memória
- **Limpeza automática** de cache CUDA
- **Configuração otimizada** de alocação de memória

### Cache Inteligente

- **Cache de modelo**: Evita recarregar modelos de IA
- **Cache de resultado**: Armazena imagens processadas
- **Cache em disco**: Para execução direta em Python
- **Limpeza automática**: Ao finalizar processamento

## 🐛 Solução de Problemas

### Erro de Memória CUDA
Se você encontrar erros de "CUDA out of memory":

1. **O sistema tentará automaticamente usar CPU**
2. **Limpe outros programas** que usam GPU
3. **Reduza o DPI** (use 150 ou 200 em vez de 300)
4. **Desative upscaling** se necessário

### Erro de Cache
Se houver problemas com cache:

1. **O sistema limpa automaticamente** o cache corrompido
2. **Reinicie o programa** se necessário
3. **Verifique permissões** de escrita no diretório

### Teste de Funcionamento
Execute o script de teste para verificar se tudo está funcionando:

```bash
python test_realesrgan.py
```

## 📁 Estrutura do Projeto

```
GeneratePdfEtdx/
├── pdf_generator/
│   ├── core.py              # Geração de PDFs
│   ├── etdx_generator.py    # Geração de .etdx
│   ├── realesrgan_upscaler.py # Upscaling com Real-ESRGAN
│   └── etdx_sizes.py        # Tamanhos de papel
├── etdx_gui.py              # Interface gráfica
├── etdx_cli.py              # Interface linha de comando
├── requirements.txt          # Dependências básicas
├── requirements-ai.txt       # Dependências para IA
└── test_upscale.py          # Script de teste
```

## 🔄 Changelog

### v3.0.0 (Atual)
- ✅ **Migração para Real-ESRGAN 0.3.0**
- ✅ **Melhor qualidade de upscaling**
- ✅ **Suporte a múltiplos modelos (x2, x4, x8)**
- ✅ **Scripts de instalação automatizados**
- ✅ **Melhor gerenciamento de memória CUDA**

### v2.0.0
- ✅ **Melhor gerenciamento de memória CUDA**
- ✅ **Fallback automático para CPU**
- ✅ **Correção de erros de cache**
- ✅ **Configuração otimizada de memória**
- ✅ **Detecção automática de dispositivo**

### v1.0.0
- ✅ Geração de PDFs a partir de .etdx
- ✅ Geração de .etdx a partir de PDFs
- ✅ Upscaling com modelos Swin2SR
- ✅ Cache inteligente

## 📄 Licença

Este projeto está sob a licença MIT. Veja o arquivo `LICENSE` para mais detalhes.

## 🤝 Contribuição

Contribuições são bem-vindas! Por favor, abra uma issue ou pull request.

## 📞 Suporte

Se você encontrar problemas:

1. **Execute o script de teste**: `python test_upscale.py`
2. **Verifique os logs** de erro
3. **Abra uma issue** com detalhes do problema
4. **Inclua informações** sobre seu sistema e configuração 