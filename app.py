# --- BIBLIOTECAS (As ferramentas que o Python usa) ---
import os
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash

# Carrega as variáveis de ambiente do arquivo .env para a memória do aplicativo
load_dotenv()

# 1. Carrega as variáveis de ambiente salvas no arquivo .env
load_dotenv()

# 2. Inicializa o aplicativo Flask
app = Flask(__name__)

# A 'secret_key' é obrigatória para o Flask conseguir usar 'session' (manter o usuário logado)
# e 'flash' (exibir mensagens de alerta/sucesso na tela).
app.secret_key = os.getenv('SECRET_KEY', 'chave_padrao_caso_nao_encontre_env')
# --- CONFIGURAÇÃO DAS PASTAS ---
ASSETS_FOLDER = os.path.join(app.root_path, 'assets')
CSS_FOLDER = os.path.join(app.root_path, 'css')
# -----------------------------------------------------------------------------
# 🔌 FUNÇÃO DE CONEXÃO COM O BANCO DE DADOS
# -----------------------------------------------------------------------------
def get_db_connection():
    """
    Abre uma conexão com o banco MySQL 'bliblitech'.
    Sempre que precisarmos consultar ou salvar algo, chamaremos essa função.
    """
    try:
        connection = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', ''),
            database=os.getenv('DB_NAME', 'bliblitech'),
            port=int(os.getenv('DB_PORT', 3306))
        )
        return connection
    except Error as e:
        print(f"❌ Erro ao conectar ao MySQL: {e}")
        return None

# -----------------------------------------------------------------------------
# 🖼️ ROTAS PARA SERVIR ARQUIVOS ESTÁTICOS (CSS E IMAGENS)
# -----------------------------------------------------------------------------
@app.route('/assets/<path:filename>')
def serve_assets(filename):
    """Permite carregar imagens da pasta assets/."""
    return send_from_directory(ASSETS_FOLDER, filename)

@app.route('/css/<path:filename>')
def serve_css(filename):
    """Permite carregar arquivos de estilo da pasta css/."""
    return send_from_directory(CSS_FOLDER, filename)

# -----------------------------------------------------------------------------
# 🏠 ROTA PRINCIPAL (HOME)
# -----------------------------------------------------------------------------
@app.route('/')
def index():
    """Página inicial do site. Busca as categorias cadastradas no MySQL para exibir."""
    connection = get_db_connection()
    categorias = []
    livros_destaque = []

    if connection:
        try:
            # dictionary=True faz o MySQL retornar os dados como dicionário Python (ex: {'nome_categoria': 'Romance'})
            cursor = connection.cursor(dictionary=True)
            
            # Buscar categorias
            cursor.execute("SELECT * FROM categorias")
            categorias = cursor.fetchall()

            # Buscar os 6 livros mais recentes
            cursor.execute("""
                SELECT l.*, c.nome_categoria
                FROM livro l
                LEFT JOIN categorias c ON l.id_categoria = c.id_categoria
                ORDER BY l.cadastro DESC LIMIT 6
            """)
            livros_destaque = cursor.fetchall()
            
        except Error as e:
            print(f"Erro na consulta da Home: {e}")
        finally:
            cursor.close()
            connection.close() # Sempre fechamos a conexão para não sobrecarregar o banco!

    return render_template('index.html', categorias=categorias, livros=livros_destaque)

# -----------------------------------------------------------------------------
# 👤 ROTA DE CADASTRO DE LEITOR
# -----------------------------------------------------------------------------
@app.route('/cadastro', methods=['GET', 'POST'])
def cadastro():
  """Permite que um novo leitor se cadastre no sistema."""
  if request.method == 'POST':
    nome = request.form.get('nome')
    email = request.form.get('email')
    telefone = request.form.get('telefone')
    sms = request.form.get('sms', telefone)  # Se SMS não for enviado, usa o mesmo número do telefone
    senha = request.form.get('senha')

    # Criptografa a senha antes de salvar no MySQL
    senha_hash = generate_password_hash(senha)

    connection = get_db_connection()
    if connection:
      try:
        cursor = connection.cursor()

        # Verifica se o e-mail já está cadastrado
        cursor.execute(
            'SELECT id_leitor FROM leitores WHERE email = %s', (email,)
        )
        if cursor.fetchone():
          flash('Este e-mail já está cadastrado. Tente fazer login!', 'warning')
          return redirect(url_for('cadastro'))

        # Insere o novo leitor na tabela 'leitores'
        # id_cargo = 1 corresponde a 'Leitor' na tabela cargos
        sql = """
                    INSERT INTO leitores (nome, id_cargo, email, telefone, sms, senha, tipo_perfil)
                    VALUES (%s, 1, %s, %s, %s, %s, 'LEITOR')
                """
        cursor.execute(sql, (nome, email, telefone, sms, senha_hash))
        connection.commit()

        flash('Cadastro realizado com sucesso! Faça seu login.', 'success')
        return redirect(url_for('login'))

      except Error as e:
        connection.rollback()
        flash(f'Erro ao realizar cadastro: {e}', 'danger')
      finally:
        cursor.close()
        connection.close()

  return render_template('cadastro.html')

# -----------------------------------------------------------------------------
# 🔑 ROTA DE LOGIN
# -----------------------------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
def login():
  """Autentica o leitor ou funcionário consultando o banco de dados."""
  if request.method == 'POST':
    email = request.form.get('email')
    senha = request.form.get('senha')

    connection = get_db_connection()
    if connection:
      try:
        cursor = connection.cursor(dictionary=True)

        # 1. Tenta buscar na tabela de leitores
        cursor.execute('SELECT * FROM leitores WHERE email = %s', (email,))
        usuario = cursor.fetchone()

        # 2. Se não encontrar em leitores, busca na tabela de funcionários
        if not usuario:
          cursor.execute(
              'SELECT * FROM funcionarios WHERE email = %s', (email,)
          )
          usuario = cursor.fetchone()

        # 3. Valida se o usuário existe e se a senha confere com o hash
        if usuario and check_password_hash(usuario['senha'], senha):
          # Salva os dados do usuário na Sessão do Flask
          session['usuario_id'] = usuario.get(
              'id_leitor'
          ) or usuario.get('id_funcionario')
          session['usuario_nome'] = usuario['nome']
          session['tipo_perfil'] = usuario['tipo_perfil']
          session['foto_perfil'] = usuario.get(
              'foto_perfil', 'default_profile.png'
          )

          flash(f'Bem-vindo(a), {usuario["nome"]}!', 'success')
          return redirect(url_for('index'))
        else:
          flash('E-mail ou senha incorretos.', 'danger')

      except Error as e:
        flash(f'Erro na autenticação: {e}', 'danger')
      finally:
        cursor.close()
        connection.close()

  return render_template('login.html')

# -----------------------------------------------------------------------------
# 🚪 ROTA DE LOGOUT
# -----------------------------------------------------------------------------
@app.route('/logout')
def logout():
  """Limpa os dados da sessão e desloga o usuário."""
  session.clear()
  flash('Sessão encerrada com sucesso.', 'info')
  return redirect(url_for('index'))

# -----------------------------------------------------------------------------
# 🟢 EXECUÇÃO DO SERVIDOR
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    os.makedirs(ASSETS_FOLDER, exist_ok=True)
    os.makedirs(CSS_FOLDER, exist_ok=True)
# Roda o servidor web em modo de desenvolvimento (atualiza a página automaticamente ao salvar)
app.run(debug=True)