# pages/5_Análise_de_Rentabilidade.py
import streamlit as st
import pandas as pd
import plotly.express as px
from scripts import processador

# --- Configuração da Página ---
st.set_page_config(page_title="SIO | Análise de Rentabilidade", layout="wide")
st.title("📊 Análise de Rentabilidade de Serviços")
st.markdown("Analise a relação entre o custo cadastrado e o preço de venda médio praticado.")

# --- Carregar e Cachear Dados ---
@st.cache_data
def carregar_dados():
    return processador.consultar_dados_rentabilidade()

df_rentabilidade = carregar_dados()

if df_rentabilidade.empty:
    st.warning("Nenhum dado de rentabilidade para analisar. Verifique se sua Base de Custos e seu Histórico de Vendas estão preenchidos.")
    st.stop()

# --- Filtros ---
st.subheader("Filtros e Pesquisa")

# Obter lista de grupos únicos para o filtro
lista_grupos = ["Todos"] + sorted(df_rentabilidade['nome_grupo'].unique().tolist())

col1, col2 = st.columns([1, 2])
with col1:
    grupo_selecionado = st.selectbox(
        "Filtrar por Grupo de Serviço:",
        options=lista_grupos
    )
with col2:
    termo_pesquisa = st.text_input(
        "Pesquisar por nome do serviço:",
        placeholder="Digite para filtrar os itens abaixo..."
    )

# Aplicar filtros
df_filtrado = df_rentabilidade.copy()
if grupo_selecionado != "Todos":
    df_filtrado = df_filtrado[df_filtrado['nome_grupo'] == grupo_selecionado]

if termo_pesquisa:
    df_filtrado = df_filtrado[df_filtrado['item_padrao'].str.contains(termo_pesquisa, case=False, na=False)]

# --- Tabela de Dados ---
st.subheader("Dados Consolidados de Custo vs. Preço")

st.dataframe(
    df_filtrado,
    column_config={
        "item_padrao": st.column_config.TextColumn("Serviço Padrão", width="large"),
        "nome_grupo": st.column_config.TextColumn("Grupo"),
        "unidade_de_medida": st.column_config.TextColumn("Un."),
        "custo_total_unitario": st.column_config.NumberColumn("Custo Unitário", format="R$ %.2f"),
        "preco_venda_medio": st.column_config.NumberColumn("Preço Médio Venda", format="R$ %.2f"),
        "num_orcamentos": st.column_config.NumberColumn("Nº Orçamentos", help="Número de orçamentos em que este item aparece."),
        "margem_bruta_rs": st.column_config.NumberColumn("Margem (R$)", format="R$ %.2f"),
        "margem_bruta_perc": st.column_config.NumberColumn("Margem (%)", format="%.2f%%")
    },
    use_container_width=True,
    hide_index=True
)

# --- Gráfico de Análise Visual ---
if not df_filtrado.empty:
    st.subheader("Análise Gráfica: Custo vs. Preço de Venda")

    # Ordenar por margem para melhor visualização
    df_grafico = df_filtrado.sort_values(by='margem_bruta_perc', ascending=False).head(20) # Limita aos 20 melhores para não poluir

    fig = px.bar(
        df_grafico,
        x='item_padrao',
        y=['custo_total_unitario', 'preco_venda_medio'],
        title='Comparativo de Custo Unitário vs. Preço de Venda Médio',
        labels={
            'item_padrao': 'Serviço',
            'value': 'Valor (R$)',
            'variable': 'Métrica'
        },
        barmode='group',
        text_auto='.2f'
    )
    fig.update_traces(textangle=0, textposition="outside")
    st.plotly_chart(fig, use_container_width=True)
else:
    st.info("Nenhum serviço encontrado para os filtros aplicados.")