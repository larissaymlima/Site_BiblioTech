DROP DATABASE IF EXISTS bliblitech;
CREATE DATABASE IF NOT EXISTS bliblitech;
USE bliblitech;


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
    sms VARCHAR(15) NOT NULL,
    senha VARCHAR(255) NOT NULL,
    foto_perfil VARCHAR(255) DEFAULT 'default_profile.png',
    tipo_perfil ENUM('FUNCIONARIO', 'LEITOR') NOT NULL,
    data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP, -- bloqueio de segurança (contra exclusão)
   FOREIGN KEY (id_cargo) REFERENCES cargos(id_cargo) ON DELETE RESTRICT ON UPDATE CASCADE
);


CREATE TABLE categorias (
   id_categoria INT AUTO_INCREMENT PRIMARY KEY,
    nome_categoria VARCHAR(50) NOT NULL
);

CREATE TABLE livro (
id_livro INT AUTO_INCREMENT PRIMARY KEY,
titulo VARCHAR(100),
autor VARCHAR (50) not null,
ano_publicacao INT,
quant_estoque INT NOT NULL DEFAULT 1,
sinopse TEXT,
capa VARCHAR(500),
cadastro timestamp default current_timestamp
);

-- Livros <-> Categorias (Relacionamento N:N)
CREATE TABLE livro_categorias (
    id_livro INT NOT NULL,
    id_categoria INT NOT NULL,
    PRIMARY KEY (id_livro, id_categoria),
    FOREIGN KEY (id_livro) REFERENCES livro(id_livro) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (id_categoria) REFERENCES categorias(id_categoria) ON DELETE CASCADE ON UPDATE CASCADE -- ON DELETE CASCADE todas as associações dele serão apagadas. ON UPDATE CASCADE: Se o ID do livro mudar, a alteração reflete aqui automaticamente.
);

CREATE TABLE leitores (
   id_leitor INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    email VARCHAR(100) NOT NULL UNIQUE,
    telefone VARCHAR(15) NOT NULL,
    sms VARCHAR(15) NOT NULL,
    senha VARCHAR(255) NOT NULL,
    foto_perfil VARCHAR(255) DEFAULT 'default_profile.png',
    tipo_perfil ENUM('FUNCIONARIO', 'LEITOR') NOT NULL,
    data_cadastro DATETIME DEFAULT CURRENT_TIMESTAMP,
    status_conta ENUM('Ativo', 'Suspenso', 'Bloqueado') DEFAULT 'Ativo'
   );
   
   CREATE TABLE exemplares (
    id_exemplar INT AUTO_INCREMENT PRIMARY KEY,
    id_livro INT NOT NULL,
    posicao_estante VARCHAR(50),
    status_exemplar ENUM('Disponível', 'Emprestado', 'Indisponível') DEFAULT 'Disponível',
    FOREIGN KEY (id_livro) REFERENCES livro(id_livro) ON DELETE CASCADE ON UPDATE CASCADE
);

   CREATE TABLE emprestimos (
    id_emprestimo INT AUTO_INCREMENT PRIMARY KEY,
    id_exemplar INT NOT NULL,
    id_leitor INT NOT NULL,
    id_funcionario INT NOT NULL, -- Quem registrou a saída do livro
    data_emprestimo DATETIME DEFAULT CURRENT_TIMESTAMP,
    data_devolucao_esperado DATE NULL, -- Preenchida pelo Trigger
    data_devolucao_real DATETIME NULL, -- Preenchido só quando o leitor devolver
    status_emprestimo ENUM('Ativo', 'Devolvido', 'Atrasado') DEFAULT 'Ativo',
    
    FOREIGN KEY (id_exemplar) REFERENCES exemplares(id_exemplar) ON DELETE RESTRICT ON UPDATE CASCADE,
    FOREIGN KEY (id_leitor) REFERENCES leitores(id_leitor) ON DELETE RESTRICT ON UPDATE CASCADE,
    FOREIGN KEY (id_funcionario) REFERENCES funcionarios(id_funcionario) ON DELETE RESTRICT ON UPDATE CASCADE
);

-- TRIGGERS
DELIMITER //

-- Trigger que muda o status do exemplar para 'Emprestado' após registro do empréstimo
CREATE TRIGGER apos_inserir_emprestimo
AFTER INSERT ON emprestimos
FOR EACH ROW
BEGIN
    -- Altera o status do exemplar associado ao novo empréstimo para 'Emprestado'
    UPDATE exemplares 
    SET status_exemplar = 'Emprestado' 
    WHERE id_exemplar = NEW.id_exemplar;
END //
DELIMITER ;
DROP TABLE IF EXISTS reservas;
-- Tabela de Reservas
CREATE TABLE reservas (
    id_reserva INT AUTO_INCREMENT PRIMARY KEY,
    id_livro INT NOT NULL,
    id_leitor INT NOT NULL,
    data_reserva DATETIME DEFAULT CURRENT_TIMESTAMP,
    status_reserva ENUM('Pendente', 'Concluida', 'Cancelada') DEFAULT 'Pendente',
    
    FOREIGN KEY (id_livro) REFERENCES livro(id_livro) ON DELETE CASCADE ON UPDATE CASCADE,
    FOREIGN KEY (id_leitor) REFERENCES leitores(id_leitor) ON DELETE RESTRICT ON UPDATE CASCADE
);

DELIMITER // -- substitiu o ; para // no bloco

CREATE TRIGGER antes_inserir_reserva -- declara novo gatilho para antes_inserir_reserva
BEFORE INSERT ON reservas -- gatilho disparado antes de novos regristros serem adicionados em reservas
FOR EACH ROW -- explica o gatilho
BEGIN -- inicio 
    DECLARE qtd_disponivel INT; -- cria variavel 

    -- Conta quantos exemplares estão marcados como 'Disponível'
    SELECT COUNT(*) INTO qtd_disponivel -- faz a conta de registros totais 
    FROM exemplares -- indica a tabela a ser consultada 
    WHERE id_livro = NEW.id_livro AND status_exemplar = 'Disponível'; -- Procura os exemplares cujo id_livro seja igual ao do reservado e seja disponível.

    -- Se houver exemplar disponível, cancela a inserção da reserva
    IF qtd_disponivel > 0 THEN -- verifica se tem pelo menos um livro com os criterios
        SIGNAL SQLSTATE '45000' -- lança um erro
        SET MESSAGE_TEXT = 'Não é possível reservar! Existem exemplares disponíveis na estante.'; -- define mensagem do erro
    END IF; -- encerra o if
END // -- fim do trigger
DELIMITER ;

-- Cargos Fixos do Sistema
INSERT INTO cargos (nome_cargo) VALUES 
('Administrador'),
('Bibliotecário'),
('Auxiliar de Biblioteca');

-- Categorias de Livros Pré-definidas
INSERT INTO categorias (nome_categoria) VALUES 
('Ficção Científica'),  -- id 1
('Fantasia'),           -- id 2
('Romance'),            -- id 3
('Terror'),             -- id 4
('Ação'),               -- id 5
('Suspense'),           -- id 6
('Aventura');           -- id 7

-- Inserindo Funcionário 
INSERT INTO funcionarios (nome, id_cargo, email, telefone, sms, senha, tipo_perfil) VALUES
('Carlos Silva', 1, 'carlos@bliblitech.com', '11999998888', '11999998888', 'B123', 'Funcionário'),
('Rebeca Monteiro', 2, 'becca@biblitech.com', '31972321537', '31972321537', 'B456', 'Funcionário');
-- Inserindo Leitor
INSERT INTO leitores (nome, email, telefone, sms, senha) VALUES 
('Felipe Rios', 'ana@gmail.com', '11977776666', '11977776666', 'L123'),
('Ana Souza', 'fr@gmail.com', '31971165397', '31971165397', 'L456');
 
 
-- Inserindo Livro e seus Exemplares
INSERT INTO livro (titulo, autor, ano_publicacao, quant_estoque) VALUES
 ('Duna', 'Frank Herbert', 1965, 2),
('Alice no País das Maravilhas', 'Lewis Carroll', 1865, 1),
('Orgulho e Preconceito', 'Jane Austen', 1813, 3),
('It: A Coisa', 'Stephen King', 1986, 4),
('O Código Da Vinci', 'Dan Brown', 2003, 2),
('A Caçada ao Outubro Vermelho', 'Tom Clancy', 1984, 3),
('O Alquimista', 'Paulo Coelho', 1988, 5);

INSERT INTO livro_categorias (id_livro, id_categoria) VALUES 
(1, 1), (1, 3), -- Duna: Ficção Científica (1) e Romance (3)
(2, 2),         -- Alice: Fantasia (2)
(3, 3),         -- Orgulho e Preconceito: Romance (3)
(4, 3), (4, 4), -- It: Romance (3) e Terror (4)
(5, 3), (5, 6), -- O Código Da Vinci: Romance (3) e Suspense (6)
(6, 5), (6, 6), -- A Caçada ao Outubro Vermelho: Ação (5) e Suspense (6)
(7, 7), (7, 3);

-- 2. Inserindo os Exemplares Físicos para TODOS os livros (respeitando a quant_estoque de cada um)
INSERT INTO exemplares (id_livro, posicao_estante, status_exemplar) VALUES 
-- Duna (2 unidades - id_livro 1)
(1, 'Corredor A - Estante 3', 'Disponível'),
(1, 'Corredor A - Estante 3', 'Disponível'),

-- Alice no País das Maravilhas (1 unidade - id_livro 2)
(2, 'Corredor B - Estante 2', 'Disponível'),

-- Orgulho e Preconceito (3 unidades - id_livro 3)
(3, 'Corredor C - Estante 1', 'Indisponível'),
(3, 'Corredor A - Estante 2', 'Disponível'),
(3, 'Corredor C - Estante 1', 'Disponível'),

-- It: A Coisa (4 unidades - id_livro 4)
(4, 'Corredor D - Estante 4', 'Disponível'),
(4, 'Corredor D - Estante 4', 'Disponível'),
(4, 'Corredor D - Estante 4', 'Disponível'),
(4, 'Corredor D - Estante 4', 'Indisponível'),

-- O Código Da Vinci (2 unidades - id_livro 5)
(5, 'Corredor B - Estante 3', 'Disponível'),
(5, 'Corredor B - Estante 3', 'Disponível'),

-- A Caçada ao Outubro Vermelho (3 unidades - id_livro 6)
(6, 'Corredor A - Estante 1', 'Disponível'),
(6, 'Corredor A - Estante 1', 'Disponível'),
(6, 'Corredor A - Estante 1', 'Disponível'),

-- O Alquimista (5 unidades - id_livro 7)
(7, 'Corredor D - Estante 3', 'Disponível'),
(7, 'Corredor C - Estante 3', 'Disponível'),
(7, 'Corredor C - Estante 3', 'Disponível'),
(7, 'Corredor C - Estante 3', 'Disponível'),
(7, 'Corredor C - Estante 3', 'Disponível');

-- 3. Registrando 5 Empréstimos 
INSERT INTO emprestimos (id_exemplar, id_leitor, id_funcionario) VALUES 
(1, 1, 1), -- Exemplar 1 para Leitor 1, registrado pelo Funcionario 1
(3, 1, 1), -- Exemplar 3 para Leitor 1, registrado pelo Funcionario 1
(4, 1, 2), -- Exemplar 4 para Leitor 1, registrado pelo Funcionario 2
(7, 1, 1), -- Exemplar 7 para Leitor 1, registrado pelo Funcionario 1
(11, 1, 2);

-- Exemplo de reserva feita para um livro (ex: Livro ID 1 - Duna)
INSERT INTO reservas (id_livro, id_leitor) VALUES 
(1, 2), -- Leitor 2 reservou o Livro 1
(4, 2); -- Leitor 2 reservou o Livro 4

