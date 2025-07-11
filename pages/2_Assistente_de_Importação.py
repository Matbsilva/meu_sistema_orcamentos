# pages/2_Assistente_de_Importação.py
import streamlit as st
import pandas as pd
from scripts import processador
import time
import unicodedata
from fuzzywuzzy import process, fuzz
import re

# FUNÇÃO DE LIMPEZA CENTRALIZADA: Usada para cabeçalhos e valores
def limpar_texto(texto):
    """Remove acentos, caracteres especiais, converte para minúsculas e padroniza espaços."""
    if not isinstance(texto, str):
        return ""
    # Converte para minúsculas e normaliza acentos
    texto_normalizado = unicodedata.normalize('NFKD', texto.lower())
    # Remove caracteres de acentuação
    texto_sem_acentos = ''.join(c for c in texto_normalizado if not unicodedata.combining(c))
    # Remove caracteres especiais, mantendo apenas letras, números e espaços
    texto_limpo = re.sub(r'[^a-z0-9\s]', ' ', texto_sem_acentos)
    # Normaliza espaços (remove múltiplos espaços, espaços no início/fim)
    texto_final = " ".join(texto_limpo.split())
    return texto_final if texto_final else ""

st.set_page_config(page_title="SIO | Assistente de Importação", layout="wide")
st.title(" 🚀 Assistente de Importação e Mapeamento")
st.markdown("Use esta ferramenta para adicionar novos orçamentos (preços) ou bases de custos.")

def inicializar_estado_importacao():
    """Limpa o estado da sessão para iniciar um novo processo de importação."""
    keys_to_clear = [
        'df_import', 'file_name', 'nome_obra', 'nome_cliente', 
        'itens_novos', 'opcoes_padrao', 'decisoes', 'observacao_inicial',
        'tipo_importacao', 'mapeamento_grupos', 'df_custos'
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

# --- 1. Upload do Arquivo ---
st.subheader("1. Envie o arquivo da planilha")
uploaded_file = st.file_uploader(
    "Selecione o arquivo de orçamento (.xlsx) ou base de custos (.xlsx)",
    type=["xlsx"],
    on_change=inicializar_estado_importacao,
    label_visibility="collapsed"
)

if uploaded_file:
    st.subheader("2. Qual tipo de dado você está importando?")
    tipo_importacao = st.radio(
        "Selecione o tipo de dado:",
        ["Preço de Venda (Orçamento de Obra)", "Base de Custos"],
        key="tipo_importacao_radio",
        horizontal=True
    )
    st.markdown("---")

    # =========================================================================
    # --- FLUXO PARA PREÇO DE VENDA (ORÇAMENTO) - CÓDIGO ORIGINAL INALTERADO ---
    # =========================================================================
    if tipo_importacao == "Preço de Venda (Orçamento de Obra)":
        if 'df_import' not in st.session_state:
            try:
                df_bruto = processador.ler_orcamento(uploaded_file)
                st.session_state.df_import = processador.preparar_dataframe(df_bruto)
                st.session_state.file_name = uploaded_file.name
                descricoes_mapeadas = processador.consultar_descricoes_mapeadas()
                descricoes_unicas_upload = st.session_state.df_import['descricao'].unique()
                st.session_state.itens_novos = [d for d in descricoes_unicas_upload if d not in descricoes_mapeadas]
                st.session_state.opcoes_padrao = processador.consultar_itens_padrao()
                st.session_state.decisoes = {}
            except Exception as e:
                st.error(f"Ocorreu um erro ao ler e preparar a planilha de orçamento: {e}")
                st.stop()

        st.subheader("A. Defina os Dados da Obra")
        col1, col2 = st.columns(2)
        with col1:
            st.session_state.nome_cliente = st.text_input(
                "Nome do Cliente:", value=st.session_state.get('nome_cliente', "")
            )
        with col2:
            nome_sugerido_ia = processador.sugerir_nome_obra_limpo(st.session_state.file_name)
            st.session_state.nome_obra = st.text_input(
                "Nome para este orçamento:", value=st.session_state.get('nome_obra', nome_sugerido_ia)
            )

        st.subheader("B. Mapeamento de Itens Novos")
        if not st.session_state.get('itens_novos', []):
            st.success("✅ Boa notícia! Todos os itens desta planilha já possuem um mapeamento padrão no sistema.")
        else:
            st.info(f"Encontramos {len(st.session_state.itens_novos)} itens que precisam ser padronizados.")
            for i, desc in enumerate(st.session_state.itens_novos):
                with st.container(border=True):
                    st.markdown(f"**Item novo:** `{desc}`")
                    sugestao, index_sugerido = None, 0
                    if st.session_state.opcoes_padrao:
                        melhor_match = processador.encontrar_melhor_correspondencia(desc, st.session_state.opcoes_padrao)
                        if melhor_match and melhor_match[1] >= 80:
                            sugestao = melhor_match[0]
                            index_sugerido = st.session_state.opcoes_padrao.index(sugestao) + 1
                    
                    acao = st.radio(
                        "O que você deseja fazer?", 
                        ["Associar a um Item Padrão existente", "Criar um novo Item Padrão"],
                        key=f"acao_{i}", horizontal=True, index=0 if sugestao else 1
                    )

                    if acao == "Associar a um Item Padrão existente":
                        if sugestao: st.info(f"💡 Sugestão ({melhor_match[1]}%): Correspondência com **'{sugestao}'**.")
                        opcoes_selectbox = ["-- Escolha um item --"] + st.session_state.opcoes_padrao
                        item_associado = st.selectbox("Selecione o Item Padrão", options=opcoes_selectbox, key=f"select_{i}", index=index_sugerido)
                        st.session_state.decisoes[desc] = {"acao": "associar", "valor": item_associado if item_associado != "-- Escolha um item --" else None}
                    else:
                        novo_item_padrao = st.text_input("Digite o nome do novo Item Padrão:", value=desc.strip().capitalize(), key=f"input_{i}")
                        st.session_state.decisoes[desc] = {"acao": "criar", "valor": novo_item_padrao}

        st.subheader("C. Adicionar Observação Inicial (Opcional)")
        observacao_inicial = st.text_area(
            "Se desejar, adicione uma observação sobre o contexto geral deste orçamento.", key="observacao_inicial_input"
        )
        st.markdown("---")

        if st.button("Concluir Mapeamento e Salvar Orçamento", type="primary", use_container_width=True):
            with st.spinner("Processando e salvando..."):
                nome_cliente = st.session_state.get('nome_cliente', '').strip()
                nome_obra = st.session_state.get('nome_obra', '').strip()
                if not nome_cliente or not nome_obra:
                    st.error("Os campos 'Nome do Cliente' e 'Nome para este orçamento' são obrigatórios.")
                    st.stop()
                
                mapeamento_completo = all(d.get('valor') and d.get('valor').strip() for d in st.session_state.get('decisoes', {}).values())
                if not mapeamento_completo:
                    st.error("Existem decisões de mapeamento pendentes. Por favor, complete todos os mapeamentos.")
                    st.stop()
                
                for desc, decisao in st.session_state.decisoes.items():
                    processador.salvar_mapeamento(desc, decisao['valor'])
                
                novos_itens = processador.salvar_na_base(
                    df=st.session_state.df_import, 
                    nome_obra=nome_obra,
                    nome_arquivo_original=st.session_state.file_name, 
                    nome_cliente=nome_cliente
                )
                if observacao_inicial and observacao_inicial.strip():
                    processador.salvar_observacao(nome_obra=nome_obra, texto_observacao=observacao_inicial)
                
                st.success(f"Sucesso! {novos_itens} novos registros foram salvos para a obra '{nome_obra}'. O mapeamento também foi salvo.")
                st.cache_data.clear()
                time.sleep(4)
                inicializar_estado_importacao()
                st.rerun()

    # =========================================================================
    # --- FLUXO PARA BASE DE CUSTOS (LÓGICA CORRIGIDA E APRIMORADA) ---
    # =========================================================================
    elif tipo_importacao == "Base de Custos":
        st.header("Importando Base de Custos")

        limpar_base = st.checkbox("Apagar base de custos e mapeamentos existentes antes de importar")
        st.info("O sistema tentará reconhecer o grupo da planilha. Para itens sem grupo ou não reconhecidos, a IA fará uma sugestão.")

        if 'df_custos' not in st.session_state:
            try:
                df_bruto = pd.read_excel(uploaded_file)
                st.write("**Debug**: Colunas lidas da planilha:", list(df_bruto.columns))  # Log de depuração

                # Dicionário robusto para reconhecer vários nomes de colunas possíveis
                mapa_colunas = {
                    'item': 'item_padrao_nome', 'descricao': 'item_padrao_nome', 'descrição': 'item_padrao_nome',
                    'unidade de medida': 'unidade_de_medida', 'unidade': 'unidade_de_medida', 'unid': 'unidade_de_medida',
                    'custo material': 'custo_material', 'custo m.o.': 'custo_mao_de_obra',
                    'homem hora profissional': 'homem_hora_profissional', 'homem hora ajudante': 'homem_hora_ajudante',
                    'codigo composicao': 'codigo_composicao', 'n manual': 'numero_manual', 'nº manual': 'numero_manual',
                    'peso item': 'peso_item', 
                    'grupo': 'grupo', 'grupo de servico': 'grupo', 'grupo composicao': 'grupo', 'grupo composição': 'grupo'
                }

                # Limpar cabeçalhos da planilha
                colunas_limpas = {col: limpar_texto(col) for col in df_bruto.columns}
                # Mapear cabeçalhos limpos para os nomes internos
                colunas_mapeadas = {}
                for col, col_limpa in colunas_limpas.items():
                    for chave, valor in mapa_colunas.items():
                        if col_limpa == limpar_texto(chave):
                            colunas_mapeadas[col] = valor
                            break
                    else:
                        colunas_mapeadas[col] = col  # Mantém o nome original se não houver correspondência

                df_renomeado = df_bruto.rename(columns=colunas_mapeadas)
                st.write("**Debug**: Colunas após mapeamento:", list(df_renomeado.columns))  # Log de depuração

                if 'item_padrao_nome' not in df_renomeado.columns:
                    st.error("Erro Crítico: A coluna 'ITEM' (ou similar) não foi encontrada na sua planilha.")
                    st.stop()

                # Limpar valores da coluna 'grupo' para evitar problemas com espaços ou caracteres invisíveis
                if 'grupo' in df_renomeado.columns:
                    df_renomeado['grupo'] = df_renomeado['grupo'].apply(lambda x: limpar_texto(str(x)) if pd.notna(x) else '')
                    df_renomeado['grupo'] = df_renomeado['grupo'].replace('', pd.NA)
                    st.write("**Debug**: Primeiros valores da coluna 'grupo' (após limpeza):", df_renomeado['grupo'].head().tolist())  # Log de depuração

                st.session_state.df_custos = df_renomeado
                st.session_state.mapeamento_grupos = {}
            except Exception as e:
                st.error(f"Ocorreu um erro ao ler e preparar a planilha de custos: {e}")
                st.stop()

        grupos_e_descricoes = processador.obter_grupos_e_descricoes()
        lista_grupos = sorted(list(grupos_e_descricoes.keys()))
        grupos_limpos_map = {limpar_texto(g): g for g in lista_grupos}
        lista_grupos_limpos = list(grupos_limpos_map.keys())
        st.write("**Debug**: Grupos disponíveis no sistema (limpos):", lista_grupos_limpos)  # Log de depuração

        df_custos = st.session_state.df_custos
        has_grupo_column = 'grupo' in df_custos.columns

        with st.form(key='form_mapeamento_grupos'):
            total_itens = len(df_custos)
            st.write(f"Encontrados {total_itens} itens para mapear.")

            for index, row in df_custos.iterrows():
                item_nome = str(row.get('item_padrao_nome', ''))
                st.markdown(f"--- \n**Serviço:** `{item_nome}`")

                grupo_final = None

                if has_grupo_column and pd.notna(row.get('grupo')) and row.get('grupo').strip():
                    grupo_planilha = str(row.get('grupo')).strip()
                    grupo_planilha_limpo = limpar_texto(grupo_planilha)
                    st.write(f"**Debug**: Grupo lido da planilha (limpo): `{grupo_planilha_limpo}`")  # Log de depuração
                    melhor_match = process.extractOne(grupo_planilha_limpo, lista_grupos_limpos, scorer=fuzz.ratio)

                    if melhor_match and melhor_match[1] >= 85:  # Reduzido de 90% para 85%
                        grupo_final = grupos_limpos_map[melhor_match[0]]
                        st.success(f"Grupo reconhecido da planilha: **{grupo_final}** (Similaridade: {melhor_match[1]}%)")
                        st.write(f"**Debug**: Grupo correspondente encontrado: `{grupo_final}` (Similaridade: {melhor_match[1]}%)")  # Log de depuração
                        st.session_state.mapeamento_grupos[item_nome] = grupo_final
                    else:
                        st.warning(f"O grupo '{grupo_planilha}' da planilha não foi reconhecido com alta confiança (Similaridade: {melhor_match[1] if melhor_match else 0}%). Usando IA para sugestão.")
                        st.write(f"**Debug**: Motivo da não correspondência: Similaridade baixa ({melhor_match[1] if melhor_match else 0}%)")  # Log de depuração

                if not grupo_final:
                    if item_nome not in st.session_state.mapeamento_grupos or not st.session_state.mapeamento_grupos.get(item_nome):
                        with st.spinner(f"Item {index+1}/{total_itens}: Consultando IA para sugestão..."):
                            sugestao_ia = processador.sugerir_grupo_para_item(item_nome, grupos_e_descricoes)
                            st.session_state.mapeamento_grupos[item_nome] = sugestao_ia
                            st.write(f"**Debug**: Sugestão da IA para '{item_nome}': `{sugestao_ia}`")  # Log de depuração
                    sugestao_atual = st.session_state.mapeamento_grupos.get(item_nome)
                    if sugestao_atual:
                        st.info(f"Sugestão da IA: **{sugestao_atual}**")
                    try:
                        indice_sugerido = lista_grupos.index(sugestao_atual) if sugestao_atual in lista_grupos else 0
                    except (ValueError, TypeError):
                        indice_sugerido = 0
                    grupo_selecionado = st.selectbox(
                        "Corrija o grupo do serviço, se necessário:",
                        options=lista_grupos,
                        index=indice_sugerido,
                        key=f"grupo_{index}"
                    )
                    st.session_state.mapeamento_grupos[item_nome] = grupo_selecionado

            st.markdown("---")
            submitted = st.form_submit_button("Concluir Mapeamento e Salvar Base de Custos", type="primary")
            if submitted:
                with st.spinner("Processando e salvando..."):
                    try:
                        st.write("**Debug**: Mapeamento final de grupos:", st.session_state.mapeamento_grupos)  # Log de depuração
                        processador.salvar_custo_em_lote(df_custos=st.session_state.df_custos, mapeamento_grupos=st.session_state.mapeamento_grupos, limpar_base_existente=limpar_base)
                        st.success(f"Sucesso! {len(st.session_state.df_custos)} itens de custo foram salvos.")
                        st.balloons()
                        st.cache_data.clear()
                        time.sleep(4)
                        inicializar_estado_importacao()
                        st.rerun()
                    except Exception as e:
                        st.error(f"Ocorreu um erro ao salvar os dados: {e}")