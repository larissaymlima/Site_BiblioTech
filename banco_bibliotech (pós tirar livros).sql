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
    status_funcionario ENUM('Ativo', 'Inativo') NOT NULL DEFAULT 'Ativo',
    data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (id_cargo) REFERENCES cargos(id_cargo) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- 3. Tabela de Categorias (IDs de 1 a 6)
CREATE TABLE categorias (
    id_categoria INT AUTO_INCREMENT PRIMARY KEY,
    nome_categoria VARCHAR(50) NOT NULL
);

-- 4. Tabela de Livros
CREATE TABLE livro (
    id_livro INT AUTO_INCREMENT PRIMARY KEY,
    titulo VARCHAR(100),
    autor VARCHAR(50) NOT NULL,
    ano_publicacao INT,
    quant_estoque INT NOT NULL DEFAULT 1,
    sinopse TEXT,
    capa VARCHAR(500),
    status_livro ENUM('Ativo', 'Descontinuado') NOT NULL DEFAULT 'Ativo',
    cadastro TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 5. Relacionamento Livros <-> Categorias
CREATE TABLE livro_categorias (
    id_livro INT NOT NULL,
    id_categoria INT NOT NULL,
    PRIMARY KEY (id_livro, id_categoria),
    FOREIGN KEY (id_livro) REFERENCES livro(id_livro) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (id_categoria) REFERENCES categorias(id_categoria) ON DELETE CASCADE ON UPDATE CASCADE
);

-- 6. Tabela de Leitores
CREATE TABLE leitores (
    id_leitor INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    telefone VARCHAR(15) NOT NULL,
    senha VARCHAR(255) NOT NULL,
    consentimento_lgpd TINYINT(1) DEFAULT 0,
    foto_perfil VARCHAR(255) DEFAULT 'default_profile.png',
    tipo_perfil ENUM('FUNCIONARIO', 'LEITOR') NOT NULL DEFAULT 'LEITOR',
    data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP,
    status_conta ENUM('Ativo', 'Suspenso', 'Bloqueado') DEFAULT 'Ativo'
);

-- 7. Tabela de Exemplares Físicos
CREATE TABLE exemplares (
    id_exemplar INT AUTO_INCREMENT PRIMARY KEY,
    id_livro INT NOT NULL,
    posicao_estante VARCHAR(50),
    status_exemplar ENUM('Disponível', 'Emprestado', 'Reservado', 'Indisponível') DEFAULT 'Disponível',
    FOREIGN KEY (id_livro) REFERENCES livro(id_livro) ON DELETE CASCADE ON UPDATE CASCADE
);

-- 8. Tabela de Empréstimos
CREATE TABLE emprestimos (
    id_emprestimo INT AUTO_INCREMENT PRIMARY KEY,
    id_exemplar INT NOT NULL,
    id_leitor INT NOT NULL,
    id_funcionario INT NOT NULL,
    data_emprestimo DATETIME DEFAULT CURRENT_TIMESTAMP,
    data_devolucao_prevista DATE NULL,
    data_devolucao_real DATETIME NULL,
    renovacoes_realizadas INT NOT NULL DEFAULT 0,
    status_emprestimo ENUM('Ativo', 'Devolvido', 'Atrasado') DEFAULT 'Ativo',
    FOREIGN KEY (id_exemplar) REFERENCES exemplares(id_exemplar) ON DELETE RESTRICT ON UPDATE CASCADE,
    FOREIGN KEY (id_leitor) REFERENCES leitores(id_leitor) ON DELETE RESTRICT ON UPDATE CASCADE,
    FOREIGN KEY (id_funcionario) REFERENCES funcionarios(id_funcionario) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- 9. Tabela de Reservas
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

-- 10. Tabela de Avaliações
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

-- 11. Tabela de Notificações de Interesse
CREATE TABLE notificacoes_interesse (
    id_notificacao INT AUTO_INCREMENT PRIMARY KEY,
    id_leitor INT NOT NULL,
    id_livro INT NOT NULL,
    consentimento_lgpd TINYINT(1) DEFAULT 0,
    receber_email BOOLEAN DEFAULT TRUE,
    receber_whatsapp BOOLEAN DEFAULT FALSE,
    receber_sms BOOLEAN DEFAULT FALSE,
    data_solicitacao DATETIME DEFAULT CURRENT_TIMESTAMP,
    status_notificacao ENUM('Pendente', 'Enviado') DEFAULT 'Pendente',
    FOREIGN KEY (id_leitor) REFERENCES leitores(id_leitor),
    FOREIGN KEY (id_livro) REFERENCES livro(id_livro),
    UNIQUE KEY leitor_livro_unico (id_leitor, id_livro)
);

-- -----------------------------------------------------------------------------
-- ⚡ TRIGGERS
-- -----------------------------------------------------------------------------
DELIMITER //

CREATE TRIGGER apos_inserir_emprestimo
AFTER INSERT ON emprestimos
FOR EACH ROW
BEGIN
    UPDATE exemplares 
    SET status_exemplar = 'Emprestado' 
    WHERE id_exemplar = NEW.id_exemplar;
END //

CREATE TRIGGER antes_inserir_reserva
BEFORE INSERT ON reservas
FOR EACH ROW
BEGIN
    DECLARE qtd_disponivel INT;

    IF NEW.status_reserva = 'Pendente' THEN
        SELECT COUNT(*) INTO qtd_disponivel 
        FROM exemplares 
        WHERE id_livro = NEW.id_livro AND status_exemplar = 'Disponível';

        IF qtd_disponivel > 0 THEN
            SIGNAL SQLSTATE '45000' 
            SET MESSAGE_TEXT = 'Não é possível entrar na fila: existem exemplares disponíveis na estante.';
        END IF;
    END IF;
END //

DELIMITER ;

-- -----------------------------------------------------------------------------
-- 📥 INSERÇÃO DE DADOS BASE
-- -----------------------------------------------------------------------------

INSERT INTO cargos (nome_cargo) VALUES  
('Bibliotecário'), 
('Auxiliar de Biblioteca');

-- Categorias de 1 a 6
INSERT INTO categorias (id_categoria, nome_categoria) VALUES 
(1, 'Fantasia'),
(2, 'Romance'),
(3, 'Terror'),
(4, 'Ação'),
(5, 'Suspense'),
(6, 'Aventura');

INSERT INTO funcionarios (nome, id_cargo, email, telefone, senha, tipo_perfil) VALUES
('Carlos Silva', 1, 'carlos@bliblitech.com', '11999998888', 'scrypt:32768:8:1$nPV45UkwdKmGkuRe$103d1d7ce6706f2ae5d64800ada5fc3bbb6a0114567481f85af73e69d98ccc8172f07a2fa57aabe15d31faac773b316a5fa3ccac986171434a53252a0cc2d953', 'FUNCIONARIO'),
('Isabela Matos', 2, 'isa@biblitech.com', '31972321537', 'scrypt:32768:8:1$vrBHjFfBdgrubZq0$ff6236bd1e79412f91aae438a8480aa3b154e762be69b7ea7f00585e97a4647e45486fc845cdccb3561b1d5650f94dd957fdb69d3d6bbe093a50f45426f54ffd', 'FUNCIONARIO');

INSERT INTO leitores (nome, email, telefone, senha, tipo_perfil, consentimento_lgpd) VALUES 
('Felipe Rios', 'felipe@gmail.com', '11977776666', 'scrypt:32768:8:1$4FMnn5lwlsz1hrz9$2d5a1d34307e245c2d5bdaef340b8cd1bc8ba2dbda7b2fae2f1bfcde0b6ac278615c9675890bd7630793be2c845f43a62c3d0850d4ca1563e0e71686f7969057', 'LEITOR', 1),
('Larissa Matias', 'ly@gmail.com', '31971165397', 'scrypt:32768:8:1$SfJ1au7yngbpB97j$59b96fd0ac014acc844b1fcf2cc290ee7ccb185b593fa43cc05549c32d3b55a9c9ce2778350bcea714a1f17cd98c4ea2c3c61b03ce8fbcad81287f8695c4f684', 'LEITOR', 1),
('Amanda Souza', 'amanda@gmail.com', '31988887777', 'scrypt:32768:8:1$oAUiGU9RllBjYHOC$6c8e736c5fcc18bfaf9b6aa61e8692296c8712eec9002fa27e764ae7820d7b4e81c8dd9be06c40005bfc9586d67e9b50f6ab0a1394ccda4b14120645fe6abf0b', 'LEITOR', 1);

-- -----------------------------------------------------------------------------
-- 📚 CADASTRO DOS LIVROS SELECIONADOS
-- -----------------------------------------------------------------------------

INSERT INTO livro (id_livro, titulo, autor, ano_publicacao, quant_estoque, cadastro) VALUES
-- 2 Livros por Categoria (IDs 1 a 12)
-- Categorias: Fantasia (1), Romance (2), Terror (3), Ação (4), Suspense (5), Aventura (6)
(1, 'O Hobbit', 'J.R.R. Tolkien', 1937, 2, '2026-01-11 10:00:00'),
(2, 'Harry Potter e a Pedra Filosofal', 'J.K. Rowling', 1997, 2, '2026-01-14 10:00:00'),
(3, 'Orgulho e Preconceito', 'Jane Austen', 1813, 2, '2026-01-21 10:00:00'),
(4, 'Dom Casmurro', 'Machado de Assis', 1899, 2, '2026-01-24 10:00:00'),
(5, 'It: A Coisa', 'Stephen King', 1986, 2, '2026-02-01 10:00:00'),
(6, 'Drácula', 'Bram Stoker', 1897, 2, '2026-02-03 10:00:00'),
(7, 'A Caçada ao Outubro Vermelho', 'Tom Clancy', 1984, 2, '2026-02-11 10:00:00'),
(8, 'A Identidade Bourne', 'Robert Ludlum', 1980, 2, '2026-02-14 10:00:00'),
(9, 'O Código Da Vinci', 'Dan Brown', 2003, 2, '2026-02-21 10:00:00'),
(10, 'A Paciente Silenciosa', 'Alex Michaelides', 2019, 2, '2026-02-26 10:00:00'),
(11, 'O Alquimista', 'Paulo Coelho', 1988, 2, '2026-08-01 09:00:00'),
(12, 'Viagem ao Centro da Terra', 'Júlio Verne', 1864, 2, '2026-08-04 09:00:00'),

-- 5 Mais Famosos (IDs 13 a 17)
(13, 'O Senhor dos Anéis: A Sociedade do Anel', 'J.R.R. Tolkien', 1954, 2, '2026-01-13 10:00:00'),
(14, 'O Iluminado', 'Stephen King', 1977, 2, '2026-02-02 10:00:00'),
(15, 'A Arte da Guerra', 'Sun Tzu', 2005, 2, '2026-02-15 10:00:00'),
(16, 'E Não Sobrou Nenhum', 'Agatha Christie', 1939, 2, '2026-02-27 10:00:00'),
(17, 'A Ilha do Tesouro', 'Robert Louis Stevenson', 1883, 2, '2026-08-02 09:00:00'),

-- 5 Mais Procurados (IDs 18 a 22)
(18, 'É Assim que Acaba', 'Colleen Hoover', 2016, 2, '2026-01-22 10:00:00'),
(19, 'Os Sete Maridos de Evelyn Hugo', 'Taylor Jenkins Reid', 2017, 2, '2026-01-25 10:00:00'),
(20, 'Verity', 'Colleen Hoover', 2018, 2, '2026-03-02 10:00:00'),
(21, 'Corte de Espinhos e Rosas', 'Sarah J. Maas', 2015, 2, '2026-01-18 10:00:00'),
(22, 'Garota Exemplar', 'Gillian Flynn', 2012, 2, '2026-02-24 10:00:00'),

-- 5 Lançamentos (IDs 23 a 27)
(23, 'É Assim que Começa', 'Colleen Hoover', 2022, 2, '2026-01-23 10:00:00'),
(24, 'A Hipótese do Amor', 'Ali Hazelwood', 2021, 2, '2026-01-27 10:00:00'),
(25, 'O Homem de Palha', 'C.J. Tudor', 2018, 2, '2026-03-01 10:00:00'),
(26, 'Vermelho, Branco e Sangue Azul', 'Casey McQuiston', 2019, 2, '2026-01-26 10:00:00'),
(27, 'Sniper Americano', 'Chris Kyle', 2012, 2, '2026-02-19 10:00:00');

-- -----------------------------------------------------------------------------
-- 🏷️ ASSOCIAÇÕES DE CATEGORIAS (IDs de 1 a 6)
-- -----------------------------------------------------------------------------
INSERT INTO livro_categorias (id_livro, id_categoria) VALUES
(1, 1), (2, 1),   -- Fantasia
(3, 2), (4, 2),   -- Romance
(5, 3), (6, 3),   -- Terror
(7, 4), (8, 4),   -- Ação
(9, 5), (10, 5),  -- Suspense
(11, 6), (12, 6), -- Aventura

-- Famosos
(13, 1), (14, 3), (15, 4), (16, 5), (17, 6),

-- Mais Procurados
(18, 2), (19, 2), (20, 5), (21, 1), (22, 5),

-- Lançamentos
(23, 2), (24, 2), (25, 5), (26, 2), (27, 4);

-- -----------------------------------------------------------------------------
-- 📦 EXEMPLARES
-- -----------------------------------------------------------------------------
INSERT INTO exemplares (id_livro, posicao_estante, status_exemplar) VALUES
(1, 'Corredor A - Estante 1', 'Disponível'), (1, 'Corredor A - Estante 1', 'Disponível'),
(2, 'Corredor A - Estante 1', 'Disponível'), (2, 'Corredor A - Estante 1', 'Disponível'),
(3, 'Corredor B - Estante 1', 'Disponível'), (3, 'Corredor B - Estante 1', 'Disponível'),
(4, 'Corredor B - Estante 1', 'Disponível'), (4, 'Corredor B - Estante 1', 'Disponível'),
(5, 'Corredor C - Estante 1', 'Disponível'), (5, 'Corredor C - Estante 1', 'Disponível'),
(6, 'Corredor C - Estante 1', 'Disponível'), (6, 'Corredor C - Estante 1', 'Disponível'),
(7, 'Corredor D - Estante 1', 'Disponível'), (7, 'Corredor D - Estante 1', 'Disponível'),
(8, 'Corredor D - Estante 1', 'Disponível'), (8, 'Corredor D - Estante 1', 'Disponível'),
(9, 'Corredor E - Estante 1', 'Disponível'), (9, 'Corredor E - Estante 1', 'Disponível'),
(10, 'Corredor E - Estante 1', 'Disponível'), (10, 'Corredor E - Estante 1', 'Disponível'),
(11, 'Corredor F - Estante 1', 'Disponível'), (11, 'Corredor F - Estante 1', 'Disponível'),
(12, 'Corredor F - Estante 1', 'Disponível'), (12, 'Corredor F - Estante 1', 'Disponível'),
(13, 'Corredor A - Estante 2', 'Disponível'), (13, 'Corredor A - Estante 2', 'Disponível'),
(14, 'Corredor C - Estante 2', 'Disponível'), (14, 'Corredor C - Estante 2', 'Disponível'),
(15, 'Corredor D - Estante 2', 'Disponível'), (15, 'Corredor D - Estante 2', 'Disponível'),
(16, 'Corredor E - Estante 2', 'Disponível'), (16, 'Corredor E - Estante 2', 'Disponível'),
(17, 'Corredor F - Estante 2', 'Disponível'), (17, 'Corredor F - Estante 2', 'Disponível'),
(18, 'Corredor B - Estante 2', 'Disponível'), (18, 'Corredor B - Estante 2', 'Disponível'),
(19, 'Corredor B - Estante 2', 'Disponível'), (19, 'Corredor B - Estante 2', 'Disponível'),
(20, 'Corredor E - Estante 2', 'Disponível'), (20, 'Corredor E - Estante 2', 'Disponível'),
(21, 'Corredor A - Estante 2', 'Disponível'), (21, 'Corredor A - Estante 2', 'Disponível'),
(22, 'Corredor E - Estante 2', 'Disponível'), (22, 'Corredor E - Estante 2', 'Disponível'),
(23, 'Corredor B - Estante 3', 'Disponível'), (23, 'Corredor B - Estante 3', 'Disponível'),
(24, 'Corredor B - Estante 3', 'Disponível'), (24, 'Corredor B - Estante 3', 'Disponível'),
(25, 'Corredor E - Estante 3', 'Disponível'), (25, 'Corredor E - Estante 3', 'Disponível'),
(26, 'Corredor B - Estante 3', 'Disponível'), (26, 'Corredor B - Estante 3', 'Disponível'),
(27, 'Corredor D - Estante 3', 'Disponível'), (27, 'Corredor D - Estante 3', 'Disponível');

-- -----------------------------------------------------------------------------
-- 🔄 EMPRÉSTIMOS E AJUSTE DE STATUS DE EXEMPLARES
-- -----------------------------------------------------------------------------
INSERT INTO emprestimos (id_exemplar, id_leitor, id_funcionario, data_devolucao_prevista, status_emprestimo) VALUES
(1, 1, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo'),
(5, 2, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo'),
(9, 3, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo'),
(15, 1, 1, DATE_SUB(CURRENT_DATE(), INTERVAL 2 DAY), 'Ativo'),
(21, 2, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo');

-- Marca todos os exemplares dos livros 18, 19, 20 e 23 como 'Emprestado'
-- para permitir que entrem na fila de reservas sem violar o Trigger
UPDATE exemplares 
SET status_exemplar = 'Emprestado' 
WHERE id_livro IN (18, 19, 20, 23);

-- -----------------------------------------------------------------------------
-- 📌 RESERVAS
-- -----------------------------------------------------------------------------
INSERT INTO reservas (id_livro, id_leitor) VALUES
(18, 1),
(19, 2),
(20, 3),
(23, 1);
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