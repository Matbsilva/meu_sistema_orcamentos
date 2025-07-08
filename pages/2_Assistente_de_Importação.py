# pages/2_Assistente_de_Importação.py
import streamlit as st
from scripts import processador
from pathlib import Path
import time

st.set_page_config(page_title="SIO | Assistente de Importação", layout="wide")
st.title(" 🚀 Assistente de Importação e Mapeamento")
st.markdown("Use esta ferramenta para adicionar novos orçamentos e padronizar os itens.")

def inicializar_estado_importacao():
    """Limpa o estado da sessão para iniciar um novo processo de importação."""
    keys_to_clear = [
        'df_import', 'file_name', 'nome_obra', 'nome_cliente', 
        'itens_novos', 'opcoes_padrao', 'decisoes', 'observacao_inicial'
    ]
    for key in keys_to_clear:
        if key in st.session_state:
            del st.session_state[key]

# --- 1. Upload do Arquivo ---
uploaded_file = st.file_uploader(
    "1. Envie o arquivo de orçamento (.xlsx)",
    type=["xlsx"],
    on_change=inicializar_estado_importacao
)

if uploaded_file:
    # --- Processamento Inicial do Arquivo ---
    if 'df_import' not in st.session_state:
        try:
            st.session_state.df_import = processador.preparar_dataframe(processador.ler_orcamento(uploaded_file))
            st.session_state.file_name = uploaded_file.name
            descricoes_mapeadas = processador.consultar_descricoes_mapeadas()
            descricoes_unicas_upload = st.session_state.df_import['descricao'].unique()
            st.session_state.itens_novos = [d for d in descricoes_unicas_upload if d not in descricoes_mapeadas]
            st.session_state.opcoes_padrao = processador.consultar_itens_padrao()
            st.session_state.decisoes = {}
        except Exception as e:
            st.error(f"Ocorreu um erro ao ler e preparar a planilha: {e}")
            st.stop()

    # --- 2. Definição dos Dados da Obra ---
    st.subheader("2. Defina os Dados da Obra")
    
    col1, col2 = st.columns(2)
    with col1:
        st.session_state.nome_cliente = st.text_input(
            "Nome do Cliente:",
            value=st.session_state.get('nome_cliente', "")
        )
    with col2:
        nome_sugerido_ia = processador.sugerir_nome_obra_limpo(st.session_state.file_name)
        st.session_state.nome_obra = st.text_input(
            "Nome para este orçamento:",
            value=st.session_state.get('nome_obra', nome_sugerido_ia)
        )

    # --- 3. Mapeamento de Itens ---
    st.subheader("3. Mapeamento de Itens Novos")
    if not st.session_state.itens_novos:
        st.success("✅ Boa notícia! Todos os itens desta planilha já possuem um mapeamento padrão.")
    else:
        st.info(f"Encontramos {len(st.session_state.itens_novos)} itens que precisam ser padronizados.")
        
        SCORE_CUTOFF = 80
        for i, desc in enumerate(st.session_state.itens_novos):
            with st.container(border=True):
                st.markdown(f"**Item novo:** `{desc}`")
                sugestao = None
                index_sugerido = 0 
                if st.session_state.opcoes_padrao:
                    melhor_match = processador.encontrar_melhor_correspondencia(desc, st.session_state.opcoes_padrao)
                    if melhor_match and melhor_match[1] >= SCORE_CUTOFF:
                        sugestao = melhor_match[0]
                        index_sugerido = st.session_state.opcoes_padrao.index(sugestao) + 1
                
                acao = st.radio(
                    "O que você deseja fazer?",
                    ["Associar a um Item Padrão existente", "Criar um novo Item Padrão"],
                    key=f"acao_{i}", horizontal=True,
                    index=0 if sugestao else 1 
                )
                
                if acao == "Associar a um Item Padrão existente":
                    if sugestao:
                        st.info(f"💡 Sugestão ({melhor_match[1]}%): Correspondência com **'{sugestao}'**.")
                    opcoes_selectbox = ["-- Escolha um item --"] + st.session_state.opcoes_padrao
                    item_associado = st.selectbox(
                        "Selecione o Item Padrão",
                        options=opcoes_selectbox,
                        key=f"select_{i}",
                        index=index_sugerido
                    )
                    st.session_state.decisoes[desc] = {"acao": "associar", "valor": item_associado if item_associado != "-- Escolha um item --" else None}
                else:
                    sugestao_de_nome = desc.strip().capitalize()
                    novo_item_padrao = st.text_input(
                        "Digite o nome do novo Item Padrão:",
                        value=sugestao_de_nome,
                        key=f"input_{i}"
                    )
                    st.session_state.decisoes[desc] = {"acao": "criar", "valor": novo_item_padrao}
    
    # --- 4. Adicionar Observação Inicial ---
    st.subheader("4. Adicionar Observação Inicial (Opcional)")
    observacao_inicial = st.text_area(
        "Se desejar, adicione uma observação sobre o contexto geral deste orçamento (ex: motivo de um preço específico, negociação com cliente, etc.).",
        key="observacao_inicial_input"
    )

    st.markdown("---")

    # --- 5. Conclusão e Salvamento ---
    if st.button("Concluir Mapeamento e Salvar na Base", type="primary"):
        with st.spinner("Processando e salvando..."):
            # Validação dos campos obrigatórios
            nome_cliente = st.session_state.get('nome_cliente', '').strip()
            nome_obra = st.session_state.get('nome_obra', '').strip()
            if not nome_cliente or not nome_obra:
                st.error("Os campos 'Nome do Cliente' e 'Nome para este orçamento' são obrigatórios.")
                st.stop()

            mapeamento_completo = True
            for desc, decisao in st.session_state.decisoes.items():
                if not decisao['valor'] or not decisao['valor'].strip():
                    st.error(f"Decisão pendente para o item: '{desc}'. Por favor, complete todos os mapeamentos.")
                    mapeamento_completo = False
                    break
            
            if mapeamento_completo:
                # Salvar os mapeamentos
                for desc, decisao in st.session_state.decisoes.items():
                    if decisao['valor']:
                        processador.salvar_mapeamento(desc, decisao['valor'])
                
                # Salvar os dados principais do orçamento
                novos_itens = processador.salvar_na_base(
                    df=st.session_state.df_import,
                    nome_obra=nome_obra,
                    nome_arquivo_original=st.session_state.file_name,
                    nome_cliente=nome_cliente
                )

                # Salvar a observação inicial, se houver
                if observacao_inicial and observacao_inicial.strip():
                    processador.salvar_observacao(
                        nome_obra=nome_obra,
                        texto_observacao=observacao_inicial
                    )
                
                placeholder = st.empty()
                msg_sucesso = f"Sucesso! {novos_itens} novos registros foram salvos para a obra '{nome_obra}'."
                if observacao_inicial and observacao_inicial.strip():
                    msg_sucesso += " A observação inicial também foi salva."
                
                placeholder.success(msg_sucesso)
                
                st.cache_data.clear()
                time.sleep(4)
                placeholder.empty()
                inicializar_estado_importacao()
                st.rerun()