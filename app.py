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

@app.route('/')
def home():
    conn = get_db_connection()
    cursor = conn.cursor()

  # Busca os 10 livros mais bem avaliados (com maior média de notas)
    sql = '''
    SELECT l.id_livro, 
            l.titulo, 
            l.autor, 
            l.capa,
            COALESCE(AVG(a.nota), 0) AS media_notas,
            COUNT(a.id_avaliacao) AS total_avaliacoes,
            COUNT(CASE WHEN e.status_exemplar = 'Disponível' THEN 1 END) AS disponiveis
        FROM livro l
        LEFT JOIN avaliacoes a ON l.id_livro = a.livro_id
        LEFT JOIN exemplares e ON l.id_livro = e.id_livro
        GROUP BY l.id_livro
        ORDER BY media_notas DESC, total_avaliacoes DESC
        LIMIT 10
    '''
    cursor.execute(sql)
    livros_destaque = cursor.fetchall()
    conn.close()

    return render_template('index.html', livros=livros_destaque)
    





# -----------------------------------------------------------------------------
# 🟢 EXECUÇÃO DO SERVIDOR
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    os.makedirs(ASSETS_FOLDER, exist_ok=True)
    os.makedirs(CSS_FOLDER, exist_ok=True)
# Roda o servidor web em modo de desenvolvimento (atualiza a página automaticamente ao salvar)
app.run(debug=True)