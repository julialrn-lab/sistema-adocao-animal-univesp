@echo off
cd /d "%~dp0"
python -m pip install -r requirements.txt
python configurar_acesso.py
pause
