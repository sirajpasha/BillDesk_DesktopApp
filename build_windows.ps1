$ErrorActionPreference = 'Stop'
python -m pip install -r requirements.txt
pyinstaller --noconfirm --clean --windowed --name BillDeskNative main.py
Write-Host "Build complete: dist/BillDeskNative/BillDeskNative.exe"
