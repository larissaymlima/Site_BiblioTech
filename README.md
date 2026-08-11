<<<<<<< HEAD
# 📚 Bibliotech - Sistema de Biblioteca Digital

O **Bibliotech** é uma aplicação web desenvolvida em Python (Flask) e MySQL que moderniza a consulta de acervos, o catálogo de livros e a reserva de exemplares.

Criado com a ideia de facilitar a consulta a acervos de bibliotecas físicas sem a necessidade de se deslocar até o local, o sistema oferece uma interface intuitiva e uma estrutura completa para localizar livros, realizar reservas e notificar usuários e funcionários sobre a situação de empréstimos e devoluções.

O **Bibliotech** é um projeto interdisciplinar desenvolvido em 2026 pelos alunos:
- 🎓 **Isabella Matos**
- 🎓 **Jhonatan Pires**
- 🎓 **Larissa Matias**
---

## 🚀 Funcionalidades

- **Catálogo Dinâmico:** Exibição de categorias e livros em alta sincronizados com o banco de dados.
- **Autenticação:** Sistema de login e cadastro seguro para leitores e funcionários com senhas criptografadas (`werkzeug.security`).
- **Navegação Intuitiva:** Links dinâmicos e carregamento otimizado de imagens e estilos.
- **Notificações e Suporte:** Estrutura integrada para envio de SMS e e-mails (Twilio e SendGrid).
=======
# 📚 Sistema Infotech - Sistema BibliTech
Projeto interdisciplinar desenvolvido no curso de Informática do Grau Técnico pelos alunos:
Isabella Matos,
Jhonatan Pires e 
Larissa Matias.

Portal web completo para gerenciamento de biblioteca, desenvolvido com **Python (Flask)**, **MySQL** e front-end moderno estruturado em HTML5, CSS3 e JavaScript. O sistema atende tanto aos leitores (consulta de acervo, reservas e histórico) quanto aos funcionários (painel administrativo de empréstimos, estoque e controle de inadimplentes).

---

## 🚀 Funcionalidades do Sistema

### 👤 1. Página Inicial (`home.html`)
* **Menu Superior Dinâmico:** Links de navegação rápida com seções integradas para *Acervo*, *Serviços*, *A Biblioteca*, *Ajuda* e *Área do Usuário*.
* **Busca Rápida:** Barra de pesquisa integrada para encontrar obras de qualquer lugar da página.
* **Sistema de Autenticação:** Modais intuitivos para Login e Cadastro. Quando logado, exibe o avatar e o nome do leitor no topo.

### 📖 2. Acervo e Catálogo (`catalogo.html`)
* **Filtros Avançados:** Busca em tempo real por título, autor, categoria e status de disponibilidade.
* **Carrosséis de Destaque:** 
  * *Mais Emprestados:* Os 5 livros com maior histórico de circulação.
  * *Mais Procurados / Reservados:* Os 5 livros com maior volume de filas ativas.
  * *Lançamentos Recentes:* As 5 últimas obras cadastradas.
* **Acervo Geral (A a Z):** Listagem completa organizada em cards interativos com paginação.
* **Visualização de Detalhes:** Sinopse completa, estoque, gênero, **localização exata na estante** (corredor e prateleira), além de opções para solicitar empréstimo, entrar na fila de espera e enviar avaliações (reviews com notas de 1 a 5 estrelas).

### ⚙️ 3. Painel Administrativo (`dashboard.html`)
* **Resumo Geral:** Cards de indicadores em tempo real (Total de Livros, Leitores Cadastrados, Empréstimos Ativos e Alertas de Atraso).
* **Balcão de Atendimento:** Gestão de retirada de reservas e registro de devoluções com atualização automática de filas.
* **Gestão de Acervo:** Cadastro, edição e controle de exemplares e localizações físicas.
* **Controle de Inadimplência:** Tabela automatizada de prazos vencidos com opções de notificação para os leitores.
>>>>>>> b327d0ab63907dfde0f05246031888ebd7cd73e0

---

## 🛠️ Tecnologias Utilizadas

<<<<<<< HEAD
- **Back-end:** Python 3, Flask, MySQL Connector
- **Front-end:** HTML5, CSS3, Jinja2
- **Banco de Dados:** MySQL (`bliblitech`)
- **Segurança & Integrações:** `werkzeug`, `python-dotenv`, Twilio API, SendGrid API

---

## 📂 Estrutura do Projeto

```text
bibliotech/
│
├── app.py                  # Servidor e rotas da aplicação
├── .env                    # Variáveis de ambiente (credenciais)
│
├── assets/                 # Imagens, avatares e ícones
│   ├── Biblioteca.jpg
│   ├── livros.jpg
│   └── ...
│
├── css/                    # Arquivos de estilização
│   └── style.css
│
└── templates/              # Páginas HTML (Jinja2)
    ├── index.html
    ├── login.html
    └── cadastro.html
=======
* **Back-end:** Python, Flask, Werkzeug (segurança e hash de senhas)
* **Banco de Dados:** MySQL
* **Front-end:** HTML5, CSS3, JavaScript, Jinja2

---

## ⚙️ Como Executar o Projeto Localmente

1. **Clone o repositório:**
   ```bash
   git clone [https://github.com/seu-usuario/site_bibliotech.git](https://github.com/seu-usuario/site_bibliotech.git)
   cd site_bibliotech
Crie e ative um ambiente virtual:

Bash
python -m venv venv
# No Windows:
venv\Scripts\activate
# No Mac/Linux:
source venv/bin/activate
Instale as dependências:

Bash
pip install flask mysql-connector-python werkzeug
Configure o Banco de Dados:

Importe o arquivo banco_bibliotech (OK).sql para o seu servidor MySQL.

Ajuste as credenciais de conexão no seu arquivo .env ou diretamente no app.py.

Execute a aplicação:

Bash
python app.py
Acesse no navegador: http://127.0.0.1:5000
>>>>>>> b327d0ab63907dfde0f05246031888ebd7cd73e0
