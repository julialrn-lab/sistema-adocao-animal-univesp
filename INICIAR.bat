@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
if not exist .auth.json (echo Configure o usuario e senha primeiro executando CONFIGURAR_ACESSO.bat & pause & exit /b 1)
python app.py
pause
