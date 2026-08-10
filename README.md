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

---

## 🛠️ Tecnologias Utilizadas

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
