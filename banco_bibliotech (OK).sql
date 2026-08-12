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
    -- NOVO: permite "excluir" um funcionário sem perder o vínculo histórico
    -- com empréstimos que ele já processou (a FK de emprestimos é RESTRICT,
    -- então um DELETE físico falharia se ele já bateu algum empréstimo).
    status_funcionario ENUM('Ativo', 'Inativo') NOT NULL DEFAULT 'Ativo',
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
    titulo VARCHAR(100),
    autor VARCHAR(50) NOT NULL,
    ano_publicacao INT,
    quant_estoque INT NOT NULL DEFAULT 1,
    sinopse TEXT,
    capa VARCHAR(500),
    -- NOVO: permite "excluir" um livro do catálogo sem perder o vínculo
    -- histórico com empréstimos antigos (mesma lógica do funcionário acima).
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
    -- NOVO: guarda a última posição na fila que já foi informada ao leitor,
    -- para só disparar uma nova notificação quando a posição REALMENTE mudar
    -- (em vez de notificar toda vez que a fila é recalculada).
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
 
    -- Só se aplica a quem está entrando na FILA DE ESPERA (status 'Pendente').
    -- A reserva direta para retirada (status 'Aguardando Retirada') é o fluxo
    -- correto quando HÁ exemplares disponíveis, então não deve ser bloqueada.
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
 
INSERT INTO categorias (id_categoria, nome_categoria) VALUES 
(1, 'Ficção Científica'),
(2, 'Fantasia'),
(3, 'Romance'),
(4, 'Terror'),
(5, 'Ação'),
(6, 'Suspense'),
(7, 'Aventura');
 
-- Senhas de demonstração (hash real via werkzeug generate_password_hash):
-- Carlos: B123 | Isabela: B456 | Felipe: L123 | Larissa: L456 | Amanda: L789
INSERT INTO funcionarios (nome, id_cargo, email, telefone, senha, tipo_perfil) VALUES
('Carlos Silva', 1, 'carlos@bliblitech.com', '11999998888', 'scrypt:32768:8:1$nPV45UkwdKmGkuRe$103d1d7ce6706f2ae5d64800ada5fc3bbb6a0114567481f85af73e69d98ccc8172f07a2fa57aabe15d31faac773b316a5fa3ccac986171434a53252a0cc2d953', 'FUNCIONARIO'),
('Isabela Matos', 2, 'isa@biblitech.com', '31972321537', 'scrypt:32768:8:1$vrBHjFfBdgrubZq0$ff6236bd1e79412f91aae438a8480aa3b154e762be69b7ea7f00585e97a4647e45486fc845cdccb3561b1d5650f94dd957fdb69d3d6bbe093a50f45426f54ffd', 'FUNCIONARIO');
 
INSERT INTO leitores (nome, email, telefone, senha, tipo_perfil, consentimento_lgpd) VALUES 
('Felipe Rios', 'felipe@gmail.com', '11977776666', 'scrypt:32768:8:1$4FMnn5lwlsz1hrz9$2d5a1d34307e245c2d5bdaef340b8cd1bc8ba2dbda7b2fae2f1bfcde0b6ac278615c9675890bd7630793be2c845f43a62c3d0850d4ca1563e0e71686f7969057', 'LEITOR', 1),
('Larissa Matias', 'ly@gmail.com', '31971165397', 'scrypt:32768:8:1$SfJ1au7yngbpB97j$59b96fd0ac014acc844b1fcf2cc290ee7ccb185b593fa43cc05549c32d3b55a9c9ce2778350bcea714a1f17cd98c4ea2c3c61b03ce8fbcad81287f8695c4f684', 'LEITOR', 1),
('Amanda Souza', 'amanda@gmail.com', '31988887777', 'scrypt:32768:8:1$oAUiGU9RllBjYHOC$6c8e736c5fcc18bfaf9b6aa61e8692296c8712eec9002fa27e764ae7820d7b4e81c8dd9be06c40005bfc9586d67e9b50f6ab0a1394ccda4b14120645fe6abf0b', 'LEITOR', 1);
 
-- -----------------------------------------------------------------------------
-- 📚 CADASTRO DOS 70 LIVROS
-- -----------------------------------------------------------------------------
 
INSERT INTO livro (id_livro, titulo, autor, ano_publicacao, quant_estoque, cadastro) VALUES
-- Categorias: FICÇÃO CIENTÍFICA (IDs 1 ao 10)
(1, 'Duna', 'Frank Herbert', 1965, 2, '2026-01-01 10:00:00'),
(2, 'Fahrenheit 451', 'Ray Bradbury', 1953, 2, '2026-01-02 10:00:00'),
(3, 'Neuromancer', 'William Gibson', 1984, 2, '2026-01-03 10:00:00'),
(4, 'Fundação', 'Isaac Asimov', 1951, 2, '2026-01-04 10:00:00'),
(5, 'O Guia do Mochileiro das Galáxias', 'Douglas Adams', 1979, 2, '2026-01-05 10:00:00'),
(6, 'O Problema dos Três Corpos', 'Cixin Liu', 2008, 2, '2026-01-06 10:00:00'),
(7, 'Androides Sonham com Ovelhas Elétricas?', 'Philip K. Dick', 1968, 2, '2026-01-07 10:00:00'),
(8, 'Perdido em Marte', 'Andy Weir', 2011, 2, '2026-01-08 10:00:00'),
(9, 'A Máquina do Tempo', 'H.G. Wells', 1895, 2, '2026-01-09 10:00:00'),
(10, 'Matéria Escura', 'Blake Crouch', 2016, 2, '2026-01-10 10:00:00'),
 
-- Categorias: FANTASIA (IDs 11 ao 20)
(11, 'O Hobbit', 'J.R.R. Tolkien', 1937, 2, '2026-01-11 10:00:00'),
(12, 'O Nome do Vento', 'Patrick Rothfuss', 2007, 2, '2026-01-12 10:00:00'),
(13, 'O Senhores dos Anéis: A Sociedade do Anel', 'J.R.R. Tolkien', 1954, 2, '2026-01-13 10:00:00'),
(14, 'Harry Potter e a Pedra Filosofal', 'J.K. Rowling', 1997, 2, '2026-01-14 10:00:00'),
(15, 'A Guerra dos Tronos', 'George R.R. Martin', 1996, 2, '2026-01-15 10:00:00'),
(16, 'Percy Jackson e o Ladrão de Raios', 'Rick Riordan', 2005, 2, '2026-01-16 10:00:00'),
(17, 'O Leão, a Feiticeira e o Guarda-Roupa', 'C.S. Lewis', 1950, 2, '2026-01-17 10:00:00'),
(18, 'Corte de Espinhos e Rosas', 'Sarah J. Maas', 2015, 2, '2026-01-18 10:00:00'),
(19, 'O Caminho dos Reis', 'Brandon Sanderson', 2010, 2, '2026-01-19 10:00:00'),
(20, 'Eragon', 'Christopher Paolini', 2002, 2, '2026-01-20 10:00:00'),
 
-- Categorias: ROMANCE (IDs 21 ao 30)
(21, 'Orgulho e Preconceito', 'Jane Austen', 1813, 2, '2026-01-21 10:00:00'),
(22, 'É Assim que Acaba', 'Colleen Hoover', 2016, 2, '2026-01-22 10:00:00'),
(23, 'É Assim que Começa', 'Colleen Hoover', 2022, 2, '2026-01-23 10:00:00'),
(24, 'Dom Casmurro', 'Machado de Assis', 1899, 2, '2026-01-24 10:00:00'),
(25, 'Os Sete Maridos de Evelyn Hugo', 'Taylor Jenkins Reid', 2017, 2, '2026-01-25 10:00:00'),
(26, 'Vermelho, Branco e Sangue Azul', 'Casey McQuiston', 2019, 2, '2026-01-26 10:00:00'),
(27, 'A Hipótese do Amor', 'Ali Hazelwood', 2021, 2, '2026-01-27 10:00:00'),
(28, 'Como Eu Era Antes de Você', 'Jojo Moyes', 2012, 2, '2026-01-28 10:00:00'),
(29, 'Jane Eyre', 'Charlotte Brontë', 1847, 2, '2026-01-29 10:00:00'),
(30, 'O Morro dos Ventos Uivantes', 'Emily Brontë', 1847, 2, '2026-01-30 10:00:00'),
 
-- Categorias: TERROR (IDs 31 ao 40)
(31, 'It: A Coisa', 'Stephen King', 1986, 2, '2026-02-01 10:00:00'),
(32, 'O Iluminado', 'Stephen King', 1977, 2, '2026-02-02 10:00:00'),
(33, 'Drácula', 'Bram Stoker', 1897, 2, '2026-02-03 10:00:00'),
(34, 'Frankenstein', 'Mary Shelley', 1818, 2, '2026-02-04 10:00:00'),
(35, 'O Exorcista', 'William Peter Blatty', 1971, 2, '2026-02-05 10:00:00'),
(36, 'Misery: Louca Obsessão', 'Stephen King', 1987, 2, '2026-02-06 10:00:00'),
(37, 'O Bicho-da-Seda', 'Robert Galbraith', 2014, 2, '2026-02-07 10:00:00'),
(38, 'A Hora do Vampiro', 'Stephen King', 1975, 2, '2026-02-08 10:00:00'),
(39, 'Satanás: Um Ensaio sobre o Mal', 'Andrew Laing', 2002, 2, '2026-02-09 10:00:00'),
(40, 'O Chamado de Cthulhu', 'H.P. Lovecraft', 1928, 2, '2026-02-10 10:00:00'),
 
-- Categorias: AÇÃO (IDs 41 ao 50)
(41, 'A Caçada ao Outubro Vermelho', 'Tom Clancy', 1984, 2, '2026-02-11 10:00:00'),
(42, 'Sem Remorso', 'Tom Clancy', 1993, 2, '2026-02-12 10:00:00'),
(43, 'O Agente das Sombras', 'Jason Bourne', 2010, 2, '2026-02-13 10:00:00'),
(44, 'A Identidade Bourne', 'Robert Ludlum', 1980, 2, '2026-02-14 10:00:00'),
(45, 'A Arte da Guerra', 'Sun Tzu', 2005, 2, '2026-02-15 10:00:00'),
(46, 'O Sobrevivente', 'Stephen King', 1982, 2, '2026-02-16 10:00:00'),
(47, 'Caçada Selvagem', 'Andy McNab', 1998, 2, '2026-02-17 10:00:00'),
(48, 'Ponto de Impacto', 'Dan Brown', 2001, 2, '2026-02-18 10:00:00'),
(49, 'Sniper Americano', 'Chris Kyle', 2012, 2, '2026-02-19 10:00:00'),
(50, 'Estrada da Sobrevivência', 'Cormac McCarthy', 2006, 2, '2026-02-20 10:00:00'),
 
-- Categorias: SUSPENSE (IDs 51 ao 60)
(51, 'O Código Da Vinci', 'Dan Brown', 2003, 2, '2026-02-21 10:00:00'),
(52, 'Anjos e Demônios', 'Dan Brown', 2000, 2, '2026-02-22 10:00:00'),
(53, 'A Garota no Trem', 'Paula Hawkins', 2015, 2, '2026-02-23 10:00:00'),
(54, 'Garota Exemplar', 'Gillian Flynn', 2012, 2, '2026-02-24 10:00:00'),
(55, 'O Silêncio dos Inocentes', 'Thomas Harris', 1988, 2, '2026-02-25 10:00:00'),
(56, 'A Paciente Silenciosa', 'Alex Michaelides', 2019, 2, '2026-02-26 10:00:00'),
(57, 'E Não Sobrou Nenhum', 'Agatha Christie', 1939, 2, '2026-02-27 10:00:00'),
(58, 'Assassinato no Expresso do Oriente', 'Agatha Christie', 1934, 2, '2026-02-28 10:00:00'),
(59, 'O Homem de Palha', 'C.J. Tudor', 2018, 2, '2026-03-01 10:00:00'),
(60, 'Verity', 'Colleen Hoover', 2018, 2, '2026-03-02 10:00:00'),
 
-- Categorias: AVENTURA (IDs 61 ao 70)
(61, 'O Alquimista', 'Paulo Coelho', 1988, 2, '2026-08-01 09:00:00'),
(62, 'A Ilha do Tesouro', 'Robert Louis Stevenson', 1883, 2, '2026-08-02 09:00:00'),
(63, 'As Aventuras de Tom Sawyer', 'Mark Twain', 1876, 2, '2026-08-03 09:00:00'),
(64, 'Viagem ao Centro da Terra', 'Júlio Verne', 1864, 2, '2026-08-04 09:00:00'),
(65, 'Vinte Mil Léguas Submarinas', 'Júlio Verne', 1870, 2, '2026-08-05 09:00:00'),
(66, 'A Volta ao Mundo em 80 Dias', 'Júlio Verne', 1872, 2, '2026-08-06 09:00:00'),
(67, 'O Chamado da Floresta', 'Jack London', 1903, 2, '2026-08-07 09:00:00'),
(68, 'As Minas do Rei Salomão', 'H. Rider Haggard', 1885, 2, '2026-08-08 09:00:00'),
(69, 'Moby Dick', 'Herman Melville', 1851, 2, '2026-08-08 14:00:00'),
(70, 'Robinson Crusoé', 'Daniel Defoe', 1719, 2, '2026-08-09 10:00:00');
 
-- Associações N:N nas Categorias
INSERT INTO livro_categorias (id_livro, id_categoria) VALUES
(1,1),(2,1),(3,1),(4,1),(5,1),(6,1),(7,1),(8,1),(9,1),(10,1),
(11,2),(12,2),(13,2),(14,2),(15,2),(16,2),(17,2),(18,2),(19,2),(20,2),
(21,3),(22,3),(23,3),(24,3),(25,3),(26,3),(27,3),(28,3),(29,3),(30,3),
(31,4),(32,4),(33,4),(34,4),(35,4),(36,4),(37,4),(38,4),(39,4),(40,4),
(41,5),(42,5),(43,5),(44,5),(45,5),(46,5),(47,5),(48,5),(49,5),(50,5),
(51,6),(52,6),(53,6),(54,6),(55,6),(56,6),(57,6),(58,6),(59,6),(60,6),
(61,7),(62,7),(63,7),(64,7),(65,7),(66,7),(67,7),(68,7),(69,7),(70,7);
 
-- Inserção dos Exemplares
INSERT INTO exemplares (id_livro, posicao_estante, status_exemplar) VALUES
-- Ficção Científica (1 a 10)
(1, 'Corredor A - Estante 1', 'Disponível'), (1, 'Corredor A - Estante 1', 'Disponível'),
(2, 'Corredor A - Estante 1', 'Disponível'), (2, 'Corredor A - Estante 1', 'Disponível'),
(3, 'Corredor A - Estante 1', 'Disponível'), (3, 'Corredor A - Estante 1', 'Disponível'),
(4, 'Corredor A - Estante 1', 'Disponível'), (4, 'Corredor A - Estante 1', 'Disponível'),
(5, 'Corredor A - Estante 1', 'Disponível'), (5, 'Corredor A - Estante 1', 'Disponível'),
(6, 'Corredor A - Estante 2', 'Disponível'), (6, 'Corredor A - Estante 2', 'Disponível'),
(7, 'Corredor A - Estante 2', 'Disponível'), (7, 'Corredor A - Estante 2', 'Disponível'),
(8, 'Corredor A - Estante 2', 'Disponível'), (8, 'Corredor A - Estante 2', 'Disponível'),
(9, 'Corredor A - Estante 2', 'Disponível'), (9, 'Corredor A - Estante 2', 'Disponível'),
(10, 'Corredor A - Estante 2', 'Disponível'), (10, 'Corredor A - Estante 2', 'Disponível'),
 
-- Fantasia (11 a 20)
(11, 'Corredor B - Estante 1', 'Disponível'), (11, 'Corredor B - Estante 1', 'Disponível'),
(12, 'Corredor B - Estante 1', 'Disponível'), (12, 'Corredor B - Estante 1', 'Disponível'),
(13, 'Corredor B - Estante 1', 'Disponível'), (13, 'Corredor B - Estante 1', 'Disponível'),
(14, 'Corredor B - Estante 1', 'Disponível'), (14, 'Corredor B - Estante 1', 'Disponível'),
(15, 'Corredor B - Estante 1', 'Disponível'), (15, 'Corredor B - Estante 1', 'Disponível'),
(16, 'Corredor B - Estante 2', 'Disponível'), (16, 'Corredor B - Estante 2', 'Disponível'),
(17, 'Corredor B - Estante 2', 'Disponível'), (17, 'Corredor B - Estante 2', 'Disponível'),
(18, 'Corredor B - Estante 2', 'Disponível'), (18, 'Corredor B - Estante 2', 'Disponível'),
(19, 'Corredor B - Estante 2', 'Disponível'), (19, 'Corredor B - Estante 2', 'Disponível'),
(20, 'Corredor B - Estante 2', 'Disponível'), (20, 'Corredor B - Estante 2', 'Disponível'),
 
-- Romance (21 a 30)
(21, 'Corredor C - Estante 1', 'Disponível'), (21, 'Corredor C - Estante 1', 'Disponível'),
(22, 'Corredor C - Estante 1', 'Disponível'), (22, 'Corredor C - Estante 1', 'Disponível'),
(23, 'Corredor C - Estante 1', 'Disponível'), (23, 'Corredor C - Estante 1', 'Disponível'),
(24, 'Corredor C - Estante 1', 'Disponível'), (24, 'Corredor C - Estante 1', 'Disponível'),
(25, 'Corredor C - Estante 1', 'Disponível'), (25, 'Corredor C - Estante 1', 'Disponível'),
(26, 'Corredor C - Estante 2', 'Disponível'), (26, 'Corredor C - Estante 2', 'Disponível'),
(27, 'Corredor C - Estante 2', 'Disponível'), (27, 'Corredor C - Estante 2', 'Disponível'),
(28, 'Corredor C - Estante 2', 'Disponível'), (28, 'Corredor C - Estante 2', 'Disponível'),
(29, 'Corredor C - Estante 2', 'Disponível'), (29, 'Corredor C - Estante 2', 'Disponível'),
(30, 'Corredor C - Estante 2', 'Disponível'), (30, 'Corredor C - Estante 2', 'Disponível'),
 
-- Terror (31 a 40)
(31, 'Corredor D - Estante 1', 'Disponível'), (31, 'Corredor D - Estante 1', 'Disponível'),
(32, 'Corredor D - Estante 1', 'Disponível'), (32, 'Corredor D - Estante 1', 'Disponível'),
(33, 'Corredor D - Estante 1', 'Disponível'), (33, 'Corredor D - Estante 1', 'Disponível'),
(34, 'Corredor D - Estante 1', 'Disponível'), (34, 'Corredor D - Estante 1', 'Disponível'),
(35, 'Corredor D - Estante 1', 'Disponível'), (35, 'Corredor D - Estante 1', 'Disponível'),
(36, 'Corredor D - Estante 2', 'Disponível'), (36, 'Corredor D - Estante 2', 'Disponível'),
(37, 'Corredor D - Estante 2', 'Disponível'), (37, 'Corredor D - Estante 2', 'Disponível'),
(38, 'Corredor D - Estante 2', 'Disponível'), (38, 'Corredor D - Estante 2', 'Disponível'),
(39, 'Corredor D - Estante 2', 'Disponível'), (39, 'Corredor D - Estante 2', 'Disponível'),
(40, 'Corredor D - Estante 2', 'Disponível'), (40, 'Corredor D - Estante 2', 'Disponível'),
 
-- Ação (41 a 50)
(41, 'Corredor E - Estante 1', 'Disponível'), (41, 'Corredor E - Estante 1', 'Disponível'),
(42, 'Corredor E - Estante 1', 'Disponível'), (42, 'Corredor E - Estante 1', 'Disponível'),
(43, 'Corredor E - Estante 1', 'Disponível'), (43, 'Corredor E - Estante 1', 'Disponível'),
(44, 'Corredor E - Estante 1', 'Disponível'), (44, 'Corredor E - Estante 1', 'Disponível'),
(45, 'Corredor E - Estante 1', 'Disponível'), (45, 'Corredor E - Estante 1', 'Disponível'),
(46, 'Corredor E - Estante 2', 'Disponível'), (46, 'Corredor E - Estante 2', 'Disponível'),
(47, 'Corredor E - Estante 2', 'Disponível'), (47, 'Corredor E - Estante 2', 'Disponível'),
(48, 'Corredor E - Estante 2', 'Disponível'), (48, 'Corredor E - Estante 2', 'Disponível'),
(49, 'Corredor E - Estante 2', 'Disponível'), (49, 'Corredor E - Estante 2', 'Disponível'),
(50, 'Corredor E - Estante 2', 'Disponível'), (50, 'Corredor E - Estante 2', 'Disponível'),
 
-- Suspense (51 a 60)
(51, 'Corredor F - Estante 1', 'Disponível'), (51, 'Corredor F - Estante 1', 'Disponível'),
(52, 'Corredor F - Estante 1', 'Disponível'), (52, 'Corredor F - Estante 1', 'Disponível'),
(53, 'Corredor F - Estante 1', 'Disponível'), (53, 'Corredor F - Estante 1', 'Disponível'),
(54, 'Corredor F - Estante 1', 'Disponível'), (54, 'Corredor F - Estante 1', 'Disponível'),
(55, 'Corredor F - Estante 1', 'Disponível'), (55, 'Corredor F - Estante 1', 'Disponível'),
(56, 'Corredor F - Estante 2', 'Disponível'), (56, 'Corredor F - Estante 2', 'Disponível'),
(57, 'Corredor F - Estante 2', 'Disponível'), (57, 'Corredor F - Estante 2', 'Disponível'),
(58, 'Corredor F - Estante 2', 'Disponível'), (58, 'Corredor F - Estante 2', 'Disponível'),
(59, 'Corredor F - Estante 2', 'Disponível'), (59, 'Corredor F - Estante 2', 'Disponível'),
(60, 'Corredor F - Estante 2', 'Disponível'), (60, 'Corredor F - Estante 2', 'Disponível'),
 
-- Aventura (61 a 70)
(61, 'Corredor G - Estante 1', 'Disponível'), (61, 'Corredor G - Estante 1', 'Disponível'),
(62, 'Corredor G - Estante 1', 'Disponível'), (62, 'Corredor G - Estante 1', 'Disponível'),
(63, 'Corredor G - Estante 1', 'Disponível'), (63, 'Corredor G - Estante 1', 'Disponível'),
(64, 'Corredor G - Estante 1', 'Disponível'), (64, 'Corredor G - Estante 1', 'Disponível'),
(65, 'Corredor G - Estante 1', 'Disponível'), (65, 'Corredor G - Estante 1', 'Disponível'),
(66, 'Corredor G - Estante 2', 'Disponível'), (66, 'Corredor G - Estante 2', 'Disponível'),
(67, 'Corredor G - Estante 2', 'Disponível'), (67, 'Corredor G - Estante 2', 'Disponível'),
(68, 'Corredor G - Estante 2', 'Disponível'), (68, 'Corredor G - Estante 2', 'Disponível'),
(69, 'Corredor G - Estante 2', 'Disponível'), (69, 'Corredor G - Estante 2', 'Disponível'),
(70, 'Corredor G - Estante 2', 'Disponível'), (70, 'Corredor G - Estante 2', 'Disponível');
 
-- -----------------------------------------------------------------------------
-- 🔄 REGISTRO DE EMPRÉSTIMOS ATIVOS
-- -----------------------------------------------------------------------------
INSERT INTO emprestimos (id_exemplar, id_leitor, id_funcionario, data_devolucao_prevista, status_emprestimo) VALUES
(5, 1, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo'), (6, 2, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo'),
(11, 1, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo'), (12, 2, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo'),
(13, 1, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo'), (14, 3, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo'),
(19, 2, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo'), (20, 3, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo'),
(23, 1, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo'),
(29, 2, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo'), (30, 3, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo'),
(35, 3, 1, DATE_SUB(CURRENT_DATE(), INTERVAL 5 DAY), 'Ativo'), (36, 1, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo'),
(37, 1, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo'), (38, 2, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo'),
(45, 2, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo'), (46, 3, 1, DATE_SUB(CURRENT_DATE(), INTERVAL 2 DAY), 'Ativo'),
(63, 3, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo'), (64, 1, 1, DATE_ADD(CURRENT_DATE(), INTERVAL 14 DAY), 'Ativo');
 
UPDATE exemplares SET status_exemplar = 'Reservado' WHERE id_exemplar = 24;
 
-- -----------------------------------------------------------------------------
-- 📌 REGISTRO DAS RESERVAS NA FILA DE ESPERA
-- -----------------------------------------------------------------------------
INSERT INTO reservas (id_livro, id_leitor) VALUES
(3, 1), (3, 2), (3, 3),
(6, 1), (6, 2),
(7, 1), (7, 3),
(10, 2),
(12, 1),
(15, 2),
(18, 3),
(19, 1),
(23, 2),
(32, 3);
 
-- -----------------------------------------------------------------------------
-- 💬 REGISTRO DAS AVALIAÇÕES / COMENTÁRIOS (TODOS OS 70 LIVROS)
-- -----------------------------------------------------------------------------
INSERT INTO avaliacoes (livro_id, leitor_id, nota, comentario, data_avaliacao) VALUES
-- Ficção Científica (1 ao 10)
(1, 2, 5, 'Uma obra-prima absoluta da ficção científica. A construção de Arrakis e a profundidade política e filosófica são simplesmente inigualáveis. Super recomendo!', '2026-02-01 14:30:00'),
(2, 2, 5, 'Uma reflexão assustadoramente atual sobre censura e o valor do conhecimento. Leitura rápida, impactante e totalmente transformadora!', '2026-02-02 11:15:00'),
(3, 1, 4, 'O pai do cyberpunk! Atmosfera sombria, ritmo acelerado e uma visão futurista incrível para a época.', '2026-02-03 16:45:00'),
(4, 3, 5, 'A escala da Fundação é fascinante. Isaac Asimov demonstra uma genialidade única ao estruturar a psicho-história.', '2026-02-04 09:20:00'),
(5, 2, 5, 'Divertidíssimo, inteligente e extremamente sagaz! Uma leitura leve que te faz dar gargalhadas do início ao fim.', '2026-02-05 18:10:00'),
(6, 1, 5, 'Uma das melhores e mais complexas ficções científicas da atualidade. O conceito do primeiro contato é brilhante!', '2026-02-06 13:00:00'),
(7, 3, 4, 'Questionamentos profundos sobre humanidade, empatia e o que nos define como seres vivos. Excelente!', '2026-02-07 15:40:00'),
(8, 2, 5, 'Incrivelmente bem pesquisado e empolgante! A resiliência do protagonista te prende em cada página.', '2026-02-08 10:25:00'),
(9, 1, 4, 'Um clássico atemporal que definiu o gênero de viagem no tempo. Vale cada segundo de leitura!', '2026-02-09 17:30:00'),
(10, 2, 5, 'Rápido, frenético e cheio de reviravoltas psicológicas. Impossível parar de ler até o capítulo final!', '2026-02-10 20:00:00'),
 
-- Fantasia (11 ao 20)
(11, 3, 5, 'A aventura perfeita para aquecer o coração! Uma jornada inesquecível do início ao fim.', '2026-02-11 12:00:00'),
(12, 2, 5, 'A narrativa do Patrick Rothfuss é pura poesia. A construção de mundo e a trajetória de Kvothe são arrebatadoras!', '2026-02-12 14:20:00'),
(13, 1, 5, 'A base de toda a fantasia moderna. A profundidade da mitologia desenvolvida por Tolkien é incomparável.', '2026-02-13 19:10:00'),
(14, 2, 5, 'Pura nostalgia e magia. A introdução mágica ideal para leitores de todas as idades!', '2026-02-14 16:05:00'),
(15, 3, 5, 'Intrigas políticas, personagens cinzentos e reviravoltas chocantes. Uma aula de escrita fantástica!', '2026-02-15 21:30:00'),
(16, 1, 4, 'Releitura fantástica da mitologia grega nos dias atuais. Divertido, dinâmico e muito cativante!', '2026-02-16 11:45:00'),
(17, 2, 5, 'Um clássico encantador repleto de alegorias marcantes e personagens inesquecíveis.', '2026-02-17 15:15:00'),
(18, 2, 5, 'Imersão pura em um universo de feéricos marcante. O desenvolvimento da protagonista e o romance são perfeitos!', '2026-02-18 22:10:00'),
(19, 1, 5, 'Construção de mundo épica e sistema de magia impecável. Brandon Sanderson entrega uma obra monumental!', '2026-02-19 18:00:00'),
(20, 3, 4, 'Uma aventura clássica sobre dragões e amizade que continua empolgando muito!', '2026-02-20 13:50:00'),
 
-- Romance (21 ao 30)
(21, 2, 5, 'Diálogos afiados, química impecável e uma crítica social genial. O romance supremo da literatura!', '2026-02-21 10:00:00'),
(22, 2, 5, 'Um livro forte, emocionalmente intenso e extremamente necessário. Colleen Hoover aborda temas delicados com muita responsabilidade.', '2026-02-22 17:40:00'),
(23, 2, 5, 'O fechamento que a história tanto merecia. Ver a superação e o carinho entre os personagens aquece a alma!', '2026-02-23 20:15:00'),
(24, 1, 4, 'Machado de Assis em sua forma mais brilhante. Um enigma psicológico envolvente do começo ao fim.', '2026-02-24 14:00:00'),
(25, 2, 5, 'Uma trajetória avassaladora e envolvente sobre a era de ouro de Hollywood. Evelyn Hugo é uma personagem inesquecível!', '2026-02-25 19:30:00'),
(26, 3, 5, 'Leve, apaixonante e incrivelmente divertido. Uma comédia romântica moderna impecável!', '2026-02-26 12:10:00'),
(27, 2, 5, 'O clichê de namoro de mentirinha executado da forma mais perfeita possível. Apaixonante e muito fofo!', '2026-02-27 16:25:00'),
(28, 3, 5, 'Uma história emocionante que toca no fundo do coração e provoca reflexões profundas sobre a vida e escolhas.', '2026-02-28 11:35:00'),
(29, 2, 5, 'Uma heroína forte, independente e a frente do seu tempo. Um romance gótico fascinante!', '2026-03-01 15:50:00'),
(30, 1, 4, 'Intenso, sombrio e cheio de paixão avassaladora. Um clássico inesquecível da literatura britânica.', '2026-03-02 18:05:00'),
 
-- Terror (31 ao 40)
(31, 1, 5, 'Uma exploração visceral do medo infantil e da amizade. Stephen King no seu auge absoluto!', '2026-03-03 21:00:00'),
(32, 2, 5, 'Construção de tensão impecável. O isolamento no Hotel Overlook é claustrofóbico e aterrorizante!', '2026-03-04 13:15:00'),
(33, 3, 5, 'O clássico supremo do terror gótico. Estrutura epistolar brilhante e atmosfera sombria impecável.', '2026-03-05 17:00:00'),
(34, 2, 5, 'Uma reflexão tocante sobre rejeição, ambição científica e a condição humana. Essencial!', '2026-03-06 10:45:00'),
(35, 1, 4, 'Perturbador e incrivelmente bem escrito. Mantém um ritmo sufocante até as páginas finais.', '2026-03-07 22:30:00'),
(36, 2, 5, 'Agoniante e claustrofóbico! A relação entre criador e fã obcecada é conduzida com maestria.', '2026-03-08 14:20:00'),
(37, 3, 4, 'Misterioso, com ótimas pitadas de investigação e um tom sombrio instigante.', '2026-03-09 19:10:00'),
(38, 1, 4, 'Uma abordagem clássica e assustadora sobre vampiros invadindo uma pequena cidade.', '2026-03-10 16:00:00'),
(39, 2, 4, 'Análise envolvente e densa sobre os mitos e o horror psicológico. Muito instigante!', '2026-03-11 11:30:00'),
(40, 3, 5, 'Mito cosmogônico perturbador e fascínio pelo desconhecido. Lovecraft revolucionou o horror!', '2026-03-12 20:40:00'),
 
-- Ação (41 ao 50)
(41, 1, 5, 'Tensão militar estratégica do mais alto nível. Tom Clancy detalha cada movimento com perfeição!', '2026-03-13 15:00:00'),
(42, 3, 4, 'Uma história de vingança rápida, eletrizante e cheia de táticas realistas.', '2026-03-14 18:25:00'),
(43, 1, 4, 'Adrenalina pura e conspirações internacionais. Muito dinâmico e cativante!', '2026-03-15 12:40:00'),
(44, 2, 5, 'Um marco nas histórias de espionagem e perda de identidade. Ritmo frenético constante!', '2026-03-16 16:15:00'),
(45, 1, 5, 'Lições de estratégia e liderança que transcendem séculos. Um verdadeiro tratado de sabedoria!', '2026-03-17 09:30:00'),
(46, 3, 4, 'Distopia de ação intensa com ritmo veloz. King entrega mais uma trama eletrizante!', '2026-03-18 20:00:00'),
(47, 1, 4, 'Combates realistas e narrativa direto ao ponto. Excelente para quem busca ação crua!', '2026-03-19 14:10:00'),
(48, 2, 5, 'Ciência, ação e mistério entrelaçados com maestria por Dan Brown. Surpreendente!', '2026-03-20 17:50:00'),
(49, 3, 4, 'Relato humano e visceral sobre os desafios do campo de batalha moderno.', '2026-03-21 13:05:00'),
(50, 1, 5, 'Pós-apocalipse cru, poético e emocionante. Uma das abordagens mais marcantes da sobrevivência humana.', '2026-03-22 19:15:00'),
 
-- Suspense (51 ao 60)
(51, 2, 5, 'Quebra-cabeças histórico brilhante! Uma caça ao tesouro intelectual que prende do começo ao fim.', '2026-03-23 11:20:00'),
(52, 1, 5, 'Ainda mais dinâmico que O Código Da Vinci! Corrida contra o tempo alucinante em Roma.', '2026-03-24 15:35:00'),
(53, 3, 4, 'Narrativa instável e cheia de suspense psicológico que te faz duvidar de todos os personagens.', '2026-03-25 18:45:00'),
(54, 2, 5, 'Uma reviravolta no meio do livro que muda tudo! Um thriller psicológico genial e sombrio.', '2026-03-26 21:10:00'),
(55, 1, 5, 'Clarice Starling e Hannibal Lecter travam um duelo mental inesquecível. Tensão no estado puro!', '2026-03-27 14:00:00'),
(56, 2, 5, 'Um final absolutamente chocante que recontextualiza o livro inteiro. Perfeito!', '2026-03-28 16:50:00'),
(57, 3, 5, 'A rainha do crime em seu momento mais genial. Isolamento, mistério e um desfecho impecável!', '2026-03-29 10:15:00'),
(58, 2, 5, 'Hercule Poirot resolvendo um crime impossível dentro de um trem preso na neve. Simplesmente clássico!', '2026-03-30 13:40:00'),
(59, 1, 4, 'Sombrio, perturbador e repleto de mistérios do passado. Muito envolvente!', '2026-03-31 17:25:00'),
(60, 2, 5, 'Perturbador, viciante e chocante! Colleen Hoover mostra sua versatilidade ao entregar um thriller psicológico impecável.', '2026-04-01 20:30:00'),
 
-- Aventura (61 ao 70)
(61, 2, 5, 'Uma jornada poética sobre seguir seus sonhos e escutar a voz do coração. Lindo e inspirador!', '2026-04-02 09:00:00'),
(62, 1, 5, 'A aventura definitiva de piratas! Mapa do tesouro, motins e personagens inesquecíveis.', '2026-04-03 14:15:00'),
(63, 3, 4, 'Toda a essência da juventude e da liberdade em uma leitura leve, divertida e encantadora.', '2026-04-04 11:50:00'),
(64, 2, 5, 'A imaginação do Júlio Verne é extraordinária. Uma expedição científica repleta de maravilhas!', '2026-04-05 16:30:00'),
(65, 1, 5, 'Capitão Nemo é um dos personagens mais complexos e fascinantes da literatura. Obra fantástica!', '2026-04-06 18:10:00'),
(66, 3, 5, 'Uma corrida contra o tempo cheia de carisma, humor e paisagens diversas pelo mundo.', '2026-04-07 13:25:00'),
(67, 1, 4, 'Uma história emocionante sobre a força da natureza e o retorno às origens selvagens.', '2026-04-08 15:40:00'),
(68, 2, 4, 'Exploração de continentes desconhecidos, perigos e tesouros lendários no melhor estilo clássico.', '2026-04-09 10:05:00'),
(69, 1, 5, 'A obsessão humana levada ao extremo. Uma obra épica, profunda e cheia de simbolismos.', '2026-04-10 19:00:00'),
(70, 3, 4, 'Um clássico sobre sobrevivência, engenhosidade e solidão em uma ilha deserta.', '2026-04-11 12:30:00');
