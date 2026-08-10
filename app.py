# --- BIBLIOTECAS ---
import os
import secrets
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect, url_for, flash, session, send_from_directory, jsonify
import mysql.connector
from mysql.connector import Error
from werkzeug.security import generate_password_hash, check_password_hash
from twilio.rest import Client
from datetime import timedelta
from flask_wtf.csrf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Carrega variáveis de ambiente
load_dotenv()

app = Flask(__name__)
# Configurações de segurança para cookies de sessão
app.config['SESSION_COOKIE_SECURE'] = True if os.getenv('FLASK_ENV') == 'production' or os.getenv('USE_HTTPS') == 'true' else False
app.config['SESSION_COOKIE_HTTPONLY'] = True  # Impede acesso ao cookie via JavaScript (proteção contra XSS)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax' # Proteção contra ataques CSRF básicos
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)  # Expira sessões inativas

secret_key = os.getenv('SECRET_KEY')
if not secret_key:
    raise ValueError("❌ ERRO DE SEGURANÇA: A variável 'SECRET_KEY' não está definida no arquivo .env!")
app.secret_key = secret_key

# --- PROTEÇÃO CSRF ---
# Protege todas as rotas POST contra Cross-Site Request Forgery.
# IMPORTANTE: cada <form method="POST"> nos templates precisa incluir
# {{ csrf_token() }} dentro de um <input type="hidden" name="csrf_token" value="{{ csrf_token() }}">
csrf = CSRFProtect(app)

# --- RATE LIMITING ---
# Limita tentativas de login/cadastro para dificultar força bruta e credential stuffing.
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://"  # Para produção com múltiplos processos, use Redis: redis://localhost:6379
)

# --- CONFIGURAÇÃO DAS PASTAS ---
ASSETS_FOLDER = os.path.join(app.root_path, 'assets')
CSS_FOLDER = os.path.join(app.root_path, 'css')

def get_db_connection():
    """Abre conexão com o banco MySQL 'bliblitech'."""
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

# --- ARQUIVOS ESTÁTICOS ---
@app.route('/assets/<path:filename>')
def serve_assets(filename):
    return send_from_directory(ASSETS_FOLDER, filename)

@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory(CSS_FOLDER, filename)

# -----------------------------------------------------------------------------
# NOTIFICAÇÕES DE DISPONIBILIDADE (Twilio + E-mail)
# -----------------------------------------------------------------------------
def disparar_notificacoes_disponibilidade(id_livro):
    """
    Busca leitores que solicitaram notificação para o livro e realiza 
    o envio via Twilio (SMS/WhatsApp) e E-mail conforme as preferências cadastradas.
    """
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor(dictionary=True)

        # 1. Busca os dados do livro e as solicitações pendentes
        sql_livro = "SELECT titulo FROM livro WHERE id_livro = %s"
        cursor.execute(sql_livro, (id_livro,))
        livro = cursor.fetchone()
        
        if not livro:
            cursor.close()
            conn.close()
            return

        titulo_livro = livro['titulo']

        sql_notificacoes = """
            SELECT n.id_notificacao, n.receber_email, n.receber_whatsapp, n.receber_sms,
                   l.nome, l.email, l.telefone
            FROM notificacoes_interesse n
            JOIN leitores l ON n.id_leitor = l.id_leitor
            WHERE n.id_livro = %s AND n.status_notificacao = 'Pendente'
        """
        cursor.execute(sql_notificacoes, (id_livro,))
        solicitacoes = cursor.fetchall()

        if not solicitacoes:
            cursor.close()
            conn.close()
            return

        # 2. Inicializa o cliente do Twilio
        account_sid = os.getenv('TWILIO_ACCOUNT_SID')
        auth_token = os.getenv('TWILIO_AUTH_TOKEN')
        twilio_sms_from = os.getenv('TWILIO_PHONE_NUMBER')
        twilio_whatsapp_from = os.getenv('TWILIO_WHATSAPP_NUMBER')

        client_twilio = None
        if account_sid and auth_token:
            client_twilio = Client(account_sid, auth_token)

        mensagem_texto = f"Olá, {titulo_livro} já está disponível para retirada na biblioteca! Acesse o sistema para reservar ou va o mais rapido para a biblioteca pegar o livro."

        for s in solicitacoes:
            telefone_formatado = s['telefone'].strip() if s['telefone'] else None
            
            # Formatação simples para código de país caso não tenha (+55 para Brasil)
            if telefone_formatado and not telefone_formatado.startswith('+'):
                telefone_formatado = f"+55{telefone_formatado}"

            # ✉️ Envio de E-mail
            if s['receber_email'] and s['email']:
                print(f"📧 [EMAIL] Enviando aviso para {s['email']}...")
                # Lógica de e-mail (Flask-Mail / Smtplib)

            # 💬 Envio via Twilio WhatsApp
            if s['receber_whatsapp'] and telefone_formatado and client_twilio:
                try:
                    msg = client_twilio.messages.create(
                        body=f"📖 *BibliTech*: {mensagem_texto}",
                        from_=f"whatsapp:{twilio_whatsapp_from}",
                        to=f"whatsapp:{telefone_formatado}"
                    )
                    print(f"💬 [TWILIO WHATSAPP] Enviado para {telefone_formatado} | SID: {msg.sid}")
                except Exception as err:
                    print(f"❌ Erro ao enviar WhatsApp Twilio: {err}")

            # 📱 Envio via Twilio SMS
            if s['receber_sms'] and telefone_formatado and client_twilio:
                try:
                    msg = client_twilio.messages.create(
                        body=f"BibliTech: {mensagem_texto}",
                        from_=twilio_sms_from,
                        to=telefone_formatado
                    )
                    print(f"📱 [TWILIO SMS] Enviado para {telefone_formatado} | SID: {msg.sid}")
                except Exception as err:
                    print(f"❌ Erro ao enviar SMS Twilio: {err}")

            # Atualiza status para 'Enviado' para evitar disparos duplicados
            cursor.execute("""
                UPDATE notificacoes_interesse 
                SET status_notificacao = 'Enviado' 
                WHERE id_notificacao = %s
            """, (s['id_notificacao'],))

        conn.commit()
        cursor.close()
        conn.close()

    except Exception as e:
        print("\n❌ ERRO NA EXECUÇÃO DO DISPARO TWILIO:", e, "\n")
        if conn and conn.is_connected():
            conn.close()

# -----------------------------------------------------------------------------
# 🏠 HOME / INDEX (HUB CENTRALIZADO)
# -----------------------------------------------------------------------------
@app.route('/')
def home():
    abrir_login = request.args.get('abrir_login', 'false')
    abrir_cadastro = request.args.get('abrir_cadastro', 'false')
    aba_ativa = request.args.get('aba', 'home')  # 'home', 'perfil', 'reservas'

    livros_destaque = []
    leitor = None
    estatisticas = None
    reservas_ativas = []
    emprestimos_ativos = []

    conn = get_db_connection()
    if not conn:
        return "Erro de conexão com o banco de dados.", 500

    try:
        cursor = conn.cursor(dictionary=True)

        # 1. Busca os 5 livros mais bem avaliados para a Home
        sql_home = '''
            SELECT l.id_livro, l.titulo, l.autor, l.capa,
                   COALESCE(AVG(a.nota), 0) AS media_notas,
                   COUNT(a.id_avaliacao) AS total_avaliacoes,
                   COUNT(CASE WHEN e.status_exemplar = 'Disponível' THEN 1 END) AS disponiveis
            FROM livro l
            LEFT JOIN avaliacoes a ON l.id_livro = a.livro_id
            LEFT JOIN exemplares e ON l.id_livro = e.id_livro
            GROUP BY l.id_livro
            ORDER BY media_notas DESC, total_avaliacoes DESC
            LIMIT 5
        '''
        cursor.execute(sql_home)
        livros_destaque = cursor.fetchall()

        # 2. Se o leitor estiver logado, carrega os dados do Perfil e Reservas para a home.html
        if 'id_leitor' in session:
            id_leitor = session['id_leitor']

            # Dados do Leitor
            cursor.execute("""
                SELECT id_leitor, nome, email, telefone, DATE_FORMAT(cadastro, '%d/%m/%Y') AS data_cadastro
                FROM leitores WHERE id_leitor = %s
            """, (id_leitor,))
            leitor = cursor.fetchone()

            # Estatísticas
            cursor.execute("SELECT COUNT(*) AS total FROM emprestimos WHERE id_leitor = %s", (id_leitor,))
            total_historico = cursor.fetchone()['total']

            cursor.execute("SELECT COUNT(*) AS total FROM avaliacoes WHERE leitor_id = %s", (id_leitor,))
            total_avaliacoes = cursor.fetchone()['total']

            estatisticas = {
                "total_emprestimos_historico": total_historico,
                "total_avaliacoes": total_avaliacoes
            }

            # Reservas Ativas
            sql_reservas = """
                SELECT r.id_reserva, l.id_livro, l.titulo, l.autor, l.capa, r.status_reserva,
                       DATE_FORMAT(r.data_reserva, '%d/%m/%Y %H:%i') AS data_reserva
                FROM reservas r
                JOIN livro l ON r.id_livro = l.id_livro
                WHERE r.id_leitor = %s AND r.status_reserva IN ('Pendente', 'Aguardando Retirada')
                ORDER BY r.data_reserva DESC
            """
            cursor.execute(sql_reservas, (id_leitor,))
            reservas_ativas = cursor.fetchall()

            # Empréstimos Ativos
            sql_emprestimos = """
                SELECT emp.id_emprestimo, l.id_livro, l.titulo, l.autor, l.capa,
                       DATE_FORMAT(emp.data_emprestimo, '%d/%m/%Y') AS data_emprestimo,
                       DATE_FORMAT(emp.data_devolucao_prevista, '%d/%m/%Y') AS data_prevista,
                       DATEDIFF(CURRENT_DATE(), emp.data_devolucao_prevista) AS dias_atraso,
                       emp.renovacoes_realizadas
                FROM emprestimos emp
                JOIN exemplares ex ON emp.id_exemplar = ex.id_exemplar
                JOIN livro l ON ex.id_livro = l.id_livro
                WHERE emp.id_leitor = %s AND emp.status_emprestimo = 'Ativo'
                ORDER BY emp.data_devolucao_prevista ASC
            """
            cursor.execute(sql_emprestimos, (id_leitor,))
            emprestimos_ativos = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template(
            'home.html',
            livros=livros_destaque,
            leitor=leitor,
            estatisticas=estatisticas,
            reservas=reservas_ativas,
            emprestimos=emprestimos_ativos,
            abrir_login=abrir_login,
            abrir_cadastro=abrir_cadastro,
            aba_ativa=aba_ativa
        )

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO NA ROTA /:", e, "\n")
        return "Erro interno ao carregar a página inicial.", 500

# -----------------------------------------------------------------------------
# 📚 CATÁLOGO & DETALHES
# -----------------------------------------------------------------------------
@app.route('/catalogo', methods=['GET'])
def catalogo():
    conn = get_db_connection()
    if not conn:
        return "Erro de conexão com o banco de dados.", 500

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute('''
            SELECT l.id_livro, l.titulo, l.autor, l.capa,
                   COUNT(CASE WHEN e.status_exemplar = 'Disponível' THEN 1 END) AS disponiveis,
                   COUNT(emp.id_emprestimo) AS total_emprestimos
            FROM livro l
            LEFT JOIN exemplares e ON l.id_livro = e.id_livro
            LEFT JOIN emprestimos emp ON e.id_exemplar = emp.id_exemplar
            GROUP BY l.id_livro ORDER BY total_emprestimos DESC, l.id_livro DESC LIMIT 5
        ''')
        mais_emprestados = cursor.fetchall()

        cursor.execute('''
            SELECT l.id_livro, l.titulo, l.autor, l.capa,
                   COUNT(CASE WHEN e.status_exemplar = 'Disponível' THEN 1 END) AS disponiveis,
                   COUNT(res.id_reserva) AS total_reservas
            FROM livro l
            LEFT JOIN exemplares e ON l.id_livro = e.id_livro
            LEFT JOIN reservas res ON l.id_livro = res.id_livro
            GROUP BY l.id_livro ORDER BY total_reservas DESC, l.id_livro DESC LIMIT 5
        ''')
        mais_procurados = cursor.fetchall()

        cursor.execute('''
            SELECT l.id_livro, l.titulo, l.autor, l.capa,
                   COUNT(CASE WHEN e.status_exemplar = 'Disponível' THEN 1 END) AS disponiveis
            FROM livro l LEFT JOIN exemplares e ON l.id_livro = e.id_livro
            GROUP BY l.id_livro ORDER BY l.cadastro DESC LIMIT 5
        ''')
        lancamentos = cursor.fetchall()

        cursor.execute('''
            SELECT l.id_livro, l.titulo, l.autor, l.capa,
                   COUNT(CASE WHEN e.status_exemplar = 'Disponível' THEN 1 END) AS disponiveis
            FROM livro l LEFT JOIN exemplares e ON l.id_livro = e.id_livro
            GROUP BY l.id_livro ORDER BY l.titulo ASC
        ''')
        todos_livros = cursor.fetchall()

        cursor.execute("SELECT * FROM categorias ORDER BY nome_categoria ASC")
        categorias = cursor.fetchall()

        cursor.close()
        conn.close()

        return render_template(
            'catalogo.html',
            mais_emprestados=mais_emprestados,
            mais_procurados=mais_procurados,
            lancamentos=lancamentos,
            todos_livros=todos_livros,
            categorias=categorias
        )

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO NA ROTA /catalogo:", e, "\n")
        return "Erro interno ao carregar o catálogo.", 500

@app.route('/livro/<int:id>', methods=['GET'])
def obter_detalhes_livro(id):
    conn = get_db_connection()
    if not conn:
        return "Erro ao conectar ao banco de dados.", 500

    try:
        cursor = conn.cursor(dictionary=True)

        sql_livro = """
            SELECT l.id_livro, l.titulo, l.autor, l.ano_publicacao, l.quant_estoque, l.sinopse, l.capa,
                   DATE_FORMAT(l.cadastro, '%d/%m/%Y') AS cadastro,
                   GROUP_CONCAT(DISTINCT c.nome_categoria SEPARATOR ', ') AS categorias
            FROM livro l
            LEFT JOIN livro_categorias lc ON l.id_livro = lc.id_livro
            LEFT JOIN categorias c ON lc.id_categoria = c.id_categoria
            WHERE l.id_livro = %s GROUP BY l.id_livro;
        """
        cursor.execute(sql_livro, (id,))
        livro = cursor.fetchone()

        if not livro:
            cursor.close()
            conn.close()
            return "Livro não encontrado.", 404

        cursor.execute("SELECT id_exemplar, posicao_estante, status_exemplar FROM exemplares WHERE id_livro = %s", (id,))
        exemplares = cursor.fetchall()

        cursor.execute("SELECT COUNT(*) AS total_fila FROM reservas WHERE id_livro = %s AND status_reserva = 'Pendente'", (id,))
        resultado_fila = cursor.fetchone()
        total_fila = resultado_fila['total_fila'] if resultado_fila else 0

        sql_reviews = """
            SELECT a.id_avaliacao, a.nota, a.comentario,
                   DATE_FORMAT(a.data_avaliacao, '%d/%m/%Y %H:%i') AS data_avaliacao,
                   l.nome AS nome_leitor
            FROM avaliacoes a JOIN leitores l ON a.leitor_id = l.id_leitor
            WHERE a.livro_id = %s ORDER BY a.data_avaliacao DESC;
        """
        cursor.execute(sql_reviews, (id,))
        reviews = cursor.fetchall()

        cursor.close()
        conn.close()

        media_notas = round(sum(r['nota'] for r in reviews) / len(reviews), 1) if reviews else "Sem avaliações"
        livro['media_avaliacao'] = media_notas

        return render_template('catalogo.html', livro=livro, exemplares=exemplares, total_fila=total_fila, reviews=reviews)

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO NA ROTA /livro:", e, "\n")
        return "Erro interno do servidor.", 500

# -----------------------------------------------------------------------------
# 🔐 AUTENTICAÇÃO & CADASTRO
# -----------------------------------------------------------------------------
@app.route('/login', methods=['GET', 'POST'])
@limiter.limit("5 per minute", methods=['POST'])
def login():
    if 'id_leitor' in session or 'id_funcionario' in session:
        return redirect(url_for('catalogo'))

    if request.method == 'GET':
        return redirect(url_for('home', abrir_login='true'))

    email = request.form.get('email', '').strip()
    senha = request.form.get('senha', '').strip()

    if not email or not senha:
        flash("Por favor, preencha todos os campos.", "danger")
        return redirect(url_for('home', abrir_login='true'))

    conn = get_db_connection()
    if not conn:
        flash("Erro ao conectar ao banco de dados.", "danger")
        return redirect(url_for('home', abrir_login='true'))

    try:
        cursor = conn.cursor(dictionary=True)

        # 1. Tenta autenticar como leitor
        cursor.execute("""
            SELECT id_leitor, nome, email, senha, status_conta
            FROM leitores WHERE email = %s
        """, (email,))
        leitor = cursor.fetchone()

        if leitor and check_password_hash(leitor['senha'], senha):
            if leitor['status_conta'] != 'Ativo':
                cursor.close()
                conn.close()
                flash("Esta conta está suspensa ou bloqueada. Procure a biblioteca para regularizar.", "danger")
                return redirect(url_for('home', abrir_login='true'))

            session.clear()
            session.permanent = True
            session['id_leitor'] = leitor['id_leitor']
            session['nome'] = leitor['nome']
            session['email'] = leitor['email']
            session['tipo_usuario'] = 'LEITOR'
            cursor.close()
            conn.close()
            flash(f"Bem-vindo(a) de volta, {leitor['nome']}!", "success")
            return redirect(url_for('catalogo'))

        # 2. Tenta autenticar como funcionário (bibliotecário/administrador)
        cursor.execute("""
            SELECT id_funcionario, nome, email, senha, tipo_perfil
            FROM funcionarios WHERE email = %s
        """, (email,))
        funcionario = cursor.fetchone()
        cursor.close()
        conn.close()

        if funcionario and check_password_hash(funcionario['senha'], senha):
            session.clear()
            session.permanent = True
            session['id_funcionario'] = funcionario['id_funcionario']
            session['nome'] = funcionario['nome']
            session['email'] = funcionario['email']
            session['tipo_usuario'] = funcionario['tipo_perfil']  # 'FUNCIONARIO'
            flash(f"Bem-vindo(a), {funcionario['nome']}!", "success")
            return redirect(url_for('admin_dashboard'))

        flash("E-mail ou senha incorretos.", "danger")
        return redirect(url_for('home', abrir_login='true'))

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO NO LOGIN:", e, "\n")
        flash("Erro ao processar o login.", "danger")
        return redirect(url_for('home', abrir_login='true'))

@app.route('/cadastrar', methods=['POST'])
@limiter.limit("5 per minute")
def cadastrar():
    nome = request.form.get('nome', '').strip()
    email = request.form.get('email', '').strip()
    senha = request.form.get('senha', '').strip()
    telefone = request.form.get('telefone', '').strip()
    # ⚖️ LGPD: Validação obrigatória do consentimento no cadastro
    consentimento_lgpd = 1 if request.form.get('consentimento_lgpd') == 'on' else 0

    if not consentimento_lgpd:
        flash("Você deve aceitar os termos de privacidade para criar uma conta.", "danger")
        return redirect(url_for('home', abrir_cadastro='true'))

    if not nome or not email or not senha or not telefone:
        flash("Por favor, preencha todos os campos.", "danger")
        return redirect(url_for('home', abrir_cadastro='true'))

    conn = get_db_connection()
    if not conn:
        flash("Erro ao conectar ao banco de dados.", "danger")
        return redirect(url_for('home', abrir_cadastro='true'))

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id_leitor FROM leitores WHERE email = %s", (email,))
        if cursor.fetchone():
            flash("E-mail já cadastrado.", "warning")
            cursor.close()
            conn.close()
            return redirect(url_for('home', abrir_cadastro='true'))

        senha_hash = generate_password_hash(senha)
        # Importante: certifique-se de que sua tabela 'leitores' possui a coluna consentimento_lgpd
        sql_insert = "INSERT INTO leitores (nome, email, senha, telefone, consentimento_lgpd) VALUES (%s, %s, %s, %s, %s)"
        cursor.execute(sql_insert, (nome, email, senha_hash, telefone, consentimento_lgpd))
        conn.commit()

        novo_id = cursor.lastrowid
        cursor.close()
        conn.close()

        session['id_leitor'] = novo_id
        session['nome'] = nome
        session['email'] = email

        flash(f"Conta criada com sucesso! Seja bem-vindo(a), {nome}!", "success")
        return redirect(url_for('catalogo'))

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO NO CADASTRO:", e, "\n")
        flash("Erro ao criar conta.", "danger")
        return redirect(url_for('home', abrir_cadastro='true'))
    
@app.route('/logout')
def logout():
    session.clear()
    flash("Sessão encerrada com sucesso.", "info")
    return redirect(url_for('home'))

# -----------------------------------------------------------------------------
# ✏️ EDICAO DE PERFIL (Redireciona para Home na Aba Perfil)
# -----------------------------------------------------------------------------
@app.route('/meu-perfil/editar', methods=['POST'])
def editar_perfil():
    if 'id_leitor' not in session:
        flash("Faça login para alterar seus dados.", "warning")
        return redirect(url_for('home', abrir_login='true'))

    id_leitor = session['id_leitor']
    nome = request.form.get('nome', '').strip()
    telefone = request.form.get('telefone', '').strip()
    nova_senha = request.form.get('nova_senha', '').strip()

    if not nome:
        flash("O nome não pode ser vazio.", "warning")
        return redirect(url_for('home', aba='perfil'))

    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            if nova_senha:
                senha_hash = generate_password_hash(nova_senha)
                sql = "UPDATE leitores SET nome = %s, telefone = %s, senha = %s WHERE id_leitor = %s"
                cursor.execute(sql, (nome, telefone, senha_hash, id_leitor))
            else:
                sql = "UPDATE leitores SET nome = %s, telefone = %s WHERE id_leitor = %s"
                cursor.execute(sql, (nome, telefone, id_leitor))

            conn.commit()
            cursor.close()
            conn.close()

            session['nome'] = nome
            flash("Perfil atualizado com sucesso!", "success")

        except Exception as e:
            if conn and conn.is_connected():
                conn.close()
            print("\n❌ ERRO AO EDITAR PERFIL:", e, "\n")
            flash("Erro ao atualizar o perfil.", "danger")

    return redirect(url_for('home', aba='perfil'))

# -----------------------------------------------------------------------------
# RESERVA OU ENTRAR NA FILA DE ESPERA
# -----------------------------------------------------------------------------
@app.route('/reservar/<int:id_livro>', methods=['POST'])
def reservar_livro(id_livro):
    if 'id_leitor' not in session:
        flash("Faça login para reservar livros.", "warning")
        return redirect(url_for('home', abrir_login='true'))

    id_leitor = session['id_leitor']
    opcao = request.form.get('opcao_indisponivel') # 'fila', 'notificar' ou None

    conn = get_db_connection()
    if not conn:
        flash("Erro ao conectar ao banco de dados.", "danger")
        return redirect(url_for('catalogo'))

    try:
        cursor = conn.cursor(dictionary=True)

        # 1. Verifica se já possui uma reserva/fila ativa
        cursor.execute("""
            SELECT id_reserva FROM reservas
            WHERE id_leitor = %s AND id_livro = %s AND status_reserva IN ('Pendente', 'Aguardando Retirada')
        """, (id_leitor, id_livro))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            flash("Você já possui uma reserva ativa ou já está na fila deste livro.", "info")
            return redirect(url_for('home', aba='reservas'))

        # 2. Verifica se há exemplares disponíveis
        cursor.execute("""
            SELECT COUNT(*) AS disponiveis FROM exemplares
            WHERE id_livro = %s AND status_exemplar = 'Disponível'
        """, (id_livro,))
        disponiveis = cursor.fetchone()['disponiveis']

        # CASO 1: Há exemplares disponíveis -> Reserva direta
        if disponiveis > 0:
            cursor.execute("""
                INSERT INTO reservas (id_leitor, id_livro, data_reserva, status_reserva)
                VALUES (%s, %s, NOW(), 'Aguardando Retirada')
            """, (id_leitor, id_livro))
            conn.commit()
            cursor.close()
            conn.close()

            flash("Reserva realizada com sucesso! O livro está aguardando sua retirada na biblioteca.", "success")
            return redirect(url_for('home', aba='reservas'))

        # CASO 2: Esgotado + Leitor ainda NÃO escolheu a opção no modal
        elif not opcao:
            cursor.close()
            conn.close()
            # Redireciona para a tela do livro passando o parâmetro que abre o modal de escolha
            return redirect(url_for('obter_detalhes_livro', id=id_livro, escolher_opcao='true'))

        # CASO 3: Esgotado + Leitor escolheu ENTRAR NA FILA
        elif opcao == 'fila':
            cursor.execute("""
                INSERT INTO reservas (id_leitor, id_livro, data_reserva, status_reserva)
                VALUES (%s, %s, NOW(), 'Pendente')
            """, (id_leitor, id_livro))
            conn.commit()
            cursor.close()
            conn.close()

            flash("Você foi inserido na fila de espera com sucesso!", "info")
            return redirect(url_for('home', aba='reservas'))

        # CASO 4: Esgotado + Leitor escolheu APENAS SER NOTIFICADO
        elif opcao == 'notificar':
            cursor.execute("""
                INSERT INTO notificacoes_interesse (id_leitor, id_livro, data_solicitacao)
                VALUES (%s, %s, NOW())
                ON DUPLICATE KEY UPDATE data_solicitacao = NOW()
            """, (id_leitor, id_livro))
            conn.commit()
            cursor.close()
            conn.close()

            flash("Aviso cadastrado! Enviaremos uma notificação assim que o livro estiver disponível.", "success")
            return redirect(url_for('obter_detalhes_livro', id=id_livro))

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO NA ROTA /reservar:", e, "\n")
        flash("Erro ao processar a solicitação.", "danger")
        return redirect(url_for('catalogo'))

@app.route('/renovar/<int:id_emprestimo>', methods=['POST'])
def renovar_emprestimo(id_emprestimo):
    if 'id_leitor' not in session:
        flash("Faça login para renovar empréstimos.", "warning")
        return redirect(url_for('home', abrir_login='true'))

    id_leitor = session['id_leitor']
    conn = get_db_connection()
    if not conn:
        flash("Erro ao conectar ao banco de dados.", "danger")
        return redirect(url_for('catalogo'))

    try:
        cursor = conn.cursor(dictionary=True)

        # Verifica se o empréstimo pertence ao leitor e está ativo
        cursor.execute("""
            SELECT * FROM emprestimos
            WHERE id_emprestimo = %s AND id_leitor = %s AND status_emprestimo = 'Ativo'
        """, (id_emprestimo, id_leitor))
        emprestimo = cursor.fetchone()

        if not emprestimo:
            flash("Empréstimo não encontrado ou não é renovável.", "warning")
            cursor.close()
            conn.close()
            return redirect(url_for('home', aba='reservas'))

        # Verifica se já atingiu o limite de renovações
        if emprestimo['renovacoes_realizadas'] >= 2:
            flash("Você atingiu o limite de renovações para este empréstimo.", "info")
            cursor.close()
            conn.close()
            return redirect(url_for('home', aba='reservas'))

        # Atualiza a data de devolução prevista e incrementa o contador de renovações
        nova_data_prevista = emprestimo['data_devolucao_prevista'] + timedelta(days=7)
        cursor.execute("""
            UPDATE emprestimos
            SET data_devolucao_prevista = %s, renovacoes_realizadas = renovacoes_realizadas + 1
            WHERE id_emprestimo = %s
        """, (nova_data_prevista, id_emprestimo))
        conn.commit()

        flash("Empréstimo renovado com sucesso!", "success")
        cursor.close()
        conn.close()
        return redirect(url_for('home', aba='reservas'))

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO AO RENOVAR EMPRÉSTIMO:", e, "\n")
        flash("Erro ao renovar empréstimo.", "danger")
        return redirect(url_for('home', aba='reservas'))

@app.route('/cancelar-reserva/<int:id_reserva>', methods=['POST'])
def cancelar_reserva(id_reserva):
    if 'id_leitor' not in session:
        flash("Faça login para cancelar reservas.", "warning")
        return redirect(url_for('home', abrir_login='true'))

    id_leitor = session['id_leitor']
    conn = get_db_connection()
    if not conn:
        flash("Erro ao conectar ao banco de dados.", "danger")
        return redirect(url_for('catalogo'))

    try:
        cursor = conn.cursor(dictionary=True)

        # Verifica se a reserva pertence ao leitor e está ativa
        cursor.execute("""
            SELECT * FROM reservas
            WHERE id_reserva = %s AND id_leitor = %s AND status_reserva IN ('Pendente', 'Aguardando Retirada')
        """, (id_reserva, id_leitor))
        reserva = cursor.fetchone()

        if not reserva:
            flash("Reserva não encontrada ou não pode ser cancelada.", "warning")
            cursor.close()
            conn.close()
            return redirect(url_for('home', aba='reservas'))

        # Atualiza o status da reserva para 'Cancelada'
        cursor.execute("""
            UPDATE reservas SET status_reserva = 'Cancelada' WHERE id_reserva = %s
        """, (id_reserva,))
        conn.commit()

        flash("Reserva cancelada com sucesso.", "success")
        cursor.close()
        conn.close()
        return redirect(url_for('home', aba='reservas'))

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO AO CANCELAR RESERVA:", e, "\n")
        flash("Erro ao cancelar reserva.", "danger")
        return redirect(url_for('home', aba='reservas'))

@app.route('/avaliar/<int:id_livro>', methods=['POST'])
def avaliar_livro(id_livro):
    if 'id_leitor' not in session:
        flash("Faça login para avaliar livros.", "warning")
        return redirect(url_for('home', abrir_login='true'))

    id_leitor = session['id_leitor']
    nota = request.form.get('nota')
    comentario = request.form.get('comentario', '').strip()

    if not nota or not nota.isdigit() or int(nota) < 1 or int(nota) > 5:
        flash("Nota inválida. Escolha entre 1 e 5.", "warning")
        return redirect(url_for('obter_detalhes_livro', id=id_livro))

    conn = get_db_connection()
    if not conn:
        flash("Erro ao conectar ao banco de dados.", "danger")
        return redirect(url_for('obter_detalhes_livro', id=id_livro))

    try:
        cursor = conn.cursor(dictionary=True)

        # Verifica se o leitor já avaliou o livro
        cursor.execute("""
            SELECT * FROM avaliacoes WHERE livro_id = %s AND leitor_id = %s
        """, (id_livro, id_leitor))
        avaliacao_existente = cursor.fetchone()

        if avaliacao_existente:
            # Atualiza avaliação existente
            cursor.execute("""
                UPDATE avaliacoes SET nota = %s, comentario = %s, data_avaliacao = NOW()
                WHERE livro_id = %s AND leitor_id = %s
            """, (nota, comentario, id_livro, id_leitor))
            flash("Avaliação atualizada com sucesso!", "success")
        else:
            # Insere nova avaliação
            cursor.execute("""
                INSERT INTO avaliacoes (livro_id, leitor_id, nota, comentario, data_avaliacao)
                VALUES (%s, %s, %s, %s, NOW())
            """, (id_livro, id_leitor, nota, comentario))
            flash("Avaliação registrada com sucesso!", "success")

        conn.commit()
        cursor.close()
        conn.close()
        return redirect(url_for('obter_detalhes_livro', id=id_livro))

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO AO AVALIAR LIVRO:", e, "\n")
        flash("Erro ao registrar avaliação.", "danger")
        return redirect(url_for('obter_detalhes_livro', id=id_livro))

@app.route('/configurar-notificacao/<int:id_livro>', methods=['POST'])
def configurar_notificacao(id_livro):
    if 'id_leitor' not in session:
        return redirect(url_for('home', abrir_login='true'))
    
    id_leitor = session['id_leitor']
    consentimento = 1 if request.form.get('consentimento_lgpd') == 'on' else 0
    
    if not consentimento:
        flash("Você precisa aceitar os termos de uso de dados para receber notificações automáticas.", "warning")
        return redirect(url_for('obter_detalhes_livro', id=id_livro))

    # Captura as preferências de canais escolhidas pelo leitor
    receber_email = 1 if request.form.get('receber_email') == 'on' else 0
    receber_whatsapp = 1 if request.form.get('receber_whatsapp') == 'on' else 0
    receber_sms = 1 if request.form.get('receber_sms') == 'on' else 0

    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO notificacoes_interesse (id_leitor, id_livro, consentimento_lgpd, receber_email, receber_whatsapp, receber_sms, status_notificacao, data_solicitacao)
                VALUES (%s, %s, %s, %s, %s, %s, 'Pendente', NOW())
                ON DUPLICATE KEY UPDATE 
                    consentimento_lgpd = %s, 
                    receber_email = %s, 
                    receber_whatsapp = %s, 
                    receber_sms = %s,
                    status_notificacao = 'Pendente',
                    data_solicitacao = NOW()
            """, (id_leitor, id_livro, consentimento, receber_email, receber_whatsapp, receber_sms, 
                  consentimento, receber_email, receber_whatsapp, receber_sms))
            conn.commit()
            cursor.close()
            conn.close()
            flash("Preferência de notificação salva com sucesso!", "success")
        except Exception as e:
            if conn and conn.is_connected():
                conn.close()
            print("❌ Erro ao configurar notificação:", e)
            flash("Erro ao salvar preferências.", "danger")
            
    return redirect(url_for('obter_detalhes_livro', id=id_livro))

@app.route('/excluir-conta', methods=['POST'])
def excluir_conta():
    if 'id_leitor' not in session:
        return redirect(url_for('home', abrir_login='true'))

    id_leitor = session['id_leitor']
    conn = get_db_connection()
    if conn:
        try:
            cursor = conn.cursor()

            # 1. Bloqueia a exclusão se houver empréstimo ATIVO (o livro físico ainda
            #    precisa ser devolvido antes de qualquer coisa).
            cursor.execute("""
                SELECT COUNT(*) FROM emprestimos
                WHERE id_leitor = %s AND status_emprestimo = 'Ativo'
            """, (id_leitor,))
            emprestimos_ativos = cursor.fetchone()[0]

            if emprestimos_ativos > 0:
                cursor.close()
                conn.close()
                flash("⚠️ Não foi possível encerrar a sua conta pois existem empréstimos ativos vinculados ao seu perfil. Por favor, realize a devolução dos livros na biblioteca antes de prosseguir com a exclusão.", "warning")
                return redirect(url_for('home'))

            # 2. Remove dependências que podem ser eliminadas sem restrição legal
            cursor.execute("DELETE FROM notificacoes_interesse WHERE id_leitor = %s", (id_leitor,))
            cursor.execute("DELETE FROM reservas WHERE id_leitor = %s", (id_leitor,))

            # 3. Tenta excluir fisicamente o cadastro do leitor
            try:
                cursor.execute("DELETE FROM leitores WHERE id_leitor = %s", (id_leitor,))
                conn.commit()
                cursor.close()
                conn.close()
                session.clear()
                flash("Sua conta e seus dados foram excluídos com sucesso.", "info")

            except mysql.connector.Error as err:
                conn.rollback()
                if err.errno == 1451:
                    # Existe histórico de empréstimos já devolvidos vinculado ao leitor.
                    # Esse histórico precisa ser mantido por obrigação legal/contábil da
                    # biblioteca, então em vez de deixar a exclusão travada para sempre
                    # (o que violaria o direito à eliminação da LGPD), anonimizamos os
                    # dados pessoais e preservamos apenas o vínculo técnico do histórico.
                    email_anonimizado = f"removido+{id_leitor}@anonimizado.bibliotech"
                    senha_invalidada = generate_password_hash(secrets.token_hex(16))
                    cursor.execute("""
                        UPDATE leitores
                        SET nome = 'Usuário Removido',
                            email = %s,
                            telefone = 'ANONIMIZADO',
                            senha = %s,
                            foto_perfil = 'default_profile.png',
                            status_conta = 'Bloqueado'
                        WHERE id_leitor = %s
                    """, (email_anonimizado, senha_invalidada, id_leitor))
                    conn.commit()
                    cursor.close()
                    conn.close()
                    session.clear()
                    flash("Seus dados pessoais foram anonimizados. O histórico de empréstimos precisa ser mantido por obrigação legal, mas deixou de estar vinculado à sua identidade.", "info")
                else:
                    cursor.close()
                    conn.close()
                    print("\n❌ ERRO SQL AO EXCLUIR CONTA:", err, "\n")
                    flash("Não foi possível excluir a conta devido a um erro interno no banco de dados.", "danger")

        except Exception as e:
            if conn and conn.is_connected():
                conn.close()
            print("\n❌ ERRO GERAL AO EXCLUIR CONTA:", e, "\n")
            flash("Erro inesperado ao processar a exclusão da conta.", "danger")

    return redirect(url_for('home'))

# -----------------------------------------------------------------------------
# 📦 EXPORTAÇÃO DE DADOS (PORTABILIDADE LGPD)
#-----------------------------------------------------------------------------
@app.route('/meu-perfil/exportar-dados', methods=['GET'])
def exportar_dados_lgpd():
    if 'id_leitor' not in session:
        flash("Faça login para exportar seus dados.", "warning")
        return redirect(url_for('home', abrir_login='true'))

    id_leitor = session['id_leitor']
    conn = get_db_connection()
    if not conn:
        flash("Erro ao conectar ao banco de dados.", "danger")
        return redirect(url_for('home', aba='perfil'))

    try:
        cursor = conn.cursor(dictionary=True)

        # 1. Dados cadastrais
        cursor.execute("""
            SELECT nome, email, telefone, cadastro, consentimento_lgpd 
            FROM leitores WHERE id_leitor = %s
        """, (id_leitor,))
        dados_leitor = cursor.fetchone()

        # 2. Histórico de empréstimos
        cursor.execute("""
            SELECT l.titulo, emp.data_emprestimo, emp.data_devolucao_prevista, emp.status_emprestimo
            FROM emprestimos emp
            JOIN exemplares ex ON emp.id_exemplar = ex.id_exemplar
            JOIN livro l ON ex.id_livro = l.id_livro
            WHERE emp.id_leitor = %s
        """, (id_leitor,))
        emprestimos = cursor.fetchall()

        # 3. Avaliações feitas
        cursor.execute("""
            SELECT l.titulo, a.nota, a.comentario, a.data_avaliacao
            FROM avaliacoes a
            JOIN livro l ON a.livro_id = l.id_livro
            WHERE a.leitor_id = %s
        """, (id_leitor,))
        avaliacoes = cursor.fetchall()

        # 4. Reservas e filas
        cursor.execute("""
            SELECT l.titulo, r.data_reserva, r.status_reserva
            FROM reservas r
            JOIN livro l ON r.id_livro = l.id_livro
            WHERE r.id_leitor = %s
        """, (id_leitor,))
        reservas = cursor.fetchall()

        cursor.close()
        conn.close()

        # Consolida tudo em um dicionário estruturado (Relatório de Portabilidade)
        relatorio_lgpd = {
            "controlador": "BibliTech",
            "titular": dados_leitor,
            "historico_emprestimos": emprestimos,
            "avaliacoes_livros": avaliacoes,
            "reservas_e_filas": reservas
        }

        # Retorna os dados como um arquivo JSON para download direto
        response = jsonify(relatorio_lgpd)
        response.headers["Content-Disposition"] = "attachment; filename=meus_dados_biblioteca.json"
        return response

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO AO EXPORTAR DADOS:", e, "\n")
        flash("Erro ao gerar arquivo de portabilidade de dados.", "danger")
        return redirect(url_for('home', aba='perfil'))

# -----------------------------------------------------------------------------
# 🛠️ MÓDULO ADMINISTRATIVO (CENTRALIZADO NO DASHBOARD)
# -----------------------------------------------------------------------------
def carregar_dados_dashboard_admin(cursor):
    """Função auxiliar para carregar todos os dados do painel do funcionário de uma só vez."""
    # 1. Métricas gerais
    cursor.execute("SELECT COUNT(*) AS total FROM livro")
    total_livros = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) AS total FROM leitores WHERE tipo_perfil = 'LEITOR'")
    total_leitores = cursor.fetchone()['total']

    cursor.execute("SELECT COUNT(*) AS total FROM emprestimos WHERE status_emprestimo = 'Ativo'")
    emprestimos_ativos_qtd = cursor.fetchone()['total']

    cursor.execute("""
        SELECT COUNT(*) AS total FROM emprestimos 
        WHERE status_emprestimo = 'Ativo' AND data_devolucao_prevista < CURRENT_DATE()
    """)
    total_atrasos = cursor.fetchone()['total']

    estatisticas = {
        "total_livros": total_livros,
        "total_leitores": total_leitores,
        "emprestimos_ativos": emprestimos_ativos_qtd,
        "total_atrasos": total_atrasos
    }

    # 2. Balcão - Reservas aguardando retirada
    cursor.execute("""
        SELECT r.id_reserva, r.data_reserva, l.nome AS leitor, liv.titulo, liv.id_livro
        FROM reservas r
        JOIN leitores l ON r.id_leitor = l.id_leitor
        JOIN livro liv ON r.id_livro = liv.id_livro
        WHERE r.status_reserva = 'Aguardando Retirada'
    """)
    reservas_retirada = cursor.fetchall()

    # 3. Balcão - Empréstimos Ativos
    cursor.execute("""
        SELECT emp.id_emprestimo, l.nome AS leitor, liv.titulo, ex.id_exemplar,
               DATE_FORMAT(emp.data_devolucao_prevista, '%d/%m/%Y') AS data_prevista
        FROM emprestimos emp
        JOIN leitores l ON emp.id_leitor = l.id_leitor
        JOIN exemplares ex ON emp.id_exemplar = ex.id_exemplar
        JOIN livro liv ON ex.id_livro = liv.id_livro
        WHERE emp.status_emprestimo = 'Ativo'
    """)
    emprestimos_ativos = cursor.fetchall()

    # 4. Acervo
    cursor.execute("""
        SELECT l.id_livro, l.titulo, l.autor, l.ano_publicacao,
               GROUP_CONCAT(ex.posicao_estante SEPARATOR ', ') as estantes
        FROM livro l
        LEFT JOIN exemplares ex ON l.id_livro = ex.id_livro
        GROUP BY l.id_livro
        ORDER BY l.id_livro DESC
    """)
    acervo = cursor.fetchall()

    # 5. Relatório de Atrasos
    cursor.execute("""
        SELECT emp.id_emprestimo, l.nome AS leitor, l.email, l.telefone, liv.titulo,
               DATE_FORMAT(emp.data_devolucao_prevista, '%d/%m/%Y') AS data_prevista,
               DATEDIFF(CURRENT_DATE(), emp.data_devolucao_prevista) AS dias_atraso
        FROM emprestimos emp
        JOIN leitores l ON emp.id_leitor = l.id_leitor
        JOIN exemplares ex ON emp.id_exemplar = ex.id_exemplar
        JOIN livro liv ON ex.id_livro = liv.id_livro
        WHERE emp.status_emprestimo = 'Ativo' AND emp.data_devolucao_prevista < CURRENT_DATE()
        ORDER BY dias_atraso DESC
    """)
    atrasos = cursor.fetchall()

    return {
        "estatisticas": estatisticas,
        "reservas": reservas_retirada,
        "emprestimos": emprestimos_ativos,
        "acervo": acervo,
        "atrasos": atrasos
    }
@app.route('/admin', methods=['GET'])
def admin_dashboard():
    if 'tipo_perfil' not in session or session.get('tipo_usuario') != 'FUNCIONARIO':
        flash("Acesso negado. Área restrita a funcionários.", "danger")
        return redirect(url_for('home'))

    conn = get_db_connection()
    if not conn:
        flash("Erro ao conectar ao banco de dados.", "danger")
        return redirect(url_for('home'))

    try:
        cursor = conn.cursor(dictionary=True)
        dados = carregar_dados_dashboard_admin(cursor)
        cursor.close()
        conn.close()

        aba_ativa = request.args.get('aba', 'metricas') # Controla qual aba do dashboard o front deve exibir por padrão

        return render_template(
            'dashboard.html',
            estatisticas=dados['estatisticas'],
            reservas=dados['reservas'],
            emprestimos=dados['emprestimos'],
            acervo=dados['acervo'],
            atrasos=dados['atrasos'],
            aba_ativa=aba_ativa
        )

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO NO DASHBOARD ADMIN:", e, "\n")
        flash("Erro ao carregar o painel administrativo.", "danger")
        return redirect(url_for('home'))

@app.route('/admin/balcao', methods=['POST'])
def admin_balcao():
    if 'tipo_perfil' not in session or session.get('tipo_usuario') != 'FUNCIONARIO':
        flash("Acesso negado.", "danger")
        return redirect(url_for('home'))

    conn = get_db_connection()
    if not conn:
        flash("Erro de conexão.", "danger")
        return redirect(url_for('admin_dashboard'))

    try:
        cursor = conn.cursor(dictionary=True)
        acao = request.form.get('acao') # 'entregar_reserva' ou 'registrar_devolucao'
        id_funcionario = session['id_funcionario']
        
        if acao == 'entregar_reserva':
            id_reserva = request.form.get('id_reserva')
            id_exemplar = request.form.get('id_exemplar')
            
            cursor.execute("SELECT id_leitor, id_livro FROM reservas WHERE id_reserva = %s", (id_reserva,))
            reserva = cursor.fetchone()
            
            if reserva:
                cursor.execute("""
                    INSERT INTO emprestimos (id_leitor, id_exemplar, id_funcionario, data_emprestimo, data_devolucao_prevista, status_emprestimo)
                    VALUES (%s, %s, %s, NOW(), DATE_ADD(NOW(), INTERVAL 14 DAY), 'Ativo')
                """, (reserva['id_leitor'], id_exemplar, id_funcionario))
                
                cursor.execute("UPDATE reservas SET status_reserva = 'Concluida' WHERE id_reserva = %s", (id_reserva,))
                cursor.execute("UPDATE exemplares SET status_exemplar = 'Emprestado' WHERE id_exemplar = %s", (id_exemplar,))
                
                conn.commit()
                flash("Empréstimo registrado com sucesso no balcão!", "success")

        elif acao == 'registrar_devolucao':
            id_emprestimo = request.form.get('id_emprestimo')
            id_exemplar = request.form.get('id_exemplar')
            
            cursor.execute("UPDATE emprestimos SET status_emprestimo = 'Devolvido', data_devolucao_real = NOW() WHERE id_emprestimo = %s", (id_emprestimo,))
            cursor.execute("UPDATE exemplares SET status_exemplar = 'Disponível' WHERE id_exemplar = %s", (id_exemplar,))
            
            cursor.execute("SELECT id_livro FROM exemplares WHERE id_exemplar = %s", (id_exemplar,))
            ex = cursor.fetchone()
            if ex:
                disparar_notificacoes_disponibilidade(ex['id_livro'])

            conn.commit()
            flash("Devolução registrada com sucesso! O exemplar voltou a ficar disponível.", "success")

        cursor.close()
        conn.close()
        return redirect(url_for('admin_dashboard', aba='balcao'))

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO NO BALCÃO:", e, "\n")
        flash("Erro ao processar operações no balcão.", "danger")
        return redirect(url_for('admin_dashboard', aba='balcao'))


@app.route('/admin/gerenciar-acervo', methods=['POST'])
def admin_gerenciar_acervo():
    if 'id_funcionario' not in session or session.get('tipo_usuario') != 'FUNCIONARIO':
        flash("Acesso negado.", "danger")
        return redirect(url_for('home'))

    conn = get_db_connection()
    if not conn:
        flash("Erro de conexão.", "danger")
        return redirect(url_for('admin_dashboard'))

    try:
        cursor = conn.cursor(dictionary=True)

        titulo = request.form.get('titulo', '').strip()
        autor = request.form.get('autor', '').strip()
        ano = request.form.get('ano_publicacao')
        sinopse = request.form.get('sinopse', '').strip()
        capa = request.form.get('capa', '').strip()
        posicao_estante = request.form.get('posicao_estante', '').strip()

        if titulo and autor:
            cursor.execute("""
                INSERT INTO livro (titulo, autor, ano_publicacao, sinopse, capa, cadastro)
                VALUES (%s, %s, %s, %s, %s, NOW())
            """, (titulo, autor, ano, sinopse, capa))
            id_novo_livro = cursor.lastrowid

            if posicao_estante:
                cursor.execute("""
                    INSERT INTO exemplares (id_livro, posicao_estante, status_exemplar)
                    VALUES (%s, %s, 'Disponível')
                """, (id_novo_livro, posicao_estante))

            conn.commit()
            flash("Livro e exemplar cadastrados com sucesso no acervo!", "success")
        else:
            flash("Título e autor são obrigatórios.", "warning")

        cursor.close()
        conn.close()
        return redirect(url_for('admin_dashboard', aba='acervo'))

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO NO ACERVO:", e, "\n")
        flash("Erro ao gerenciar o acervo.", "danger")
        return redirect(url_for('admin_dashboard', aba='acervo'))
    
# -----------------------------------------------------------------------------
# 🟢 EXECUÇÃO DO SERVIDOR
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    os.makedirs(ASSETS_FOLDER, exist_ok=True)
    os.makedirs(CSS_FOLDER, exist_ok=True)

    # Lê a flag de ambiente para o debug (False por padrão para segurança)
    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode)