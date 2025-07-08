# scripts/processador.py
import sqlite3
from datetime import datetime
from pathlib import Path
import pandas as pd
import unicodedata
import re
from fuzzywuzzy import fuzz, process

# --- Configuração de Paths e Banco de Dados --------------------------------- #
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "orcamentos.db"

# --- Funções de IA (Simulada) e Mapeamento Inteligente -------------------- #
def _preprocess_string(s: str) -> str:
    if not isinstance(s, str): return ""
    s = unicodedata.normalize("NFKD", s.lower()).encode("ascii", "ignore").decode("utf-8")
    s = re.sub(r"[^a-z0-9\s]", "", s)
    return s

def encontrar_melhor_correspondencia(query: str, choices: list) -> tuple | None:
    if not query or not choices: return None
    best_wratio = process.extractOne(query, choices, scorer=fuzz.WRatio, processor=_preprocess_string)
    best_partial = process.extractOne(query, choices, scorer=fuzz.partial_ratio, processor=_preprocess_string)
    best_token_set = process.extractOne(query, choices, scorer=fuzz.token_set_ratio, processor=_preprocess_string)
    all_results = [best_wratio, best_partial, best_token_set]
    best_overall = max(all_results, key=lambda item: item[1])
    return best_overall

def sugerir_nome_obra_limpo(nome_arquivo: str) -> str:
    termos_finais = [
        'PLANILHA ORÇAMENTÁRIA', 'PLANILHA ORCAMENTARIA', 'ORÇAMENTO', 
        'ORCAMENTO', 'PROPOSTA', 'REVISAO', 'REVISÃO', 'VERSAO', 'VERSÃO', 'REV'
    ]
    nome_obra = Path(nome_arquivo).stem
    nome_obra = re.sub(r"^(GEFORCE\s*-\s*)", "", nome_obra, flags=re.IGNORECASE).strip()
    nome_obra_upper = nome_obra.upper()
    for termo in termos_finais:
        posicao = nome_obra_upper.find(termo)
        if posicao != -1:
            nome_obra = nome_obra[:posicao]
            break
    nome_obra = nome_obra.strip(' -_')
    return nome_obra.strip()

# --- Funções Principais de Processamento ------------------------------------ #
def ler_orcamento(file_buffer: bytes) -> pd.DataFrame:
    try:
        df = pd.read_excel(file_buffer, engine="openpyxl", header=None)
    except Exception as e:
        raise RuntimeError(f"Falha ao ler o arquivo Excel: {e}") from e
    chaves_header = {"item", "desc", "unid", "quant", "valor", "preco", "preç"}
    idx_header = -1
    for i, row in df.head(15).iterrows():
        matches = sum(1 for cell in row if str(cell).strip().lower().startswith(tuple(chaves_header)))
        if matches > 2:
            idx_header = i
            break
    if idx_header == -1:
        raise ValueError("Cabeçalho não detectado. Verifique as colunas.")
    df.columns = df.iloc[idx_header]
    df = df.drop(index=range(idx_header + 1)).reset_index(drop=True)
    return df

def preparar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    def _normalize_text(text: str) -> str:
        if not isinstance(text, str): return ""
        text = unicodedata.normalize("NFKD", text.lower()).encode("ascii", "ignore").decode("utf-8")
        return re.sub(r"[\s-]+", "_", text.strip())

    def _parse_num(value):
        if pd.isna(value): return None
        if isinstance(value, (int, float)): return float(value)
        s_value = str(value)
        s_value = re.sub(r"[^0-9,.-]", "", s_value)
        if ',' in s_value and '.' in s_value:
            s_value = s_value.replace('.', '').replace(',', '.')
        else:
            s_value = s_value.replace(',', '.')
        try:
            return float(s_value)
        except (ValueError, TypeError):
            return None

    df.columns = [_normalize_text(col) for col in df.columns]
    rename_map = {
        "item": "item", "descricao": "descricao", "desc": "descricao",
        "unidade": "unidade", "unid": "unidade", "quantidade": "quantidade", "qtd": "quantidade",
        "valor_unitario": "valor_unitario", "preco_unitario": "valor_unitario", "valor_unit": "valor_unitario",
        "valor_total": "valor_total", "preco_total": "valor_total",
    }
    df = df.rename(columns={c: next((v for k, v in rename_map.items() if c.startswith(k)), c) for c in df.columns})
    for col in ["quantidade", "valor_unitario"]:
        if col not in df.columns: raise ValueError(f"Coluna obrigatória '{col}' não encontrada.")
        df[col] = df[col].apply(_parse_num)
    if 'valor_total' not in df.columns:
        df['valor_total'] = df['quantidade'] * df['valor_unitario']
    else:
        df['valor_total'] = df['valor_total'].apply(_parse_num)
    df = df.dropna(subset=["descricao", "quantidade", "valor_unitario"])
    colunas_finais = ["item", "descricao", "unidade", "quantidade", "valor_unitario", "valor_total"]
    df = df[[c for c in colunas_finais if c in df.columns]]
    return df

# --- Funções de Banco de Dados ---------------------------------------------- #
def _garantir_tabelas():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS itens_orcamento (
        id INTEGER PRIMARY KEY AUTOINCREMENT, descricao TEXT, unidade TEXT,
        quantidade REAL, valor_unitario REAL, valor_total REAL,
        nome_obra TEXT, arquivo_original TEXT, importado_em TIMESTAMP,
        nome_cliente TEXT
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS mapa_itens (
        id_mapa INTEGER PRIMARY KEY AUTOINCREMENT,
        descricao_original TEXT UNIQUE, item_padrao TEXT
    )""")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS observacoes_obra (
        id_observacao INTEGER PRIMARY KEY AUTOINCREMENT,
        nome_obra TEXT NOT NULL,
        texto_observacao TEXT NOT NULL,
        data_criacao TIMESTAMP
    )""")
    try:
        cursor.execute("SELECT nome_cliente FROM itens_orcamento LIMIT 1")
    except sqlite3.OperationalError:
        cursor.execute("ALTER TABLE itens_orcamento ADD COLUMN nome_cliente TEXT")
    conn.commit()
    conn.close()

def salvar_na_base(df: pd.DataFrame, nome_obra: str, nome_arquivo_original: str, nome_cliente: str) -> int:
    _garantir_tabelas()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    itens_adicionados = 0
    for _, row in df.iterrows():
        cursor.execute("SELECT 1 FROM itens_orcamento WHERE descricao = ? AND unidade = ? AND quantidade = ? AND valor_unitario = ? AND arquivo_original = ?",
                       (row.get("descricao"), row.get("unidade"), row.get("quantidade"), row.get("valor_unitario"), nome_arquivo_original))
        if cursor.fetchone() is None:
            cursor.execute("""
                INSERT INTO itens_orcamento
                (descricao, unidade, quantidade, valor_unitario, valor_total, nome_obra, arquivo_original, importado_em, nome_cliente)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (row.get("descricao"), row.get("unidade"), row.get("quantidade"), row.get("valor_unitario"),
                  row.get("valor_total"), nome_obra, nome_arquivo_original, datetime.now(), nome_cliente))
            itens_adicionados += 1
    conn.commit()
    conn.close()
    return itens_adicionados

def consultar_itens_com_mapeamento() -> pd.DataFrame:
    _garantir_tabelas()
    if not DB_PATH.exists(): return pd.DataFrame()
    try:
        conn = sqlite3.connect(DB_PATH)
        query = "SELECT i.*, m.item_padrao FROM itens_orcamento AS i LEFT JOIN mapa_itens AS m ON i.descricao = m.descricao_original"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    except Exception as e:
        print(f"Erro ao consultar itens com mapeamento: {e}")
        return pd.DataFrame()

def salvar_mapeamento(descricao_original: str, item_padrao: str):
    _garantir_tabelas()
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("INSERT OR IGNORE INTO mapa_itens (descricao_original, item_padrao) VALUES (?, ?)", (descricao_original, item_padrao))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erro ao salvar mapeamento: {e}")

def consultar_itens_padrao() -> list:
    _garantir_tabelas()
    if not DB_PATH.exists(): return []
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT item_padrao FROM mapa_itens WHERE item_padrao IS NOT NULL ORDER BY item_padrao")
        itens = [item[0] for item in cursor.fetchall()]
        conn.close()
        return itens
    except Exception as e:
        print(f"Erro ao consultar itens padrão: {e}")
        return []

def consultar_descricoes_mapeadas() -> list:
    _garantir_tabelas()
    if not DB_PATH.exists(): return []
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT descricao_original FROM mapa_itens")
        descricoes = [item[0] for item in cursor.fetchall()]
        conn.close()
        return descricoes
    except Exception as e:
        print(f"Erro ao consultar descrições mapeadas: {e}")
        return []

# --- Funções de Banco de Dados (Observações) --------------------------------- #

def salvar_observacao(nome_obra: str, texto_observacao: str) -> None:
    """Salva uma nova observação para uma obra específica."""
    _garantir_tabelas()
    if not texto_observacao or not texto_observacao.strip():
        return
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO observacoes_obra (nome_obra, texto_observacao, data_criacao) VALUES (?, ?, ?)",
            (nome_obra, texto_observacao, datetime.now())
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erro ao salvar observação: {e}")

def consultar_observacoes_por_obra(nome_obra: str) -> list:
    """Consulta todas as observações de uma obra, retornando uma lista de dicionários."""
    _garantir_tabelas()
    if not nome_obra: return []
    try:
        conn = sqlite3.connect(DB_PATH)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM observacoes_obra WHERE nome_obra = ? ORDER BY data_criacao DESC", (nome_obra,))
        observacoes = [dict(row) for row in cursor.fetchall()]
        conn.close()
        return observacoes
    except Exception as e:
        print(f"Erro ao consultar observações: {e}")
        return []

def atualizar_observacao(id_observacao: int, novo_texto: str) -> None:
    """Atualiza o texto de uma observação existente."""
    _garantir_tabelas()
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE observacoes_obra SET texto_observacao = ? WHERE id_observacao = ?",
            (novo_texto, id_observacao)
        )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"Erro ao atualizar observação: {e}")

def consultar_nomes_de_obras_unicas() -> list:
    """Consulta e retorna uma lista com os nomes de todas as obras únicas já importadas."""
    _garantir_tabelas()
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # Busca na tabela principal de orçamentos para garantir que todas as obras apareçam
        cursor.execute("SELECT DISTINCT nome_obra FROM itens_orcamento ORDER BY nome_obra")
        obras = [row[0] for row in cursor.fetchall()]
        conn.close()
        return obras
    except Exception as e:
        print(f"Erro ao consultar nomes de obras únicas: {e}")
        return []