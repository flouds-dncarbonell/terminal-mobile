# Capturas de apresentação

As imagens mostram a interface real do projeto com dados inteiramente fictícios: texto do terminal, nomes de contas, saldos e arquivos. Não são capturas de sessões pessoais ou resultados de chamadas aos modelos.

Para atualizar, instale as dependências de desenvolvimento e o Chromium:

```bash
venv/bin/pip install -r requirements-dev.txt
venv/bin/playwright install chromium
venv/bin/python docs/capture_screenshots.py
```

O script serve apenas os assets do projeto e fixtures de demonstração em uma porta aleatória de loopback. Não lê credenciais, não inicia agentes, não consulta o 9router e não modifica sessões tmux. A resolução é 430 × 900 CSS pixels, com densidade 2×. Revise as três imagens antes de publicar.
