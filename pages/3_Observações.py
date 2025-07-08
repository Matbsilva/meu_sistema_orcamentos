# pages/3_Observações.py
import streamlit as st
from scripts import processador
from datetime import datetime

# --- Configuração da Página ---
st.set_page_config(page_title="SIO | Observações", layout="wide")
st.title("📖 Observações das Obras")
st.markdown("Consulte, adicione ou edite anotações e o contexto de cada obra.")

# --- Carregar Dados ---
lista_obras = processador.consultar_nomes_de_obras_unicas()

if not lista_obras:
    st.warning("Nenhuma obra foi encontrada no banco de dados. Importe um orçamento primeiro.")
    st.stop()

# --- Barra de Pesquisa ---
termo_pesquisa = st.text_input(
    "Pesquisar por nome da obra:",
    placeholder="Digite para filtrar as obras abaixo..."
)

# --- Filtrar Obras ---
if termo_pesquisa:
    obras_filtradas = [obra for obra in lista_obras if termo_pesquisa.lower() in obra.lower()]
else:
    obras_filtradas = lista_obras

if not obras_filtradas:
    st.info(f"Nenhuma obra encontrada com o termo '{termo_pesquisa}'.")

# --- Loop para exibir os "Cards" de cada obra ---
for obra in obras_filtradas:
    with st.container(border=True):
        st.subheader(obra)
        
        observacoes = processador.consultar_observacoes_por_obra(obra)
        
        if not observacoes:
            st.info("Esta obra ainda não possui observações salvas.")
        else:
            for obs in observacoes:
                obs_id = obs['id_observacao']
                edit_key = f"edit_mode_{obs_id}"

                # Verifica se a observação específica está em modo de edição
                if st.session_state.get(edit_key, False):
                    # --- MODO DE EDIÇÃO ---
                    st.write("---")
                    novo_texto = st.text_area(
                        "Editando observação:",
                        value=obs['texto_observacao'],
                        key=f"text_area_{obs_id}",
                        height=120
                    )
                    
                    col1, col2, _ = st.columns([1, 1, 5]) # Colunas para botões
                    with col1:
                        if st.button("Salvar", key=f"save_btn_{obs_id}", type="primary"):
                            processador.atualizar_observacao(obs_id, novo_texto)
                            st.session_state[edit_key] = False
                            st.rerun()
                    with col2:
                        if st.button("Cancelar", key=f"cancel_btn_{obs_id}"):
                            st.session_state[edit_key] = False
                            st.rerun()
                    st.write("---")

                else:
                    # --- MODO DE VISUALIZAÇÃO ---
                    st.markdown(f"> {obs['texto_observacao'].replace(chr(10), '<br>')}", unsafe_allow_html=True)
                    data_formatada = datetime.fromisoformat(obs['data_criacao']).strftime('%d/%m/%Y às %H:%M')
                    st.caption(f"Anotado em: {data_formatada}")
                    
                    if st.button("Editar Observação", key=f"edit_btn_{obs_id}"):
                        st.session_state[edit_key] = True
                        st.rerun()
                
                st.divider()

        # --- Formulário para adicionar nova observação ---
        with st.expander("➕ Adicionar nova observação para esta obra"):
            nova_obs_texto = st.text_area(
                "Digite a nova observação:", 
                key=f"new_obs_{obra}",
                height=100
            )
            if st.button("Salvar Nova Observação", key=f"save_new_{obra}"):
                if nova_obs_texto and nova_obs_texto.strip():
                    processador.salvar_observacao(obra, nova_obs_texto)
                    st.success("Nova observação salva com sucesso!")
                    # Limpar a caixa de texto após salvar, se desejado
                    if f"new_obs_{obra}" in st.session_state:
                        st.session_state[f"new_obs_{obra}"] = ""
                    st.rerun()
                else:
                    st.warning("A observação não pode estar vazia.")