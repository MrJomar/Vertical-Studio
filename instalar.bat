@echo off
chcp 65001 >nul
echo === Vertical Studio: instalacion ===
python --version || (echo Instala Python 3.10+ desde python.org y marca "Add to PATH" & pause & exit /b 1)
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
where ffmpeg >nul 2>nul || echo AVISO: no encuentro ffmpeg. Instalalo con:  winget install Gyan.FFmpeg   (o copia ffmpeg.exe y ffprobe.exe a la carpeta bin\)
echo.
echo Listo. Abre la app con:  python app.py   (o doble clic en iniciar.bat)
pause
