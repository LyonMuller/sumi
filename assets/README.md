# Recursos visuais

- `brand/app-icon.png` e `app-icon.ico`: identidade do aplicativo; o ICO é usado
  nas janelas e nos executáveis Windows.
- `brand/readme-cover.png`: capa da apresentação no GitHub.
- `gestures/`: ilustrações da ajuda, listadas em `gestures/README.md`.

As imagens de ajuda e a identidade foram fornecidas pelo mantenedor. Elas não
aparecem na câmera virtual. Os efeitos de vídeo são desenhados em código.

A interface mantém a proporção de cada ilustração, inclusive as sequências
horizontais. O ICO inclui 16, 24, 32, 48, 64, 128 e 256 px. Para reexportá-lo:

```powershell
.venv\Scripts\python.exe tools/export_icon.py
```

O exportador enquadra a região visível do símbolo para evitar ícones pequenos
por excesso de margem transparente. Não coloque capturas reais de webcam aqui.
