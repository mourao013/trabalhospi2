# Aplicação Desktop (Adicional — Item 4 e Item 7.5)

Interface gráfica multi-plataforma desenvolvida em **Python + Tkinter/ttk** que consome os endpoints HTTP/HTTPS da API Flask (`/api/servidores`, `/api/saude`). Não utiliza Docker no cliente.

## Como executar diretamente

```bash
python desktop/app_desktop.py
```

## Como compilar o executável final (.exe / binário standalone)

```bash
pip install pyinstaller
pyinstaller --onefile --windowed --name ConsultaServidoresFederal desktop/app_desktop.py
```

O executável compilado será gerado em `dist/ConsultaServidoresFederal.exe` (Windows) ou `dist/ConsultaServidoresFederal` (Linux/macOS).
