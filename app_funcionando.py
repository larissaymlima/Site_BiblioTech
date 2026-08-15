import os
import uuid
import random
import datetime
from datetime import timedelta
from functools import wraps
from flask import Flask, request, jsonify, session
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail

load_dotenv()

app = Flask(__name__)

# Configurações de Segurança e Sessão
app.secret_key = os.getenv('SECRET_KEY', 'chave_secreta_padrao_para_testes')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)

# Configurações do SendGrid
SENDGRID_API_KEY = os.getenv('SENDGRID_API_KEY')
SENDGRID_SENDER_EMAIL = os.getenv('SENDGRID_SENDER_EMAIL')

# Configuração da pasta de upload
UPLOAD_FOLDER = os.path.join(os.getcwd(), 'uploads', 'avatars')
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'webp'}
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
# 📧 FUNÇÕES AUXILIARES E DE E-MAIL
# =============================================================================

def arquivo_permitido(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def enviar_email_codigo(email_destino, codigo):
    if not SENDGRID_API_KEY or not SENDGRID_SENDER_EMAIL:
        print("⚠️ [AVISO] Chaves do SendGrid não configuradas no .env.")
        return False

    conteudo_html = f"""
    <div style="font-family: Arial, sans-serif; color: #333; max-width: 600px; margin: 0 auto; padding: 20px; border: 1px solid #e0e0e0; border-radius: 8px;">
        <h2 style="color: #2c3e50;">Código de Recuperação — BiblioTech</h2>
        <p>Olá,</p>
        <p>Seu código de verificação para redefinir a senha é:</p>
        <div style="text-align: center; margin: 25px 0;">
            <span style="background-color: #f4f4f4; padding: 12px 24px; font-size: 28px; font-weight: bold; letter-spacing: 6px; border-radius: 5px; border: 1px dashed #cccccc; color: #007bff;">
                {codigo}
            </span>
        </div>
        <p>Este código expira em 15 minutos.</p>
    </div>
    """

    mensagem = Mail(
        from_email=SENDGRID_SENDER_EMAIL,
        to_emails=email_destino,
        subject='Seu Código de Recuperação — BiblioTech',
        html_content=conteudo_html
    )

    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(mensagem)
        return response.status_code == 202
    except Exception as e:
        print(f"❌ Erro ao enviar e-mail via SendGrid: {str(e)}")
        return False

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

# 2. ENCERRAR SESSÃO (LOGOUT)
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

# 4. RECUPERAÇÃO DE SENHA — SOLICITAR CÓDIGO - preciso do twilo pra testar 
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
            return jsonify({"sucesso": True, "mensagem": "Se o e-mail estiver cadastrado, um código de verificação será enviado."}), 200

        codigo = str(random.randint(1000, 9999))
        expiracao = datetime.datetime.now() + timedelta(minutes=15)
        
        codigos_recuperacao[email] = {
            "codigo": codigo,
            "expiracao": expiracao
        }

        enviar_email_codigo(email, codigo)

        return jsonify({"sucesso": True, "mensagem": "Se o e-mail estiver cadastrado, um código de verificação será enviado."}), 200

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
# 1. LISTAR TODOS OS FUNCIONÁRIOS
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

# 2. CADASTRAR FUNCIONÁRIO
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

# 3. EDITAR FUNCIONÁRIO (EXCLUSIVO PARA ADMINISTRADOR)
@app.route('/funcionarios/<int:id_funcionario>', methods=['PUT'])
@apenas_administrador
def editar_funcionario(id_funcionario):
    data = request.get_json() or {}

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

        return jsonify({"sucesso": True, "mensagem": "Dados do funcionário atualizados com sucesso!"}), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao atualizar dados: {str(e)}"}), 400

# 4. EXCLUIR / INATIVAR FUNCIONÁRIO
@app.route('/funcionarios/<int:id_funcionario>', methods=['DELETE'])
@apenas_administrador
def excluir_funcionario(id_funcionario):
    usuario_logado = session.get('usuario', {})

    # Impede que o usuário delete a si mesmo via ID salvo na sessão
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

            return jsonify({"sucesso": True, "mensagem": "Funcionário excluído com sucesso."}), 200

        except mysql.connector.Error as err:
            conn.rollback()
            # Tratamento para erro de chave estrangeira (1451): inativa o perfil em vez de apagar
            if err.errno == 1451:
                cursor.execute("UPDATE funcionarios SET status_funcionario = 'Inativo' WHERE id_funcionario = %s", (id_funcionario,))
                conn.commit()
                cursor.close()
                conn.close()

                return jsonify({"sucesso": True, "mensagem": "O funcionário possui registros vinculados no sistema. Seu status foi alterado para 'Inativo'."}), 200

            cursor.close()
            conn.close()
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
    consentimento_lgpd = bool(data.get('consentimento_lgpd', True))

    if not nome or not email or not telefone or not senha:
        return jsonify({"sucesso": False, "mensagem": "Nome, e-mail, telefone e senha são obrigatórios."}), 400

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
    if usuario_logado['tipo_perfil'] != 'LEITOR':
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

        # 2. Anonimização com valores reduzidos para evitar truncamento
        cursor.execute("""
            UPDATE leitores
            SET nome = 'Usuário Anônimo',
                email = CONCAT('anonimo_', id_leitor, '@lgpd.deleted'),
                telefone = '',
                foto_perfil = NULL,
                senha = '',
                status_conta = 'Inativo',
                consentimento_lgpd = 0
            WHERE id_leitor = %s
        """, (id_leitor,))

        conn.commit()

        cursor.close()
        conn.close()

        # Encerra a sessão do usuário
        session.clear()

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
            "SELECT id_reserva, id_livro, status_reserva FROM reservas WHERE id_reserva = %s",
            (id_reserva,)
        )
        reserva = cursor.fetchone()

        if not reserva:
            cursor.close()
            conn.close()
            return jsonify({"sucesso": False, "mensagem": "Reserva não encontrada."}), 404

        cursor.execute(
            "UPDATE reservas SET status_reserva = %s WHERE id_reserva = %s",
            (novo_status, id_reserva)
        )

        # Atualiza a coluna 'status_livro' na tabela 'livro'
        if novo_status == 'Aguardando Retirada' and reserva['status_reserva'] != 'Aguardando Retirada':
            cursor.execute(
                """UPDATE livro SET status_livro = 'Reservado'
                   WHERE id_livro = %s AND status_livro = 'Disponível'""",
                (reserva['id_livro'],)
            )

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"sucesso": True, "mensagem": "Status da reserva atualizado com sucesso."}), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        return jsonify({"sucesso": False, "mensagem": f"Erro ao atualizar status: {str(e)}"}), 500
    
if __name__ == '__main__':
    app.run(debug=True, port=5000)
