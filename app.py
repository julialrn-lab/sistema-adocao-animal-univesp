from flask import Flask, render_template, request, redirect, url_for, jsonify, send_from_directory, abort
from pathlib import Path
from werkzeug.utils import secure_filename
from uuid import uuid4
import sqlite3
import os, json, secrets
from functools import wraps
from flask import session
from werkzeug.security import check_password_hash

BASE = Path(__file__).resolve().parent
app = Flask(__name__)
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY') or (BASE / '.secret_key').read_text().strip() if (BASE / '.secret_key').exists() else None
if not app.config['SECRET_KEY']:
    app.config['SECRET_KEY'] = secrets.token_hex(32)
    (BASE / '.secret_key').write_text(app.config['SECRET_KEY'], encoding='utf-8')
app.config.update(SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE='Lax')
app.config['MAX_CONTENT_LENGTH'] = 3 * 1024 * 1024
DB = BASE / 'caes.db'
UPLOADS = BASE / 'fotos'
UPLOADS.mkdir(exist_ok=True)
STATUSES = ('Em tratamento', 'Disponível para adoção', 'Adotado')

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c

def init_db():
    with db() as c:
        c.execute('CREATE TABLE IF NOT EXISTS animais(id INTEGER PRIMARY KEY AUTOINCREMENT,nome TEXT NOT NULL,sexo TEXT,idade TEXT,resgate TEXT,status TEXT NOT NULL,observacoes TEXT)')
        c.execute('CREATE TABLE IF NOT EXISTS tratamentos(id INTEGER PRIMARY KEY AUTOINCREMENT,animal_id INTEGER NOT NULL,data TEXT NOT NULL,procedimento TEXT NOT NULL,observacoes TEXT,FOREIGN KEY(animal_id) REFERENCES animais(id))')
        if 'foto' not in [x[1] for x in c.execute('PRAGMA table_info(animais)')]:
            c.execute('ALTER TABLE animais ADD COLUMN foto TEXT')

def get_animals(public=False):
    with db() as c:
        return [dict(r) for r in c.execute('SELECT * FROM animais' + (' WHERE status=?' if public else '') + ' ORDER BY id DESC', ('Disponível para adoção',) if public else ())]

def save_photo(file):
    if not file or not file.filename: return None
    ext = Path(secure_filename(file.filename)).suffix.lower()
    if ext not in ('.jpg','.jpeg','.png','.webp'): abort(400, 'Formato de foto inválido')
    content = file.read()
    valid = (ext in ('.jpg','.jpeg') and content.startswith(b'\xff\xd8\xff')) or (ext=='.png' and content.startswith(b'\x89PNG\r\n\x1a\n')) or (ext=='.webp' and content.startswith(b'RIFF') and content[8:12]==b'WEBP')
    if not valid or len(content)>3_000_000: abort(400, 'Foto inválida ou muito grande')
    name = uuid4().hex + ext
    (UPLOADS / name).write_bytes(content)
    return name

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get('admin'):
            return redirect(url_for('login'))
        return fn(*args, **kwargs)
    return wrapper

@app.before_request
def protect_posts():
    if request.method == 'POST' and request.endpoint not in ('login',):
        if not session.get('admin'):
            abort(403)
        if not secrets.compare_digest(request.form.get('csrf_token', ''), session.get('csrf_token', '')):
            abort(400, 'Token de formulário inválido')

@app.context_processor
def inject_csrf():
    return {'csrf_token': session.get('csrf_token', '')}

@app.route('/login', methods=['GET','POST'])
def login():
    if request.method == 'POST':
        authfile = BASE / '.auth.json'
        if not authfile.exists():
            abort(503, 'Configure a senha executando CONFIGURAR_ACESSO.bat')
        stored = json.loads(authfile.read_text(encoding='utf-8'))
        if request.form.get('usuario') == stored['usuario'] and check_password_hash(stored['senha_hash'], request.form.get('senha','')):
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
    animals=get_animals()
    counts={'Total':len(animals), **{s:sum(a['status']==s for a in animals) for s in STATUSES}}
    return render_template('painel.html', animals=animals, counts=counts)

@app.route('/adocao')
def adocao():
    return render_template('adocao.html', animals=get_animals(public=True))

@app.route('/novo',methods=['GET','POST'])
@admin_required
def novo():
    if request.method=='POST':
        nome=request.form.get('nome','').strip()
        status=request.form.get('status','')
        if not nome or status not in STATUSES: abort(400)
        foto=save_photo(request.files.get('foto'))
        with db() as c:
            c.execute('INSERT INTO animais(nome,sexo,idade,resgate,status,observacoes,foto) VALUES(?,?,?,?,?,?,?)',(nome,request.form.get('sexo',''),request.form.get('idade',''),request.form.get('resgate',''),status,request.form.get('observacoes',''),foto))
        return redirect(url_for('painel'))
    return render_template('novo.html',statuses=STATUSES)

@app.route('/animal/<int:animal_id>')
@admin_required
def animal(animal_id):
    with db() as c:
        a=c.execute('SELECT * FROM animais WHERE id=?',(animal_id,)).fetchone()
        if not a: abort(404)
        trs=[dict(t) for t in c.execute('SELECT * FROM tratamentos WHERE animal_id=? ORDER BY data DESC',(animal_id,))]
    return render_template('animal.html',animal=dict(a),trs=trs,statuses=STATUSES)

@app.post('/animal/<int:animal_id>/status')
@admin_required
def status(animal_id):
    value=request.form.get('status')
    if value not in STATUSES: abort(400)
    with db() as c:
        c.execute('UPDATE animais SET status=? WHERE id=?',(value,animal_id))
    return redirect(url_for('animal',animal_id=animal_id))

@app.post('/animal/<int:animal_id>/foto')
@admin_required
def foto(animal_id):
    filename=save_photo(request.files.get('foto'))
    if not filename: abort(400)
    with db() as c:
        c.execute('UPDATE animais SET foto=? WHERE id=?',(filename,animal_id))
    return redirect(url_for('animal',animal_id=animal_id))

@app.route('/tratamento',methods=['GET','POST'])
@admin_required
def tratamento():
    if request.method=='POST':
        try: animal_id=int(request.form.get('animal_id',''))
        except ValueError: abort(400)
        if not request.form.get('data') or not request.form.get('procedimento'): abort(400)
        with db() as c:
            c.execute('INSERT INTO tratamentos(animal_id,data,procedimento,observacoes) VALUES(?,?,?,?)',(animal_id,request.form['data'],request.form['procedimento'],request.form.get('observacoes','')))
        return redirect(url_for('animal',animal_id=animal_id))
    return render_template('tratamento.html',animals=get_animals())

@app.get('/fotos/<path:filename>')
def fotos(filename):
    with db() as c:
        allowed=c.execute('SELECT 1 FROM animais WHERE foto=? AND status=?', (filename,'Disponível para adoção')).fetchone()
        if not allowed and not session.get('admin'):
            abort(404)
    return send_from_directory(UPLOADS,filename)

@app.get('/api/animais')
def api_animais():
    # API pública: nunca retorna observações clínicas ou dados administrativos.
    return jsonify([{'id':a['id'],'nome':a['nome'],'sexo':a['sexo'],'idade':a['idade'],'foto_url':url_for('fotos',filename=a['foto']) if a['foto'] else None} for a in get_animals(public=True)])

init_db()
if __name__=='__main__':
    app.run(host='127.0.0.1',port=8000,debug=False)
