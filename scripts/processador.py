# scripts/processador.py
import sqlite3
from datetime import datetime
from pathlib import Path
import pandas as pd
import unicodedata
import re
import time
import os
import google.generativeai as genai
from fuzzywuzzy import fuzz, process
import numpy as np

# --- Configuração de Paths e Banco de Dados --------------------------------- #
DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)
DB_PATH = DATA_DIR / "orcamentos.db"

# --- Configuração da IA (Gemini) ---
model = None
try:
    GOOGLE_API_KEY = os.environ.get('GOOGLE_API_KEY')
    if not GOOGLE_API_KEY:
        raise ValueError("A variável de ambiente GOOGLE_API_KEY não foi encontrada ou não está configurada.")
    
    genai.configure(api_key=GOOGLE_API_KEY)
    model = genai.GenerativeModel('gemini-1.5-flash-latest')
    print("Modelo Gemini configurado com sucesso.")
except Exception as e:
    print(f"ATENÇÃO: Erro na configuração do Gemini. A sugestão por IA não funcionará. Erro: {e}")


# --- Funções de IA e Mapeamento Inteligente -------------------- #
def sugerir_grupo_para_item(item_nome: str, grupos_e_descricoes: dict) -> str | None:
    """Sugere o grupo mais provável para um item usando a IA do Gemini com um prompt aprimorado."""
    if not model:
        print("Modelo de IA não inicializado. Usando sugestão nula.")
        return None
        
    if not item_nome or not grupos_e_descricoes:
        return None

    time.sleep(4.1) 

    opcoes_formatadas = "\n".join([f"- {nome}: {desc}" for nome, desc in grupos_e_descricoes.items()])
    lista_nomes_grupos = list(grupos_e_descricoes.keys())

    prompt = f"""
    Você é um assistente de IA especialista em engenharia civil e orçamentos. Sua tarefa é classificar um determinado "Serviço" na "Categoria" mais adequada.
    **Exemplo 1:**
    Serviço: "Instalação de porta de madeira com dobradiças e fechadura"
    Categoria Correta: Esquadrias (Portas e Janelas)
    **Exemplo 2:**
    Serviço: "Aplicação de massa corrida em teto de gesso"
    Categoria Correta: Pintura e Tratamentos de Superfície
    **Exemplo 3:**
    Serviço: "Demolir parede de tijolos"
    Categoria Correta: Demolições e Remoções
    **--- SUA TAREFA AGORA ---**
    Analise o serviço abaixo e, com base na lista de "Categorias Disponíveis", escolha a mais apropriada.
    Responda APENAS com o NOME EXATO da categoria escolhida, sem nenhuma palavra adicional.
    **Serviço:** "{item_nome}"
    **Categorias Disponíveis:**
    {opcoes_formatadas}
    **Categoria Correta:**
    """

    try:
        response = model.generate_content(prompt)
        sugestao = response.text.strip()
        
        if sugestao in lista_nomes_grupos:
            print(f"Serviço: '{item_nome}' -> Sugestão IA: '{sugestao}'")
            return sugestao
        else:
            print(f"Resposta da IA ('{sugestao}') não é um grupo válido. Tentando fallback.")
            melhor_match = process.extractOne(sugestao, lista_nomes_grupos, scorer=fuzz.ratio)
            if melhor_match and melhor_match[1] > 80:
                print(f"Fallback bem-sucedido para: '{melhor_match[0]}'")
                return melhor_match[0]
            return None
            
    except Exception as e:
        print(f"Erro ao chamar a IA para sugestão de grupo: {e}")
        return None

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
        descricao_original TEXT UNIQUE,
        item_padrao TEXT,
        peso_item REAL,
        id_grupo INTEGER REFERENCES grupos_servico(id_grupo)
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS observacoes_obra (
        id_observacao INTEGER PRIMARY KEY AUTOINCREMENT,
        nome_obra TEXT NOT NULL,
        texto_observacao TEXT NOT NULL,
        data_criacao TIMESTAMP
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS grupos_servico (
        id_grupo INTEGER PRIMARY KEY AUTOINCREMENT,
        nome_grupo TEXT UNIQUE NOT NULL
    )""")
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS base_custos (
        id_custo INTEGER PRIMARY KEY AUTOINCREMENT,
        item_padrao_nome TEXT UNIQUE NOT NULL,
        unidade_de_medida TEXT,
        custo_material REAL,
        custo_mao_de_obra REAL,
        homem_hora_profissional REAL,
        homem_hora_ajudante REAL,
        data_referencia TIMESTAMP,
        codigo_composicao TEXT,
        numero_manual TEXT
    )""")

    try: cursor.execute("SELECT codigo_composicao FROM base_custos LIMIT 1")
    except sqlite3.OperationalError: cursor.execute("ALTER TABLE base_custos ADD COLUMN codigo_composicao TEXT")
    
    try: cursor.execute("SELECT numero_manual FROM base_custos LIMIT 1")
    except sqlite3.OperationalError: cursor.execute("ALTER TABLE base_custos ADD COLUMN numero_manual TEXT")

    try: cursor.execute("SELECT peso_item FROM mapa_itens LIMIT 1")
    except sqlite3.OperationalError: cursor.execute("ALTER TABLE mapa_itens ADD COLUMN peso_item REAL")
    
    try: cursor.execute("SELECT id_grupo FROM mapa_itens LIMIT 1")
    except sqlite3.OperationalError: cursor.execute("ALTER TABLE mapa_itens ADD COLUMN id_grupo INTEGER REFERENCES grupos_servico(id_grupo)")
    
    try: cursor.execute("SELECT nome_cliente FROM itens_orcamento LIMIT 1")
    except sqlite3.OperationalError: cursor.execute("ALTER TABLE itens_orcamento ADD COLUMN nome_cliente TEXT")

    try: conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_item_padrao ON mapa_itens(item_padrao)")
    except Exception: pass
    
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

def salvar_mapeamento(descricao_original: str, item_padrao: str, grupo: str = None, peso_item: float = None):
    _garantir_tabelas()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    id_grupo = None
    if grupo:
        id_grupo = adicionar_grupo(conn, grupo)
    
    cursor.execute("""
        INSERT INTO mapa_itens (descricao_original, item_padrao, id_grupo)
        VALUES (?, ?, ?)
        ON CONFLICT(descricao_original) DO UPDATE SET
        item_padrao=excluded.item_padrao,
        id_grupo=excluded.id_grupo
    """, (descricao_original, item_padrao, id_grupo))
    
    if peso_item is not None:
        cursor.execute("""
            UPDATE mapa_itens SET peso_item = ? WHERE item_padrao = ?
        """, (peso_item, item_padrao))

    conn.commit()
    conn.close()

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

def salvar_observacao(nome_obra: str, texto_observacao: str) -> None:
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
    _garantir_tabelas()
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT nome_obra FROM itens_orcamento ORDER BY nome_obra")
        obras = [row[0] for row in cursor.fetchall()]
        conn.close()
        return obras
    except Exception as e:
        print(f"Erro ao consultar nomes de obras únicas: {e}")
        return []

def obter_grupos_e_descricoes() -> dict:
    return {
        "Serviços Preliminares e Apoio à Obra": "Administração, mobilização, limpeza de canteiro, tapumes, locação de equipamentos de apoio (andaimes, caçambas).",
        "Demolições e Remoções": "Demolição de alvenaria, pisos, forros; remoção de portas, janelas, louças e revestimentos antigos.",
        "Infraestrutura, Fundações e Estruturas": "Escavações, bases, sapatas, vigas, pilares, lajes, formas, armação e concretagem.",
        "Alvenaria e Vedações Verticais": "Levantamento de paredes de blocos (concreto/cerâmico), tijolos, e sistemas de vedação como Drywall.",
        "Esquadrias (Portas e Janelas)": "Fornecimento e instalação de portas, janelas, portões e seus respectivos batentes, guarnições e ferragens.",
        "Sistemas de Cobertura": "Estrutura de telhado, telhas, mantas de subcobertura, calhas, rufos e condutores.",
        "Instalações Elétricas, Dados e CFTV": "Passagem de eletrodutos, fiação, cabos de rede, montagem de quadros, tomadas, interruptores, luminárias e câmeras.",
        "Instalações Hidrossanitárias, Gás e Incêndio": "Tubulações de água, esgoto, gás, pontos de sprinklers e hidrantes, instalação de caixas e ralos.",
        "Impermeabilização e Tratamento de Umidade": "Aplicação de mantas, membranas, argamassas poliméricas e outros produtos para proteção contra água.",
        "Revestimentos de Parede e Forros": "Chapisco, emboço, reboco, assentamento de azulejos e porcelanatos em paredes, instalação de forros.",
        "Pisos, Contrapisos e Enchimentos": "Camadas de enchimento (EPS, bloco celular), contrapisos, e assentamento de revestimentos de piso.",
        "Pintura e Tratamentos de Superfície": "Preparação da superfície (massa, lixamento, selador) e aplicação de tintas, texturas, vernizes e stains.",
        "Aparelhos, Louças e Metais Sanitários": "Instalação final de vasos sanitários, cubas, pias, tanques, torneiras, registros, chuveiros e duchas.",
        "Marcenaria e Marmoraria": "Instalação de bancadas de pedra (mármore, granito), armários, painéis de madeira e móveis planejados.",
        "Acessórios e Equipamentos": "Fixação de itens como dispensers, suportes, toalheiros, espelhos, persianas e extintores.",
        "Comunicação Visual e Sinalização": "Instalação de placas de sinalização, adesivos, películas decorativas e logotipos."
    }

def adicionar_grupo(conn: sqlite3.Connection, nome_grupo: str) -> int:
    """Adiciona um novo grupo de serviço usando uma conexão existente."""
    cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO grupos_servico (nome_grupo) VALUES (?)", (nome_grupo,))
    conn.commit()
    cursor.execute("SELECT id_grupo FROM grupos_servico WHERE nome_grupo = ?", (nome_grupo,))
    resultado = cursor.fetchone()
    return resultado[0] if resultado else None

def salvar_custo_em_lote(df_custos: pd.DataFrame, mapeamento_grupos: dict, limpar_base_existente: bool = False):
    _garantir_tabelas()
    conn = sqlite3.connect(DB_PATH)
    try:
        cursor = conn.cursor()
        if limpar_base_existente:
            cursor.execute("DELETE FROM base_custos")
            cursor.execute("DELETE FROM mapa_itens")

        for _, row in df_custos.iterrows():
            item_padrao = row['item_padrao_nome']
            
            dados_custo = {
                "item_padrao_nome": item_padrao, "unidade_de_medida": row.get('unidade_de_medida'),
                "custo_material": row.get('custo_material'), "custo_mao_de_obra": row.get('custo_mao_de_obra'),
                "homem_hora_profissional": row.get('homem_hora_profissional'), "homem_hora_ajudante": row.get('homem_hora_ajudante'),
                "data_referencia": datetime.now(), "codigo_composicao": row.get('codigo_composicao'),
                "numero_manual": row.get('numero_manual')
            }
            cursor.execute("""
                INSERT OR REPLACE INTO base_custos (
                    item_padrao_nome, unidade_de_medida, custo_material, custo_mao_de_obra, 
                    homem_hora_profissional, homem_hora_ajudante, data_referencia,
                    codigo_composicao, numero_manual
                ) VALUES (
                    :item_padrao_nome, :unidade_de_medida, :custo_material, :custo_mao_de_obra, 
                    :homem_hora_profissional, :homem_hora_ajudante, :data_referencia,
                    :codigo_composicao, :numero_manual
                )
            """, dados_custo)

            grupo_nome = mapeamento_grupos.get(item_padrao)
            id_grupo = adicionar_grupo(conn, grupo_nome) if grupo_nome else None
            
            peso_item = row.get('peso_item')

            cursor.execute("""
                INSERT OR REPLACE INTO mapa_itens (descricao_original, item_padrao, id_grupo, peso_item)
                VALUES (?, ?, ?, ?)
            """, (item_padrao, item_padrao, id_grupo, peso_item))

        conn.commit()
    finally:
        conn.close()

def consultar_custo_por_item(item_padrao_nome: str) -> dict | None:
    _garantir_tabelas()
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM base_custos WHERE item_padrao_nome = ? ORDER BY data_referencia DESC LIMIT 1", (item_padrao_nome,))
    custo = cursor.fetchone()
    conn.close()
    return dict(custo) if custo else None

def consultar_itens_de_custo() -> list:
    _garantir_tabelas()
    if not DB_PATH.exists(): return []
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("SELECT DISTINCT item_padrao_nome FROM base_custos ORDER BY item_padrao_nome")
        itens = [item[0] for item in cursor.fetchall()]
        conn.close()
        return itens
    except Exception as e:
        print(f"Erro ao consultar itens de custo: {e}")
        return []

def consultar_itens_por_grupo() -> dict:
    _garantir_tabelas()
    query = """
    SELECT
        g.nome_grupo,
        b.item_padrao_nome
    FROM base_custos b
    LEFT JOIN mapa_itens m ON b.item_padrao_nome = m.item_padrao
    LEFT JOIN grupos_servico g ON m.id_grupo = g.id_grupo
    ORDER BY g.nome_grupo, b.item_padrao_nome
    """
    try:
        conn = sqlite3.connect(DB_PATH)
        df = pd.read_sql_query(query, conn)
        conn.close()
        
        itens_por_grupo = {}
        for _, row in df.iterrows():
            grupo = row['nome_grupo'] if pd.notna(row['nome_grupo']) else "Sem Grupo"
            item = row['item_padrao_nome']
            if grupo not in itens_por_grupo:
                itens_por_grupo[grupo] = []
            itens_por_grupo[grupo].append(item)
            
        return itens_por_grupo
    except Exception as e:
        print(f"Erro ao consultar itens por grupo: {e}")
        return {}

def salvar_orcamento_gerado(df_orcamento: pd.DataFrame, nome_obra: str, nome_cliente: str, observacao: str) -> int:
    _garantir_tabelas()
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    itens_adicionados = 0
    
    nome_arquivo_original = f"Gerado_pelo_SIO_{nome_obra}_{datetime.now().strftime('%Y%m%d%H%M%S')}"

    for _, row in df_orcamento.iterrows():
        cursor.execute("""
            INSERT INTO itens_orcamento
            (descricao, unidade, quantidade, valor_unitario, valor_total, nome_obra, arquivo_original, importado_em, nome_cliente)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            row["descricao"], row["unidade"], row["quantidade"], row["valor_unitario"],
            row["valor_total"], nome_obra, nome_arquivo_original, datetime.now(), nome_cliente
        ))
        itens_adicionados += 1
    
    conn.commit()
    conn.close()
    
    if observacao and observacao.strip():
        salvar_observacao(nome_obra, observacao)
        
    return itens_adicionados

def consultar_dados_rentabilidade() -> pd.DataFrame:
    """
    Busca e consolida dados de custos e preços de venda para análise de rentabilidade.
    """
    _garantir_tabelas()
    if not DB_PATH.exists():
        return pd.DataFrame()

    try:
        conn = sqlite3.connect(DB_PATH)

        query_custos = """
        SELECT 
            item_padrao_nome,
            unidade_de_medida,
            (COALESCE(custo_material, 0) + COALESCE(custo_mao_de_obra, 0)) AS custo_total_unitario
        FROM base_custos
        """
        df_custos = pd.read_sql_query(query_custos, conn)
        df_custos = df_custos.rename(columns={'item_padrao_nome': 'item_padrao'})

        query_precos = """
        SELECT
            m.item_padrao,
            AVG(io.valor_unitario) as preco_venda_medio,
            COUNT(DISTINCT io.nome_obra) as num_orcamentos
        FROM itens_orcamento io
        JOIN mapa_itens m ON io.descricao = m.descricao_original
        WHERE m.item_padrao IS NOT NULL
        GROUP BY m.item_padrao
        """
        df_precos_agregado = pd.read_sql_query(query_precos, conn)

        query_grupos = """
        SELECT DISTINCT
            m.item_padrao,
            g.nome_grupo
        FROM mapa_itens m
        LEFT JOIN grupos_servico g ON m.id_grupo = g.id_grupo
        WHERE m.item_padrao IS NOT NULL
        """
        df_grupos = pd.read_sql_query(query_grupos, conn)

        df_final = pd.merge(df_custos, df_precos_agregado, on='item_padrao', how='left')
        df_final = pd.merge(df_final, df_grupos, on='item_padrao', how='left')

        df_final['margem_bruta_rs'] = df_final['preco_venda_medio'] - df_final['custo_total_unitario']
        
        df_final['margem_bruta_perc'] = (df_final['margem_bruta_rs'] / df_final['preco_venda_medio']).replace([np.inf, -np.inf], 0) * 100
        
        df_final['preco_venda_medio'].fillna(0, inplace=True)
        df_final['num_orcamentos'].fillna(0, inplace=True)
        df_final['margem_bruta_rs'].fillna(0, inplace=True)
        df_final['margem_bruta_perc'].fillna(0, inplace=True)
        df_final['nome_grupo'].fillna('Sem Grupo', inplace=True)

        colunas_ordenadas = [
            'item_padrao', 'nome_grupo', 'unidade_de_medida', 'custo_total_unitario', 
            'preco_venda_medio', 'num_orcamentos', 'margem_bruta_rs', 'margem_bruta_perc'
        ]
        df_final = df_final[colunas_ordenadas]

        conn.close()
        return df_final

    except Exception as e:
        print(f"Erro ao consultar dados de rentabilidade: {e}")
        return pd.DataFrame()

# --- NOVA FUNÇÃO PARA LIMPAR O HISTÓRICO DE PREÇOS ---
def limpar_historico_precos():
    """Apaga todos os registros da tabela itens_orcamento e do mapa_itens."""
    _garantir_tabelas()
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        # Apaga os orçamentos importados
        cursor.execute("DELETE FROM itens_orcamento")
        # Apaga também o mapa de itens, pois ele é construído a partir dos orçamentos
        cursor.execute("DELETE FROM mapa_itens WHERE descricao_original NOT IN (SELECT item_padrao_nome FROM base_custos)")
        conn.commit()
        print("Histórico de preços (itens_orcamento) e mapeamentos associados foram limpos com sucesso.")
        return True
    except Exception as e:
        print(f"Erro ao limpar histórico de preços: {e}")
        return False
    finally:
        conn.close()