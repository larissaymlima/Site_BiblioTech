"""
=============================================================================
 BIBLITECH — Sistema de Biblioteca Física (Backend Flask + MySQL)
=============================================================================
Este projeto usa APENAS 3 templates HTML, e todas as rotas do backend
renderizam ou dão suporte a um desses três:

    home.html      -> página inicial / hub do leitor (perfil, reservas,
                       empréstimos ativos, destaques)
    catalogo.html  -> catálogo de livros, busca, detalhes de um livro
    dashboard.html -> painel administrativo (funcionários/bibliotecários)

Rotas que não renderizam HTML (login, cadastro, reservar, avaliar, CRUDs
administrativos etc.) são "rotas de ação": processam um formulário e
devolvem o usuário para uma dessas 3 páginas via redirect + flash message
(ou JSON puro, se a requisição pedir — ver seção de testes abaixo).

⚠️ BANCO DE DADOS: este app.py espera 3 colunas NOVAS que não existiam na
primeira versão do schema. Rode o banco_bibliotech.sql atualizado (ou as
3 linhas ALTER TABLE que estão comentadas no topo dele):
    - funcionarios.status_funcionario  ENUM('Ativo','Inativo')
    - livro.status_livro               ENUM('Ativo','Descontinuado')
    - reservas.posicao_fila_notificada INT NULL

-----------------------------------------------------------------------------
 COMO TESTAR TODAS AS ROTAS NO THUNDER CLIENT
-----------------------------------------------------------------------------
1) Rode o Flask localmente (http://127.0.0.1:5000) com um arquivo .env
   contendo pelo menos: SECRET_KEY, DB_HOST, DB_USER, DB_PASSWORD, DB_NAME.

2) HABILITE COOKIES no Thunder Client (Settings > General > "Enable Cookies"
   ou crie um Environment e mantenha a mesma Collection). Necessário porque
   login usa sessão (cookie), igual um navegador.

3) CSRF: toda rota POST é protegida (Flask-WTF). Use:
       a) GET  /api/csrf-token  -> retorna {"csrf_token": "..."}
       b) Copie o valor e envie em TODO POST como header: X-CSRFToken: <valor>

4) RESPOSTA EM JSON PARA TESTE: mande o header "Accept: application/json"
   em qualquer rota de ação e ela devolve JSON puro em vez de redirect:
       { "sucesso": true, "mensagem": "..." }
   Sem esse header, o comportamento continua sendo o normal do site
   (redirect 302 + flash message) — nada quebra pra quem usa pelo navegador.

5) ROTAS GET QUE RENDERIZAM HTML (/, /catalogo, /admin) continuam
   devolvendo HTML; no Thunder Client basta conferir o status 200.

-----------------------------------------------------------------------------
 TABELA-RESUMO DE ROTAS
-----------------------------------------------------------------------------
  GET   /                                  -> nenhuma        -> home.html
  GET   /catalogo[?busca=&categoria=]      -> nenhuma        -> catalogo.html
  GET   /livro/<id>                        -> nenhuma        -> catalogo.html (detalhe)
  GET   /api/csrf-token                    -> nenhuma        -> JSON com o token CSRF
  GET|POST /login                          -> nenhuma        -> autentica leitor/funcionário
  POST  /cadastrar                         -> nenhuma        -> cria conta de leitor (self-service)
  GET   /logout                            -> leitor/func.   -> encerra sessão
  POST  /meu-perfil/editar                 -> leitor         -> edita nome/telefone/senha (self-service)
  GET   /meu-perfil/exportar-dados         -> leitor         -> exporta dados (LGPD)
  POST  /excluir-conta                     -> leitor         -> exclui/anonimiza a própria conta (LGPD)
  POST  /reservar/<id_livro>               -> leitor         -> reserva ou entra na fila
  POST  /renovar/<id_emprestimo>           -> leitor         -> renova empréstimo
  POST  /cancelar-reserva/<id_reserva>     -> leitor         -> cancela reserva/sai da fila
  POST  /avaliar/<id_livro>                -> leitor         -> avalia (nota 1-5 + comentário)
  POST  /configurar-notificacao/<id_livro> -> leitor         -> avisar quando disponível (sem entrar na fila)

  GET   /admin                             -> funcionário    -> dashboard.html

  --- CRUD DE LIVRO ---
  POST  /admin/livro/criar                 -> funcionário    -> CREATE
  POST  /admin/livro/<id>/editar           -> funcionário    -> UPDATE
  POST  /admin/livro/<id>/excluir          -> funcionário    -> DELETE (ou descontinua se tiver histórico)

  --- CRUD DE EXEMPLAR (cópia física de um livro) ---
  POST  /admin/exemplar/criar              -> funcionário    -> CREATE
  POST  /admin/exemplar/<id>/editar        -> funcionário    -> UPDATE (posição/status)
  POST  /admin/exemplar/<id>/excluir       -> funcionário    -> DELETE (ou marca Indisponível se tiver histórico)

  --- CRUD DE FUNCIONÁRIO (restrito ao cargo Administrador) ---
  POST  /admin/funcionario/criar           -> administrador  -> CREATE
  POST  /admin/funcionario/<id>/editar     -> administrador  -> UPDATE
  POST  /admin/funcionario/<id>/excluir    -> administrador  -> DELETE (ou inativa se tiver histórico)

  --- CRUD DE LEITOR (cadastro/gestão pelo funcionário, ex.: balcão) ---
  POST  /admin/leitor/criar                -> funcionário    -> CREATE
  POST  /admin/leitor/<id>/editar          -> funcionário    -> UPDATE (dados + status_conta)
  POST  /admin/leitor/<id>/excluir         -> funcionário    -> DELETE (ou anonimiza se tiver histórico)

  --- BALCÃO ---
  POST  /admin/balcao                      -> funcionário    -> entrega reserva / registra devolução
=============================================================================
"""

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
from flask_wtf.csrf import CSRFProtect, generate_csrf
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

# Carrega variáveis de ambiente do arquivo .env (SECRET_KEY, DB_*, TWILIO_*, etc.)
load_dotenv()

app = Flask(__name__)

# --- CONFIGURAÇÕES DE SEGURANÇA DO COOKIE DE SESSÃO ---
app.config['SESSION_COOKIE_SECURE'] = True if os.getenv('FLASK_ENV') == 'production' or os.getenv('USE_HTTPS') == 'true' else False
app.config['SESSION_COOKIE_HTTPONLY'] = True   # JS não consegue ler o cookie (proteção XSS)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'  # Proteção básica contra CSRF via cookie
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(hours=8)  # Sessão expira após 8h

secret_key = os.getenv('SECRET_KEY')
if not secret_key:
    raise ValueError("❌ ERRO DE SEGURANÇA: A variável 'SECRET_KEY' não está definida no arquivo .env!")
app.secret_key = secret_key

# --- PROTEÇÃO CSRF ---
csrf = CSRFProtect(app)

# --- RATE LIMITING ---
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=[],
    storage_uri="memory://"  # Para produção com múltiplos processos, use Redis: redis://localhost:6379
)

# --- CONFIGURAÇÃO DAS PASTAS ESTÁTICAS ---
ASSETS_FOLDER = os.path.join(app.root_path, 'assets')
CSS_FOLDER = os.path.join(app.root_path, 'css')


def get_db_connection():
    """Abre e retorna uma conexão com o banco MySQL 'bliblitech'. Retorna None em caso de falha."""
    try:
        connection = mysql.connector.connect(
            host=os.getenv('DB_HOST', 'localhost'),
            user=os.getenv('DB_USER', 'root'),
            password=os.getenv('DB_PASSWORD', ''),
            database=os.getenv('DB_NAME', 'bibliotech'),
            port=int(os.getenv('DB_PORT', 3306))
        )
        return connection
    except Error as e:
        print(f"❌ Erro ao conectar ao MySQL: {e}")
        return None


def quer_json():
    """Diz se o cliente pediu resposta em JSON (Thunder Client) via header 'Accept: application/json'."""
    return request.headers.get('Accept', '') == 'application/json'


def resposta(sucesso, mensagem, categoria='info', redirect_endpoint='home', dados_extra=None, **url_kwargs):
    """
    Padroniza a resposta das rotas de ação:
    - Cliente pediu JSON -> devolve {"sucesso": bool, "mensagem": str, ...} com status 200/400.
    - Senão -> flash() + redirect() (comportamento normal do site).
    """
    if quer_json():
        payload = {"sucesso": sucesso, "mensagem": mensagem}
        if dados_extra:
            payload.update(dados_extra)
        return jsonify(payload), (200 if sucesso else 400)

    flash(mensagem, categoria)
    return redirect(url_for(redirect_endpoint, **url_kwargs))


def eh_funcionario_logado():
    """True se há um funcionário autenticado na sessão (qualquer cargo)."""
    return 'id_funcionario' in session and session.get('tipo_usuario') == 'FUNCIONARIO'


def eh_administrador_logado():
    """
    True se o funcionário logado tem cargo 'Administrador'.
    Usado para restringir o CRUD de FUNCIONÁRIOS (só admin gerencia colegas
    de trabalho) — gerenciar livros/exemplares/leitores continua liberado
    para qualquer funcionário (bibliotecário, auxiliar etc.).
    """
    return eh_funcionario_logado() and session.get('nome_cargo') == 'Administrador'


def exigir_funcionario():
    """
    Helper de estudo: repete a checagem de acesso usada em toda rota
    /admin/*. Retorna None se pode passar, ou uma resposta de erro pronta
    (pra rota fazer `bloqueio = exigir_funcionario(); if bloqueio: return bloqueio`).
    """
    if not eh_funcionario_logado():
        return resposta(False, "Acesso negado. Área restrita a funcionários.", "danger", "home")
    return None


def exigir_administrador():
    """Igual a exigir_funcionario(), mas exige também o cargo Administrador."""
    if not eh_administrador_logado():
        return resposta(False, "Acesso negado. Ação restrita ao cargo Bibliotecario.", "danger", "admin_dashboard")
    return None


# -----------------------------------------------------------------------------
# 🔔 NOTIFICAÇÕES (fila de espera + lista de interesse)
# -----------------------------------------------------------------------------
def _cliente_twilio():
    """Cria e retorna um client Twilio se as credenciais existirem no .env, senão None."""
    account_sid = os.getenv('TWILIO_ACCOUNT_SID')
    auth_token = os.getenv('TWILIO_AUTH_TOKEN')
    if account_sid and auth_token:
        return Client(account_sid, auth_token)
    return None


def notificar_pessoa_da_fila(nome, email, telefone, mensagem):
    """
    Notificação "de serviço" para quem está na FILA DE ESPERA (não é a
    lista de interesse opcional). Quem entra na fila já deu consentimento
    implícito — é parte do próprio serviço de reserva que ele pediu — então
    mandamos por e-mail e, se houver telefone + Twilio configurado, por SMS.
    """
    if email:
        print(f"📧 [EMAIL - FILA] Para {email}: {mensagem}")
        # Lógica de e-mail real (Flask-Mail / Smtplib) — não implementada neste projeto acadêmico

    client_twilio = _cliente_twilio()
    if telefone and client_twilio:
        telefone_formatado = telefone.strip()
        if not telefone_formatado.startswith('+'):
            telefone_formatado = f"+55{telefone_formatado}"
        try:
            msg = client_twilio.messages.create(
                body=f"BibliTech: {mensagem}",
                from_=os.getenv('TWILIO_PHONE_NUMBER'),
                to=telefone_formatado
            )
            print(f"📱 [SMS - FILA] Enviado para {telefone_formatado} | SID: {msg.sid}")
        except Exception as err:
            print(f"❌ Erro ao enviar SMS de fila: {err}")


def disparar_notificacoes_disponibilidade(id_livro):
    """
    Notifica quem pediu para SER AVISADO sobre `id_livro` (tabela
    notificacoes_interesse) — usa as preferências de canal escolhidas por
    cada leitor (e-mail/SMS/WhatsApp), diferente da notificação de fila
    acima. Só deve ser chamada quando a FILA DE ESPERA está vazia (ver
    processar_exemplar_disponivel), porque enquanto há fila o exemplar
    já tem dono e não está realmente disponível ao público.
    """
    conn = get_db_connection()
    if not conn:
        return

    try:
        cursor = conn.cursor(dictionary=True)

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

        client_twilio = _cliente_twilio()
        twilio_sms_from = os.getenv('TWILIO_PHONE_NUMBER')
        twilio_whatsapp_from = os.getenv('TWILIO_WHATSAPP_NUMBER')
        mensagem_texto = f"Olá, {titulo_livro} já está disponível para retirada na biblioteca! Acesse o sistema para reservar ou vá o mais rápido possível para a biblioteca pegar o livro."

        for s in solicitacoes:
            telefone_formatado = s['telefone'].strip() if s['telefone'] else None
            if telefone_formatado and not telefone_formatado.startswith('+'):
                telefone_formatado = f"+55{telefone_formatado}"

            if s['receber_email'] and s['email']:
                print(f"📧 [EMAIL] Enviando aviso para {s['email']}...")

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

            cursor.execute("""
                UPDATE notificacoes_interesse SET status_notificacao = 'Enviado'
                WHERE id_notificacao = %s
            """, (s['id_notificacao'],))

        conn.commit()
        cursor.close()
        conn.close()

    except Exception as e:
        print("\n❌ ERRO NA EXECUÇÃO DO DISPARO TWILIO:", e, "\n")
        if conn and conn.is_connected():
            conn.close()


def recalcular_posicoes_fila(cursor, id_livro):
    """
    Recalcula a posição de todo mundo 'Pendente' na fila de um livro
    (ordenado por quem entrou primeiro) e SÓ notifica quem teve a posição
    realmente alterada desde a última notificação (compara com
    `posicao_fila_notificada`, salvo no banco). Evita notificar toda vez
    que a fila é recalculada sem mudança real para aquela pessoa.

    Chame sempre que alguém sai DA FRENTE da fila (foi promovido ou
    cancelou estando 'Pendente'), o que faz todo mundo atrás "andar".
    """
    cursor.execute("""
        SELECT r.id_reserva, r.posicao_fila_notificada, l.nome, l.email, l.telefone
        FROM reservas r
        JOIN leitores l ON r.id_leitor = l.id_leitor
        WHERE r.id_livro = %s AND r.status_reserva = 'Pendente'
        ORDER BY r.data_reserva ASC
    """, (id_livro,))
    fila_atual = cursor.fetchall()

    for posicao, pessoa in enumerate(fila_atual, start=1):
        if pessoa['posicao_fila_notificada'] != posicao:
            cursor.execute(
                "UPDATE reservas SET posicao_fila_notificada = %s WHERE id_reserva = %s",
                (posicao, pessoa['id_reserva'])
            )
            notificar_pessoa_da_fila(
                pessoa['nome'], pessoa['email'], pessoa['telefone'],
                f"Sua posição na fila de espera mudou! Agora você está em {posicao}º lugar."
            )


def processar_exemplar_disponivel(cursor, id_livro, id_exemplar):
    """
    Chamada sempre que um exemplar volta a ficar fisicamente disponível
    (devolução no balcão OU cancelamento de quem estava 'Aguardando Retirada').

    REGRA DE NEGÓCIO:
    - Se existe alguém 'Pendente' na fila desse livro, o exemplar NÃO fica
      público: é reservado para o próximo da fila, que é avisado de que
      chegou a sua vez. As posições de quem sobrou na fila são recalculadas
      e só quem mudou de posição é notificado.
    - Só quando a fila termina (ninguém mais 'Pendente') avisamos quem
      apenas pediu para SER NOTIFICADO (notificacoes_interesse), sem ter
      entrado na fila oficial — como pedido: essa notificação só dispara
      quando a lista de espera acaba.
    """
    cursor.execute("""
        SELECT r.id_reserva, r.id_leitor, l.nome, l.email, l.telefone
        FROM reservas r
        JOIN leitores l ON r.id_leitor = l.id_leitor
        WHERE r.id_livro = %s AND r.status_reserva = 'Pendente'
        ORDER BY r.data_reserva ASC LIMIT 1
    """, (id_livro,))
    proximo_da_fila = cursor.fetchone()

    if proximo_da_fila:
        cursor.execute(
            "UPDATE reservas SET status_reserva = 'Aguardando Retirada', posicao_fila_notificada = 0 WHERE id_reserva = %s",
            (proximo_da_fila['id_reserva'],)
        )
        cursor.execute(
            "UPDATE exemplares SET status_exemplar = 'Reservado' WHERE id_exemplar = %s",
            (id_exemplar,)
        )
        notificar_pessoa_da_fila(
            proximo_da_fila['nome'], proximo_da_fila['email'], proximo_da_fila['telefone'],
            "Chegou a sua vez! O livro que você esperava está reservado para você — retire na biblioteca."
        )
        recalcular_posicoes_fila(cursor, id_livro)
    else:
        # Fila vazia -> o exemplar fica realmente disponível ao público,
        # e SÓ AGORA avisamos quem só pediu notificação (sem fila).
        disparar_notificacoes_disponibilidade(id_livro)


# -----------------------------------------------------------------------------
# 🔑 CSRF TOKEN PARA TESTES (Thunder Client / Postman)
# -----------------------------------------------------------------------------
@app.route('/api/csrf-token', methods=['GET'])
def obter_csrf_token():
    """GET /api/csrf-token — copie o valor e mande como header X-CSRFToken em todo POST."""
    return jsonify({"csrf_token": generate_csrf()})


# --- ARQUIVOS ESTÁTICOS ---
@app.route('/assets/<path:filename>')
def serve_assets(filename):
    return send_from_directory(ASSETS_FOLDER, filename)


@app.route('/css/<path:filename>')
def serve_css(filename):
    return send_from_directory(CSS_FOLDER, filename)


# -----------------------------------------------------------------------------
# 🏠 HOME / INDEX (HUB CENTRALIZADO) — usa home.html -- OK
# -----------------------------------------------------------------------------
@app.route('/')
def home():
    """
    GET /
    Autenticação: nenhuma obrigatória (sessão de leitor, se houver, traz
    perfil/reservas/empréstimos). Query params: ?abrir_login=true |
    ?abrir_cadastro=true | ?aba=perfil|reservas|home
    """
    abrir_login = request.args.get('abrir_login', 'false')
    abrir_cadastro = request.args.get('abrir_cadastro', 'false')
    aba_ativa = request.args.get('aba', 'home')

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

        sql_home = '''
            SELECT l.id_livro, l.titulo, l.autor, l.capa,
                   COALESCE(AVG(a.nota), 0) AS media_notas,
                   COUNT(a.id_avaliacao) AS total_avaliacoes,
                   COUNT(CASE WHEN e.status_exemplar = 'Disponível' THEN 1 END) AS disponiveis
            FROM livro l
            LEFT JOIN avaliacoes a ON l.id_livro = a.livro_id
            LEFT JOIN exemplares e ON l.id_livro = e.id_livro
            WHERE l.status_livro = 'Ativo'
            GROUP BY l.id_livro
            ORDER BY media_notas DESC, total_avaliacoes DESC
            LIMIT 5
        '''
        cursor.execute(sql_home)
        livros_destaque = cursor.fetchall()

        if 'id_leitor' in session:
            id_leitor = session['id_leitor']

            cursor.execute("""
                SELECT id_leitor, nome, email, telefone, DATE_FORMAT(cadastro, '%d/%m/%Y') AS data_cadastro
                FROM leitores WHERE id_leitor = %s
            """, (id_leitor,))
            leitor = cursor.fetchone()

            cursor.execute("SELECT COUNT(*) AS total FROM emprestimos WHERE id_leitor = %s", (id_leitor,))
            total_historico = cursor.fetchone()['total']

            cursor.execute("SELECT COUNT(*) AS total FROM avaliacoes WHERE leitor_id = %s", (id_leitor,))
            total_avaliacoes = cursor.fetchone()['total']

            estatisticas = {
                "total_emprestimos_historico": total_historico,
                "total_avaliacoes": total_avaliacoes
            }

            # Reservas ativas — agora também mostrando a posição na fila (quando aplicável)
            sql_reservas = """
                SELECT r.id_reserva, l.id_livro, l.titulo, l.autor, l.capa, r.status_reserva,
                       r.posicao_fila_notificada,
                       DATE_FORMAT(r.data_reserva, '%d/%m/%Y %H:%i') AS data_reserva
                FROM reservas r
                JOIN livro l ON r.id_livro = l.id_livro
                WHERE r.id_leitor = %s AND r.status_reserva IN ('Pendente', 'Aguardando Retirada')
                ORDER BY r.data_reserva DESC
            """
            cursor.execute(sql_reservas, (id_leitor,))
            reservas_ativas = cursor.fetchall()

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
# 📚 CATÁLOGO & DETALHES — usa catalogo.html
# -----------------------------------------------------------------------------
@app.route('/catalogo', methods=['GET'])
def catalogo():
    """
    GET /catalogo[?busca=texto][?categoria=id]
    Autenticação: nenhuma. Livros com status_livro='Descontinuado' não
    aparecem no catálogo público (mas continuam existindo no banco, ligados
    ao histórico de empréstimos antigos).
    """
    conn = get_db_connection()
    if not conn:
        return "Erro de conexão com o banco de dados.", 500

    termo_busca = request.args.get('busca', '').strip()
    id_categoria = request.args.get('categoria', '').strip()

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute('''
            SELECT l.id_livro, l.titulo, l.autor, l.capa,
                   COUNT(CASE WHEN e.status_exemplar = 'Disponível' THEN 1 END) AS disponiveis,
                   COUNT(emp.id_emprestimo) AS total_emprestimos
            FROM livro l
            LEFT JOIN exemplares e ON l.id_livro = e.id_livro
            LEFT JOIN emprestimos emp ON e.id_exemplar = emp.id_exemplar
            WHERE l.status_livro = 'Ativo'
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
            WHERE l.status_livro = 'Ativo'
            GROUP BY l.id_livro ORDER BY total_reservas DESC, l.id_livro DESC LIMIT 5
        ''')
        mais_procurados = cursor.fetchall()

        cursor.execute('''
            SELECT l.id_livro, l.titulo, l.autor, l.capa,
                   COUNT(CASE WHEN e.status_exemplar = 'Disponível' THEN 1 END) AS disponiveis
            FROM livro l LEFT JOIN exemplares e ON l.id_livro = e.id_livro
            WHERE l.status_livro = 'Ativo'
            GROUP BY l.id_livro ORDER BY l.cadastro DESC LIMIT 5
        ''')
        lancamentos = cursor.fetchall()

        # Lista completa com busca/filtro opcional (WHERE dinâmico)
        sql_todos = '''
            SELECT l.id_livro, l.titulo, l.autor, l.capa,
                   COUNT(CASE WHEN e.status_exemplar = 'Disponível' THEN 1 END) AS disponiveis
            FROM livro l
            LEFT JOIN exemplares e ON l.id_livro = e.id_livro
        '''
        condicoes = ["l.status_livro = 'Ativo'"]
        parametros = []

        if id_categoria:
            sql_todos += " JOIN livro_categorias lc ON l.id_livro = lc.id_livro "
            condicoes.append("lc.id_categoria = %s")
            parametros.append(id_categoria)

        if termo_busca:
            condicoes.append("(l.titulo LIKE %s OR l.autor LIKE %s)")
            curinga = f"%{termo_busca}%"
            parametros.extend([curinga, curinga])

        sql_todos += " WHERE " + " AND ".join(condicoes)
        sql_todos += " GROUP BY l.id_livro ORDER BY l.titulo ASC"
        cursor.execute(sql_todos, tuple(parametros))
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
                    categorias=categorias,
                    termo_busca=termo_busca,
                    id_categoria=id_categoria
                ), 200

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO NA ROTA /catalogo:", e, "\n")
        return "Erro interno ao carregar o catálogo.", 500


@app.route('/livro/<int:id>', methods=['GET'])
def obter_detalhes_livro(id):
    """GET /livro/<id> — autenticação: nenhuma."""
    conn = get_db_connection()
    if not conn:
        return "Erro ao conectar ao banco de dados.", 500

    try:
        cursor = conn.cursor(dictionary=True)

        sql_livro = """
            SELECT l.id_livro, l.titulo, l.autor, l.ano_publicacao, l.quant_estoque, l.sinopse, l.capa,
                   l.status_livro,
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
    """
    POST /login — Body: email, senha.
    Tenta autenticar como leitor primeiro, depois como funcionário.
    Bloqueia leitor com status_conta != 'Ativo' e funcionário com
    status_funcionario != 'Ativo'.
    """
    if 'id_leitor' in session or 'id_funcionario' in session:
        return redirect(url_for('catalogo'))

    if request.method == 'GET':
        return redirect(url_for('home', abrir_login='true'))

    email = request.form.get('email', '').strip()
    senha = request.form.get('senha', '').strip()

    if not email or not senha:
        return resposta(False, "Por favor, preencha todos os campos.", "danger", "home", abrir_login='true')

    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro ao conectar ao banco de dados.", "danger", "home", abrir_login='true')

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
                return resposta(False, "Esta conta está suspensa ou bloqueada. Procure a biblioteca para regularizar.", "danger", "home", abrir_login='true')

            session.clear()
            session.permanent = True
            session['id_leitor'] = leitor['id_leitor']
            session['nome'] = leitor['nome']
            session['email'] = leitor['email']
            session['tipo_usuario'] = 'LEITOR'
            cursor.close()
            conn.close()
            return resposta(True, f"Bem-vindo(a) de volta, {leitor['nome']}!", "success", "catalogo")

        # 2. Tenta autenticar como funcionário — também traz o CARGO (join com
        #    'cargos'), necessário pro CRUD de funcionários (só Administrador).
        cursor.execute("""
            SELECT f.id_funcionario, f.nome, f.email, f.senha, f.tipo_perfil,
                   f.status_funcionario, f.id_cargo, c.nome_cargo
            FROM funcionarios f
            JOIN cargos c ON f.id_cargo = c.id_cargo
            WHERE f.email = %s
        """, (email,))
        funcionario = cursor.fetchone()
        cursor.close()
        conn.close()

        if funcionario and check_password_hash(funcionario['senha'], senha):
            if funcionario['status_funcionario'] != 'Ativo':
                return resposta(False, "Este funcionário está inativo. Procure a administração.", "danger", "home", abrir_login='true')

            session.clear()
            session.permanent = True
            session['id_funcionario'] = funcionario['id_funcionario']
            session['nome'] = funcionario['nome']
            session['email'] = funcionario['email']
            session['tipo_usuario'] = funcionario['tipo_perfil']  # 'FUNCIONARIO'
            session['id_cargo'] = funcionario['id_cargo']
            session['nome_cargo'] = funcionario['nome_cargo']     # ex.: 'Administrador', 'Bibliotecário'
            return resposta(True, f"Bem-vindo(a), {funcionario['nome']}!", "success", "admin_dashboard")

        return resposta(False, "E-mail ou senha incorretos.", "danger", "home", abrir_login='true')

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO NO LOGIN:", e, "\n")
        return resposta(False, "Erro ao processar o login.", "danger", "home", abrir_login='true')


@app.route('/cadastrar', methods=['POST'])
@limiter.limit("5 per minute")
def cadastrar():
    """POST /cadastrar (self-service) — Body: nome, email, senha, telefone, consentimento_lgpd='on'."""
    nome = request.form.get('nome', '').strip()
    email = request.form.get('email', '').strip()
    senha = request.form.get('senha', '').strip()
    telefone = request.form.get('telefone', '').strip()
    consentimento_lgpd = 1 if request.form.get('consentimento_lgpd') == 'on' else 0

    if not consentimento_lgpd:
        return resposta(False, "Você deve aceitar os termos de privacidade para criar uma conta.", "danger", "home", abrir_cadastro='true')

    if not nome or not email or not senha or not telefone:
        return resposta(False, "Por favor, preencha todos os campos.", "danger", "home", abrir_cadastro='true')

    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro ao conectar ao banco de dados.", "danger", "home", abrir_cadastro='true')

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id_leitor FROM leitores WHERE email = %s", (email,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return resposta(False, "E-mail já cadastrado.", "warning", "home", abrir_cadastro='true')

        senha_hash = generate_password_hash(senha)
        sql_insert = "INSERT INTO leitores (nome, email, senha, telefone, consentimento_lgpd) VALUES (%s, %s, %s, %s, %s)"
        cursor.execute(sql_insert, (nome, email, senha_hash, telefone, consentimento_lgpd))
        conn.commit()

        novo_id = cursor.lastrowid
        cursor.close()
        conn.close()

        session['id_leitor'] = novo_id
        session['nome'] = nome
        session['email'] = email
        session['tipo_usuario'] = 'LEITOR'

        return resposta(True, f"Conta criada com sucesso! Seja bem-vindo(a), {nome}!", "success", "catalogo")

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO NO CADASTRO:", e, "\n")
        return resposta(False, "Erro ao criar conta.", "danger", "home", abrir_cadastro='true')


@app.route('/logout')
def logout():
    """GET /logout — encerra a sessão atual (leitor ou funcionário)."""
    session.clear()
    return resposta(True, "Sessão encerrada com sucesso.", "info", "home")


# -----------------------------------------------------------------------------
# ✏️ EDIÇÃO DE PERFIL (self-service do leitor)
# -----------------------------------------------------------------------------
@app.route('/meu-perfil/editar', methods=['POST'])
def editar_perfil():
    """POST /meu-perfil/editar — leitor logado. Body: nome, telefone, nova_senha (opcional)."""
    if 'id_leitor' not in session:
        return resposta(False, "Faça login para alterar seus dados.", "warning", "home", abrir_login='true')

    id_leitor = session['id_leitor']
    nome = request.form.get('nome', '').strip()
    telefone = request.form.get('telefone', '').strip()
    nova_senha = request.form.get('nova_senha', '').strip()

    if not nome:
        return resposta(False, "O nome não pode ser vazio.", "warning", "home", aba='perfil')

    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro ao conectar ao banco de dados.", "danger", "home", aba='perfil')

    try:
        cursor = conn.cursor()
        if nova_senha:
            senha_hash = generate_password_hash(nova_senha)
            cursor.execute("UPDATE leitores SET nome = %s, telefone = %s, senha = %s WHERE id_leitor = %s",
                           (nome, telefone, senha_hash, id_leitor))
        else:
            cursor.execute("UPDATE leitores SET nome = %s, telefone = %s WHERE id_leitor = %s",
                           (nome, telefone, id_leitor))
        conn.commit()
        cursor.close()
        conn.close()

        session['nome'] = nome
        return resposta(True, "Perfil atualizado com sucesso!", "success", "home", aba='perfil')

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO AO EDITAR PERFIL:", e, "\n")
        return resposta(False, "Erro ao atualizar o perfil.", "danger", "home", aba='perfil')


# -----------------------------------------------------------------------------
# RESERVA OU ENTRAR NA FILA DE ESPERA
# -----------------------------------------------------------------------------
@app.route('/reservar/<int:id_livro>', methods=['POST'])
def reservar_livro(id_livro):
    """
    POST /reservar/<id_livro> — leitor logado.
    Body opcional: opcao_indisponivel = 'fila' | 'notificar' (só necessário
    quando NÃO há exemplar disponível).
    """
    if 'id_leitor' not in session:
        return resposta(False, "Faça login para reservar livros.", "warning", "home", abrir_login='true')

    id_leitor = session['id_leitor']
    opcao = request.form.get('opcao_indisponivel')

    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro ao conectar ao banco de dados.", "danger", "catalogo")

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT id_reserva FROM reservas
            WHERE id_leitor = %s AND id_livro = %s AND status_reserva IN ('Pendente', 'Aguardando Retirada')
        """, (id_leitor, id_livro))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return resposta(False, "Você já possui uma reserva ativa ou já está na fila deste livro.", "info", "home", aba='reservas')

        cursor.execute("""
            SELECT id_exemplar FROM exemplares
            WHERE id_livro = %s AND status_exemplar = 'Disponível' LIMIT 1
        """, (id_livro,))
        exemplar_livre = cursor.fetchone()

        # CASO 1: Há exemplar disponível -> Reserva direta (e já marca o
        # exemplar como 'Reservado', pra não deixar dois leitores contando
        # com a mesma cópia física ao mesmo tempo).
        if exemplar_livre:
            cursor.execute("""
                INSERT INTO reservas (id_leitor, id_livro, data_reserva, status_reserva)
                VALUES (%s, %s, NOW(), 'Aguardando Retirada')
            """, (id_leitor, id_livro))
            cursor.execute(
                "UPDATE exemplares SET status_exemplar = 'Reservado' WHERE id_exemplar = %s",
                (exemplar_livre['id_exemplar'],)
            )
            conn.commit()
            cursor.close()
            conn.close()
            return resposta(True, "Reserva realizada com sucesso! O livro está aguardando sua retirada na biblioteca.", "success", "home", aba='reservas')

        # CASO 2: Esgotado + leitor ainda NÃO escolheu a opção no modal
        elif not opcao:
            cursor.close()
            conn.close()
            if quer_json():
                return jsonify({
                    "sucesso": False,
                    "mensagem": "Livro esgotado. Reenvie com o campo 'opcao_indisponivel' = 'fila' ou 'notificar'.",
                    "precisa_escolher_opcao": True
                }), 409
            return redirect(url_for('obter_detalhes_livro', id=id_livro, escolher_opcao='true'))

        # CASO 3: Esgotado + leitor escolheu ENTRAR NA FILA
        elif opcao == 'fila':
            cursor.execute("SELECT COUNT(*) AS total FROM reservas WHERE id_livro = %s AND status_reserva = 'Pendente'", (id_livro,))
            posicao_inicial = cursor.fetchone()['total'] + 1

            cursor.execute("""
                INSERT INTO reservas (id_leitor, id_livro, data_reserva, status_reserva, posicao_fila_notificada)
                VALUES (%s, %s, NOW(), 'Pendente', %s)
            """, (id_leitor, id_livro, posicao_inicial))
            conn.commit()

            cursor.execute("SELECT nome, email, telefone FROM leitores WHERE id_leitor = %s", (id_leitor,))
            leitor_atual = cursor.fetchone()
            notificar_pessoa_da_fila(
                leitor_atual['nome'], leitor_atual['email'], leitor_atual['telefone'],
                f"Você entrou na fila de espera! Sua posição atual é {posicao_inicial}º."
            )
            cursor.close()
            conn.close()
            return resposta(True, f"Você foi inserido na fila de espera com sucesso! Posição atual: {posicao_inicial}º.", "info", "home", aba='reservas')

        # CASO 4: Esgotado + leitor escolheu APENAS SER NOTIFICADO (não entra na fila)
        elif opcao == 'notificar':
            cursor.execute("""
                INSERT INTO notificacoes_interesse (id_leitor, id_livro, data_solicitacao)
                VALUES (%s, %s, NOW())
                ON DUPLICATE KEY UPDATE data_solicitacao = NOW()
            """, (id_leitor, id_livro))
            conn.commit()
            cursor.close()
            conn.close()
            return resposta(True, "Aviso cadastrado! Você será notificado somente quando a fila de espera terminar e o livro ficar realmente disponível.", "success", "obter_detalhes_livro", id=id_livro)

        cursor.close()
        conn.close()
        return resposta(False, "Opção inválida.", "warning", "catalogo")

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO NA ROTA /reservar:", e, "\n")
        return resposta(False, "Erro ao processar a solicitação.", "danger", "catalogo")


@app.route('/renovar/<int:id_emprestimo>', methods=['POST'])
def renovar_emprestimo(id_emprestimo):
    """POST /renovar/<id_emprestimo> — leitor logado (dono do empréstimo). Máx. 2 renovações, +7 dias cada."""
    if 'id_leitor' not in session:
        return resposta(False, "Faça login para renovar empréstimos.", "warning", "home", abrir_login='true')

    id_leitor = session['id_leitor']
    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro ao conectar ao banco de dados.", "danger", "catalogo")

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT * FROM emprestimos
            WHERE id_emprestimo = %s AND id_leitor = %s AND status_emprestimo = 'Ativo'
        """, (id_emprestimo, id_leitor))
        emprestimo = cursor.fetchone()

        if not emprestimo:
            cursor.close()
            conn.close()
            return resposta(False, "Empréstimo não encontrado ou não é renovável.", "warning", "home", aba='reservas')

        if emprestimo['renovacoes_realizadas'] >= 2:
            cursor.close()
            conn.close()
            return resposta(False, "Você atingiu o limite de renovações para este empréstimo.", "info", "home", aba='reservas')

        nova_data_prevista = emprestimo['data_devolucao_prevista'] + timedelta(days=7)
        cursor.execute("""
            UPDATE emprestimos
            SET data_devolucao_prevista = %s, renovacoes_realizadas = renovacoes_realizadas + 1
            WHERE id_emprestimo = %s
        """, (nova_data_prevista, id_emprestimo))
        conn.commit()

        cursor.close()
        conn.close()
        return resposta(True, "Empréstimo renovado com sucesso!", "success", "home", aba='reservas')

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO AO RENOVAR EMPRÉSTIMO:", e, "\n")
        return resposta(False, "Erro ao renovar empréstimo.", "danger", "home", aba='reservas')


@app.route('/cancelar-reserva/<int:id_reserva>', methods=['POST'])
def cancelar_reserva(id_reserva):
    """
    POST /cancelar-reserva/<id_reserva> — leitor logado (dono da reserva).

    NOVO comportamento:
    - Se a reserva estava 'Pendente' (na fila): ao sair, todo mundo atrás
      dela na fila "anda" uma posição; recalculamos e notificamos só quem
      mudou de posição.
    - Se a reserva estava 'Aguardando Retirada' (exemplar já reservado pra
      ela): o exemplar volta a ficar disponível, o que dispara a MESMA regra
      de negócio de uma devolução (promove o próximo da fila, ou — se a fila
      estiver vazia — avisa a lista de interesse).
    """
    if 'id_leitor' not in session:
        return resposta(False, "Faça login para cancelar reservas.", "warning", "home", abrir_login='true')

    id_leitor = session['id_leitor']
    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro ao conectar ao banco de dados.", "danger", "catalogo")

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT * FROM reservas
            WHERE id_reserva = %s AND id_leitor = %s AND status_reserva IN ('Pendente', 'Aguardando Retirada')
        """, (id_reserva, id_leitor))
        reserva = cursor.fetchone()

        if not reserva:
            cursor.close()
            conn.close()
            return resposta(False, "Reserva não encontrada ou não pode ser cancelada.", "warning", "home", aba='reservas')

        status_anterior = reserva['status_reserva']
        id_livro = reserva['id_livro']

        cursor.execute("UPDATE reservas SET status_reserva = 'Cancelada' WHERE id_reserva = %s", (id_reserva,))

        if status_anterior == 'Pendente':
            # Saiu da fila: recalcula e notifica quem mudou de posição.
            recalcular_posicoes_fila(cursor, id_livro)

        elif status_anterior == 'Aguardando Retirada':
            # O exemplar que estava reservado pra essa pessoa volta ao jogo.
            # Simplificação acadêmica: como não guardamos qual exemplar
            # exato está ligado a cada reserva, pegamos qualquer exemplar
            # 'Reservado' desse livro (na prática, com 1 exemplar por
            # reserva pendente isso é sempre o certo).
            cursor.execute("""
                SELECT id_exemplar FROM exemplares
                WHERE id_livro = %s AND status_exemplar = 'Reservado' LIMIT 1
            """, (id_livro,))
            exemplar_liberado = cursor.fetchone()
            if exemplar_liberado:
                processar_exemplar_disponivel(cursor, id_livro, exemplar_liberado['id_exemplar'])
            else:
                # Não achou exemplar 'Reservado' vinculado — só libera como Disponível.
                pass

        conn.commit()
        cursor.close()
        conn.close()
        return resposta(True, "Reserva cancelada com sucesso.", "success", "home", aba='reservas')

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO AO CANCELAR RESERVA:", e, "\n")
        return resposta(False, "Erro ao cancelar reserva.", "danger", "home", aba='reservas')


@app.route('/avaliar/<int:id_livro>', methods=['POST'])
def avaliar_livro(id_livro):
    """POST /avaliar/<id_livro> — leitor logado. Body: nota (1-5), comentario (opcional)."""
    if 'id_leitor' not in session:
        return resposta(False, "Faça login para avaliar livros.", "warning", "home", abrir_login='true')

    id_leitor = session['id_leitor']
    nota = request.form.get('nota')
    comentario = request.form.get('comentario', '').strip()

    if not nota or not nota.isdigit() or int(nota) < 1 or int(nota) > 5:
        return resposta(False, "Nota inválida. Escolha entre 1 e 5.", "warning", "obter_detalhes_livro", id=id_livro)

    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro ao conectar ao banco de dados.", "danger", "obter_detalhes_livro", id=id_livro)

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT * FROM avaliacoes WHERE livro_id = %s AND leitor_id = %s", (id_livro, id_leitor))
        avaliacao_existente = cursor.fetchone()

        if avaliacao_existente:
            cursor.execute("""
                UPDATE avaliacoes SET nota = %s, comentario = %s, data_avaliacao = NOW()
                WHERE livro_id = %s AND leitor_id = %s
            """, (nota, comentario, id_livro, id_leitor))
            mensagem = "Avaliação atualizada com sucesso!"
        else:
            cursor.execute("""
                INSERT INTO avaliacoes (livro_id, leitor_id, nota, comentario, data_avaliacao)
                VALUES (%s, %s, %s, %s, NOW())
            """, (id_livro, id_leitor, nota, comentario))
            mensagem = "Avaliação registrada com sucesso!"

        conn.commit()
        cursor.close()
        conn.close()
        return resposta(True, mensagem, "success", "obter_detalhes_livro", id=id_livro)

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO AO AVALIAR LIVRO:", e, "\n")
        return resposta(False, "Erro ao registrar avaliação.", "danger", "obter_detalhes_livro", id=id_livro)


@app.route('/configurar-notificacao/<int:id_livro>', methods=['POST'])
def configurar_notificacao(id_livro):
    """
    POST /configurar-notificacao/<id_livro> — leitor logado.
    Body: consentimento_lgpd='on' (obrigatório), receber_email/receber_whatsapp/receber_sms='on' (opcionais).
    Lembrete: essa notificação só dispara quando a fila de espera do livro
    estiver vazia (ver processar_exemplar_disponivel).
    """
    if 'id_leitor' not in session:
        return resposta(False, "Faça login para configurar notificações.", "warning", "home", abrir_login='true')

    id_leitor = session['id_leitor']
    consentimento = 1 if request.form.get('consentimento_lgpd') == 'on' else 0

    if not consentimento:
        return resposta(False, "Você precisa aceitar os termos de uso de dados para receber notificações automáticas.", "warning", "obter_detalhes_livro", id=id_livro)

    receber_email = 1 if request.form.get('receber_email') == 'on' else 0
    receber_whatsapp = 1 if request.form.get('receber_whatsapp') == 'on' else 0
    receber_sms = 1 if request.form.get('receber_sms') == 'on' else 0

    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro ao conectar ao banco de dados.", "danger", "obter_detalhes_livro", id=id_livro)

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
        return resposta(True, "Preferência de notificação salva com sucesso!", "success", "obter_detalhes_livro", id=id_livro)
    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("❌ Erro ao configurar notificação:", e)
        return resposta(False, "Erro ao salvar preferências.", "danger", "obter_detalhes_livro", id=id_livro)


# -----------------------------------------------------------------------------
# 🗑️ EXCLUSÃO/ANONIMIZAÇÃO DE LEITOR (compartilhada entre self-service e admin)
# -----------------------------------------------------------------------------
def excluir_ou_anonimizar_leitor(cursor, conn, id_leitor):
    """
    Função auxiliar (não é rota) usada tanto por /excluir-conta (o próprio
    leitor se excluindo) quanto por /admin/leitor/<id>/excluir (funcionário
    excluindo um leitor pelo balcão). Retorna (sucesso: bool, mensagem: str).

    Regra: bloqueia se houver empréstimo ATIVO. Tenta excluir de verdade;
    se houver histórico de empréstimos já devolvidos (FK RESTRICT), anonimiza
    os dados pessoais em vez de apagar (LGPD: direito à eliminação + dever
    legal de manter o histórico contábil da biblioteca).
    """
    cursor.execute("""
        SELECT COUNT(*) AS total FROM emprestimos
        WHERE id_leitor = %s AND status_emprestimo = 'Ativo'
    """, (id_leitor,))
    if cursor.fetchone()['total'] > 0:
        return False, "⚠️ Não é possível excluir: existem empréstimos ativos vinculados a este leitor. Realize a devolução dos livros antes."

    cursor.execute("DELETE FROM notificacoes_interesse WHERE id_leitor = %s", (id_leitor,))
    cursor.execute("DELETE FROM reservas WHERE id_leitor = %s", (id_leitor,))

    try:
        cursor.execute("DELETE FROM leitores WHERE id_leitor = %s", (id_leitor,))
        conn.commit()
        return True, "Conta e dados excluídos com sucesso."
    except mysql.connector.Error as err:
        conn.rollback()
        if err.errno == 1451:
            email_anonimizado = f"removido+{id_leitor}@anonimizado.bibliotech"
            senha_invalidada = generate_password_hash(secrets.token_hex(16))
            cursor.execute("""
                UPDATE leitores
                SET nome = 'Usuário Removido', email = %s, telefone = 'ANONIMIZADO',
                    senha = %s, foto_perfil = 'default_profile.png', status_conta = 'Bloqueado'
                WHERE id_leitor = %s
            """, (email_anonimizado, senha_invalidada, id_leitor))
            conn.commit()
            return True, "Dados pessoais anonimizados (histórico de empréstimos precisa ser mantido por obrigação legal)."
        else:
            print("\n❌ ERRO SQL AO EXCLUIR LEITOR:", err, "\n")
            return False, "Não foi possível excluir devido a um erro interno no banco de dados."


@app.route('/excluir-conta', methods=['POST'])
def excluir_conta():
    """POST /excluir-conta (self-service) — leitor logado exclui/anonimiza a própria conta."""
    if 'id_leitor' not in session:
        return resposta(False, "Faça login para excluir sua conta.", "warning", "home", abrir_login='true')

    id_leitor = session['id_leitor']
    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro ao conectar ao banco de dados.", "danger", "home")

    try:
        cursor = conn.cursor(dictionary=True)
        sucesso, mensagem = excluir_ou_anonimizar_leitor(cursor, conn, id_leitor)
        cursor.close()
        conn.close()

        if sucesso:
            session.clear()
        return resposta(sucesso, mensagem, "info" if sucesso else "warning", "home")

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO GERAL AO EXCLUIR CONTA:", e, "\n")
        return resposta(False, "Erro inesperado ao processar a exclusão da conta.", "danger", "home")


# -----------------------------------------------------------------------------
# 📦 EXPORTAÇÃO DE DADOS (PORTABILIDADE LGPD)
# -----------------------------------------------------------------------------
@app.route('/meu-perfil/exportar-dados', methods=['GET'])
def exportar_dados_lgpd():
    """GET /meu-perfil/exportar-dados — leitor logado. Retorna JSON para download."""
    if 'id_leitor' not in session:
        return resposta(False, "Faça login para exportar seus dados.", "warning", "home", abrir_login='true')

    id_leitor = session['id_leitor']
    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro ao conectar ao banco de dados.", "danger", "home", aba='perfil')

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT nome, email, telefone, cadastro, consentimento_lgpd
            FROM leitores WHERE id_leitor = %s
        """, (id_leitor,))
        dados_leitor = cursor.fetchone()

        cursor.execute("""
            SELECT l.titulo, emp.data_emprestimo, emp.data_devolucao_prevista, emp.status_emprestimo
            FROM emprestimos emp
            JOIN exemplares ex ON emp.id_exemplar = ex.id_exemplar
            JOIN livro l ON ex.id_livro = l.id_livro
            WHERE emp.id_leitor = %s
        """, (id_leitor,))
        emprestimos = cursor.fetchall()

        cursor.execute("""
            SELECT l.titulo, a.nota, a.comentario, a.data_avaliacao
            FROM avaliacoes a
            JOIN livro l ON a.livro_id = l.id_livro
            WHERE a.leitor_id = %s
        """, (id_leitor,))
        avaliacoes = cursor.fetchall()

        cursor.execute("""
            SELECT l.titulo, r.data_reserva, r.status_reserva
            FROM reservas r
            JOIN livro l ON r.id_livro = l.id_livro
            WHERE r.id_leitor = %s
        """, (id_leitor,))
        reservas = cursor.fetchall()

        cursor.close()
        conn.close()

        relatorio_lgpd = {
            "controlador": "BibliTech",
            "titular": dados_leitor,
            "historico_emprestimos": emprestimos,
            "avaliacoes_livros": avaliacoes,
            "reservas_e_filas": reservas
        }

        response = jsonify(relatorio_lgpd)
        response.headers["Content-Disposition"] = "attachment; filename=meus_dados_biblioteca.json"
        return response

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO AO EXPORTAR DADOS:", e, "\n")
        return resposta(False, "Erro ao gerar arquivo de portabilidade de dados.", "danger", "home", aba='perfil')


# -----------------------------------------------------------------------------
# 🛠️ MÓDULO ADMINISTRATIVO — usa dashboard.html
# -----------------------------------------------------------------------------
def carregar_dados_dashboard_admin(cursor):
    """Função auxiliar (não é rota): carrega todos os dados do painel do funcionário de uma vez."""
    cursor.execute("SELECT COUNT(*) AS total FROM livro WHERE status_livro = 'Ativo'")
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

    cursor.execute("""
        SELECT r.id_reserva, r.data_reserva, l.nome AS leitor, liv.titulo, liv.id_livro
        FROM reservas r
        JOIN leitores l ON r.id_leitor = l.id_leitor
        JOIN livro liv ON r.id_livro = liv.id_livro
        WHERE r.status_reserva = 'Aguardando Retirada'
    """)
    reservas_retirada = cursor.fetchall()

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

    # Acervo — agora inclui status_livro e a lista de id_exemplar (pra
    # dashboard.html oferecer os botões de editar/excluir do CRUD)
    cursor.execute("""
        SELECT l.id_livro, l.titulo, l.autor, l.ano_publicacao, l.status_livro,
               GROUP_CONCAT(ex.posicao_estante SEPARATOR ', ') as estantes
        FROM livro l
        LEFT JOIN exemplares ex ON l.id_livro = ex.id_livro
        GROUP BY l.id_livro
        ORDER BY l.id_livro DESC
    """)
    acervo = cursor.fetchall()

    # Exemplares — lista "achatada" (1 linha por cópia física) pro CRUD de exemplar
    cursor.execute("""
        SELECT ex.id_exemplar, ex.id_livro, l.titulo, ex.posicao_estante, ex.status_exemplar
        FROM exemplares ex
        JOIN livro l ON ex.id_livro = l.id_livro
        ORDER BY l.titulo ASC, ex.id_exemplar ASC
    """)
    exemplares_todos = cursor.fetchall()

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

    # NOVO: lista de funcionários (pro CRUD de funcionário)
    cursor.execute("""
        SELECT f.id_funcionario, f.nome, f.email, f.telefone, f.status_funcionario, c.nome_cargo
        FROM funcionarios f
        JOIN cargos c ON f.id_cargo = c.id_cargo
        ORDER BY f.nome ASC
    """)
    funcionarios = cursor.fetchall()

    # NOVO: lista de leitores (pro CRUD de leitor)
    cursor.execute("""
        SELECT id_leitor, nome, email, telefone, status_conta,
               DATE_FORMAT(data_cadastro, '%d/%m/%Y') AS data_cadastro
        FROM leitores ORDER BY nome ASC
    """)
    leitores = cursor.fetchall()

    return {
        "estatisticas": estatisticas,
        "reservas": reservas_retirada,
        "emprestimos": emprestimos_ativos,
        "acervo": acervo,
        "exemplares": exemplares_todos,
        "atrasos": atrasos,
        "funcionarios": funcionarios,
        "leitores": leitores
    }


@app.route('/admin', methods=['GET'])
def admin_dashboard():
    """GET /admin — funcionário logado. Mostra métricas, balcão, acervo e os CRUDs (livro/exemplar/funcionário/leitor)."""
    bloqueio = exigir_funcionario()
    if bloqueio:
        return bloqueio

    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro ao conectar ao banco de dados.", "danger", "home")

    try:
        cursor = conn.cursor(dictionary=True)
        dados = carregar_dados_dashboard_admin(cursor)
        cursor.close()
        conn.close()

        if quer_json():
            dados["eh_administrador"] = eh_administrador_logado()
            return jsonify(dados)

        aba_ativa = request.args.get('aba', 'metricas')

        return render_template(
            'dashboard.html',
            estatisticas=dados['estatisticas'],
            reservas=dados['reservas'],
            emprestimos=dados['emprestimos'],
            acervo=dados['acervo'],
            exemplares=dados['exemplares'],
            atrasos=dados['atrasos'],
            funcionarios=dados['funcionarios'],
            leitores=dados['leitores'],
            eh_administrador=eh_administrador_logado(),
            aba_ativa=aba_ativa
        )

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO NO DASHBOARD ADMIN:", e, "\n")
        return resposta(False, "Erro ao carregar o painel administrativo.", "danger", "home")


@app.route('/admin/balcao', methods=['POST'])
def admin_balcao():
    """
    POST /admin/balcao — funcionário logado.
    Body: acao = 'entregar_reserva' (id_reserva, id_exemplar) | 'registrar_devolucao' (id_emprestimo, id_exemplar).
    Ao registrar devolução, usa processar_exemplar_disponivel() para
    promover a fila de espera ou avisar a lista de interesse (fila vazia).
    """
    bloqueio = exigir_funcionario()
    if bloqueio:
        return bloqueio

    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro de conexão.", "danger", "admin_dashboard")

    try:
        cursor = conn.cursor(dictionary=True)
        acao = request.form.get('acao')
        id_funcionario = session['id_funcionario']

        if acao == 'entregar_reserva':
            id_reserva = request.form.get('id_reserva')
            id_exemplar = request.form.get('id_exemplar')

            cursor.execute("SELECT id_leitor, id_livro FROM reservas WHERE id_reserva = %s", (id_reserva,))
            reserva = cursor.fetchone()

            if not reserva:
                cursor.close()
                conn.close()
                return resposta(False, "Reserva não encontrada.", "warning", "admin_dashboard", aba='balcao')

            cursor.execute("""
                INSERT INTO emprestimos (id_leitor, id_exemplar, id_funcionario, data_emprestimo, data_devolucao_prevista, status_emprestimo)
                VALUES (%s, %s, %s, NOW(), DATE_ADD(NOW(), INTERVAL 14 DAY), 'Ativo')
            """, (reserva['id_leitor'], id_exemplar, id_funcionario))

            cursor.execute("UPDATE reservas SET status_reserva = 'Concluida' WHERE id_reserva = %s", (id_reserva,))
            cursor.execute("UPDATE exemplares SET status_exemplar = 'Emprestado' WHERE id_exemplar = %s", (id_exemplar,))

            conn.commit()
            cursor.close()
            conn.close()
            return resposta(True, "Empréstimo registrado com sucesso no balcão!", "success", "admin_dashboard", aba='balcao')

        elif acao == 'registrar_devolucao':
            id_emprestimo = request.form.get('id_emprestimo')
            id_exemplar = request.form.get('id_exemplar')

            cursor.execute("UPDATE emprestimos SET status_emprestimo = 'Devolvido', data_devolucao_real = NOW() WHERE id_emprestimo = %s", (id_emprestimo,))
            cursor.execute("UPDATE exemplares SET status_exemplar = 'Disponível' WHERE id_exemplar = %s", (id_exemplar,))

            cursor.execute("SELECT id_livro FROM exemplares WHERE id_exemplar = %s", (id_exemplar,))
            ex = cursor.fetchone()
            if ex:
                processar_exemplar_disponivel(cursor, ex['id_livro'], id_exemplar)

            conn.commit()
            cursor.close()
            conn.close()
            return resposta(True, "Devolução registrada com sucesso! O exemplar voltou a ficar disponível (ou foi reservado para o próximo da fila).", "success", "admin_dashboard", aba='balcao')

        cursor.close()
        conn.close()
        return resposta(False, "Ação inválida.", "warning", "admin_dashboard", aba='balcao')

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO NO BALCÃO:", e, "\n")
        return resposta(False, "Erro ao processar operações no balcão.", "danger", "admin_dashboard", aba='balcao')


# =============================================================================
# 📖 CRUD DE LIVRO
# =============================================================================
@app.route('/admin/livro/criar', methods=['POST'])
def admin_criar_livro():
    """
    POST /admin/livro/criar — funcionário logado.
    Body: titulo, autor (obrigatórios); ano_publicacao, sinopse, capa,
    posicao_estante (opcionais — se enviado, já cria o 1º exemplar junto).
    """
    bloqueio = exigir_funcionario()
    if bloqueio:
        return bloqueio

    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro de conexão.", "danger", "admin_dashboard")

    try:
        cursor = conn.cursor(dictionary=True)

        titulo = request.form.get('titulo', '').strip()
        autor = request.form.get('autor', '').strip()
        ano = request.form.get('ano_publicacao')
        sinopse = request.form.get('sinopse', '').strip()
        capa = request.form.get('capa', '').strip()
        posicao_estante = request.form.get('posicao_estante', '').strip()

        if not titulo or not autor:
            cursor.close()
            conn.close()
            return resposta(False, "Título e autor são obrigatórios.", "warning", "admin_dashboard", aba='acervo')

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
        cursor.close()
        conn.close()
        return resposta(True, "Livro cadastrado com sucesso no acervo!", "success", "admin_dashboard", aba='acervo', dados_extra={"id_livro": id_novo_livro})

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO AO CRIAR LIVRO:", e, "\n")
        return resposta(False, "Erro ao cadastrar o livro.", "danger", "admin_dashboard", aba='acervo')


@app.route('/admin/livro/<int:id_livro>/editar', methods=['POST'])
def admin_editar_livro(id_livro):
    """POST /admin/livro/<id>/editar — funcionário logado. Body: titulo, autor, ano_publicacao, sinopse, capa."""
    bloqueio = exigir_funcionario()
    if bloqueio:
        return bloqueio

    titulo = request.form.get('titulo', '').strip()
    autor = request.form.get('autor', '').strip()
    ano = request.form.get('ano_publicacao')
    sinopse = request.form.get('sinopse', '').strip()
    capa = request.form.get('capa', '').strip()

    if not titulo or not autor:
        return resposta(False, "Título e autor são obrigatórios.", "warning", "admin_dashboard", aba='acervo')

    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro de conexão.", "danger", "admin_dashboard")

    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE livro SET titulo = %s, autor = %s, ano_publicacao = %s, sinopse = %s, capa = %s
            WHERE id_livro = %s
        """, (titulo, autor, ano, sinopse, capa, id_livro))
        conn.commit()
        linhas_afetadas = cursor.rowcount
        cursor.close()
        conn.close()

        if linhas_afetadas == 0:
            return resposta(False, "Livro não encontrado.", "warning", "admin_dashboard", aba='acervo')
        return resposta(True, "Livro atualizado com sucesso!", "success", "admin_dashboard", aba='acervo')

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO AO EDITAR LIVRO:", e, "\n")
        return resposta(False, "Erro ao atualizar o livro.", "danger", "admin_dashboard", aba='acervo')


@app.route('/admin/livro/<int:id_livro>/excluir', methods=['POST'])
def admin_excluir_livro(id_livro):
    """
    POST /admin/livro/<id>/excluir — funcionário logado.
    Tenta excluir de verdade. Se o livro tiver histórico de empréstimos
    (bloqueado por FK RESTRICT em emprestimos->exemplares), em vez de travar
    para sempre, marca status_livro='Descontinuado' (some do catálogo
    público, mas o histórico continua íntegro).
    """
    bloqueio = exigir_funcionario()
    if bloqueio:
        return bloqueio

    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro de conexão.", "danger", "admin_dashboard")

    try:
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM livro WHERE id_livro = %s", (id_livro,))
            conn.commit()
            cursor.close()
            conn.close()
            return resposta(True, "Livro excluído com sucesso.", "success", "admin_dashboard", aba='acervo')
        except mysql.connector.Error as err:
            conn.rollback()
            if err.errno == 1451:
                cursor.execute("UPDATE livro SET status_livro = 'Descontinuado' WHERE id_livro = %s", (id_livro,))
                conn.commit()
                cursor.close()
                conn.close()
                return resposta(True, "Este livro tem histórico de empréstimos e não pode ser apagado, então foi marcado como Descontinuado (some do catálogo público).", "info", "admin_dashboard", aba='acervo')
            cursor.close()
            conn.close()
            print("\n❌ ERRO SQL AO EXCLUIR LIVRO:", err, "\n")
            return resposta(False, "Não foi possível excluir o livro.", "danger", "admin_dashboard", aba='acervo')

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO AO EXCLUIR LIVRO:", e, "\n")
        return resposta(False, "Erro ao excluir o livro.", "danger", "admin_dashboard", aba='acervo')


# =============================================================================
# 📗 CRUD DE EXEMPLAR (cópia física de um livro)
# =============================================================================
@app.route('/admin/exemplar/criar', methods=['POST'])
def admin_criar_exemplar():
    """POST /admin/exemplar/criar — funcionário logado. Body: id_livro, posicao_estante."""
    bloqueio = exigir_funcionario()
    if bloqueio:
        return bloqueio

    id_livro = request.form.get('id_livro')
    posicao_estante = request.form.get('posicao_estante', '').strip()

    if not id_livro:
        return resposta(False, "Informe o id_livro.", "warning", "admin_dashboard", aba='acervo')

    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro de conexão.", "danger", "admin_dashboard")

    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO exemplares (id_livro, posicao_estante, status_exemplar)
            VALUES (%s, %s, 'Disponível')
        """, (id_livro, posicao_estante))
        conn.commit()
        novo_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return resposta(True, "Novo exemplar cadastrado com sucesso!", "success", "admin_dashboard", aba='acervo', dados_extra={"id_exemplar": novo_id})

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO AO CRIAR EXEMPLAR:", e, "\n")
        return resposta(False, "Erro ao cadastrar o exemplar (verifique se o id_livro existe).", "danger", "admin_dashboard", aba='acervo')


@app.route('/admin/exemplar/<int:id_exemplar>/editar', methods=['POST'])
def admin_editar_exemplar(id_exemplar):
    """
    POST /admin/exemplar/<id>/editar — funcionário logado.
    Body: posicao_estante, status_exemplar ('Disponível'|'Emprestado'|'Reservado'|'Indisponível').
    Se o status for alterado manualmente PARA 'Disponível' (ex.: voltou de
    manutenção), isso também é tratado como "exemplar ficou disponível" —
    então dispara a mesma regra de fila/notificação de uma devolução.
    """
    bloqueio = exigir_funcionario()
    if bloqueio:
        return bloqueio

    posicao_estante = request.form.get('posicao_estante', '').strip()
    novo_status = request.form.get('status_exemplar', '').strip()
    status_validos = {'Disponível', 'Emprestado', 'Reservado', 'Indisponível'}

    if novo_status and novo_status not in status_validos:
        return resposta(False, f"Status inválido. Use um de: {', '.join(status_validos)}.", "warning", "admin_dashboard", aba='acervo')

    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro de conexão.", "danger", "admin_dashboard")

    try:
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id_livro, status_exemplar FROM exemplares WHERE id_exemplar = %s", (id_exemplar,))
        exemplar_atual = cursor.fetchone()
        if not exemplar_atual:
            cursor.close()
            conn.close()
            return resposta(False, "Exemplar não encontrado.", "warning", "admin_dashboard", aba='acervo')

        status_antigo = exemplar_atual['status_exemplar']

        campos = []
        valores = []
        if posicao_estante:
            campos.append("posicao_estante = %s")
            valores.append(posicao_estante)
        if novo_status:
            campos.append("status_exemplar = %s")
            valores.append(novo_status)

        if not campos:
            cursor.close()
            conn.close()
            return resposta(False, "Nada para atualizar.", "warning", "admin_dashboard", aba='acervo')

        valores.append(id_exemplar)
        cursor.execute(f"UPDATE exemplares SET {', '.join(campos)} WHERE id_exemplar = %s", tuple(valores))

        if novo_status == 'Disponível' and status_antigo != 'Disponível':
            processar_exemplar_disponivel(cursor, exemplar_atual['id_livro'], id_exemplar)

        conn.commit()
        cursor.close()
        conn.close()
        return resposta(True, "Exemplar atualizado com sucesso!", "success", "admin_dashboard", aba='acervo')

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO AO EDITAR EXEMPLAR:", e, "\n")
        return resposta(False, "Erro ao atualizar o exemplar.", "danger", "admin_dashboard", aba='acervo')


@app.route('/admin/exemplar/<int:id_exemplar>/excluir', methods=['POST'])
def admin_excluir_exemplar(id_exemplar):
    """
    POST /admin/exemplar/<id>/excluir — funcionário logado.
    Tenta excluir de verdade; se tiver histórico de empréstimos (FK RESTRICT),
    marca status_exemplar='Indisponível' em vez de travar (não precisa de
    coluna nova, o enum já tem esse valor).
    """
    bloqueio = exigir_funcionario()
    if bloqueio:
        return bloqueio

    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro de conexão.", "danger", "admin_dashboard")

    try:
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM exemplares WHERE id_exemplar = %s", (id_exemplar,))
            conn.commit()
            cursor.close()
            conn.close()
            return resposta(True, "Exemplar excluído com sucesso.", "success", "admin_dashboard", aba='acervo')
        except mysql.connector.Error as err:
            conn.rollback()
            if err.errno == 1451:
                cursor.execute("UPDATE exemplares SET status_exemplar = 'Indisponível' WHERE id_exemplar = %s", (id_exemplar,))
                conn.commit()
                cursor.close()
                conn.close()
                return resposta(True, "Este exemplar tem histórico de empréstimos e não pode ser apagado, então foi marcado como Indisponível.", "info", "admin_dashboard", aba='acervo')
            cursor.close()
            conn.close()
            print("\n❌ ERRO SQL AO EXCLUIR EXEMPLAR:", err, "\n")
            return resposta(False, "Não foi possível excluir o exemplar.", "danger", "admin_dashboard", aba='acervo')

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO AO EXCLUIR EXEMPLAR:", e, "\n")
        return resposta(False, "Erro ao excluir o exemplar.", "danger", "admin_dashboard", aba='acervo')


# =============================================================================
# 👔 CRUD DE FUNCIONÁRIO (restrito ao cargo Administrador)
# =============================================================================
@app.route('/admin/funcionario/criar', methods=['POST'])
def admin_criar_funcionario():
    """POST /admin/funcionario/criar — só Administrador. Body: nome, email, telefone, senha, id_cargo."""
    bloqueio = exigir_administrador()
    if bloqueio:
        return bloqueio

    nome = request.form.get('nome', '').strip()
    email = request.form.get('email', '').strip()
    telefone = request.form.get('telefone', '').strip()
    senha = request.form.get('senha', '').strip()
    id_cargo = request.form.get('id_cargo')

    if not nome or not email or not telefone or not senha or not id_cargo:
        return resposta(False, "Preencha nome, email, telefone, senha e id_cargo.", "warning", "admin_dashboard", aba='funcionarios')

    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro de conexão.", "danger", "admin_dashboard")

    try:
        cursor = conn.cursor()

        cursor.execute("SELECT id_funcionario FROM funcionarios WHERE email = %s", (email,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return resposta(False, "Já existe um funcionário com este e-mail.", "warning", "admin_dashboard", aba='funcionarios')

        senha_hash = generate_password_hash(senha)
        cursor.execute("""
            INSERT INTO funcionarios (nome, id_cargo, email, telefone, senha, tipo_perfil)
            VALUES (%s, %s, %s, %s, %s, 'FUNCIONARIO')
        """, (nome, id_cargo, email, telefone, senha_hash))
        conn.commit()
        novo_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return resposta(True, "Funcionário cadastrado com sucesso!", "success", "admin_dashboard", aba='funcionarios', dados_extra={"id_funcionario": novo_id})

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO AO CRIAR FUNCIONÁRIO:", e, "\n")
        return resposta(False, "Erro ao cadastrar funcionário (verifique se o id_cargo existe).", "danger", "admin_dashboard", aba='funcionarios')


@app.route('/admin/funcionario/<int:id_funcionario>/editar', methods=['POST'])
def admin_editar_funcionario(id_funcionario):
    """POST /admin/funcionario/<id>/editar — só Administrador. Body: nome, telefone, id_cargo, status_funcionario, nova_senha (opcional)."""
    bloqueio = exigir_administrador()
    if bloqueio:
        return bloqueio

    nome = request.form.get('nome', '').strip()
    telefone = request.form.get('telefone', '').strip()
    id_cargo = request.form.get('id_cargo')
    status_funcionario = request.form.get('status_funcionario', '').strip()
    nova_senha = request.form.get('nova_senha', '').strip()

    if not nome or not telefone or not id_cargo:
        return resposta(False, "Preencha nome, telefone e id_cargo.", "warning", "admin_dashboard", aba='funcionarios')

    if status_funcionario and status_funcionario not in ('Ativo', 'Inativo'):
        return resposta(False, "status_funcionario deve ser 'Ativo' ou 'Inativo'.", "warning", "admin_dashboard", aba='funcionarios')

    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro de conexão.", "danger", "admin_dashboard")

    try:
        cursor = conn.cursor()

        if nova_senha:
            senha_hash = generate_password_hash(nova_senha)
            cursor.execute("""
                UPDATE funcionarios SET nome = %s, telefone = %s, id_cargo = %s,
                       status_funcionario = COALESCE(NULLIF(%s, ''), status_funcionario), senha = %s
                WHERE id_funcionario = %s
            """, (nome, telefone, id_cargo, status_funcionario, senha_hash, id_funcionario))
        else:
            cursor.execute("""
                UPDATE funcionarios SET nome = %s, telefone = %s, id_cargo = %s,
                       status_funcionario = COALESCE(NULLIF(%s, ''), status_funcionario)
                WHERE id_funcionario = %s
            """, (nome, telefone, id_cargo, status_funcionario, id_funcionario))

        conn.commit()
        linhas_afetadas = cursor.rowcount
        cursor.close()
        conn.close()

        if linhas_afetadas == 0:
            return resposta(False, "Funcionário não encontrado.", "warning", "admin_dashboard", aba='funcionarios')
        return resposta(True, "Funcionário atualizado com sucesso!", "success", "admin_dashboard", aba='funcionarios')

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO AO EDITAR FUNCIONÁRIO:", e, "\n")
        return resposta(False, "Erro ao atualizar funcionário.", "danger", "admin_dashboard", aba='funcionarios')


@app.route('/admin/funcionario/<int:id_funcionario>/excluir', methods=['POST'])
def admin_excluir_funcionario(id_funcionario):
    """
    POST /admin/funcionario/<id>/excluir — só Administrador.
    Tenta excluir de verdade; se ele já processou algum empréstimo (FK
    RESTRICT em emprestimos->funcionarios), marca status_funcionario='Inativo'
    em vez de travar (ele também não consegue mais logar, ver login()).
    """
    bloqueio = exigir_administrador()
    if bloqueio:
        return bloqueio

    if id_funcionario == session.get('id_funcionario'):
        return resposta(False, "Você não pode excluir a si mesmo enquanto estiver logado.", "warning", "admin_dashboard", aba='funcionarios')

    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro de conexão.", "danger", "admin_dashboard")

    try:
        cursor = conn.cursor()
        try:
            cursor.execute("DELETE FROM funcionarios WHERE id_funcionario = %s", (id_funcionario,))
            conn.commit()
            cursor.close()
            conn.close()
            return resposta(True, "Funcionário excluído com sucesso.", "success", "admin_dashboard", aba='funcionarios')
        except mysql.connector.Error as err:
            conn.rollback()
            if err.errno == 1451:
                cursor.execute("UPDATE funcionarios SET status_funcionario = 'Inativo' WHERE id_funcionario = %s", (id_funcionario,))
                conn.commit()
                cursor.close()
                conn.close()
                return resposta(True, "Este funcionário já processou empréstimos e não pode ser apagado, então foi marcado como Inativo (não consegue mais logar).", "info", "admin_dashboard", aba='funcionarios')
            cursor.close()
            conn.close()
            print("\n❌ ERRO SQL AO EXCLUIR FUNCIONÁRIO:", err, "\n")
            return resposta(False, "Não foi possível excluir o funcionário.", "danger", "admin_dashboard", aba='funcionarios')

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO AO EXCLUIR FUNCIONÁRIO:", e, "\n")
        return resposta(False, "Erro ao excluir funcionário.", "danger", "admin_dashboard", aba='funcionarios')


# =============================================================================
# 🙋 CRUD DE LEITOR (gestão pelo funcionário — ex.: cadastro no balcão)
# =============================================================================
@app.route('/admin/leitor/criar', methods=['POST'])
def admin_criar_leitor():
    """
    POST /admin/leitor/criar — funcionário logado.
    Cadastro de leitor feito PELO FUNCIONÁRIO (ex.: pessoa se cadastra
    presencialmente no balcão, sem usar o /cadastrar self-service).
    Body: nome, email, senha, telefone, consentimento_lgpd='on'.
    """
    bloqueio = exigir_funcionario()
    if bloqueio:
        return bloqueio

    nome = request.form.get('nome', '').strip()
    email = request.form.get('email', '').strip()
    senha = request.form.get('senha', '').strip()
    telefone = request.form.get('telefone', '').strip()
    consentimento_lgpd = 1 if request.form.get('consentimento_lgpd') == 'on' else 0

    if not consentimento_lgpd:
        return resposta(False, "É necessário registrar o consentimento LGPD do leitor.", "danger", "admin_dashboard", aba='leitores')

    if not nome or not email or not senha or not telefone:
        return resposta(False, "Preencha nome, email, senha e telefone.", "warning", "admin_dashboard", aba='leitores')

    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro de conexão.", "danger", "admin_dashboard")

    try:
        cursor = conn.cursor()

        cursor.execute("SELECT id_leitor FROM leitores WHERE email = %s", (email,))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return resposta(False, "E-mail já cadastrado.", "warning", "admin_dashboard", aba='leitores')

        senha_hash = generate_password_hash(senha)
        cursor.execute("""
            INSERT INTO leitores (nome, email, senha, telefone, consentimento_lgpd)
            VALUES (%s, %s, %s, %s, %s)
        """, (nome, email, senha_hash, telefone, consentimento_lgpd))
        conn.commit()
        novo_id = cursor.lastrowid
        cursor.close()
        conn.close()
        return resposta(True, "Leitor cadastrado com sucesso!", "success", "admin_dashboard", aba='leitores', dados_extra={"id_leitor": novo_id})

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO AO CRIAR LEITOR:", e, "\n")
        return resposta(False, "Erro ao cadastrar leitor.", "danger", "admin_dashboard", aba='leitores')


@app.route('/admin/leitor/<int:id_leitor>/editar', methods=['POST'])
def admin_editar_leitor(id_leitor):
    """POST /admin/leitor/<id>/editar — funcionário logado. Body: nome, telefone, status_conta ('Ativo'|'Suspenso'|'Bloqueado')."""
    bloqueio = exigir_funcionario()
    if bloqueio:
        return bloqueio

    nome = request.form.get('nome', '').strip()
    telefone = request.form.get('telefone', '').strip()
    status_conta = request.form.get('status_conta', '').strip()

    if not nome or not telefone:
        return resposta(False, "Preencha nome e telefone.", "warning", "admin_dashboard", aba='leitores')

    if status_conta and status_conta not in ('Ativo', 'Suspenso', 'Bloqueado'):
        return resposta(False, "status_conta deve ser 'Ativo', 'Suspenso' ou 'Bloqueado'.", "warning", "admin_dashboard", aba='leitores')

    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro de conexão.", "danger", "admin_dashboard")

    try:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE leitores SET nome = %s, telefone = %s,
                   status_conta = COALESCE(NULLIF(%s, ''), status_conta)
            WHERE id_leitor = %s
        """, (nome, telefone, status_conta, id_leitor))
        conn.commit()
        linhas_afetadas = cursor.rowcount
        cursor.close()
        conn.close()

        if linhas_afetadas == 0:
            return resposta(False, "Leitor não encontrado.", "warning", "admin_dashboard", aba='leitores')
        return resposta(True, "Leitor atualizado com sucesso!", "success", "admin_dashboard", aba='leitores')

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO AO EDITAR LEITOR:", e, "\n")
        return resposta(False, "Erro ao atualizar leitor.", "danger", "admin_dashboard", aba='leitores')


@app.route('/admin/leitor/<int:id_leitor>/excluir', methods=['POST'])
def admin_excluir_leitor(id_leitor):
    """
    POST /admin/leitor/<id>/excluir — funcionário logado.
    Reaproveita a mesma lógica de exclusão/anonimização do self-service
    (excluir_ou_anonimizar_leitor), só que disparada pelo funcionário.
    """
    bloqueio = exigir_funcionario()
    if bloqueio:
        return bloqueio

    conn = get_db_connection()
    if not conn:
        return resposta(False, "Erro de conexão.", "danger", "admin_dashboard")

    try:
        cursor = conn.cursor(dictionary=True)
        sucesso, mensagem = excluir_ou_anonimizar_leitor(cursor, conn, id_leitor)
        cursor.close()
        conn.close()
        return resposta(sucesso, mensagem, "success" if sucesso else "warning", "admin_dashboard", aba='leitores')

    except Exception as e:
        if conn and conn.is_connected():
            conn.close()
        print("\n❌ ERRO AO EXCLUIR LEITOR (ADMIN):", e, "\n")
        return resposta(False, "Erro ao excluir leitor.", "danger", "admin_dashboard", aba='leitores')


# -----------------------------------------------------------------------------
# 🟢 EXECUÇÃO DO SERVIDOR
# -----------------------------------------------------------------------------
if __name__ == '__main__':
    os.makedirs(ASSETS_FOLDER, exist_ok=True)
    os.makedirs(CSS_FOLDER, exist_ok=True)

    debug_mode = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(debug=debug_mode)