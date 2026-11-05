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
