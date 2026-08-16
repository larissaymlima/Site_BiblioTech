DROP DATABASE IF EXISTS bibliotech;
CREATE DATABASE IF NOT EXISTS bibliotech;
USE bibliotech;

-- 1. Tabela de Cargos
CREATE TABLE cargos (
    id_cargo INT AUTO_INCREMENT PRIMARY KEY,
    nome_cargo VARCHAR(50) NOT NULL
);

-- 2. Tabela de Funcionários
CREATE TABLE funcionarios (
    id_funcionario INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    id_cargo INT NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    telefone VARCHAR(15) NOT NULL,
    senha VARCHAR(255) NOT NULL,
    foto_perfil VARCHAR(255) DEFAULT 'default_profile.png',
    tipo_perfil ENUM('FUNCIONARIO', 'LEITOR') NOT NULL DEFAULT 'FUNCIONARIO',
    status_funcionario ENUM('Ativo', 'Suspenso', 'Bloqueado') NOT NULL DEFAULT 'Ativo',
    data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_cargo) REFERENCES cargos(id_cargo) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- 3. Tabela de Categorias
CREATE TABLE categorias (
    id_categoria INT AUTO_INCREMENT PRIMARY KEY,
    nome_categoria VARCHAR(50) NOT NULL
);

-- 4. Tabela de Livros
CREATE TABLE livro (
    id_livro INT AUTO_INCREMENT PRIMARY KEY,
    titulo VARCHAR(100) NOT NULL,
    autor VARCHAR(50) NOT NULL,
    ano_publicacao INT,
    quant_estoque INT NOT NULL DEFAULT 1,
    sinopse TEXT,
    capa VARCHAR(500),
    posicao_estante VARCHAR(50),
    status_exemplar ENUM('Disponível', 'Emprestado', 'Reservado', 'Indisponível') DEFAULT 'Disponível',
    status_livro ENUM('Ativo', 'Indisponível') NOT NULL DEFAULT 'Ativo',
    id_categoria INT NOT NULL,
    cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_categoria) REFERENCES categorias(id_categoria) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- 5. Tabela de Leitores
CREATE TABLE leitores (
    id_leitor INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    telefone VARCHAR(15) NOT NULL,
    senha VARCHAR(255) NOT NULL,
    consentimento_lgpd BOOLEAN DEFAULT 0,
    foto_perfil VARCHAR(255) DEFAULT 'default_profile.png',
    tipo_perfil ENUM('FUNCIONARIO', 'LEITOR') NOT NULL DEFAULT 'LEITOR',
    data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP,
    status_conta ENUM('Ativo', 'Suspenso', 'Bloqueado') DEFAULT 'Ativo'
);

-- 6. Tabela de Empréstimos
CREATE TABLE emprestimos (
    id_emprestimo INT AUTO_INCREMENT PRIMARY KEY,
    id_livro INT NOT NULL,
    id_leitor INT NOT NULL,
    id_funcionario INT NOT NULL,
    data_emprestimo DATETIME DEFAULT CURRENT_TIMESTAMP,
    data_devolucao_prevista DATE NULL,
    data_devolucao_real DATETIME NULL,
    renovacoes_realizadas INT NOT NULL DEFAULT 0,
    status_emprestimo ENUM('Ativo', 'Devolvido', 'Atrasado') DEFAULT 'Ativo',
    FOREIGN KEY (id_livro) REFERENCES livro(id_livro) ON DELETE RESTRICT ON UPDATE CASCADE,
    FOREIGN KEY (id_leitor) REFERENCES leitores(id_leitor) ON DELETE RESTRICT ON UPDATE CASCADE,
    FOREIGN KEY (id_funcionario) REFERENCES funcionarios(id_funcionario) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- 7. Tabela de Reservas
CREATE TABLE reservas (
    id_reserva INT AUTO_INCREMENT PRIMARY KEY,
    id_livro INT NOT NULL,
    id_leitor INT NOT NULL,
    data_reserva DATETIME DEFAULT CURRENT_TIMESTAMP,
    status_reserva ENUM('Pendente', 'Aguardando Retirada', 'Concluida', 'Cancelada') DEFAULT 'Pendente',
    posicao_fila_notificada INT NULL,
    FOREIGN KEY (id_livro) REFERENCES livro(id_livro) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (id_leitor) REFERENCES leitores(id_leitor) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- 8. Tabela de Avaliações
CREATE TABLE avaliacoes (
    id_avaliacao INT AUTO_INCREMENT PRIMARY KEY,
    livro_id INT NOT NULL,
    leitor_id INT NOT NULL,
    nota INT CHECK (nota BETWEEN 1 AND 5),
    comentario TEXT,
    data_avaliacao DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (livro_id) REFERENCES livro(id_livro) ON DELETE CASCADE,
    FOREIGN KEY (leitor_id) REFERENCES leitores(id_leitor) ON DELETE CASCADE
);

-- 9. Tabela de Notificações de Interesse
CREATE TABLE notificacoes_interesse (
    id_notificacao INT AUTO_INCREMENT PRIMARY KEY,
    id_leitor INT NOT NULL,
    id_livro INT NOT NULL,
    consentimento_lgpd BOOLEAN NOT NULL DEFAULT 0,
    receber_email BOOLEAN NOT NULL DEFAULT 1,
    receber_whatsapp BOOLEAN NOT NULL DEFAULT 0,
    receber_sms BOOLEAN NOT NULL DEFAULT 0,
    data_solicitacao DATETIME DEFAULT CURRENT_TIMESTAMP,
    status ENUM('Pendente', 'Notificado', 'Cancelado') DEFAULT 'Pendente',

    CONSTRAINT fk_notificacoes_leitor 
        FOREIGN KEY (id_leitor) REFERENCES leitores(id_leitor) 
        ON DELETE CASCADE 
        ON UPDATE CASCADE,
        
    CONSTRAINT fk_notificacoes_livro 
        FOREIGN KEY (id_livro) REFERENCES livro(id_livro) 
        ON DELETE CASCADE 
        ON UPDATE CASCADE,

    CONSTRAINT uk_notificacoes_leitor_livro UNIQUE (id_leitor, id_livro)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- -----------------------------------------------------------------------------
-- ⚡ TRIGGERS
-- -----------------------------------------------------------------------------
DELIMITER //

-- Valida o limite de até 3 livros emprestados por leitor
CREATE TRIGGER antes_inserir_emprestimo
BEFORE INSERT ON emprestimos
FOR EACH ROW
BEGIN
    DECLARE total_ativos INT;

    SELECT COUNT(*) INTO total_ativos
    FROM emprestimos
    WHERE id_leitor = NEW.id_leitor AND data_devolucao_real IS NULL;

    IF total_ativos >= 3 THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Limite atingido: o leitor já possui 3 livros emprestados.';
    END IF;
END //

-- Atualiza o status do livro para 'Emprestado' quando atinge o total do estoque
CREATE TRIGGER apos_inserir_emprestimo
AFTER INSERT ON emprestimos
FOR EACH ROW
BEGIN
    DECLARE total_emprestados INT;
    DECLARE qtd_estoque INT;

    SELECT COUNT(*) INTO total_emprestados 
    FROM emprestimos 
    WHERE id_livro = NEW.id_livro AND data_devolucao_real IS NULL;

    SELECT quant_estoque INTO qtd_estoque 
    FROM livro 
    WHERE id_livro = NEW.id_livro;

    IF total_emprestados >= qtd_estoque THEN
        UPDATE livro SET status_exemplar = 'Emprestado' WHERE id_livro = NEW.id_livro;
    END IF;
END //

-- Impede reservas se ainda houverem exemplares disponíveis
CREATE TRIGGER antes_inserir_reserva
BEFORE INSERT ON reservas
FOR EACH ROW
BEGIN
    DECLARE total_emprestados INT;
    DECLARE qtd_estoque INT;

    IF NEW.status_reserva = 'Pendente' THEN
        SELECT COUNT(*) INTO total_emprestados 
        FROM emprestimos 
        WHERE id_livro = NEW.id_livro AND data_devolucao_real IS NULL;

        SELECT quant_estoque INTO qtd_estoque 
        FROM livro 
        WHERE id_livro = NEW.id_livro;

        IF total_emprestados < qtd_estoque THEN
            SIGNAL SQLSTATE '45000' 
            SET MESSAGE_TEXT = 'Não é possível entrar na fila: existem exemplares disponíveis na estante.';
        END IF;
    END IF;
END //

-- Impede que um leitor reserve um livro que já possui emprestado ativamente
CREATE TRIGGER antes_inserir_reserva_duplicada_emprestimo
BEFORE INSERT ON reservas
FOR EACH ROW
BEGIN
    DECLARE v_possui_emprestimo INT;

    SELECT COUNT(*) INTO v_possui_emprestimo
    FROM emprestimos
    WHERE id_leitor = NEW.id_leitor
      AND id_livro = NEW.id_livro
      AND data_devolucao_real IS NULL;

    IF v_possui_emprestimo > 0 THEN
        SIGNAL SQLSTATE '45000'
        SET MESSAGE_TEXT = 'Não é permitido reservar um livro que você já possui emprestado.';
    END IF;
END //

DELIMITER ;

-- -----------------------------------------------------------------------------
-- 📥 INSERÇÃO DE DADOS BASE
-- -----------------------------------------------------------------------------

INSERT INTO cargos (nome_cargo) VALUES  
('Bibliotecário'), 
('Auxiliar de Biblioteca');

INSERT INTO categorias (id_categoria, nome_categoria) VALUES 
(1, 'Fantasia'),
(2, 'Romance'),
(3, 'Terror'),
(4, 'Ação'),
(5, 'Suspense'),
(6, 'Aventura');

INSERT INTO funcionarios (nome, id_cargo, email, telefone, senha, tipo_perfil) VALUES
('Carlos Silva', 1, 'carlos@bliblitech.com', '11999998888', 'scrypt:32768:8:1$nPV45UkwdKmGkuRe$103d1d7ce6706f2ae5d64800ada5fc3bbb6a0114567481f85af73e69d98ccc8172f07a2fa57aabe15d31faac773b316a5fa3ccac986171434a53252a0cc2d953', 'FUNCIONARIO'),
('Isabela Matos', 2, 'isa@biblitech.com', '31972321537', 'scrypt:32768:8:1$OTqIGW9yfBYMKEpb$2b3247c4e557751ded9e19b4729e43a86d68f9a84ccb3f74043581a15292c95209f50961c80f9d7c1081d264a97270413b308a58edaa991b4640aeebe05e03e2', 'FUNCIONARIO');

-- Diversificação dos leitores (IDs de 1 a 6)
INSERT INTO leitores (id_leitor, nome, email, telefone, senha, tipo_perfil, consentimento_lgpd) VALUES 
(1, 'Felipe Rios', 'felipe@gmail.com', '11977776666', 'scrypt:32768:8:1$4FMnn5lwlsz1hrz9$2d5a1d34307e245c2d5bdaef340b8cd1bc8ba2dbda7b2fae2f1bfcde0b6ac278615c9675890bd7630793be2c845f43a62c3d0850d4ca1563e0e71686f7969057', 'LEITOR', 1),
(2, 'Larissa Matias', 'ly@gmail.com', '31971165397', 'scrypt:32768:8:1$OTqIGW9yfBYMKEpb$2b3247c4e557751ded9e19b4729e43a86d68f9a84ccb3f74043581a15292c95209f50961c80f9d7c1081d264a97270413b308a58edaa991b4640aeebe05e03e2', 'LEITOR', 1),
(3, 'Amanda Souza', 'amanda@gmail.com', '31988887777', 'scrypt:32768:8:1$oAUiGU9RllBjYHOC$6c8e736c5fcc18bfaf9b6aa61e8692296c8712eec9002fa27e764ae7820d7b4e81c8dd9be06c40005bfc9586d67e9b50f6ab0a1394ccda4b14120645fe6abf0b', 'LEITOR', 1),
(4, 'Carlos Eduardo', 'carlos.eduardo@email.com', '31988880001', 'scrypt:32768:8:1$hash1', 'LEITOR', 1),
(5, 'Mariana Lima', 'mariana.lima@email.com', '31988880002', 'scrypt:32768:8:1$hash2', 'LEITOR', 1),
(6, 'Lucas Souza', 'lucas.souza@email.com', '31988880003', 'scrypt:32768:8:1$hash3', 'LEITOR', 1);

INSERT INTO livro (id_livro, titulo, autor, ano_publicacao, quant_estoque, id_categoria, posicao_estante, cadastro) VALUES
(1, 'O Hobbit', 'J.R.R. Tolkien', 1937, 2, 1, 'Corredor A - Estante 1', '2026-01-11 10:00:00'),
(2, 'Harry Potter e a Pedra Filosofal', 'J.K. Rowling', 1997, 2, 1, 'Corredor A - Estante 1', '2026-01-14 10:00:00'),
(3, 'Orgulho e Preconceito', 'Jane Austen', 1813, 2, 2, 'Corredor B - Estante 1', '2026-01-21 10:00:00'),
(4, 'Dom Casmurro', 'Machado de Assis', 1899, 2, 2, 'Corredor B - Estante 1', '2026-01-24 10:00:00'),
(5, 'It: A Coisa', 'Stephen King', 1986, 2, 3, 'Corredor C - Estante 1', '2026-02-01 10:00:00'),
(6, 'Drácula', 'Bram Stoker', 1897, 2, 3, 'Corredor C - Estante 1', '2026-02-03 10:00:00'),
(7, 'A Caçada ao Outubro Vermelho', 'Tom Clancy', 1984, 2, 4, 'Corredor D - Estante 1', '2026-02-11 10:00:00'),
(8, 'A Identidade Bourne', 'Robert Ludlum', 1980, 2, 4, 'Corredor D - Estante 1', '2026-02-14 10:00:00'),
(9, 'O Código Da Vinci', 'Dan Brown', 2003, 2, 5, 'Corredor E - Estante 1', '2026-02-21 10:00:00'),
(10, 'A Paciente Silenciosa', 'Alex Michaelides', 2019, 2, 5, 'Corredor E - Estante 1', '2026-02-26 10:00:00'),
(11, 'O Alquimista', 'Paulo Coelho', 1988, 2, 6, 'Corredor F - Estante 1', '2026-08-01 09:00:00'),
(12, 'Viagem ao Centro da Terra', 'Júlio Verne', 1864, 2, 6, 'Corredor F - Estante 1', '2026-08-04 09:00:00'),
(13, 'O Senhor dos Anéis: A Sociedade do Anel', 'J.R.R. Tolkien', 1954, 2, 1, 'Corredor A - Estante 2', '2026-01-13 10:00:00'),
(14, 'O Iluminado', 'Stephen King', 1977, 2, 3, 'Corredor C - Estante 2', '2026-02-02 10:00:00'),
(15, 'A Arte da Guerra', 'Sun Tzu', 2005, 2, 4, 'Corredor D - Estante 2', '2026-02-15 10:00:00'),
(16, 'E Não Sobrou Nenhum', 'Agatha Christie', 1939, 2, 5, 'Corredor E - Estante 2', '2026-02-27 10:00:00'),
(17, 'A Ilha do Tesouro', 'Robert Louis Stevenson', 1883, 2, 6, 'Corredor F - Estante 2', '2026-08-02 09:00:00'),
(18, 'É Assim que Acaba', 'Colleen Hoover', 2016, 2, 2, 'Corredor B - Estante 2', '2026-01-22 10:00:00'),
(19, 'Os Sete Maridos de Evelyn Hugo', 'Taylor Jenkins Reid', 2017, 2, 2, 'Corredor B - Estante 2', '2026-01-25 10:00:00'),
(20, 'Verity', 'Colleen Hoover', 2018, 2, 5, 'Corredor E - Estante 2', '2026-03-02 10:00:00'),
(21, 'Corte de Espinhos e Rosas', 'Sarah J. Maas', 2015, 2, 1, 'Corredor A - Estante 2', '2026-01-18 10:00:00'),
(22, 'Garota Exemplar', 'Gillian Flynn', 2012, 2, 5, 'Corredor E - Estante 2', '2026-02-24 10:00:00'),
(23, 'É Assim que Começa', 'Colleen Hoover', 2022, 2, 2, 'Corredor B - Estante 3', '2026-01-23 10:00:00'),
(24, 'A Hipótese do Amor', 'Ali Hazelwood', 2021, 2, 2, 'Corredor B - Estante 3', '2026-01-27 10:00:00'),
(25, 'O Homem de Palha', 'C.J. Tudor', 2018, 2, 5, 'Corredor E - Estante 3', '2026-03-01 10:00:00'),
(26, 'Vermelho, Branco e Sangue Azul', 'Casey McQuiston', 2019, 2, 2, 'Corredor B - Estante 3', '2026-01-26 10:00:00'),
(27, 'Sniper Americano', 'Chris Kyle', 2012, 2, 4, 'Corredor D - Estante 3', '2026-02-19 10:00:00');

-- -----------------------------------------------------------------------------
-- 🔄 EMPRÉSTIMOS REESTRUTURADOS
-- -----------------------------------------------------------------------------

-- Leitor 1 (Felipe): Atinge o limite máximo de 3 empréstimos ativos (Livros 18, 19, 23)
-- Leitor 2 (Larissa): 2 empréstimos ativos (Livros 18 e 20) -> Pode fazer +1 empréstimo
-- Leitor 3 (Amanda): 1 empréstimo ativo (Livro 19) -> Pode fazer +2 empréstimos
-- Leitor 4 (Carlos): 1 empréstimo ativo (Livro 20) -> Pode fazer +2 empréstimos
-- Leitores 5 e 6: 0 empréstimos ativos -> Elegíveis para até 3 empréstimos

-- Livros 18, 19 e 20: Totalmente sem estoque (2 empréstimos de 2 disponíveis)
-- Livro 23: Estoque parcial (1 emprestado de 2 disponíveis)
-- Demais livros: 100% disponíveis na estante

INSERT INTO emprestimos (id_livro, id_leitor, id_funcionario, data_devolucao_prevista) VALUES
-- Livro 18 esgotado (Leitores 1 e 2)
(18, 1, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY)),
(18, 2, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY)),

-- Livro 19 esgotado (Leitores 1 e 3)
(19, 1, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY)),
(19, 3, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY)),

-- Livro 20 esgotado (Leitores 2 e 4)
(20, 2, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY)),
(20, 4, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY)),

-- Livro 23 com estoque parcial (Leitor 1)
(23, 1, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY));

-- -----------------------------------------------------------------------------
-- 📌 RESERVAS VALIDADAS
-- -----------------------------------------------------------------------------
-- Reservas permitidas somente para livros 100% esgotados (18, 19, 20)
-- Os leitores que reservam NÃO possuem o livro emprestado no momento

INSERT INTO reservas (id_leitor, id_livro, data_reserva, status_reserva) VALUES
(3, 18, NOW(), 'Pendente'), -- Leitora 3 na fila do Livro 18 (esgotado)
(4, 18, NOW(), 'Pendente'), -- Leitor 4 na fila do Livro 18 (2º da fila)
(2, 19, NOW(), 'Pendente'), -- Leitora 2 na fila do Livro 19 (esgotado)
(5, 20, NOW(), 'Pendente'); -- Leitora 5 na fila do Livro 20 (esgotado)

-- -----------------------------------------------------------------------------
-- 💬 AVALIAÇÕES
-- -----------------------------------------------------------------------------
INSERT INTO avaliacoes (livro_id, leitor_id, nota, comentario, data_avaliacao) VALUES
(1, 3, 5, 'Uma aventura clássica e encantadora!', '2026-02-11 12:00:00'),
(2, 2, 5, 'Pura nostalgia e magia.', '2026-02-14 16:05:00'),
(3, 2, 5, 'Diálogos afiados e química impecável!', '2026-02-21 10:00:00'),
(4, 1, 4, 'Um enigma psicológico envolvente.', '2026-02-24 14:00:00'),
(5, 1, 5, 'Stephen King no seu auge absoluto!', '2026-03-03 21:00:00'),
(9, 2, 5, 'Uma caça ao tesouro intelectual genial.', '2026-03-23 11:20:00'),
(11, 2, 5, 'Inspirador e poético.', '2026-04-02 09:00:00'),
(18, 2, 5, 'Um livro forte e emocionalmente intenso.', '2026-02-22 17:40:00'),
(19, 2, 5, 'Evelyn Hugo é inesquecível!', '2026-02-25 19:30:00'),
(20, 2, 5, 'Um thriller psicológico impecável!', '2026-04-01 20:30:00');
