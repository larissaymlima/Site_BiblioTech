// Bibliotech - autenticação simples (armazenamento local no navegador)
// Observação: isto é uma demonstração front-end. Não substitui um backend real
// com hashing de senha e banco de dados seguro.
(function () {
    const USERS_KEY = "bibliotech_users";
    const SESSION_KEY = "bibliotech_sessao";

    const DEFAULT_AVATAR = "https://api.dicebear.com/7.x/avataaars/svg?seed=Bibliotech1";
//(function () { ... })() é uma "caixa fechada" que evita que suas variáveis conflitem com outros scripts. USERS_KEY e SESSION_KEY são os "nomes das gavetas" onde vamos guardar os dados no navegador (localStorage). DEFAULT_AVATAR é a foto usada se ninguém escolher nenhuma.

    //utilidades de armazenamento 
    function getUsers() {
        try {
            return JSON.parse(localStorage.getItem(USERS_KEY)) || {};
        } catch (e) {
            return {};
        }
    }

    function saveUsers(users) {
        localStorage.setItem(USERS_KEY, JSON.stringify(users));
    }

    function getSessionEmail() {
        return localStorage.getItem(SESSION_KEY);
    }

    function setSessionEmail(email) {
        localStorage.setItem(SESSION_KEY, email);
    }

    function clearSession() {
        localStorage.removeItem(SESSION_KEY);
    }

    function getCurrentUser() {
        const email = getSessionEmail();
        if (!email) return null;
        const users = getUsers();
        return users[email] || null;
    }
//são as "ferramentas" básicas..
//getSessionEmail() / setSessionEmail() / clearSession(): controlam quem está logado no momento (é o "crachá" de quem entrou).
//getCurrentUser(): descobre qual usuário está logado agora e traz os dados dele (nome, foto, etc).
//getUsers() / saveUsers(): leem e gravam a lista de contas cadastradas.
//getSessionEmail() / setSessionEmail() / clearSession(): controlam quem está logado no momento (é o "crachá" de quem entrou).
//getCurrentUser(): descobre qual usuário está logado agora e traz os dados dele (nome, foto, etc).

    //elementos
    const authModal = document.getElementById("authModal");
    const closeAuthModal = document.getElementById("closeAuthModal");
    const authArea = document.getElementById("authArea");

    const tabBtns = document.querySelectorAll(".tab-btn");
    const loginForm = document.getElementById("loginForm");
    const cadastroForm = document.getElementById("cadastroForm");
    const loginMsg = document.getElementById("loginMsg");
    const cadMsg = document.getElementById("cadMsg");

    const avatarPicker = document.getElementById("avatarPicker");
    const avatarUpload = document.getElementById("avatarUpload");
    const cadFoto = document.getElementById("cadFoto");

    let pendingReservaBtn = null; // botão "Reservar" que abriu o modal, se houver
//pega, pelo id de cada elemento (os mesmos IDs que colocamos no HTML), uma "referência" para poder controlar cada peça da tela pelo JavaScript — o modal, os botões, os campos do formulário, etc. pendingReservaBtn guarda qual livro a pessoa tentou reservar, caso ela precise logar primeiro.

    //modal open/close
    function openModal(tab) {
        authModal.classList.add("open");
        if (tab) switchTab(tab);
        setMsg(loginMsg, "");
        setMsg(cadMsg, "");
    }

    function closeModal() {
        authModal.classList.remove("open");
        pendingReservaBtn = null;
    }

    function switchTab(tab) {
        tabBtns.forEach((b) => b.classList.toggle("active", b.dataset.tab === tab));
        loginForm.hidden = tab !== "login";
        cadastroForm.hidden = tab !== "cadastro";
    }

    tabBtns.forEach((btn) => {
        btn.addEventListener("click", () => switchTab(btn.dataset.tab));
    });

    closeAuthModal.addEventListener("click", closeModal);
    authModal.addEventListener("click", (e) => {
        if (e.target === authModal) closeModal();
    });

    function setMsg(el, text, isError) {
        el.textContent = text || "";
        el.classList.remove("error", "success");
        if (text) el.classList.add(isError ? "error" : "success");
    }
//openModal() / closeModal(): mostram ou escondem a janela de login.
//switchTab(): alterna entre a aba "Entrar" e "Criar conta".
//Os addEventListener fazem: clicar no botão "Entrar" abre o modal; clicar no X fecha; clicar fora da caixa (no fundo escuro) também fecha.
//setMsg(): mostra mensagens de erro (vermelho) ou sucesso (verde) embaixo dos formulários.

    // seleção de avatar
    let selectedAvatar = DEFAULT_AVATAR;

    avatarPicker.querySelectorAll(".avatar-option[data-avatar]").forEach((img) => {
        img.addEventListener("click", () => {
            selectedAvatar = img.dataset.avatar;
            cadFoto.value = selectedAvatar;
            avatarPicker.querySelectorAll(".avatar-option").forEach((el) => el.classList.remove("selected"));
            img.classList.add("selected");
        });
    });

    // marca o primeiro avatar como selecionado por padrão
    const firstAvatar = avatarPicker.querySelector(".avatar-option[data-avatar]");
    if (firstAvatar) firstAvatar.classList.add("selected");
    cadFoto.value = selectedAvatar;

    avatarUpload.addEventListener("change", () => {
        const file = avatarUpload.files[0];
        if (!file) return;
        const reader = new FileReader();
        reader.onload = () => {
            selectedAvatar = reader.result; // base64
            cadFoto.value = selectedAvatar;
            avatarPicker.querySelectorAll(".avatar-option").forEach((el) => el.classList.remove("selected"));
            // mostra a foto enviada como miniatura selecionada, no lugar do botão "+"
            const uploadLabel = document.getElementById("avatarUploadLabel");
            uploadLabel.style.backgroundImage = `url(${selectedAvatar})`;
            uploadLabel.style.backgroundSize = "cover";
            uploadLabel.style.backgroundPosition = "center";
            uploadLabel.querySelector("span").style.display = "none";
            uploadLabel.classList.add("selected");
        };
        reader.readAsDataURL(file);
    });
//controla os 4 avatares prontos + a opção de enviar foto própria.
//Clicar em um avatar pronto: marca ele como escolhido (borda laranja).
//Clicar no "+" e escolher um arquivo do computador: o FileReader lê a imagem e a transforma em texto (base64) para guardar junto com os dados do usuário, e mostra essa foto no lugar do "+".

    // cadastro
    cadastroForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const usuario = document.getElementById("cadUsuario").value.trim();
        const email = document.getElementById("cadEmail").value.trim().toLowerCase();
        const senha = document.getElementById("cadSenha").value;
        const foto = cadFoto.value || DEFAULT_AVATAR;

        if (!usuario || !email || senha.length < 6) {
            setMsg(cadMsg, "Preencha todos os campos (senha com 6+ caracteres).", true);
            return;
        }

        const users = getUsers();
        if (users[email]) {
            setMsg(cadMsg, "Já existe uma conta com esse email.", true);
            return;
        }

        users[email] = { usuario, email, senha, foto };
        saveUsers(users);
        setSessionEmail(email);

        setMsg(cadMsg, "Conta criada com sucesso!");
        updateAuthUI();
        setTimeout(() => {
            closeModal();
            afterLoginSuccess();
        }, 700);
    });
//quando a pessoa clica em "Criar conta":
//Pega os valores digitados (usuário, email, senha) e a foto escolhida.
//Confere se preencheu tudo certo e se a senha tem 6+ caracteres.
//Confere se aquele email já não está cadastrado.
//Se estiver tudo certo, salva a conta nova, faz login automático e fecha o modal.

    // login
    loginForm.addEventListener("submit", (e) => {
        e.preventDefault();
        const email = document.getElementById("loginEmail").value.trim().toLowerCase();
        const senha = document.getElementById("loginSenha").value;

        const users = getUsers();
        const user = users[email];

        if (!user || user.senha !== senha) {
            setMsg(loginMsg, "Email ou senha incorretos.", true);
            return;
        }

        setSessionEmail(email);
        setMsg(loginMsg, "Login realizado!");
        updateAuthUI();
        setTimeout(() => {
            closeModal();
            afterLoginSuccess();
        }, 500);
    });

    function afterLoginSuccess() {
        if (pendingReservaBtn) {
            const livro = pendingReservaBtn.dataset.livro || "o livro";
            alert(`Reserva confirmada para: ${livro}`);
            pendingReservaBtn = null;
        }
    }
//quando a pessoa clica em "Entrar":
//Confere se o email existe e a senha bate.
//Se estiver errado, mostra mensagem de erro.
//Se estiver certo, faz login e fecha o modal.
//afterLoginSuccess(): se a pessoa tentou reservar um livro antes de logar, essa função completa a reserva automaticamente assim que ela loga.

    //área de usuário no cabeçalho
    function updateAuthUI() {
        const user = getCurrentUser();
        authArea.innerHTML = "";

        if (!user) {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "btn btn-auth";
            btn.id = "openAuthBtn";
            btn.textContent = "Entrar";
            btn.addEventListener("click", () => openModal("login"));
            authArea.appendChild(btn);
            return;
        }

        const chip = document.createElement("button");
        chip.type = "button";
        chip.className = "user-chip";
        chip.title = "Clique para sair";

        const img = document.createElement("img");
        img.src = user.foto || DEFAULT_AVATAR;
        img.alt = user.usuario;

        const span = document.createElement("span");
        span.textContent = user.usuario;

        const logoutX = document.createElement("span");
        logoutX.className = "logout-x";
        logoutX.textContent = "×";

        chip.appendChild(img);
        chip.appendChild(span);
        chip.appendChild(logoutX);

        chip.addEventListener("click", () => {
            if (confirm("Deseja sair da sua conta?")) {
                clearSession();
                updateAuthUI();
            }
        });

        authArea.appendChild(chip);
    }
//atualiza o que aparece no canto do cabeçalho.
//Se ninguém está logado: mostra o botão "Entrar".
//Se alguém está logado: mostra a foto + nome do usuário, num "chip" clicável. Clicar nele pergunta se a pessoa quer sair (logout).

    // botões "Reservar" exigem login
    document.querySelectorAll(".btn-reservar").forEach((btn) => {
        btn.addEventListener("click", (e) => {
            e.preventDefault();
            const user = getCurrentUser();
            if (!user) {
                pendingReservaBtn = btn;
                openModal("login");
                return;
            }
            alert(`Reserva confirmada para: ${btn.dataset.livro}`);
        });
    });
//: pega todos os botões com a classe btn-reservar (os 6 que marcamos no HTML). Ao clicar:
//Se não estiver logado: abre o modal de login e guarda qual livro era, para reservar automaticamente depois do login.
//Se já estiver logado: confirma a reserva na hora.

    //inicialização
    updateAuthUI();
})();
//roda a função updateAuthUI() assim que a página carrega, para já mostrar corretamente se tem alguém logado ou não. O })(); fecha a "caixa" que abrimos lá na Parte 1.