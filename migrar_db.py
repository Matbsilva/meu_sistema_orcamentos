import sqlite3
import os

# --- Configurações ---
DB_PATH = os.path.join("data", "orcamentos.db")

def migrar_db():
    """
    Executa a migração do banco de dados SQLite.
    - Renomeia a coluna 'arquivo' para 'arquivo_original'.
    - Adiciona a coluna 'nome_obra'.
    - Copia os dados de 'arquivo' para 'nome_obra'.
    - Cria a tabela 'mapa_itens'.
    """
    print(f"Conectando ao banco de dados em: {DB_PATH}")
    if not os.path.exists(DB_PATH):
        print("Erro: Banco de dados não encontrado. Execute o assistente de importação primeiro.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. Verificar se a migração já foi feita
        print("Verificando status da migração...")
        cursor.execute("PRAGMA table_info(itens_orcamento)")
        colunas = [info[1] for info in cursor.fetchall()]

        if 'nome_obra' in colunas and 'arquivo_original' in colunas:
            print("Migração já foi aplicada anteriormente. Nenhuma ação necessária.")
            return

        print("Iniciando o processo de migração...")

        # Inicia uma transação para garantir a segurança da operação
        cursor.execute("BEGIN TRANSACTION;")

        # 2. Renomear a tabela original
        print("  - Passo 1/5: Renomeando tabela 'itens_orcamento' para 'itens_orcamento_old'...")
        cursor.execute("ALTER TABLE itens_orcamento RENAME TO itens_orcamento_old;")

        # 3. Criar a nova tabela com o schema atualizado
        print("  - Passo 2/5: Criando nova tabela 'itens_orcamento' com colunas 'arquivo_original' e 'nome_obra'...")
        create_table_sql = """
        CREATE TABLE itens_orcamento (
            id INTEGER PRIMARY KEY,
            descricao TEXT,
            unidade TEXT,
            quantidade REAL,
            valor_unitario REAL,
            valor_total REAL,
            arquivo_original TEXT,
            importado_em TEXT,
            nome_obra TEXT
        );
        """
        cursor.execute(create_table_sql)

        # 4. Copiar os dados da tabela antiga para a nova, preenchendo as novas colunas
        print("  - Passo 3/5: Copiando dados e populando a nova coluna 'nome_obra'...")
        copy_data_sql = """
        INSERT INTO itens_orcamento (id, descricao, unidade, quantidade, valor_unitario, valor_total, arquivo_original, importado_em, nome_obra)
        SELECT id, descricao, unidade, quantidade, valor_unitario, valor_total, arquivo, importado_em, arquivo
        FROM itens_orcamento_old;
        """
        cursor.execute(copy_data_sql)

        # 5. Remover a tabela antiga
        print("  - Passo 4/5: Removendo a tabela temporária 'itens_orcamento_old'...")
        cursor.execute("DROP TABLE itens_orcamento_old;")

        # 6. Criar a nova tabela 'mapa_itens'
        print("  - Passo 5/5: Criando a tabela 'mapa_itens'...")
        create_mapa_sql = """
        CREATE TABLE IF NOT EXISTS mapa_itens (
            id_mapa INTEGER PRIMARY KEY AUTOINCREMENT,
            descricao_original TEXT UNIQUE NOT NULL,
            item_padrao TEXT
        );
        """
        cursor.execute(create_mapa_sql)

        # Finaliza a transação
        conn.commit()
        print("\nSUCESSO: A migração do banco de dados foi concluída com êxito!")

    except sqlite3.Error as e:
        print(f"\nERRO: Ocorreu um problema durante a migração: {e}")
        print("A operação foi revertida (rollback). O banco de dados não foi alterado.")
        conn.rollback()
    finally:
        conn.close()
        print("Conexão com o banco de dados fechada.")

if __name__ == "__main__":
    migrar_db()
