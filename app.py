from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify
import sqlite3
from datetime import datetime
import os
from werkzeug.utils import secure_filename
import uuid

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'sua_chave_secreta_aqui')

# Configurações para upload de imagens
UPLOAD_FOLDER = 'static/images'
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'webp'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER

# Criar pasta de upload se não existir
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Inicialização do Banco de Dados
def init_db():
    try:
        conn = sqlite3.connect('estoque.db')
        cursor = conn.cursor()
        
        # Criar tabela produtos se não existir
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS produtos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                nome TEXT NOT NULL,
                preco REAL NOT NULL,
                quantidade INTEGER NOT NULL,
                imagem TEXT
            )
        ''')
        
        # Verificar se a coluna imagem existe, se não, adicionar
        cursor.execute("PRAGMA table_info(produtos)")
        columns = [column[1] for column in cursor.fetchall()]
        
        if 'imagem' not in columns:
            cursor.execute("ALTER TABLE produtos ADD COLUMN imagem TEXT")
            print("Coluna 'imagem' adicionada à tabela produtos")
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS vendas (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                id_produto INTEGER NOT NULL,
                nome TEXT NOT NULL,
                quantidade INTEGER NOT NULL,
                total REAL NOT NULL,
                data TEXT NOT NULL,
                FOREIGN KEY (id_produto) REFERENCES produtos(id)
            )
        ''')
        
        # Criar tabela de configurações se não existir
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS configuracoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chave TEXT UNIQUE NOT NULL,
                valor TEXT
            )
        ''')
        
        # Inserir configuração padrão de fundo se não existir
        cursor.execute("SELECT COUNT(*) FROM configuracoes WHERE chave = 'background_image'")
        if cursor.fetchone()[0] == 0:
            cursor.execute("INSERT INTO configuracoes (chave, valor) VALUES (?, ?)", ('background_image', ''))
        
        conn.commit()
        conn.close()
        print("Banco de dados inicializado com sucesso!")
    except Exception as e:
        print(f"Erro ao inicializar banco de dados: {e}")

# Rotas
@app.route('/')
def index():
    try:
        conn = sqlite3.connect('estoque.db')
        cursor = conn.cursor()
        
        # Total de produtos
        cursor.execute("SELECT COUNT(*) FROM produtos")
        total_produtos = cursor.fetchone()[0] or 0
        
        # Vendas de hoje
        hoje = datetime.now().strftime('%Y-%m-%d')
        cursor.execute("SELECT SUM(total) FROM vendas WHERE date(data) = date(?)", (hoje,))
        vendas_hoje = cursor.fetchone()[0] or 0
        
        # Vendas do mês atual
        mes_atual = datetime.now().strftime('%Y-%m')
        cursor.execute("SELECT SUM(total) FROM vendas WHERE strftime('%Y-%m', data) = ?", (mes_atual,))
        vendas_mes = cursor.fetchone()[0] or 0
        
        # Total geral de vendas
        cursor.execute("SELECT SUM(total) FROM vendas")
        total_vendas = cursor.fetchone()[0] or 0
        
        # Produtos com estoque baixo (menos de 10 unidades)
        cursor.execute("SELECT COUNT(*) FROM produtos WHERE quantidade < 10")
        produtos_estoque_baixo = cursor.fetchone()[0] or 0
        
        # Data atual formatada
        data_atual = datetime.now().strftime('%d/%m/%Y')
        
        conn.close()
        
        return render_template('index.html', 
                             total_produtos=total_produtos,
                             vendas_hoje=vendas_hoje,
                             vendas_mes=vendas_mes,
                             total_vendas=total_vendas,
                             produtos_estoque_baixo=produtos_estoque_baixo,
                             data_atual=data_atual)
    except Exception as e:
        flash(f'Erro ao carregar dashboard: {str(e)}', 'danger')
        return render_template('index.html', 
                             total_produtos=0,
                             vendas_hoje=0,
                             vendas_mes=0,
                             total_vendas=0,
                             produtos_estoque_baixo=0,
                             data_atual=datetime.now().strftime('%d/%m/%Y'))

@app.route('/cadastrar', methods=['GET', 'POST'])
def cadastrar():
    if request.method == 'POST':
        try:
            nome = request.form['nome']
            preco = float(request.form['preco'])
            quantidade = int(request.form['quantidade'])
            
            if not nome or preco <= 0 or quantidade <= 0:
                flash('Dados inválidos! Verifique os valores.', 'danger')
                return render_template('cadastrar.html')
            
            # Processar upload de imagem
            imagem_path = None
            if 'imagem' in request.files:
                file = request.files['imagem']
                if file and file.filename != '' and allowed_file(file.filename):
                    # Gerar nome único para o arquivo
                    filename = secure_filename(file.filename)
                    unique_filename = f"{uuid.uuid4().hex}_{filename}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                    file.save(filepath)
                    imagem_path = f"images/{unique_filename}"
            
            conn = sqlite3.connect('estoque.db')
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO produtos (nome, preco, quantidade, imagem) VALUES (?, ?, ?, ?)",
                (nome, preco, quantidade, imagem_path)
            )
            conn.commit()
            conn.close()
            flash('Produto cadastrado com sucesso!', 'success')
            return redirect(url_for('estoque'))
        except (ValueError, KeyError):
            flash('Dados inválidos! Verifique os valores.', 'danger')
        except Exception as e:
            flash(f'Erro ao cadastrar produto: {str(e)}', 'danger')
    
    return render_template('cadastrar.html')

@app.route('/estoque')
def estoque():
    try:
        conn = sqlite3.connect('estoque.db')
        cursor = conn.cursor()
        cursor.execute("SELECT id, nome, preco, quantidade, imagem FROM produtos ORDER BY nome")
        produtos = cursor.fetchall()
        conn.close()
        return render_template('estoque.html', produtos=produtos)
    except Exception as e:
        flash(f'Erro ao carregar estoque: {str(e)}', 'danger')
        return render_template('estoque.html', produtos=[])

@app.route('/vender', methods=['GET', 'POST'])
def vender():
    try:
        conn = sqlite3.connect('estoque.db')
        cursor = conn.cursor()
        
        if request.method == 'POST':
            try:
                id_produto = int(request.form['id_produto'])
                quantidade_vendida = int(request.form['quantidade'])
                
                if quantidade_vendida <= 0:
                    flash('Quantidade deve ser maior que zero!', 'danger')
                    return redirect(url_for('vender'))
                
                cursor.execute(
                    "SELECT id, nome, preco, quantidade, imagem FROM produtos WHERE id = ?",
                    (id_produto,)
                )
                produto = cursor.fetchone()
                
                if produto and produto[3] >= quantidade_vendida:
                    novo_estoque = produto[3] - quantidade_vendida
                    total = produto[2] * quantidade_vendida
                    data_venda = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    
                    cursor.execute(
                        "UPDATE produtos SET quantidade = ? WHERE id = ?",
                        (novo_estoque, id_produto)
                    )
                    
                    cursor.execute(
                        '''INSERT INTO vendas 
                        (id_produto, nome, quantidade, total, data) 
                        VALUES (?, ?, ?, ?, ?)''',
                        (id_produto, produto[1], quantidade_vendida, total, data_venda)
                    )
                    
                    conn.commit()
                    conn.close()
                    flash('Venda registrada com sucesso!', 'success')
                    return redirect(url_for('relatorio'))
                else:
                    flash('Quantidade indisponível em estoque!', 'danger')
            except (ValueError, KeyError):
                flash('Dados inválidos! Verifique os valores.', 'danger')
            except Exception as e:
                flash(f'Erro ao registrar venda: {str(e)}', 'danger')
        
        # Buscar produtos com estoque > 0
        cursor.execute("SELECT id, nome, preco, quantidade, imagem FROM produtos WHERE quantidade > 0 ORDER BY nome")
        produtos = cursor.fetchall()
        conn.close()
        
        now = datetime.now().strftime('%Y-%m-%d')
        hora = datetime.now().strftime('%H:%M')
        
        return render_template('vender.html', produtos=produtos, now=now, hora=hora)
    except Exception as e:
        flash(f'Erro ao carregar página de vendas: {str(e)}', 'danger')
        return render_template('vender.html', produtos=[], now='', hora='')

# Rota para buscar produto por código
@app.route('/buscar_produto/<int:codigo>')
def buscar_produto(codigo):
    try:
        conn = sqlite3.connect('estoque.db')
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT id, nome, preco, quantidade, imagem FROM produtos WHERE id = ? AND quantidade > 0",
            (codigo,)
        )
        produto = cursor.fetchone()
        conn.close()
        
        if produto:
            return jsonify({
                'success': True,
                'produto': {
                    'id': produto[0],
                    'nome': produto[1],
                    'preco': produto[2],
                    'quantidade': produto[3],
                    'imagem': produto[4]
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Produto não encontrado ou sem estoque'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erro ao buscar produto: {str(e)}'
        })

# Rota para buscar produto por nome
@app.route('/buscar_produto_nome/<nome>')
def buscar_produto_nome(nome):
    try:
        conn = sqlite3.connect('estoque.db')
        cursor = conn.cursor()
        
        cursor.execute(
            "SELECT id, nome, preco, quantidade, imagem FROM produtos WHERE nome LIKE ? AND quantidade > 0 ORDER BY nome LIMIT 1",
            (f'%{nome}%',)
        )
        produto = cursor.fetchone()
        conn.close()
        
        if produto:
            return jsonify({
                'success': True,
                'produto': {
                    'id': produto[0],
                    'nome': produto[1],
                    'preco': produto[2],
                    'quantidade': produto[3],
                    'imagem': produto[4]
                }
            })
        else:
            return jsonify({
                'success': False,
                'message': 'Produto não encontrado ou sem estoque'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'message': f'Erro ao buscar produto: {str(e)}'
        })

# Rota para configurações
@app.route('/configuracoes', methods=['GET', 'POST'])
def configuracoes():
    try:
        conn = sqlite3.connect('estoque.db')
        cursor = conn.cursor()
        
        if request.method == 'POST':
            # Processar upload de imagem de fundo
            if 'background_image' in request.files:
                file = request.files['background_image']
                if file and file.filename != '' and allowed_file(file.filename):
                    # Gerar nome único para o arquivo
                    filename = secure_filename(file.filename)
                    unique_filename = f"bg_{uuid.uuid4().hex}_{filename}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                    file.save(filepath)
                    background_path = f"images/{unique_filename}"
                    
                    # Atualizar configuração no banco
                    cursor.execute("UPDATE configuracoes SET valor = ? WHERE chave = ?", (background_path, 'background_image'))
                    conn.commit()
                    flash('Imagem de fundo atualizada com sucesso!', 'success')
                else:
                    flash('Arquivo inválido! Use apenas imagens (PNG, JPG, JPEG, GIF, WEBP).', 'danger')
        
        # Buscar configuração atual
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = ?", ('background_image',))
        result = cursor.fetchone()
        background_image = result[0] if result else ''
        
        conn.close()
        return render_template('configuracoes.html', background_image=background_image)
    except Exception as e:
        flash(f'Erro ao carregar configurações: {str(e)}', 'danger')
        return render_template('configuracoes.html', background_image='')

# Rota para editar produto
@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar_produto(id):
    try:
        conn = sqlite3.connect('estoque.db')
        cursor = conn.cursor()
        
        if request.method == 'POST':
            nome = request.form['nome']
            preco = float(request.form['preco'])
            quantidade = int(request.form['quantidade'])
            
            if not nome or preco <= 0 or quantidade < 0:
                flash('Dados inválidos! Verifique os valores.', 'danger')
                return redirect(url_for('editar_produto', id=id))
            
            # Processar upload de nova imagem
            imagem_path = None
            if 'imagem' in request.files:
                file = request.files['imagem']
                if file and file.filename != '' and allowed_file(file.filename):
                    # Gerar nome único para o arquivo
                    filename = secure_filename(file.filename)
                    unique_filename = f"{uuid.uuid4().hex}_{filename}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], unique_filename)
                    file.save(filepath)
                    imagem_path = f"images/{unique_filename}"
            
            # Atualizar produto
            if imagem_path:
                cursor.execute(
                    "UPDATE produtos SET nome = ?, preco = ?, quantidade = ?, imagem = ? WHERE id = ?",
                    (nome, preco, quantidade, imagem_path, id)
                )
            else:
                cursor.execute(
                    "UPDATE produtos SET nome = ?, preco = ?, quantidade = ? WHERE id = ?",
                    (nome, preco, quantidade, id)
                )
            
            conn.commit()
            conn.close()
            flash('Produto atualizado com sucesso!', 'success')
            return redirect(url_for('estoque'))
        
        # Buscar produto para edição
        cursor.execute("SELECT id, nome, preco, quantidade, imagem FROM produtos WHERE id = ?", (id,))
        produto = cursor.fetchone()
        conn.close()
        
        if produto:
            return render_template('editar_produto.html', produto=produto)
        else:
            flash('Produto não encontrado!', 'danger')
            return redirect(url_for('estoque'))
    except Exception as e:
        flash(f'Erro ao editar produto: {str(e)}', 'danger')
        return redirect(url_for('estoque'))

# Rota para excluir produto
@app.route('/excluir/<int:id>')
def excluir_produto(id):
    try:
        conn = sqlite3.connect('estoque.db')
        cursor = conn.cursor()
        
        # Verificar se o produto existe
        cursor.execute("SELECT nome, imagem FROM produtos WHERE id = ?", (id,))
        result = cursor.fetchone()
        
        if not result:
            flash('Produto não encontrado!', 'danger')
            return redirect(url_for('estoque'))
        
        nome_produto = result[0]
        imagem_path = result[1]
        
        # Verificar se há vendas associadas ao produto
        cursor.execute("SELECT COUNT(*) FROM vendas WHERE id_produto = ?", (id,))
        vendas_count = cursor.fetchone()[0]
        
        if vendas_count > 0:
            flash(f'Não é possível excluir o produto "{nome_produto}" pois existem {vendas_count} venda(s) associada(s) a ele. Use a opção "Excluir com Vendas" se desejar remover tudo.', 'danger')
            return redirect(url_for('estoque'))
        
        # Excluir arquivo de imagem se existir
        if imagem_path:
            try:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], imagem_path.replace('images/', ''))
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Erro ao excluir imagem: {e}")
        
        # Excluir produto
        cursor.execute("DELETE FROM produtos WHERE id = ?", (id,))
        conn.commit()
        conn.close()
        
        flash(f'Produto "{nome_produto}" excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir produto: {str(e)}', 'danger')
    
    return redirect(url_for('estoque'))

# Rota para excluir produto com vendas
@app.route('/excluir_com_vendas/<int:id>')
def excluir_produto_com_vendas(id):
    try:
        conn = sqlite3.connect('estoque.db')
        cursor = conn.cursor()
        
        # Verificar se o produto existe
        cursor.execute("SELECT nome, imagem FROM produtos WHERE id = ?", (id,))
        result = cursor.fetchone()
        
        if not result:
            flash('Produto não encontrado!', 'danger')
            return redirect(url_for('estoque'))
        
        nome_produto = result[0]
        imagem_path = result[1]
        
        # Contar vendas que serão excluídas
        cursor.execute("SELECT COUNT(*) FROM vendas WHERE id_produto = ?", (id,))
        vendas_count = cursor.fetchone()[0]
        
        # Excluir vendas relacionadas primeiro
        cursor.execute("DELETE FROM vendas WHERE id_produto = ?", (id,))
        
        # Excluir arquivo de imagem se existir
        if imagem_path:
            try:
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], imagem_path.replace('images/', ''))
                if os.path.exists(file_path):
                    os.remove(file_path)
            except Exception as e:
                print(f"Erro ao excluir imagem: {e}")
        
        # Excluir produto
        cursor.execute("DELETE FROM produtos WHERE id = ?", (id,))
        conn.commit()
        conn.close()
        
        if vendas_count > 0:
            flash(f'Produto "{nome_produto}" e {vendas_count} venda(s) relacionada(s) excluído(s) com sucesso!', 'success')
        else:
            flash(f'Produto "{nome_produto}" excluído com sucesso!', 'success')
    except Exception as e:
        flash(f'Erro ao excluir produto: {str(e)}', 'danger')
    
    return redirect(url_for('estoque'))

# Rota para obter configuração de fundo
@app.route('/get_background')
def get_background():
    try:
        conn = sqlite3.connect('estoque.db')
        cursor = conn.cursor()
        cursor.execute("SELECT valor FROM configuracoes WHERE chave = ?", ('background_image',))
        result = cursor.fetchone()
        conn.close()
        
        background_image = result[0] if result else ''
        return jsonify({'background_image': background_image})
    except Exception as e:
        return jsonify({'background_image': ''})

@app.route('/relatorio')
def relatorio():
    try:
        conn = sqlite3.connect('estoque.db')
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT v.id, v.nome, v.quantidade, v.total, v.data, p.preco
            FROM vendas v
            JOIN produtos p ON v.id_produto = p.id
            ORDER BY v.data DESC
        ''')
        
        vendas = cursor.fetchall()
        cursor.execute("SELECT SUM(total) FROM vendas")
        total_vendas = cursor.fetchone()[0] or 0
        
        # Calcular ticket médio
        ticket_medio = total_vendas / len(vendas) if vendas else 0
        
        conn.close()
        
        return render_template('relatorio.html', vendas=vendas, total_vendas=total_vendas, ticket_medio=ticket_medio)
    except Exception as e:
        flash(f'Erro ao carregar relatório: {str(e)}', 'danger')
        return render_template('relatorio.html', vendas=[], total_vendas=0, ticket_medio=0)

@app.route('/graficos', methods=['GET', 'POST'])
def graficos():
    try:
        conn = sqlite3.connect('estoque.db')
        cursor = conn.cursor()

        if request.method == 'POST':
            data_inicio = request.form.get('data_inicio', '')
            data_fim = request.form.get('data_fim', '')
        else:
            data_inicio = ''
            data_fim = ''

        filtro = ""
        params = []
        
        if data_inicio and data_fim:
            filtro = "WHERE date(data) BETWEEN date(?) AND date(?)"
            params = [data_inicio, data_fim]

        cursor.execute(f'''
            SELECT date(data) as dia, SUM(total)
            FROM vendas
            {filtro}
            GROUP BY dia
            ORDER BY dia
        ''', params)
        
        vendas_dia = {
            'labels': [],
            'data': []
        }
        
        for dia, total in cursor.fetchall():
            vendas_dia['labels'].append(dia)
            vendas_dia['data'].append(float(total))

        cursor.execute(f'''
            SELECT strftime('%Y-%m', data) as mes, SUM(total)
            FROM vendas
            {filtro}
            GROUP BY mes
            ORDER BY mes
        ''', params)
        
        vendas_mes = {
            'labels': [],
            'data': []
        }
        
        for mes, total in cursor.fetchall():
            vendas_mes['labels'].append(mes)
            vendas_mes['data'].append(float(total))

        conn.close()

        return render_template(
            'graficos.html',
            vendas_dia=vendas_dia,
            vendas_mes=vendas_mes,
            data_inicio=data_inicio,
            data_fim=data_fim
        )
    except Exception as e:
        flash(f'Erro ao carregar gráficos: {str(e)}', 'danger')
        return render_template(
            'graficos.html',
            vendas_dia={'labels': [], 'data': []},
            vendas_mes={'labels': [], 'data': []},
            data_inicio='',
            data_fim=''
        )

if __name__ == '__main__':
    init_db()
    app.run(debug=True)