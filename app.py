from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory, abort, session
from pathlib import Path
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash
from uuid import uuid4
from functools import wraps
import sqlite3
import os
import json
import secrets

BASE = Path(__file__).resolve().parent
app = Flask(__name__)

# On Render, configure SECRET_KEY in Environment Variables.
# Locally, keep a generated key in an ignored file.
secret_key = os.environ.get('SECRET_KEY')
key_file = BASE / '.secret_key'
if not secret_key:
    if key_file.exists():
        secret_key = key_file.read_text(encoding='utf-8').strip()
    if not secret_key:
        secret_key = secrets.token_hex(32)
        key_file.write_text(secret_key, encoding='utf-8')

app.config.update(
    SECRET_KEY=secret_key,
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE='Lax',
    SESSION_COOKIE_SECURE=bool(os.environ.get('RENDER')),
    MAX_CONTENT_LENGTH=3 * 1024 * 1024,
)

DB = BASE / 'caes.db'
UPLOADS = BASE / 'fotos'
UPLOADS.mkdir(exist_ok=True)
STATUSES = ('Em tratamento', 'Disponível para adoção', 'Adotado')


def db():
    connection = sqlite3.connect(DB)
    connection.row_factory = sqlite3.Row
    return connection


def init_db():
    with db() as connection:
        connection.execute('CREATE TABLE IF NOT EXISTS animais(id INTEGER PRIMARY KEY AUTOINCREMENT,nome TEXT NOT NULL,sexo TEXT,idade TEXT,resgate TEXT,status TEXT NOT NULL,observacoes TEXT)')
        connection.execute('CREATE TABLE IF NOT EXISTS tratamentos(id INTEGER PRIMARY KEY AUTOINCREMENT,animal_id INTEGER NOT NULL,data TEXT NOT NULL,procedimento TEXT NOT NULL,observacoes TEXT,FOREIGN KEY(animal_id) REFERENCES animais(id))')
        if 'foto' not in [column[1] for column in connection.execute('PRAGMA table_info(animais)')]:
            connection.execute('ALTER TABLE animais ADD COLUMN foto TEXT')


def get_animals(public=False):
    with db() as connection:
        sql = 'SELECT * FROM animais' + (' WHERE status=?' if public else '') + ' ORDER BY id DESC'
        params = ('Disponível para adoção',) if public else ()
        return [dict(row) for row in connection.execute(sql, params)]


def save_photo(file):
    if not file or not file.filename:
        return None
    ext = Path(secure_filename(file.filename)).suffix.lower()
    if ext not in ('.jpg', '.jpeg', '.png', '.webp'):
        abort(400, 'Formato de foto inválido')
    content = file.read()
    valid = (
        (ext in ('.jpg', '.jpeg') and content.startswith(b'\xff\xd8\xff'))
        or (ext == '.png' and content.startswith(b'\x89PNG\r\n\x1a\n'))
        or (ext == '.webp' and content.startswith(b'RIFF') and content[8:12] == b'WEBP')
    )
    if not valid or len(content) > 3_000_000:
        abort(400, 'Foto inválida ou muito grande')
    filename = uuid4().hex + ext
    (UPLOADS / filename).write_bytes(content)
    return filename


def admin_required(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('login'))
        return function(*args, **kwargs)
    return wrapper


@app.context_processor
def inject_csrf_token():
    # Disponibiliza o token para todos os templates, inclusive base.html.
    return {'csrf_token': session.get('csrf_token', '')}


@app.before_request
def protect_posts():
    if request.method == 'POST' and request.endpoint != 'login':
        if not session.get('admin'):
            abort(403)
        submitted_token = request.form.get('csrf_token', '')
        expected_token = session.get('csrf_token', '')
        if not submitted_token or not expected_token or not secrets.compare_digest(submitted_token, expected_token):
            abort(400, 'Token de formulário inválido')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('usuario', '')
        password = request.form.get('senha', '')
        expected_username = os.environ.get('ADMIN_USER')
        expected_hash = os.environ.get('ADMIN_PASSWORD_HASH')

        # The local configuration file remains supported for Windows testing.
        if not expected_username or not expected_hash:
            authfile = BASE / '.auth.json'
            if not authfile.exists():
                abort(503, 'Acesso administrativo não configurado')
            stored = json.loads(authfile.read_text(encoding='utf-8'))
            expected_username = stored['usuario']
            expected_hash = stored['senha_hash']

        if (secrets.compare_digest(username, expected_username)
                and check_password_hash(expected_hash, password)):
            session.clear()
            session['admin'] = True
            session['csrf_token'] = secrets.token_hex(32)
            return redirect(url_for('painel'))
        return render_template('login.html', erro='Usuário ou senha incorretos'), 401
    return render_template('login.html')


@app.post('/sair')
@admin_required
def sair():
    session.clear()
    return redirect(url_for('adocao'))


@app.route('/')
@admin_required
def painel():
    animals = get_animals()
    counts = {'Total': len(animals), **{status: sum(a['status'] == status for a in animals) for status in STATUSES}}
    return render_template('painel.html', animals=animals, counts=counts)


@app.route('/adocao')
def adocao():
    return render_template('adocao.html', animals=get_animals(public=True))


@app.route('/novo', methods=['GET', 'POST'])
@admin_required
def novo():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        status = request.form.get('status', '')
        if not nome or status not in STATUSES:
            abort(400)
        photo = save_photo(request.files.get('foto'))
        with db() as connection:
            connection.execute('INSERT INTO animais(nome,sexo,idade,resgate,status,observacoes,foto) VALUES(?,?,?,?,?,?,?)', (nome, request.form.get('sexo', ''), request.form.get('idade', ''), request.form.get('resgate', ''), status, request.form.get('observacoes', ''), photo))
        return redirect(url_for('painel'))
    return render_template('novo.html', statuses=STATUSES)


@app.route('/animal/<int:animal_id>')
@admin_required
def animal(animal_id):
    with db() as connection:
        row = connection.execute('SELECT * FROM animais WHERE id=?', (animal_id,)).fetchone()
        if not row:
            abort(404)
        treatments = [dict(item) for item in connection.execute('SELECT * FROM tratamentos WHERE animal_id=? ORDER BY data DESC', (animal_id,))]
    return render_template('animal.html', animal=dict(row), trs=treatments, statuses=STATUSES)


@app.post('/animal/<int:animal_id>/status')
@admin_required
def status(animal_id):
    value = request.form.get('status')
    if value not in STATUSES:
        abort(400)
    with db() as connection:
        connection.execute('UPDATE animais SET status=? WHERE id=?', (value, animal_id))
    return redirect(url_for('animal', animal_id=animal_id))


@app.post('/animal/<int:animal_id>/foto')
@admin_required
def foto(animal_id):
    filename = save_photo(request.files.get('foto'))
    if not filename:
        abort(400)
    with db() as connection:
        connection.execute('UPDATE animais SET foto=? WHERE id=?', (filename, animal_id))
    return redirect(url_for('animal', animal_id=animal_id))


@app.route('/tratamento', methods=['GET', 'POST'])
@admin_required
def tratamento():
    if request.method == 'POST':
        try:
            animal_id = int(request.form.get('animal_id', ''))
        except (ValueError, TypeError):
            abort(400)
        if not request.form.get('data') or not request.form.get('procedimento'):
            abort(400)
        with db() as connection:
            connection.execute('INSERT INTO tratamentos(animal_id,data,procedimento,observacoes) VALUES(?,?,?,?)', (animal_id, request.form['data'], request.form['procedimento'], request.form.get('observacoes', '')))
        return redirect(url_for('animal', animal_id=animal_id))
    return render_template('tratamento.html', animals=get_animals())


@app.get('/fotos/<path:filename>')
def fotos(filename):
    with db() as connection:
        allowed = connection.execute('SELECT 1 FROM animais WHERE foto=? AND status=?', (filename, 'Disponível para adoção')).fetchone()
        if not allowed and not session.get('admin'):
            abort(404)
    return send_from_directory(UPLOADS, filename)


@app.get('/api/animais')
def api_animais():
    return jsonify([
        {
            'id': animal['id'],
            'nome': animal['nome'],
            'sexo': animal['sexo'],
            'idade': animal['idade'],
            'foto_url': url_for('fotos', filename=animal['foto']) if animal['foto'] else None,
        }
        for animal in get_animals(public=True)
    ])


@app.get('/healthz')
def healthz():
    return jsonify({'status': 'ok'})


init_db()

if __name__ == '__main__':
    app.run(host='127.0.0.1', port=8000, debug=False)
