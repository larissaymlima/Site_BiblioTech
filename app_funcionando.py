import os
import uuid
import random
import secrets
import datetime
import logging
from datetime import timedelta
from functools import wraps
from flask import Flask, request, jsonify, session
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)

# Configurações de Segurança e Sessão
app.secret_key = os.getenv('SECRET_KEY', 'chave_secreta_padrao_para_testes')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)

# Configuração da pasta de upload
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads', 'avatars')
UPLOAD_FOLDER_CAPAS = os.path.join(os.getcwd(), 'uploads', 'capas')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(UPLOAD_FOLDER_CAPAS, exist_ok=True)

# Dicionário temporário na memória para os códigos de recuperação de senha
codigos_recuperacao = {}

# =============================================================================
# 🛠️ CONEXÃO COM O BANCO DE DADOS
# =============================================================================

def get_db_connection():
    """Cria e retorna a conexão com o banco MySQL bibliotech."""
    try:
        conn = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', ''),
            database=os.getenv('DB_NAME', 'bibliotech'),
            port=int(os.getenv('DB_PORT', 3306))
        )
        return conn
    except Error as err:
        print(f"❌ Erro de conexão com o banco de dados: {err}")
        return None

# =============================================================================
# 📧 FUNÇÕES AUXILIARES
# =============================================================================

def arquivo_permitido(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def gerar_codigo_recuperacao(email_destino, codigo):
    """
    Sem provedor externo de e-mail/SMS (sem SendGrid/Twilio) configurado neste
    projeto. Para viabilizar o teste via Thunder Client, o código é apenas
    registrado no log do servidor. Em produção, aqui entraria a integração
    real de envio (e-mail/SMS) escolhida pelo time.
    """
    print(f"📨 [SIMULAÇÃO DE ENVIO] Código de recuperação para {email_destino}: {codigo}")
    logger_lgpd.info(f"Código de recuperação de senha gerado para o e-mail [{email_destino}].")

# =============================================================================
# 🔒 MIDDLEWARES DE AUTENTICAÇÃO VIA SESSÃO
# =============================================================================

def login_requerido(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'usuario' not in session:
            return jsonify({"sucesso": False, "mensagem": "Acesso não autorizado. Faça login primeiro."}), 401
        return f(*args, **kwargs)
    return decorated

def apenas_funcionario(f):
    """Permite acesso a qualquer funcionário (Bibliotecário ou Auxiliar),
    ao contrário de apenas_administrador que exige cargo de Bibliotecário (id_cargo=1)."""
    @wraps(f)
    def decorated(*args, **kwargs):
        usuario = session.get('usuario')
        if not usuario:
            return jsonify({"sucesso": False, "mensagem": "Acesso não autorizado. Faça login primeiro."}), 401

        if usuario.get('tipo_perfil') != 'FUNCIONARIO':
            return jsonify({"sucesso": False, "mensagem": "Acesso restrito a funcionários."}), 403

        return f(*args, **kwargs)
    return decorated

def apenas_administrador(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        usuario = session.get('usuario')
        if not usuario:
            return jsonify({"sucesso": False, "mensagem": "Acesso não autorizado. Faça login primeiro."}), 401
        
        if usuario.get('tipo_perfil') != 'FUNCIONARIO' or usuario.get('id_cargo') != 1:
            return jsonify({"sucesso": False, "mensagem": "Acesso restrito apenas para administradores."}), 403

        return f(*args, **kwargs)
    return decorated

def apenas_leitor(f):
    """Permite acesso apenas a leitores autenticados."""
    @wraps(f)
    def decorated(*args, **kwargs):
        usuario = session.get('usuario')
        if not usuario:
            return jsonify({"sucesso": False, "mensagem": "Acesso não autorizado. Faça login primeiro."}), 401

        if usuario.get('tipo_perfil') != 'LEITOR':
            return jsonify({"sucesso": False, "mensagem": "Acesso restrito a leitores."}), 403

        return f(*args, **kwargs)
    return decorated

STATUS_RESERVA_VALIDOS = ('Pendente', 'Aguardando Retirada', 'Concluida', 'Cancelada')

# Configura um log focado em auditoria (Guarde em local seguro)
LOG_FOLDER = os.path.join(os.getcwd(), 'logs')
os.makedirs(LOG_FOLDER, exist_ok=True)

logger_lgpd = logging.getLogger('auditoria_lgpd')
logger_lgpd.setLevel(logging.INFO)
logger_lgpd.propagate = False

if not logger_lgpd.handlers:
    _handler_lgpd = logging.FileHandler(
        os.path.join(LOG_FOLDER, 'auditoria_lgpd.log'), encoding='utf-8'
    )
    _handler_lgpd.setFormatter(
        logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    )
    logger_lgpd.addHandler(_handler_lgpd)
# =============================================================================
# 🔐 MÓDULO DE AUTENTICAÇÃO E SESSÃO
# =============================================================================
# 1. INICIAR SESSÃO (LOGIN) - OK
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json() or {}
    email = str(data.get('email', '')).strip()
    senha = str(data.get('senha', '')).strip()

    if not email or not senha:
        return jsonify({"sucesso": False, "mensagem": "E-mail e senha são obrigatórios."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        usuario = None
        tipo_perfil = None

        # Busca em funcionários
        sql_func = """
            SELECT f.id_funcionario AS id, f.nome, f.email, f.senha, f.status_funcionario AS status, 
                   f.id_cargo, c.nome_cargo 
            FROM funcionarios f
            INNER JOIN cargos c ON f.id_cargo = c.id_cargo
            WHERE f.email = %s
        """
        cursor.execute(sql_func, (email,))
        usuario = cursor.fetchone()

        if usuario:
            tipo_perfil = 'FUNCIONARIO'
        else:
            # Busca em leitores
            sql_leitor = """
                SELECT id_leitor AS id, nome, email, senha, status_conta AS status
                FROM leitores
                WHERE email = %s
            """
            cursor.execute(sql_leitor, (email,))
            usuario = cursor.fetchone()
            if usuario:
                tipo_perfil = 'LEITOR'

        cursor.close()
        conn.close()

        if not usuario or not check_password_hash(usuario['senha'], senha):
            return jsonify({"sucesso": False, "mensagem": "E-mail ou senha incorretos."}), 401

        if usuario['status'] in ['Inativo', 'Suspenso', 'Bloqueado']:
            return jsonify({"sucesso": False, "mensagem": f"Conta {usuario['status'].lower()}. Entre em contato com o suporte."}), 403

        # Salva as informações do usuário na sessão do servidor
        session.permanent = True
        session['usuario'] = {
            "id": usuario['id'],
            "nome": usuario['nome'],
            "email": usuario['email'],
            "tipo_perfil": tipo_perfil,
            "id_cargo": usuario.get('id_cargo'),
            "cargo": usuario.get('nome_cargo')
        }

        return jsonify({
            "sucesso": True,
            "mensagem": "Login realizado com sucesso!",
            "usuario": session['usuario']
        }), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro interno ao autenticar: {str(e)}"}), 500

# 2. ENCERRAR SESSÃO (LOGOUT) - OK
@app.route('/logout', methods=['POST'])
@login_requerido
def logout():
    session.clear()
    return jsonify({"sucesso": True, "mensagem": "Sessão encerrada com sucesso."}), 200

# 3. RETORNAR PERFIL DO USUÁRIO LOGADO - OK
@app.route('/me', methods=['GET'])
@login_requerido
def obter_perfil_logado():
    return jsonify({
        "sucesso": True,
        "usuario": session.get('usuario')
    }), 200

# 4. RECUPERAÇÃO DE SENHA — SOLICITAR CÓDIGO
@app.route('/recuperar-senha/solicitar', methods=['POST'])
def solicitar_codigo_recuperacao():
    data = request.get_json() or {}
    email = str(data.get('email', '')).strip()

    if not email:
        return jsonify({"sucesso": False, "mensagem": "O e-mail é obrigatório."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT email FROM funcionarios WHERE email = %s", (email,))
        usuario = cursor.fetchone()

        if not usuario:
            cursor.execute("SELECT email FROM leitores WHERE email = %s", (email,))
            usuario = cursor.fetchone()

        cursor.close()
        conn.close()

        if not usuario:
            return jsonify({"sucesso": True, "mensagem": "Se o e-mail estiver cadastrado, um código de verificação foi gerado."}), 200

        codigo = str(random.randint(1000, 9999))
        expiracao = datetime.datetime.now() + timedelta(minutes=15)
        
        codigos_recuperacao[email] = {
            "codigo": codigo,
            "expiracao": expiracao
        }

        gerar_codigo_recuperacao(email, codigo)

        resposta = {
            "sucesso": True,
            "mensagem": "Se o e-mail estiver cadastrado, um código de verificação foi gerado."
        }

        # Sem provedor externo de e-mail/SMS (SendGrid/Twilio) neste projeto:
        # o código é devolvido diretamente na resposta apenas para viabilizar
        # o teste via Thunder Client. Remova este campo antes de um deploy real.
        resposta["codigo_teste"] = codigo

        return jsonify(resposta), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro interno: {str(e)}"}), 500

# 5. RECUPERAÇÃO DE SENHA — REDEFINIR COM CÓDIGO DE 4 DÍGITOS
@app.route('/recuperar-senha/redefinir', methods=['POST'])
def redefinir_senha_com_codigo():
    data = request.get_json() or {}
    email = str(data.get('email', '')).strip()
    codigo = str(data.get('codigo', '')).strip()
    nova_senha = str(data.get('nova_senha', '')).strip()

    if not email or not codigo or not nova_senha:
        return jsonify({"sucesso": False, "mensagem": "E-mail, código e nova senha são obrigatórios."}), 400

    dados_codigo = codigos_recuperacao.get(email)

    if not dados_codigo:
        return jsonify({"sucesso": False, "mensagem": "Nenhuma solicitação de código encontrada para este e-mail."}), 400

    if datetime.datetime.now() > dados_codigo['expiracao']:
        codigos_recuperacao.pop(email, None)
        return jsonify({"sucesso": False, "mensagem": "O código expirou. Solicite um novo código."}), 400

    if dados_codigo['codigo'] != codigo:
        return jsonify({"sucesso": False, "mensagem": "Código de verificação incorreto."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor()
        nova_senha_hash = generate_password_hash(nova_senha)

        cursor.execute("UPDATE funcionarios SET senha = %s WHERE email = %s", (nova_senha_hash, email))
        conn.commit()

        if cursor.rowcount == 0:
            cursor.execute("UPDATE leitores SET senha = %s WHERE email = %s", (nova_senha_hash, email))
            conn.commit()

        cursor.close()
        conn.close()

        codigos_recuperacao.pop(email, None)

        return jsonify({"sucesso": True, "mensagem": "Senha redefinida com sucesso! Faça login com a nova senha."}), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao redefinir senha: {str(e)}"}), 500

# =============================================================================
# ⚙️ MÓDULO ADMINISTRATIVO: CRUD DE FUNCIONÁRIOS (SESSÃO)
# =============================================================================
# 1. LISTAR TODOS OS FUNCIONÁRIOS - OK
@app.route('/funcionarios', methods=['GET'])
@apenas_administrador
def listar_funcionarios():
    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT f.id_funcionario, f.nome, f.email, f.telefone, f.status_funcionario, f.data_cadastro, c.nome_cargo 
            FROM funcionarios f
            INNER JOIN cargos c ON f.id_cargo = c.id_cargo
        """
        cursor.execute(sql)
        funcionarios = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "funcionarios": funcionarios}), 200
    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao buscar funcionários: {str(e)}"}), 500

# 2. CADASTRAR FUNCIONÁRIO - OK 
@app.route('/funcionarios', methods=['POST'])
@apenas_administrador
def criar_funcionario():
    data = request.get_json() or {}

    nome = str(data.get('nome', '')).strip()
    email = str(data.get('email', '')).strip()
    telefone = str(data.get('telefone', '')).strip()
    senha = str(data.get('senha', '')).strip()
    id_cargo = data.get('id_cargo')

    if not nome or not email or not telefone or not senha or not id_cargo:
        return jsonify({"sucesso": False, "mensagem": "Preencha todos os campos obrigatórios."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id_funcionario FROM funcionarios WHERE email = %s", (email,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Este e-mail já está cadastrado."}), 400

        senha_hash = generate_password_hash(senha)

        sql = """
            INSERT INTO funcionarios (nome, id_cargo, email, telefone, senha, tipo_perfil, status_funcionario)
            VALUES (%s, %s, %s, %s, %s, 'FUNCIONARIO', 'Ativo')
        """
        cursor.execute(sql, (nome, id_cargo, email, telefone, senha_hash))
        conn.commit()

        novo_id = cursor.lastrowid
        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "mensagem": "Funcionário cadastrado com sucesso!", "id_funcionario": novo_id}), 201

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao cadastrar funcionário: {str(e)}"}), 400

# 3. EDITAR FUNCIONÁRIO (EXCLUSIVO PARA ADMINISTRADOR) - OK
@app.route('/funcionarios/<int:id_funcionario>', methods=['PUT'])
@apenas_administrador
def editar_funcionario(id_funcionario):
    data = request.get_json() or {}

    usuario_responsavel = session.get('usuario', {}).get('email')

    nome = str(data.get('nome', '')).strip()
    telefone = str(data.get('telefone', '')).strip()
    status_funcionario = str(data.get('status_funcionario', 'Ativo')).strip()
    
    try:
        id_cargo = int(data.get('id_cargo'))
    except (ValueError, TypeError):
        id_cargo = None

    if not nome or not telefone or not id_cargo:
        return jsonify({"sucesso": False, "mensagem": "Nome, Telefone e Cargo são obrigatórios."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        sql = """
            UPDATE funcionarios 
            SET nome = %s, telefone = %s, id_cargo = %s, status_funcionario = %s
            WHERE id_funcionario = %s
        """
        cursor.execute(sql, (nome, telefone, id_cargo, status_funcionario, id_funcionario))
        conn.commit()
        linhas_afetadas = cursor.rowcount

        cursor.close()
        conn.close()

        if linhas_afetadas == 0:
            return jsonify({"sucesso": False, "mensagem": "Nenhum funcionário encontrado ou nenhuma alteração realizada."}), 404

        # 2. TRILHA DE AUDITORIA (Exigência da LGPD)
        # Registra a ação sem expor explicitamente o dado novo no log de texto comum
        logger_lgpd.info(
            f"Auditoria LGPD: Usuário [{usuario_responsavel}] MODIFICOU os dados "
            f"pessoais do funcionário ID [{id_funcionario}]."
        )

        return jsonify({"sucesso": True, "mensagem": "Dados do funcionário atualizados com sucesso!"}), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        
        # 3. SEGURANÇA: Salva o erro real no servidor, mas esconde do usuário externo
        logger_lgpd.error(f"Erro crítico na edição do funcionário {id_funcionario}: {str(e)}")
        return jsonify({
            "sucesso": False, 
            "mensagem": "Erro interno no servidor ao processar a atualização. Tente novamente mais tarde."
        }), 500

# 4. EXCLUIR / INATIVAR FUNCIONÁRIO - OK
@app.route('/funcionarios/<int:id_funcionario>', methods=['DELETE'])
@apenas_administrador
def excluir_funcionario(id_funcionario):
    usuario_logado = session.get('usuario', {})

    if id_funcionario == usuario_logado.get('id'):
        return jsonify({"sucesso": False, "mensagem": "Você não pode excluir sua própria conta enquanto estiver logado."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM funcionarios WHERE id_funcionario = %s", (id_funcionario,))
            conn.commit()
            cursor.close()
            conn.close()

            logger_lgpd.info(f"Auditoria LGPD: Exclusão total do funcionário ID [{id_funcionario}].")
            return jsonify({"sucesso": True, "mensagem": "Funcionário excluído com sucesso."}), 200

        except mysql.connector.Error as err:
            conn.rollback()
            if err.errno == 1451:  # Restrição de Chave Estrangeira (vínculos com empréstimos)
                senha_inutilizavel = generate_password_hash(secrets.token_hex(16))
                cursor.execute("""
                    UPDATE funcionarios 
                    SET nome = 'Ex-Funcionário (Anonimizado)',
                        email = CONCAT('ex_func_', id_funcionario, '@lgpd.deleted'),
                        telefone = '',
                        senha = %s,
                        foto_perfil = 'default_profile.png',
                        status_funcionario = 'Bloqueado'
                    WHERE id_funcionario = %s
                """, (senha_inutilizavel, id_funcionario))
                conn.commit()
                cursor.close()
                conn.close()

                logger_lgpd.info(f"Auditoria LGPD: Dados pessoais do funcionário ID [{id_funcionario}] foram anonimizados devido a vínculos históricos.")
                return jsonify({
                    "sucesso": True, 
                    "mensagem": "O funcionário possui registros vinculados no histórico. Seus dados pessoais foram anonimizados conforme a LGPD."
                }), 200
            
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Restrição de banco de dados ao tentar excluir."}), 400

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro interno ao tentar excluir: {str(e)}"}), 500

# =============================================================================
# 📚 MÓDULO: ACERVO DE LIVROS
# =============================================================================
STATUS_LIVRO_VALIDOS = ('Ativo', 'Indisponível')

def _recalcular_status_exemplar(cursor, id_livro):
    """Recalcula e grava livro.status_exemplar com base no estoque atual
    e nos empréstimos ativos, mantendo o campo sincronizado após qualquer
    alteração manual de quant_estoque."""
    cursor.execute(
        "SELECT COUNT(*) AS total FROM emprestimos WHERE id_livro = %s AND data_devolucao_real IS NULL",
        (id_livro,)
    )
    total_emprestados = cursor.fetchone()['total']

    cursor.execute("SELECT quant_estoque FROM livro WHERE id_livro = %s", (id_livro,))
    qtd_estoque = cursor.fetchone()['quant_estoque']

    if total_emprestados >= qtd_estoque:
        novo_status = 'Emprestado'
    else:
        cursor.execute(
            "SELECT COUNT(*) AS total FROM reservas WHERE id_livro = %s AND status_reserva = 'Aguardando Retirada'",
            (id_livro,)
        )
        aguardando_retirada = cursor.fetchone()['total']
        novo_status = 'Reservado' if aguardando_retirada > 0 else 'Disponível'

    cursor.execute("UPDATE livro SET status_exemplar = %s WHERE id_livro = %s", (novo_status, id_livro))
    return novo_status

# 1. LISTAR CATÁLOGO PÚBLICO DE LIVROS ATIVOS - OK
@app.route('/livros', methods=['GET'])
def listar_livros():
    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT l.id_livro, l.titulo, l.autor, l.ano_publicacao, l.quant_estoque, l.sinopse,
                   l.capa, l.posicao_estante, l.status_exemplar, l.status_livro,
                   l.id_categoria, c.nome_categoria,
                   ROUND(AVG(a.nota), 1) AS media_avaliacoes, COUNT(a.id_avaliacao) AS total_avaliacoes
            FROM livro l
            INNER JOIN categorias c ON l.id_categoria = c.id_categoria
            LEFT JOIN avaliacoes a ON a.livro_id = l.id_livro
            WHERE l.status_livro = 'Ativo'
            GROUP BY l.id_livro
            ORDER BY l.titulo ASC
        """
        cursor.execute(sql)
        livros = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "livros": livros}), 200
    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao buscar livros: {str(e)}"}), 500

# 2. BUSCAR POR TÍTULO, AUTOR OU CATEGORIA - OK
@app.route('/livros/busca', methods=['GET'])
def buscar_livros():
    termo = request.args.get('q', '').strip()
    id_categoria = request.args.get('id_categoria')

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT l.id_livro, l.titulo, l.autor, l.ano_publicacao, l.quant_estoque, l.sinopse,
                   l.capa, l.posicao_estante, l.status_exemplar, l.status_livro,
                   l.id_categoria, c.nome_categoria,
                   ROUND(AVG(a.nota), 1) AS media_avaliacoes, COUNT(a.id_avaliacao) AS total_avaliacoes
            FROM livro l
            INNER JOIN categorias c ON l.id_categoria = c.id_categoria
            LEFT JOIN avaliacoes a ON a.livro_id = l.id_livro
            WHERE l.status_livro = 'Ativo'
        """
        params = []

        if termo:
            sql += " AND (l.titulo LIKE %s OR l.autor LIKE %s)"
            params.extend([f"%{termo}%", f"%{termo}%"])

        if id_categoria:
            sql += " AND l.id_categoria = %s"
            params.append(id_categoria)

        sql += " GROUP BY l.id_livro ORDER BY l.titulo ASC"

        cursor.execute(sql, tuple(params))
        livros = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "livros": livros}), 200
    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro na busca: {str(e)}"}), 500

# 3. EXIBIR DETALHES DO LIVRO E MÉDIA DE NOTAS - OK
@app.route('/livros/<int:id_livro>', methods=['GET'])
def detalhar_livro(id_livro):
    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT l.id_livro, l.titulo, l.autor, l.ano_publicacao, l.quant_estoque, l.sinopse,
                   l.capa, l.posicao_estante, l.status_exemplar, l.status_livro,
                   l.id_categoria, c.nome_categoria,
                   ROUND(AVG(a.nota), 1) AS media_avaliacoes, COUNT(a.id_avaliacao) AS total_avaliacoes
            FROM livro l
            INNER JOIN categorias c ON l.id_categoria = c.id_categoria
            LEFT JOIN avaliacoes a ON a.livro_id = l.id_livro
            WHERE l.id_livro = %s
            GROUP BY l.id_livro
        """
        cursor.execute(sql, (id_livro,))
        livro = cursor.fetchone()
        cursor.close()
        conn.close()

        if not livro:
            return jsonify({"sucesso": False, "mensagem": "Livro não encontrado."}), 404

        return jsonify({"sucesso": True, "livro": livro}), 200
    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao buscar livro: {str(e)}"}), 500

# 4. CADASTRAR LIVRO E VINCULAR CATEGORIA (funcionários) - OK
@app.route('/livros', methods=['POST'])
@apenas_funcionario
def criar_livro():
    data = request.get_json() or {}

    titulo = str(data.get('titulo', '')).strip()
    autor = str(data.get('autor', '')).strip()
    ano_publicacao = data.get('ano_publicacao')
    quant_estoque = data.get('quant_estoque', 1)
    sinopse = data.get('sinopse')
    posicao_estante = data.get('posicao_estante')
    id_categoria = data.get('id_categoria')

    if not titulo or not autor or not id_categoria:
        return jsonify({"sucesso": False, "mensagem": "Título, autor e id_categoria são obrigatórios."}), 400

    try:
        quant_estoque = int(quant_estoque)
        if quant_estoque < 1:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"sucesso": False, "mensagem": "quant_estoque deve ser um número inteiro maior que zero."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id_categoria FROM categorias WHERE id_categoria = %s", (id_categoria,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Categoria informada não existe."}), 400

        sql = """
            INSERT INTO livro (titulo, autor, ano_publicacao, quant_estoque, sinopse, posicao_estante, id_categoria)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """
        cursor.execute(sql, (titulo, autor, ano_publicacao, quant_estoque, sinopse, posicao_estante, id_categoria))
        conn.commit()

        novo_id = cursor.lastrowid
        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "mensagem": "Livro cadastrado com sucesso!", "id_livro": novo_id}), 201

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao cadastrar livro: {str(e)}"}), 400

# 5. EDITAR INFORMAÇÕES DO LIVRO (funcionários) - OK
@app.route('/livros/<int:id_livro>', methods=['PUT'])
@apenas_funcionario
def editar_livro(id_livro):
    data = request.get_json() or {}

    titulo = str(data.get('titulo', '')).strip()
    autor = str(data.get('autor', '')).strip()
    ano_publicacao = data.get('ano_publicacao')
    sinopse = data.get('sinopse')
    posicao_estante = data.get('posicao_estante')
    id_categoria = data.get('id_categoria')

    try:
        quant_estoque = int(data.get('quant_estoque'))
        if quant_estoque < 1:
            raise ValueError
    except (ValueError, TypeError):
        return jsonify({"sucesso": False, "mensagem": "quant_estoque deve ser um número inteiro maior que zero."}), 400

    if not titulo or not autor or not id_categoria:
        return jsonify({"sucesso": False, "mensagem": "Título, autor e id_categoria são obrigatórios."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id_livro FROM livro WHERE id_livro = %s", (id_livro,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Livro não encontrado."}), 404

        cursor.execute("SELECT id_categoria FROM categorias WHERE id_categoria = %s", (id_categoria,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Categoria informada não existe."}), 400

        sql = """
            UPDATE livro
            SET titulo = %s, autor = %s, ano_publicacao = %s, quant_estoque = %s,
                sinopse = %s, posicao_estante = %s, id_categoria = %s
            WHERE id_livro = %s
        """
        cursor.execute(sql, (titulo, autor, ano_publicacao, quant_estoque, sinopse, posicao_estante, id_categoria, id_livro))

        # Mantém livro.status_exemplar sincronizado com o novo quant_estoque
        novo_status_exemplar = _recalcular_status_exemplar(cursor, id_livro)

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "sucesso": True,
            "mensagem": "Livro atualizado com sucesso!",
            "status_exemplar": novo_status_exemplar
        }), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.rollback()
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao editar livro: {str(e)}"}), 400

# 6. ALTERNAR STATUS DO LIVRO (Ativo/Indisponível) (funcionários) - OK
@app.route('/livros/<int:id_livro>/status', methods=['PUT'])
@apenas_funcionario
def alternar_status_livro(id_livro):
    data = request.get_json() or {}
    novo_status = str(data.get('status_livro', '')).strip()

    if novo_status not in STATUS_LIVRO_VALIDOS:
        return jsonify({
            "sucesso": False,
            "mensagem": f"Status inválido. Use um dos seguintes: {', '.join(STATUS_LIVRO_VALIDOS)}."
        }), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE livro SET status_livro = %s WHERE id_livro = %s", (novo_status, id_livro))
        conn.commit()
        linhas_afetadas = cursor.rowcount
        cursor.close()
        conn.close()

        if linhas_afetadas == 0:
            return jsonify({"sucesso": False, "mensagem": "Livro não encontrado."}), 404

        return jsonify({"sucesso": True, "mensagem": f"Status do livro atualizado para '{novo_status}'."}), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao atualizar status: {str(e)}"}), 500

# 7. ENVIAR IMAGEM DA CAPA (funcionários) - OK
@app.route('/livros/<int:id_livro>/capa', methods=['POST'])
@apenas_funcionario
def upload_capa_livro(id_livro):
    if 'capa' not in request.files:
        return jsonify({"sucesso": False, "mensagem": "Nenhum arquivo enviado."}), 400

    file = request.files['capa']

    if file.filename == '':
        return jsonify({"sucesso": False, "mensagem": "Nenhum arquivo selecionado."}), 400

    if not file or not arquivo_permitido(file.filename):
        return jsonify({"sucesso": False, "mensagem": "Formato não permitido (use PNG, JPG, JPEG ou WEBP)."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor()
        cursor.execute("SELECT id_livro FROM livro WHERE id_livro = %s", (id_livro,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Livro não encontrado."}), 404

        extensao = file.filename.rsplit('.', 1)[1].lower()
        nome_arquivo = f"capa_livro_{id_livro}_{uuid.uuid4().hex[:8]}.{extensao}"
        caminho_salvar = os.path.join(UPLOAD_FOLDER_CAPAS, nome_arquivo)
        file.save(caminho_salvar)

        url_relativa = f"/uploads/capas/{nome_arquivo}"

        cursor.execute("UPDATE livro SET capa = %s WHERE id_livro = %s", (url_relativa, id_livro))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "mensagem": "Capa atualizada com sucesso!", "capa": url_relativa}), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao salvar capa: {str(e)}"}), 500

# =============================================================================
# 📂 MÓDULO: CATEGORIAS (CRUD COMPLETO)
# =============================================================================

# 1. CADASTRAR CATEGORIA (funcionários) - OK
@app.route('/categorias', methods=['POST'])
@apenas_funcionario
def criar_categoria():
    data = request.get_json() or {}
    nome_categoria = str(data.get('nome_categoria', '')).strip()

    if not nome_categoria:
        return jsonify({"sucesso": False, "mensagem": "O campo nome_categoria é obrigatório."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO categorias (nome_categoria) VALUES (%s)", (nome_categoria,))
        conn.commit()
        novo_id = cursor.lastrowid
        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "mensagem": "Categoria cadastrada com sucesso!", "id_categoria": novo_id}), 201

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao cadastrar categoria: {str(e)}"}), 400

# 2. LISTAR TODAS AS CATEGORIAS - OK
@app.route('/categorias', methods=['GET'])
def listar_categorias():
    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id_categoria, nome_categoria FROM categorias ORDER BY nome_categoria ASC")
        categorias = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "categorias": categorias}), 200
    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao listar categorias: {str(e)}"}), 500

# 3. CONSULTAR CATEGORIA ESPECÍFICA - OK
@app.route('/categorias/<int:id_categoria>', methods=['GET'])
def consultar_categoria(id_categoria):
    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT id_categoria, nome_categoria FROM categorias WHERE id_categoria = %s", (id_categoria,))
        categoria = cursor.fetchone()
        cursor.close()
        conn.close()

        if not categoria:
            return jsonify({"sucesso": False, "mensagem": "Categoria não encontrada."}), 404

        return jsonify({"sucesso": True, "categoria": categoria}), 200
    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao consultar categoria: {str(e)}"}), 500

# 4. EDITAR NOME DA CATEGORIA (funcionários) - OK
@app.route('/categorias/<int:id_categoria>', methods=['PUT'])
@apenas_funcionario
def editar_categoria(id_categoria):
    data = request.get_json() or {}
    nome_categoria = str(data.get('nome_categoria', '')).strip()

    if not nome_categoria:
        return jsonify({"sucesso": False, "mensagem": "O campo nome_categoria é obrigatório."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor()
        cursor.execute("UPDATE categorias SET nome_categoria = %s WHERE id_categoria = %s", (nome_categoria, id_categoria))
        conn.commit()
        linhas_afetadas = cursor.rowcount
        cursor.close()
        conn.close()

        if linhas_afetadas == 0:
            return jsonify({"sucesso": False, "mensagem": "Categoria não encontrada."}), 404

        return jsonify({"sucesso": True, "mensagem": "Categoria atualizada com sucesso!"}), 200
    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao editar categoria: {str(e)}"}), 500

# 5. EXCLUIR CATEGORIA (funcionários) - OK
@app.route('/categorias/<int:id_categoria>', methods=['DELETE'])
@apenas_funcionario
def excluir_categoria(id_categoria):
    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM categorias WHERE id_categoria = %s", (id_categoria,))
            conn.commit()
            linhas_afetadas = cursor.rowcount
            cursor.close()
            conn.close()

            if linhas_afetadas == 0:
                return jsonify({"sucesso": False, "mensagem": "Categoria não encontrada."}), 404

            return jsonify({"sucesso": True, "mensagem": "Categoria excluída com sucesso."}), 200

        except mysql.connector.Error as err:
            conn.rollback()
            cursor.close()
            conn.close()
            if err.errno == 1451:  # Restrição de Chave Estrangeira (livros vinculados)
                return jsonify({
                    "sucesso": False,
                    "mensagem": "Não é possível excluir: existem livros vinculados a esta categoria."
                }), 400
            return jsonify({"sucesso": False, "mensagem": "Restrição de banco de dados ao tentar excluir."}), 400

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro interno ao tentar excluir: {str(e)}"}), 500

# =============================================================================
# 👥 MÓDULO: LEITORES E LGPD
# =============================================================================

@app.route('/leitores', methods=['POST'])
def cadastrar_leitor():
    data = request.get_json() or {}

    nome = str(data.get('nome', '')).strip()
    email = str(data.get('email', '')).strip()
    telefone = str(data.get('telefone', '')).strip()
    senha = str(data.get('senha', '')).strip()
    consentimento_lgpd = data.get('consentimento_lgpd')

    if not nome or not email or not telefone or not senha:
        return jsonify({"sucesso": False, "mensagem": "Nome, e-mail, telefone e senha são obrigatórios."}), 400
    
    if not bool(consentimento_lgpd):
        return jsonify({
            "sucesso": False, 
            "mensagem": "É necessário aceitar os termos da LGPD para se cadastrar."
        }), 400
    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id_leitor FROM leitores WHERE email = %s", (email,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Este e-mail já está cadastrado."}), 400

        senha_hash = generate_password_hash(senha)

        sql = """
            INSERT INTO leitores (nome, email, telefone, senha, consentimento_lgpd, tipo_perfil, status_conta)
            VALUES (%s, %s, %s, %s, %s, 'LEITOR', 'Ativo')
        """
        cursor.execute(sql, (nome, email, telefone, senha_hash, consentimento_lgpd))
        conn.commit()

        novo_id = cursor.lastrowid
        cursor.close()
        conn.close()

        logger_lgpd.info(f"Auditoria LGPD: Novo leitor cadastrado ID [{novo_id}] com consentimento registrado ({consentimento_lgpd}).")
        
        return jsonify({"sucesso": True, "mensagem": "Cadastro realizado com sucesso!", "id_leitor": novo_id}), 201

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao cadastrar leitor: {str(e)}"}), 500


@app.route('/leitores', methods=['GET'])
@apenas_administrador
def listar_leitores():
    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        sql = "SELECT id_leitor, nome, email, telefone, foto_perfil, status_conta, consentimento_lgpd, data_cadastro FROM leitores"
        cursor.execute(sql)
        leitores = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "leitores": leitores}), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao listar leitores: {str(e)}"}), 500


@app.route('/leitores/<int:id_leitor>', methods=['GET'])
@login_requerido
def consultar_leitor(id_leitor):
    usuario_logado = session.get('usuario')

    if usuario_logado['tipo_perfil'] == 'LEITOR' and usuario_logado['id'] != id_leitor:
        return jsonify({"sucesso": False, "mensagem": "Você só pode consultar seu próprio perfil."}), 403

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        sql = "SELECT id_leitor, nome, email, telefone, foto_perfil, status_conta, consentimento_lgpd, data_cadastro FROM leitores WHERE id_leitor = %s"
        cursor.execute(sql, (id_leitor,))
        leitor = cursor.fetchone()

        cursor.close()
        conn.close()

        if not leitor:
            return jsonify({"sucesso": False, "mensagem": "Leitor não encontrado."}), 404

        return jsonify({"sucesso": True, "leitor": leitor}), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao consultar leitor: {str(e)}"}), 500


@app.route('/leitores/dados', methods=['PUT'])
@login_requerido
def atualizar_dados_leitor():
    usuario_logado = session.get('usuario')
    if usuario_logado['tipo_perfil'] != 'LEITOR':
        return jsonify({"sucesso": False, "mensagem": "Esta rota é exclusiva para leitores."}), 403

    data = request.get_json() or {}
    nome = str(data.get('nome', '')).strip()
    telefone = str(data.get('telefone', '')).strip()

    if not nome or not telefone:
        return jsonify({"sucesso": False, "mensagem": "Nome e telefone são obrigatórios."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor()
        sql = "UPDATE leitores SET nome = %s, telefone = %s WHERE id_leitor = %s"
        cursor.execute(sql, (nome, telefone, usuario_logado['id']))
        conn.commit()

        cursor.close()
        conn.close()

        session['usuario']['nome'] = nome

        return jsonify({"sucesso": True, "mensagem": "Dados pessoais atualizados com sucesso!"}), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao atualizar dados: {str(e)}"}), 500

@app.route('/leitores/senha', methods=['PUT'])
@login_requerido
def atualizar_senha_leitor():
    usuario_logado = session.get('usuario')
    if usuario_logado['tipo_perfil'] != 'LEITOR':
        return jsonify({"sucesso": False, "mensagem": "Esta rota é exclusiva para leitores."}), 403

    data = request.get_json() or {}
    senha_atual = str(data.get('senha_atual', '')).strip()
    nova_senha = str(data.get('nova_senha', '')).strip()

    if not senha_atual or not nova_senha:
        return jsonify({"sucesso": False, "mensagem": "Senha atual e nova senha são obrigatórias."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT senha FROM leitores WHERE id_leitor = %s", (usuario_logado['id'],))
        leitor = cursor.fetchone()

        if not leitor or not check_password_hash(leitor['senha'], senha_atual):
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Senha atual incorreta."}), 400

        nova_senha_hash = generate_password_hash(nova_senha)
        cursor.execute("UPDATE leitores SET senha = %s WHERE id_leitor = %s", (nova_senha_hash, usuario_logado['id']))
        conn.commit()

        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "mensagem": "Senha alterada com sucesso!"}), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao alterar senha: {str(e)}"}), 500


@app.route('/leitores/avatar', methods=['POST'])
@login_requerido
def upload_avatar_leitor():
    usuario_logado = session.get('usuario')
    if usuario_logado['tipo_perfil'] != 'LEITOR':
        return jsonify({"sucesso": False, "mensagem": "Esta rota é exclusiva para leitores."}), 403

    if 'foto' not in request.files:
        return jsonify({"sucesso": False, "mensagem": "Nenhum arquivo enviado."}), 400

    file = request.files['foto']

    if file.filename == '':
        return jsonify({"sucesso": False, "mensagem": "Nenhum arquivo selecionado."}), 400

    if file and arquivo_permitido(file.filename):
        extensao = file.filename.rsplit('.', 1)[1].lower()
        nome_arquivo = f"avatar_leitor_{usuario_logado['id']}_{uuid.uuid4().hex[:8]}.{extensao}"
        caminho_salvar = os.path.join(UPLOAD_FOLDER, nome_arquivo)
        file.save(caminho_salvar)

        url_relativa = f"/uploads/avatars/{nome_arquivo}"

        conn = get_db_connection()
        if not conn:
            return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

        try:
            cursor = conn.cursor()
            cursor.execute("UPDATE leitores SET foto_perfil = %s WHERE id_leitor = %s", (url_relativa, usuario_logado['id']))
            conn.commit()
            cursor.close()
            conn.close()

            return jsonify({"sucesso": True, "mensagem": "Foto de perfil atualizada!", "foto_perfil": url_relativa}), 200

        except Exception as e:
            if conn and conn.is_connected():
                conn.close()
            return jsonify({"sucesso": False, "mensagem": f"Erro ao salvar no banco: {str(e)}"}), 500

    return jsonify({"sucesso": False, "mensagem": "Formato não permitido (use PNG, JPG, JPEG ou WEBP)."}), 400

@app.route('/leitores/exportar-dados', methods=['GET'])
@login_requerido
def exportar_dados_leitor():
    usuario_logado = session.get('usuario')
    if usuario_logado['tipo_perfil'] != 'LEITOR':
        return jsonify({"sucesso": False, "mensagem": "Esta rota é exclusiva para leitores."}), 403

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        # 1. Dados Pessoais
        cursor.execute("""
            SELECT id_leitor, nome, email, telefone, foto_perfil, status_conta, consentimento_lgpd, data_cadastro 
            FROM leitores WHERE id_leitor = %s
        """, (usuario_logado['id'],))
        perfil = cursor.fetchone()

        # 2. Histórico de Empréstimos (Relacionando diretamente e.id_livro = l.id_livro)
        cursor.execute("""
            SELECT e.id_emprestimo, l.titulo AS livro, e.data_emprestimo, e.data_devolucao_prevista, e.data_devolucao_real, e.status_emprestimo
            FROM emprestimos e
            INNER JOIN livro l ON e.id_livro = l.id_livro
            WHERE e.id_leitor = %s
        """, (usuario_logado['id'],))
        emprestimos = cursor.fetchall()

        # 3. Histórico de Reservas
        cursor.execute("""
            SELECT r.id_reserva, l.titulo AS livro, r.data_reserva, r.status_reserva
            FROM reservas r
            INNER JOIN livro l ON r.id_livro = l.id_livro
            WHERE r.id_leitor = %s
        """, (usuario_logado['id'],))
        reservas = cursor.fetchall()

        # 4. Avaliações (Corrigido para livro_id e leitor_id)
        cursor.execute("""
            SELECT a.id_avaliacao, l.titulo AS livro, a.nota, a.comentario, a.data_avaliacao
            FROM avaliacoes a
            INNER JOIN livro l ON a.livro_id = l.id_livro
            WHERE a.leitor_id = %s
        """, (usuario_logado['id'],))
        avaliacoes = cursor.fetchall()

        cursor.close()
        conn.close()

        logger_lgpd.info(f"Auditoria LGPD: O leitor ID [{usuario_logado['id']}] solicitou a exportação completa de seus dados (Art. 18 LGPD).")

        return jsonify({
            "sucesso": True,
            "direitos_lgpd": "Exportação de dados nos termos do Art. 18 da LGPD (Lei nº 13.709/2018)",
            "dados_pessoais": perfil,
            "historico_emprestimos": emprestimos,
            "historico_reservas": reservas,
            "avaliacoes_realizadas": avaliacoes
        }), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao exportar dados: {str(e)}"}), 500

@app.route('/leitores/conta', methods=['DELETE'])
@login_requerido
def deletar_conta_leitor():
    usuario_logado = session.get('usuario')
    if usuario_logado.get('tipo_perfil') != 'LEITOR':
        return jsonify({"sucesso": False, "mensagem": "Esta rota é exclusiva para leitores."}), 403

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True, buffered=True)
        id_leitor = usuario_logado['id']

        # 1. Verifica se existem empréstimos pendentes/ativos
        cursor.execute("""
            SELECT id_emprestimo FROM emprestimos
            WHERE id_leitor = %s AND status_emprestimo = 'Ativo'
        """, (id_leitor,))
        emprestimo_ativo = cursor.fetchone()

        if emprestimo_ativo:
            cursor.close()
            conn.close()
            return jsonify({
                "sucesso": False,
                "mensagem": "Não é possível excluir a conta com empréstimos ativos pendentes de devolução."
            }), 400

        # 2. Anonimização e desativação na tabela LEITORES
        senha_inutilizavel = generate_password_hash(secrets.token_hex(16))
        cursor.execute("""
            UPDATE leitores 
            SET nome = 'Ex-Leitor (Anonimizado)',
                email = CONCAT('ex_leitor_', id_leitor, '@lgpd.deleted'),
                telefone = '00000000000',
                senha = %s,
                foto_perfil = 'default_profile.png',
                consentimento_lgpd = 0,
                status_conta = 'Bloqueado'
            WHERE id_leitor = %s
        """, (senha_inutilizavel, id_leitor))
        
        conn.commit()
        cursor.close()
        conn.close()

        # Encerra a sessão do usuário
        session.clear()

        logger_lgpd.info(f"Auditoria LGPD: O leitor ID [{id_leitor}] executou o direito de exclusão/anonimização de sua conta.")

        return jsonify({
            "sucesso": True,
            "mensagem": "Sua conta foi desativada e seus dados pessoais foram anonimizados com sucesso em conformidade com a LGPD."
        }), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.rollback()
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao processar solicitação: {str(e)}"}), 500

# =============================================================================
# 🔔 MÓDULO: NOTIFICAÇÕES DE INTERESSE
# =============================================================================
# Observação: não há integração real de envio (sem SendGrid/Twilio neste
# projeto) — estas rotas registram o interesse/consentimento e as preferências
# de canal do leitor. O disparo efetivo do aviso fica a cargo de um processo
# futuro que leia notificacoes_interesse com status = 'Pendente'.

# 1. CADASTRAR ALERTA DE INTERESSE EM UM LIVRO (somente leitor) - OK
@app.route('/livros/<int:id_livro>/notificar-interesse', methods=['POST'])
@apenas_leitor
def notificar_interesse(id_livro):
    usuario_logado = session.get('usuario')

    data = request.get_json() or {}
    consentimento_lgpd = bool(data.get('consentimento_lgpd', False))
    receber_email = bool(data.get('receber_email', True))
    receber_whatsapp = bool(data.get('receber_whatsapp', False))
    receber_sms = bool(data.get('receber_sms', False))

    if not consentimento_lgpd:
        return jsonify({
            "sucesso": False,
            "mensagem": "O consentimento explícito (consentimento_lgpd) é obrigatório para cadastrar alertas."
        }), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id_livro FROM livro WHERE id_livro = %s", (id_livro,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Livro não encontrado."}), 404

        sql = """
            INSERT INTO notificacoes_interesse 
                (id_leitor, id_livro, consentimento_lgpd, receber_email, receber_whatsapp, receber_sms, status)
            VALUES (%s, %s, %s, %s, %s, %s, 'Pendente')
            ON DUPLICATE KEY UPDATE
                consentimento_lgpd = VALUES(consentimento_lgpd),
                receber_email = VALUES(receber_email),
                receber_whatsapp = VALUES(receber_whatsapp),
                receber_sms = VALUES(receber_sms),
                status = 'Pendente';
        """
        cursor.execute(sql, (
            usuario_logado['id'], id_livro, consentimento_lgpd,
            receber_email, receber_whatsapp, receber_sms
        ))
        conn.commit()
        cursor.close()
        conn.close()

        logger_lgpd.info(f"Auditoria LGPD: Leitor ID [{usuario_logado['id']}] registrou consentimento de notificação para o Livro ID [{id_livro}].")

        return jsonify({"sucesso": True, "mensagem": "Alerta de interesse cadastrado com sucesso!"}), 201

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao cadastrar alerta: {str(e)}"}), 500


# 2. ATUALIZAR CANAIS DE NOTIFICAÇÃO DE UM ALERTA JÁ EXISTENTE (somente leitor) - OK
@app.route('/leitores/preferencias-notificacao', methods=['PUT'])
@apenas_leitor
def atualizar_preferencias_notificacao():
    usuario_logado = session.get('usuario')

    data = request.get_json() or {}
    id_livro = data.get('id_livro')
    receber_email = data.get('receber_email')
    receber_whatsapp = data.get('receber_whatsapp')
    receber_sms = data.get('receber_sms')

    if not id_livro:
        return jsonify({"sucesso": False, "mensagem": "O campo id_livro é obrigatório."}), 400

    if receber_email is None and receber_whatsapp is None and receber_sms is None:
        return jsonify({"sucesso": False, "mensagem": "Informe ao menos um canal para atualizar."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id_notificacao FROM notificacoes_interesse WHERE id_leitor = %s AND id_livro = %s",
            (usuario_logado['id'], id_livro)
        )
        alerta = cursor.fetchone()

        if not alerta:
            cursor.close()
            conn.close()
            return jsonify({
                "sucesso": False,
                "mensagem": "Nenhum alerta de interesse encontrado para este livro. Cadastre um primeiro em /livros/<id>/notificar-interesse."
            }), 404

        campos = []
        valores = []
        if receber_email is not None:
            campos.append("receber_email = %s")
            valores.append(bool(receber_email))
        if receber_whatsapp is not None:
            campos.append("receber_whatsapp = %s")
            valores.append(bool(receber_whatsapp))
        if receber_sms is not None:
            campos.append("receber_sms = %s")
            valores.append(bool(receber_sms))

        valores.append(alerta['id_notificacao'])
        sql = f"UPDATE notificacoes_interesse SET {', '.join(campos)} WHERE id_notificacao = %s"
        cursor.execute(sql, tuple(valores))
        conn.commit()
        cursor.close()
        conn.close()

        logger_lgpd.info(f"Auditoria LGPD: Leitor ID [{usuario_logado['id']}] atualizou canais de notificação do alerta do Livro ID [{id_livro}].")

        return jsonify({"sucesso": True, "mensagem": "Preferências de notificação atualizadas com sucesso!"}), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao atualizar preferências: {str(e)}"}), 500

# =============================================================================
# 📌 MÓDULO DE RESERVAS
# =============================================================================
# 1. SOLICITAR RESERVA (somente leitor, somente se não há exemplares livres) - OK
@app.route('/reservas', methods=['POST'])
@apenas_leitor
def solicitar_reserva():
    usuario_logado = session.get('usuario')
    id_leitor = usuario_logado['id']

    data = request.get_json() or {}
    id_livro = data.get('id_livro')

    if not id_livro:
        return jsonify({"sucesso": False, "mensagem": "O campo id_livro é obrigatório."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id_livro FROM livro WHERE id_livro = %s", (id_livro,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Livro não encontrado."}), 404

        # Impede reserva duplicada do mesmo leitor para o mesmo livro
        cursor.execute(
            """SELECT id_reserva FROM reservas
               WHERE id_livro = %s AND id_leitor = %s
               AND status_reserva IN ('Pendente', 'Aguardando Retirada')""",
            (id_livro, id_leitor)
        )
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Você já possui uma reserva ativa para este livro."}), 400

        # A trigger 'antes_inserir_reserva' bloqueia o INSERT se ainda houver
        # exemplares disponíveis na estante para este livro.
        cursor.execute(
            "INSERT INTO reservas (id_livro, id_leitor) VALUES (%s, %s)",
            (id_livro, id_leitor)
        )
        conn.commit()
        nova_reserva_id = cursor.lastrowid

        cursor.close()
        conn.close()

        return jsonify({
            "sucesso": True,
            "mensagem": "Reserva solicitada com sucesso!",
            "id_reserva": nova_reserva_id
        }), 201

    except mysql.connector.Error as err:
        if conn and conn.is_connected():
            conn.rollback()
            conn.close()
        # errno 1644 = erro disparado via SIGNAL SQLSTATE '45000' na trigger antes_inserir_reserva
        if err.errno == 1644:
            return jsonify({"sucesso": False, "mensagem": err.msg}), 400
        return jsonify({"sucesso": False, "mensagem": f"Erro ao solicitar reserva: {str(err)}"}), 400
    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro interno: {str(e)}"}), 500


# 2. CONSULTAR MINHAS RESERVAS (leitor logado)
@app.route('/minhas-reservas', methods=['GET'])
@apenas_leitor
def minhas_reservas():
    usuario_logado = session.get('usuario')
    id_leitor = usuario_logado['id']

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT r.id_reserva, r.id_livro, l.titulo, l.autor, l.capa,
                   r.data_reserva, r.status_reserva, r.posicao_fila_notificada
            FROM reservas r
            INNER JOIN livro l ON r.id_livro = l.id_livro
            WHERE r.id_leitor = %s
            ORDER BY r.data_reserva DESC
        """
        cursor.execute(sql, (id_leitor,))
        reservas = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "reservas": reservas}), 200
    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao buscar reservas: {str(e)}"}), 500


# 3. CANCELAR RESERVA (o próprio leitor dono da reserva, ou qualquer funcionário) - OK
@app.route('/reservas/<int:id_reserva>', methods=['DELETE'])
@login_requerido
def cancelar_reserva(id_reserva):
    usuario_logado = session.get('usuario')

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id_leitor, status_reserva FROM reservas WHERE id_reserva = %s",
            (id_reserva,)
        )
        reserva = cursor.fetchone()

        if not reserva:
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Reserva não encontrada."}), 404

        # Leitor só pode cancelar a própria reserva; funcionário pode cancelar qualquer uma
        if usuario_logado['tipo_perfil'] == 'LEITOR' and reserva['id_leitor'] != usuario_logado['id']:
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Você não tem permissão para cancelar esta reserva."}), 403

        if reserva['status_reserva'] in ('Concluida', 'Cancelada'):
            cursor.close()
            conn.close()
            return jsonify({
                "sucesso": False,
                "mensagem": f"Não é possível cancelar uma reserva com status '{reserva['status_reserva']}'."
            }), 400

        cursor.execute(
            "UPDATE reservas SET status_reserva = 'Cancelada' WHERE id_reserva = %s",
            (id_reserva,)
        )
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "mensagem": "Reserva cancelada com sucesso."}), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao cancelar reserva: {str(e)}"}), 500


# 4. PAINEL GERAL DE RESERVAS (funcionários)
@app.route('/reservas', methods=['GET'])
@apenas_funcionario
def listar_reservas():
    status_filtro = request.args.get('status')

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        sql = """
            SELECT r.id_reserva, r.id_livro, l.titulo, l.autor,
                   r.id_leitor, lt.nome AS nome_leitor, lt.email AS email_leitor,
                   r.data_reserva, r.status_reserva, r.posicao_fila_notificada
            FROM reservas r
            INNER JOIN livro l ON r.id_livro = l.id_livro
            INNER JOIN leitores lt ON r.id_leitor = lt.id_leitor
        """
        params = ()
        if status_filtro:
            if status_filtro not in STATUS_RESERVA_VALIDOS:
                cursor.close()
                conn.close()
                return jsonify({
                    "sucesso": False,
                    "mensagem": f"Status inválido. Use um dos seguintes: {', '.join(STATUS_RESERVA_VALIDOS)}."
                }), 400
            sql += " WHERE r.status_reserva = %s"
            params = (status_filtro,)
        sql += " ORDER BY r.data_reserva DESC"

        cursor.execute(sql, params)
        reservas = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "reservas": reservas}), 200
    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao buscar reservas: {str(e)}"}), 500

# 5. ATUALIZAR STATUS DA RESERVA (funcionários) - ok
@app.route('/reservas/<int:id_reserva>/status', methods=['PUT'])
@apenas_funcionario
def atualizar_status_reserva(id_reserva):
    data = request.get_json() or {}
    novo_status = str(data.get('status_reserva', '')).strip()

    if novo_status not in STATUS_RESERVA_VALIDOS:
        return jsonify({
            "sucesso": False,
            "mensagem": f"Status inválido. Use um dos seguintes: {', '.join(STATUS_RESERVA_VALIDOS)}."
        }), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id_reserva, id_livro, id_leitor, status_reserva FROM reservas WHERE id_reserva = %s",
            (id_reserva,)
        )
        reserva = cursor.fetchone()

        if not reserva:
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Reserva não encontrada."}), 404

        id_livro = reserva['id_livro']
        id_leitor = reserva['id_leitor']
        id_funcionario = session.get('usuario', {}).get('id')

        # 1. Atualiza o status da reserva
        cursor.execute(
            "UPDATE reservas SET status_reserva = %s WHERE id_reserva = %s",
            (novo_status, id_reserva)
        )
        id_funcionario = session.get('usuario', {}).get('id')

        # 2. Tratamento das regras de negócio conforme o status
        if novo_status == "Concluida":
            # Atualiza exemplar para Emprestado
            cursor.execute(
                "UPDATE livro SET status_exemplar = 'Emprestado' WHERE id_livro = %s",
                (id_livro,)
            )
            
            # Gera o registro do empréstimo (Prazo padrão: 14 dias)
            sql_emprestimo = """
                INSERT INTO emprestimos (id_livro, id_leitor, id_funcionario, data_devolucao_prevista, status_emprestimo)
                VALUES (%s, %s, %s, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo')
            """
            cursor.execute(sql_emprestimo, (id_livro, id_leitor, id_funcionario))

        elif novo_status == "Aguardando Retirada":
            cursor.execute(
                "UPDATE livro SET status_exemplar = 'Reservado' WHERE id_livro = %s",
                (id_livro,)
            )

        elif novo_status == "Cancelada":
            cursor.execute(
                "SELECT COUNT(*) AS total FROM reservas WHERE id_livro = %s AND status_reserva IN ('Pendente', 'Aguardando Retirada')",
                (id_livro,)
            )
            qtd_reservas_ativas = cursor.fetchone()['total']

            if qtd_reservas_ativas == 0:
                cursor.execute(
                    "UPDATE livro SET status_exemplar = 'Disponível' WHERE id_livro = %s",
                    (id_livro,)
                )

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "mensagem": "Status da reserva atualizado com sucesso."}), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.rollback()
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao atualizar status: {str(e)}"}), 500

# =============================================================================
# 📋 MÓDULO: EMPRÉSTIMOS E DEVOLUÇÕES
# =============================================================================
STATUS_EMPRESTIMO_VALIDOS = ('Ativo', 'Devolvido', 'Atrasado')
VALOR_MULTA_POR_DIA = 1.00   # R$ por dia de atraso (não persistido no banco — calculado sob demanda)
DIAS_EMPRESTIMO = 14
DIAS_RENOVACAO = 7
MAX_RENOVACOES = 2

def _atualizar_emprestimos_atrasados(cursor):
    """Promove para 'Atrasado' qualquer empréstimo Ativo cujo prazo já venceu."""
    cursor.execute(
        "UPDATE emprestimos SET status_emprestimo = 'Atrasado' "
        "WHERE status_emprestimo = 'Ativo' AND data_devolucao_prevista < CURDATE()"
    )

def _calcular_multa(data_devolucao_prevista, data_devolucao_real):
    """Calcula multa por atraso sob demanda (não há coluna de multa no banco)."""
    if not data_devolucao_prevista:
        return {"dias_atraso": 0, "valor_multa": 0.0}

    if data_devolucao_real:
        referencia = data_devolucao_real.date() if isinstance(data_devolucao_real, datetime.datetime) else data_devolucao_real
    else:
        referencia = datetime.date.today()

    dias_atraso = max((referencia - data_devolucao_prevista).days, 0)
    return {"dias_atraso": dias_atraso, "valor_multa": round(dias_atraso * VALOR_MULTA_POR_DIA, 2)}

# 1. LISTAR TODOS OS EMPRÉSTIMOS REGISTRADOS (funcionários) - OK
@app.route('/emprestimos', methods=['GET'])
@apenas_funcionario
def listar_emprestimos():
    status_filtro = request.args.get('status')
    if status_filtro and status_filtro not in STATUS_EMPRESTIMO_VALIDOS:
        return jsonify({
            "sucesso": False,
            "mensagem": f"Status inválido. Use um dos seguintes: {', '.join(STATUS_EMPRESTIMO_VALIDOS)}."
        }), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        _atualizar_emprestimos_atrasados(cursor)
        conn.commit()

        sql = """
            SELECT e.id_emprestimo, e.id_livro, l.titulo, l.autor,
                   e.id_leitor, lt.nome AS nome_leitor, lt.email AS email_leitor,
                   e.id_funcionario, f.nome AS nome_funcionario,
                   e.data_emprestimo, e.data_devolucao_prevista, e.data_devolucao_real,
                   e.renovacoes_realizadas, e.status_emprestimo
            FROM emprestimos e
            INNER JOIN livro l ON e.id_livro = l.id_livro
            INNER JOIN leitores lt ON e.id_leitor = lt.id_leitor
            INNER JOIN funcionarios f ON e.id_funcionario = f.id_funcionario
        """
        params = ()
        if status_filtro:
            sql += " WHERE e.status_emprestimo = %s"
            params = (status_filtro,)
        sql += " ORDER BY e.data_emprestimo DESC"

        cursor.execute(sql, params)
        emprestimos = cursor.fetchall()

        for emp in emprestimos:
            emp['multa'] = _calcular_multa(emp['data_devolucao_prevista'], emp['data_devolucao_real'])

        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "emprestimos": emprestimos}), 200
    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao buscar empréstimos: {str(e)}"}), 500

# 2. REGISTRAR RETIRADA FÍSICA NO BALCÃO (funcionários) - OK
@app.route('/emprestimos', methods=['POST'])
@apenas_funcionario
def registrar_emprestimo_balcao():
    data = request.get_json() or {}
    id_livro = data.get('id_livro')
    id_leitor = data.get('id_leitor')
    id_funcionario = session.get('usuario', {}).get('id')

    if not id_livro or not id_leitor:
        return jsonify({"sucesso": False, "mensagem": "Os campos id_livro e id_leitor são obrigatórios."}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT status_conta FROM leitores WHERE id_leitor = %s", (id_leitor,))
        leitor = cursor.fetchone()
        if not leitor:
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Leitor não encontrado."}), 404
        if leitor['status_conta'] != 'Ativo':
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": f"Leitor com conta '{leitor['status_conta']}' não pode retirar livros."}), 403

        cursor.execute("SELECT quant_estoque, status_livro FROM livro WHERE id_livro = %s", (id_livro,))
        livro = cursor.fetchone()
        if not livro:
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Livro não encontrado."}), 404
        if livro['status_livro'] != 'Ativo':
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Este livro está indisponível para empréstimo."}), 400

        cursor.execute(
            "SELECT COUNT(*) AS total FROM emprestimos WHERE id_livro = %s AND data_devolucao_real IS NULL",
            (id_livro,)
        )
        if cursor.fetchone()['total'] >= livro['quant_estoque']:
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Não há exemplares disponíveis para empréstimo no momento."}), 400

        _atualizar_emprestimos_atrasados(cursor)
        conn.commit()
        cursor.execute(
            "SELECT COUNT(*) AS total FROM emprestimos WHERE id_leitor = %s AND status_emprestimo = 'Atrasado'",
            (id_leitor,)
        )
        if cursor.fetchone()['total'] > 0:
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Leitor possui empréstimo em atraso. Regularize a devolução antes de retirar outro livro."}), 400

        try:
            cursor.execute(
                """INSERT INTO emprestimos (id_livro, id_leitor, id_funcionario, data_devolucao_prevista)
                   VALUES (%s, %s, %s, DATE_ADD(CURRENT_DATE(), INTERVAL %s DAY))""",
                (id_livro, id_leitor, id_funcionario, DIAS_EMPRESTIMO)
            )
        except mysql.connector.Error as err:
            conn.rollback()
            cursor.close()
            conn.close()
            # errno 1644 = SIGNAL SQLSTATE '45000' da trigger antes_inserir_emprestimo (limite de 3 livros ativos)
            if err.errno == 1644:
                return jsonify({"sucesso": False, "mensagem": err.msg}), 400
            return jsonify({"sucesso": False, "mensagem": f"Erro ao registrar empréstimo: {str(err)}"}), 400

        novo_id = cursor.lastrowid
        novo_status_exemplar = _recalcular_status_exemplar(cursor, id_livro)
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({
            "sucesso": True,
            "mensagem": "Empréstimo registrado com sucesso!",
            "id_emprestimo": novo_id,
            "status_exemplar": novo_status_exemplar
        }), 201

    except Exception as e:
        if conn and conn.is_connected():
            conn.rollback()
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro interno ao registrar empréstimo: {str(e)}"}), 500

# 3. REGISTRAR DEVOLUÇÃO DO EXEMPLAR (funcionários) - OK
@app.route('/emprestimos/<int:id_emprestimo>/devolver', methods=['PUT'])
@apenas_funcionario
def devolver_emprestimo(id_emprestimo):
    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id_livro, id_leitor, data_devolucao_prevista, data_devolucao_real FROM emprestimos WHERE id_emprestimo = %s",
            (id_emprestimo,)
        )
        emprestimo = cursor.fetchone()

        if not emprestimo:
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Empréstimo não encontrado."}), 404

        if emprestimo['data_devolucao_real'] is not None:
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Este empréstimo já foi devolvido."}), 400

        cursor.execute(
            "UPDATE emprestimos SET data_devolucao_real = NOW(), status_emprestimo = 'Devolvido' WHERE id_emprestimo = %s",
            (id_emprestimo,)
        )

        multa = _calcular_multa(emprestimo['data_devolucao_prevista'], datetime.datetime.now())

        id_livro = emprestimo['id_livro']

        # Promove a próxima reserva pendente da fila, se houver
        cursor.execute(
            "SELECT id_reserva FROM reservas WHERE id_livro = %s AND status_reserva = 'Pendente' ORDER BY data_reserva ASC LIMIT 1",
            (id_livro,)
        )
        proxima_reserva = cursor.fetchone()
        if proxima_reserva:
            cursor.execute(
                "UPDATE reservas SET status_reserva = 'Aguardando Retirada' WHERE id_reserva = %s",
                (proxima_reserva['id_reserva'],)
            )

        novo_status_exemplar = _recalcular_status_exemplar(cursor, id_livro)
        conn.commit()
        cursor.close()
        conn.close()

        mensagem = "Devolução registrada com sucesso."
        if proxima_reserva:
            mensagem += " Há uma reserva na fila que passou a aguardar retirada."

        return jsonify({
            "sucesso": True,
            "mensagem": mensagem,
            "status_exemplar": novo_status_exemplar,
            "multa": multa
        }), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.rollback()
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao registrar devolução: {str(e)}"}), 500

# 4. INCREMENTAR RENOVAÇÕES E ESTENDER PRAZO (leitor dono do empréstimo ou funcionário) - OK
@app.route('/emprestimos/<int:id_emprestimo>/renovar', methods=['PUT'])
@login_requerido
def renovar_emprestimo(id_emprestimo):
    usuario_logado = session.get('usuario')

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute(
            "SELECT id_livro, id_leitor, data_devolucao_real, renovacoes_realizadas FROM emprestimos WHERE id_emprestimo = %s",
            (id_emprestimo,)
        )
        emprestimo = cursor.fetchone()

        if not emprestimo:
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Empréstimo não encontrado."}), 404

        if usuario_logado['tipo_perfil'] == 'LEITOR' and emprestimo['id_leitor'] != usuario_logado['id']:
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Você só pode renovar seus próprios empréstimos."}), 403

        if emprestimo['data_devolucao_real'] is not None:
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Este empréstimo já foi devolvido."}), 400

        _atualizar_emprestimos_atrasados(cursor)
        conn.commit()
        cursor.execute("SELECT status_emprestimo FROM emprestimos WHERE id_emprestimo = %s", (id_emprestimo,))
        if cursor.fetchone()['status_emprestimo'] == 'Atrasado':
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Não é possível renovar um empréstimo em atraso. Regularize a devolução primeiro."}), 400

        if emprestimo['renovacoes_realizadas'] >= MAX_RENOVACOES:
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": f"Limite de {MAX_RENOVACOES} renovações já atingido para este empréstimo."}), 400

        cursor.execute(
            "SELECT COUNT(*) AS total FROM reservas WHERE id_livro = %s AND status_reserva IN ('Pendente', 'Aguardando Retirada')",
            (emprestimo['id_livro'],)
        )
        if cursor.fetchone()['total'] > 0:
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Não é possível renovar: há leitores na fila de espera por este livro."}), 400

        cursor.execute(
            """UPDATE emprestimos
               SET data_devolucao_prevista = DATE_ADD(data_devolucao_prevista, INTERVAL %s DAY),
                   renovacoes_realizadas = renovacoes_realizadas + 1
               WHERE id_emprestimo = %s""",
            (DIAS_RENOVACAO, id_emprestimo)
        )
        conn.commit()

        cursor.execute(
            "SELECT data_devolucao_prevista, renovacoes_realizadas FROM emprestimos WHERE id_emprestimo = %s",
            (id_emprestimo,)
        )
        atualizado = cursor.fetchone()
        cursor.close()
        conn.close()

        return jsonify({
            "sucesso": True,
            "mensagem": "Empréstimo renovado com sucesso!",
            "nova_data_devolucao_prevista": str(atualizado['data_devolucao_prevista']),
            "renovacoes_realizadas": atualizado['renovacoes_realizadas']
        }), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.rollback()
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao renovar empréstimo: {str(e)}"}), 500

# 5. HISTÓRICO DE EMPRÉSTIMOS DO LEITOR LOGADO - OK
@app.route('/meus-emprestimos', methods=['GET'])
@apenas_leitor
def meus_emprestimos():
    usuario_logado = session.get('usuario')

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        _atualizar_emprestimos_atrasados(cursor)
        conn.commit()

        cursor.execute("""
            SELECT e.id_emprestimo, e.id_livro, l.titulo, l.autor, l.capa,
                   e.data_emprestimo, e.data_devolucao_prevista, e.data_devolucao_real,
                   e.renovacoes_realizadas, e.status_emprestimo
            FROM emprestimos e
            INNER JOIN livro l ON e.id_livro = l.id_livro
            WHERE e.id_leitor = %s
            ORDER BY e.data_emprestimo DESC
        """, (usuario_logado['id'],))
        emprestimos = cursor.fetchall()

        for emp in emprestimos:
            emp['multa'] = _calcular_multa(emp['data_devolucao_prevista'], emp['data_devolucao_real'])

        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "emprestimos": emprestimos}), 200
    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao buscar empréstimos: {str(e)}"}), 500

# 6. ATENDIMENTOS REGISTRADOS PELO FUNCIONÁRIO LOGADO - OK
@app.route('/funcionarios/meus-atendimentos', methods=['GET'])
@apenas_funcionario
def meus_atendimentos():
    usuario_logado = session.get('usuario')

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT e.id_emprestimo, e.id_livro, l.titulo, e.id_leitor, lt.nome AS nome_leitor,
                   e.data_emprestimo, e.data_devolucao_prevista, e.data_devolucao_real, e.status_emprestimo
            FROM emprestimos e
            INNER JOIN livro l ON e.id_livro = l.id_livro
            INNER JOIN leitores lt ON e.id_leitor = lt.id_leitor
            WHERE e.id_funcionario = %s
            ORDER BY e.data_emprestimo DESC
        """, (usuario_logado['id'],))
        atendimentos = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "atendimentos": atendimentos}), 200
    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao buscar atendimentos: {str(e)}"}), 500

# =============================================================================
# ⭐ MÓDULO: AVALIAÇÕES E RESENHAS (CRUD COMPLETO)
# =============================================================================

# 1. ENVIAR NOTA (1 A 5) E COMENTÁRIO (somente leitor que já pegou o livro emprestado) - OK
@app.route('/livros/<int:id_livro>/avaliacoes', methods=['POST'])
@apenas_leitor
def criar_avaliacao(id_livro):
    usuario_logado = session.get('usuario')
    data = request.get_json() or {}

    try:
        nota = int(data.get('nota'))
        if nota < 1 or nota > 5:
            raise ValueError
    except (TypeError, ValueError):
        return jsonify({"sucesso": False, "mensagem": "O campo nota é obrigatório e deve ser um número entre 1 e 5."}), 400

    comentario = data.get('comentario')

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id_livro FROM livro WHERE id_livro = %s", (id_livro,))
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Livro não encontrado."}), 404

        cursor.execute(
            "SELECT id_emprestimo FROM emprestimos WHERE id_livro = %s AND id_leitor = %s LIMIT 1",
            (id_livro, usuario_logado['id'])
        )
        if not cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Você só pode avaliar livros que já retirou emprestados."}), 403

        cursor.execute(
            "SELECT id_avaliacao FROM avaliacoes WHERE livro_id = %s AND leitor_id = %s",
            (id_livro, usuario_logado['id'])
        )
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Você já avaliou este livro. Use PUT /avaliacoes/<id> para editar sua avaliação."}), 400

        cursor.execute(
            "INSERT INTO avaliacoes (livro_id, leitor_id, nota, comentario) VALUES (%s, %s, %s, %s)",
            (id_livro, usuario_logado['id'], nota, comentario)
        )
        conn.commit()
        novo_id = cursor.lastrowid
        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "mensagem": "Avaliação registrada com sucesso!", "id_avaliacao": novo_id}), 201

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao registrar avaliação: {str(e)}"}), 400

# 2. LISTAR RESENHAS DE UM LIVRO - OK
@app.route('/livros/<int:id_livro>/avaliacoes', methods=['GET'])
def listar_avaliacoes_livro(id_livro):
    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT a.id_avaliacao, a.leitor_id, lt.nome AS nome_leitor, a.nota, a.comentario, a.data_avaliacao
            FROM avaliacoes a
            INNER JOIN leitores lt ON a.leitor_id = lt.id_leitor
            WHERE a.livro_id = %s
            ORDER BY a.data_avaliacao DESC
        """, (id_livro,))
        avaliacoes = cursor.fetchall()
        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "avaliacoes": avaliacoes}), 200
    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao buscar avaliações: {str(e)}"}), 500

# 3. CONSULTAR UMA AVALIAÇÃO ESPECÍFICA - OK
@app.route('/avaliacoes/<int:id_avaliacao>', methods=['GET'])
def consultar_avaliacao(id_avaliacao):
    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT a.id_avaliacao, a.livro_id, l.titulo, a.leitor_id, lt.nome AS nome_leitor,
                   a.nota, a.comentario, a.data_avaliacao
            FROM avaliacoes a
            INNER JOIN livro l ON a.livro_id = l.id_livro
            INNER JOIN leitores lt ON a.leitor_id = lt.id_leitor
            WHERE a.id_avaliacao = %s
        """, (id_avaliacao,))
        avaliacao = cursor.fetchone()
        cursor.close()
        conn.close()

        if not avaliacao:
            return jsonify({"sucesso": False, "mensagem": "Avaliação não encontrada."}), 404

        return jsonify({"sucesso": True, "avaliacao": avaliacao}), 200
    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao consultar avaliação: {str(e)}"}), 500

# 4. EDITAR AVALIAÇÃO FEITA PELO LEITOR (somente o próprio autor) - OK
@app.route('/avaliacoes/<int:id_avaliacao>', methods=['PUT'])
@apenas_leitor
def editar_avaliacao(id_avaliacao):
    usuario_logado = session.get('usuario')
    data = request.get_json() or {}

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT leitor_id FROM avaliacoes WHERE id_avaliacao = %s", (id_avaliacao,))
        avaliacao = cursor.fetchone()

        if not avaliacao:
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Avaliação não encontrada."}), 404

        if avaliacao['leitor_id'] != usuario_logado['id']:
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Você só pode editar sua própria avaliação."}), 403

        campos = []
        valores = []

        if 'nota' in data:
            try:
                nota = int(data.get('nota'))
                if nota < 1 or nota > 5:
                    raise ValueError
            except (TypeError, ValueError):
                cursor.close()
                conn.close()
                return jsonify({"sucesso": False, "mensagem": "nota deve ser um número entre 1 e 5."}), 400
            campos.append("nota = %s")
            valores.append(nota)

        if 'comentario' in data:
            campos.append("comentario = %s")
            valores.append(data.get('comentario'))

        if not campos:
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Informe ao menos nota ou comentario para atualizar."}), 400

        valores.append(id_avaliacao)
        cursor.execute(f"UPDATE avaliacoes SET {', '.join(campos)} WHERE id_avaliacao = %s", tuple(valores))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "mensagem": "Avaliação atualizada com sucesso!"}), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao editar avaliação: {str(e)}"}), 500

# 5. REMOVER AVALIAÇÃO (autor da avaliação ou funcionário para moderação) - OK
@app.route('/avaliacoes/<int:id_avaliacao>', methods=['DELETE'])
@login_requerido
def excluir_avaliacao(id_avaliacao):
    usuario_logado = session.get('usuario')

    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT leitor_id FROM avaliacoes WHERE id_avaliacao = %s", (id_avaliacao,))
        avaliacao = cursor.fetchone()

        if not avaliacao:
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Avaliação não encontrada."}), 404

        if usuario_logado['tipo_perfil'] == 'LEITOR' and avaliacao['leitor_id'] != usuario_logado['id']:
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Você só pode excluir sua própria avaliação."}), 403

        cursor.execute("DELETE FROM avaliacoes WHERE id_avaliacao = %s", (id_avaliacao,))
        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "mensagem": "Avaliação removida com sucesso."}), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao excluir avaliação: {str(e)}"}), 500

# =============================================================================
# 📊 MÓDULO: RELATÓRIOS E ADMINISTRATIVO
# =============================================================================

# 1. MÉTRICAS CONSOLIDADAS DO SISTEMA (funcionários) - OK
@app.route('/relatorios/dashboard', methods=['GET'])
@apenas_funcionario
def dashboard_metrics():
    conn = get_db_connection()
    if not conn:
        return jsonify({"sucesso": False, "mensagem": "Erro de conexão com o banco de dados."}), 500

    try:
        cursor = conn.cursor(dictionary=True)
        _atualizar_emprestimos_atrasados(cursor)
        conn.commit()

        cursor.execute("SELECT COUNT(*) AS total FROM livro WHERE status_livro = 'Ativo'")
        total_livros_ativos = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) AS total FROM leitores WHERE status_conta = 'Ativo'")
        total_leitores_ativos = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) AS total FROM funcionarios WHERE status_funcionario = 'Ativo'")
        total_funcionarios_ativos = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) AS total FROM emprestimos WHERE status_emprestimo = 'Ativo'")
        emprestimos_ativos = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) AS total FROM emprestimos WHERE status_emprestimo = 'Atrasado'")
        emprestimos_atrasados = cursor.fetchone()['total']

        cursor.execute("SELECT COUNT(*) AS total FROM reservas WHERE status_reserva IN ('Pendente', 'Aguardando Retirada')")
        reservas_ativas = cursor.fetchone()['total']

        cursor.execute("""
            SELECT l.id_livro, l.titulo, COUNT(e.id_emprestimo) AS total_emprestimos
            FROM emprestimos e
            INNER JOIN livro l ON e.id_livro = l.id_livro
            GROUP BY l.id_livro
            ORDER BY total_emprestimos DESC
            LIMIT 5
        """)
        livros_mais_emprestados = cursor.fetchall()

        cursor.execute("""
            SELECT l.id_livro, l.titulo, ROUND(AVG(a.nota), 1) AS media_avaliacoes, COUNT(a.id_avaliacao) AS total_avaliacoes
            FROM avaliacoes a
            INNER JOIN livro l ON a.livro_id = l.id_livro
            GROUP BY l.id_livro
            HAVING total_avaliacoes > 0
            ORDER BY media_avaliacoes DESC
            LIMIT 5
        """)
        livros_mais_bem_avaliados = cursor.fetchall()

        cursor.close()
        conn.close()

        return jsonify({
            "sucesso": True,
            "dashboard": {
                "total_livros_ativos": total_livros_ativos,
                "total_leitores_ativos": total_leitores_ativos,
                "total_funcionarios_ativos": total_funcionarios_ativos,
                "emprestimos_ativos": emprestimos_ativos,
                "emprestimos_atrasados": emprestimos_atrasados,
                "reservas_ativas": reservas_ativas,
                "livros_mais_emprestados": livros_mais_emprestados,
                "livros_mais_bem_avaliados": livros_mais_bem_avaliados
            }
        }), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao gerar dashboard: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(debug=True, port=5000)
