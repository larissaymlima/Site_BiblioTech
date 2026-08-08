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

---

## 🛠️ Tecnologias Utilizadas

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