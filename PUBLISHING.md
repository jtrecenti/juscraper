# Guia de Publicação no PyPI

Este documento descreve o processo completo para publicar o pacote `juscraper` no PyPI.

## Pré-requisitos

1. **Conta no PyPI**: Crie uma conta em [pypi.org](https://pypi.org)
2. **Conta no Test PyPI**: Crie uma conta em [test.pypi.org](https://test.pypi.org) para testes
3. **Trusted Publishing**: Configure o Trusted Publishing no PyPI/Test PyPI

## Configuração do Trusted Publishing

### 1. No PyPI

1. Acesse [pypi.org](https://pypi.org) e faça login
2. Vá para "Account settings" → "Publishing"
3. Clique em "Add a new pending publisher"
4. Preencha:
   - **PyPI Project Name**: `juscraper`
   - **Owner**: `jtrecenti` (seu usuário do GitHub)
   - **Repository name**: `juscraper`
   - **Workflow name**: `publish.yml`
   - **Environment name**: `pypi`

### 2. No Test PyPI

Repita o processo acima em [test.pypi.org](https://test.pypi.org) com:
- **Environment name**: `test-pypi`

## Processo de Release

### Método 1: Usando o Script Automatizado

```bash
# Instalar dependências de desenvolvimento
uv sync --all-extras

# Executar o script de release
uv run python scripts/release.py 0.1.0

# Fazer push das alterações
git push origin main
git push origin v0.1.0
```

### Método 2: Manual

1. **Atualizar versão no `pyproject.toml`**:
   ```toml
   version = "0.1.0"
   ```

2. **Atualizar CHANGELOG.md** com as mudanças da nova versão

3. **Commit e tag**:
   ```bash
   git add pyproject.toml CHANGELOG.md
   git commit -m "chore: bump version to 0.1.0"
   git tag -a v0.1.0 -m "Release version 0.1.0"
   git push origin main
   git push origin v0.1.0
   ```

## Criando a Release no GitHub

1. Vá para [GitHub Releases](https://github.com/jtrecenti/juscraper/releases)
2. Clique em "Create a new release"
3. Selecione a tag `v0.1.0`
4. Use o template em `.github/RELEASE_TEMPLATE.md`
5. Publique a release

## Publicação Automática

Após criar a release no GitHub:

1. O workflow `publish.yml` será executado automaticamente
2. Os testes serão executados em múltiplas versões do Python
3. O pacote será construído
4. O pacote será publicado no PyPI usando Trusted Publishing

## Testando Antes da Publicação

### Publicar no Test PyPI

```bash
# Executar workflow manualmente para Test PyPI
# No GitHub: Actions → Publish to PyPI → Run workflow
# Marcar "Publish to Test PyPI instead of PyPI"
```

### Testar instalação do Test PyPI

```bash
pip install --index-url https://test.pypi.org/simple/ juscraper==0.1.0
```

## Verificação Pós-Publicação

1. **Verificar no PyPI**: [https://pypi.org/project/juscraper/](https://pypi.org/project/juscraper/)
2. **Testar instalação**:
   ```bash
   pip install juscraper==0.1.0
   ```
3. **Verificar importação**:
   ```python
   import juscraper
   print(juscraper.__version__)
   ```

## Estrutura de Versionamento

Seguimos o [Semantic Versioning](https://semver.org/):

- **MAJOR** (X.y.z): Mudanças incompatíveis na API
- **MINOR** (x.Y.z): Novas funcionalidades compatíveis
- **PATCH** (x.y.Z): Correções de bugs compatíveis

## Troubleshooting

### Erro de Trusted Publishing

Se o Trusted Publishing falhar:

1. Verifique se o repositório, workflow e environment estão corretos
2. Certifique-se de que a release foi criada (não apenas a tag)
3. Verifique os logs do workflow no GitHub Actions

### Erro de Nome de Pacote

Se o nome `juscraper` já existir:

1. Escolha um novo nome único
2. Atualize `pyproject.toml`
3. Atualize todas as referências nos workflows

### Problemas de Build

```bash
# Testar build localmente
uv build

# Verificar conteúdo do pacote
tar -tzf dist/juscraper-0.1.0.tar.gz
```

## Recursos Adicionais

- [PyPI Trusted Publishing Guide](https://docs.pypi.org/trusted-publishers/)
- [Python Packaging User Guide](https://packaging.python.org/)
- [Semantic Versioning](https://semver.org/)
- [Keep a Changelog](https://keepachangelog.com/)
