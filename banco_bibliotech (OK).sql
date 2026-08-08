DROP DATABASE IF EXISTS bliblitech;
CREATE DATABASE IF NOT EXISTS bliblitech;
USE bliblitech;

-- 1. Tabela de Cargos
CREATE TABLE cargos (
    id_cargo INT AUTO_INCREMENT PRIMARY KEY,
    nome_cargo VARCHAR(50) NOT NULL
);

CREATE TABLE categorias (
    id_categoria INT AUTO_INCREMENT PRIMARY KEY,
    nome_categoria VARCHAR(50) NOT NULL
);

-- 2. Tabela de Funcionários
CREATE TABLE funcionarios (
   id_funcionario INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    cpf VARCHAR(14) NOT NULL UNIQUE,
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

CREATE TABLE livro (
id_livro INT AUTO_INCREMENT PRIMARY KEY,
titulo VARCHAR(100),
posicao_estante VARCHAR(50),
autor VARCHAR (50) not null,
ano_publicacao INT,
quant_estoque INT NOT NULL DEFAULT 1,
sinopse TEXT,
capa VARCHAR(500),
id_categoria INT,
status_livro ENUM('Emprestado', 'Livre') DEFAULT 'Livre',
cadastro timestamp default current_timestamp,
FOREIGN KEY (id_categoria) REFERENCES categorias(id_categoria)
);

CREATE TABLE leitores (
   id_leitor INT AUTO_INCREMENT PRIMARY KEY,
    nome VARCHAR(100) NOT NULL,
    id_cargo INT NOT NULL,
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

--  Criação da Trigger (vinculada à tabela emprestimos)
DELIMITER //

CREATE TRIGGER set_data_devolucao_esperada
BEFORE INSERT ON emprestimos
FOR EACH ROW
BEGIN
    -- Define o prazo padrão (exemplo: 14 dias)
    SET NEW.data_devolucao_esperado = DATE_ADD(CURRENT_DATE, INTERVAL 14 DAY);
END //

DELIMITER ;
