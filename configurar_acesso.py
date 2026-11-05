from pathlib import Path
from getpass import getpass
from werkzeug.security import generate_password_hash
import json, secrets
base=Path(__file__).resolve().parent
print('CONFIGURACAO DE ACESSO VETERINARIO')
usuario=input('Usuario do veterinario: ').strip()
while not usuario: usuario=input('Informe um usuario: ').strip()
senha=getpass('Crie uma senha forte (minimo 12 caracteres): ')
if len(senha)<12: raise SystemExit('Senha curta. Execute novamente e use ao menos 12 caracteres.')
confirmacao=getpass('Repita a senha: ')
if senha!=confirmacao: raise SystemExit('Senhas diferentes. Execute novamente.')
(base/'.auth.json').write_text(json.dumps({'usuario':usuario,'senha_hash':generate_password_hash(senha)}),encoding='utf-8')
if not (base/'.secret_key').exists(): (base/'.secret_key').write_text(secrets.token_hex(32),encoding='utf-8')
print('Acesso configurado. Execute INICIAR.bat.')
