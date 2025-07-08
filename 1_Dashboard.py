# 1_Dashboard.py
import streamlit as st
import pandas as pd
import plotly.express as px
from scripts import processador

st.set_page_config(page_title="SIO | Dashboard de Análise", layout="wide")

@st.cache_data
def carregar_dados_mapeados():
    """Carrega os itens já com as colunas de mapeamento e cliente."""
    return processador.consultar_itens_com_mapeamento()

df_completo = carregar_dados_mapeados()

st.title("📊 Dashboard de Análise de Itens")
st.markdown("Use esta tela para analisar o histórico de preços e serviços por obra e cliente.")

if df_completo.empty:
    st.warning("Nenhum dado encontrado no banco. Comece importando orçamentos na página 'Assistente de Importação'.")
    st.stop()

# --- Filtros e Pesquisa ---
st.header("Pesquisa e Filtros")
termo_pesquisa = st.text_input(
    "Digite uma palavra-chave para buscar um serviço (padrão ou original):",
    placeholder="Ex: Escavação, Concreto, Pintura..."
)

if termo_pesquisa:
    filtro_descricao = df_completo['descricao'].str.contains(termo_pesquisa, case=False, na=False)
    filtro_item_padrao = df_completo['item_padrao'].str.contains(termo_pesquisa, case=False, na=False)
    df_pesquisa = df_completo[filtro_descricao | filtro_item_padrao]
else:
    df_pesquisa = df_completo.copy()

lista_itens_padrao = df_pesquisa['item_padrao'].dropna().unique().tolist()
lista_itens_padrao.sort()
OPCAO_TODOS = "-- Analisar todos os itens encontrados --"
lista_itens_padrao.insert(0, OPCAO_TODOS)

item_padrao_selecionado = st.selectbox(
    "Para ver o histórico de um Item Padrão específico, selecione-o abaixo:",
    options=lista_itens_padrao
)

if item_padrao_selecionado == OPCAO_TODOS:
    df_final = df_pesquisa.copy()
else:
    df_final = df_pesquisa[df_pesquisa['item_padrao'] == item_padrao_selecionado]

# --- Gráfico de Histórico de Preços ---
if item_padrao_selecionado != OPCAO_TODOS and not df_final.empty:
    st.subheader(f"Histórico de Preço para: {item_padrao_selecionado}")
    
    # Adiciona o nome do cliente ao rótulo da obra para diferenciação no gráfico
    df_final['obra_cliente'] = df_final['nome_obra'] + " (" + df_final['nome_cliente'].fillna('N/A') + ")"
    
    max_valor = df_final['valor_unitario'].max()
    range_y_max = max_valor * 1.20

    fig = px.bar(
        df_final, 
        x='obra_cliente', 
        y='valor_unitario', 
        title="Variação de Valor Unitário por Obra",
        labels={'obra_cliente': 'Obra (Cliente)', 'valor_unitario': 'Valor Unitário (R$)'}, 
        text='valor_unitario', 
        range_y=[0, range_y_max]
    )
    fig.update_traces(texttemplate='R$ %{y:.2f}', textposition='outside')
    fig.update_layout(uniformtext_minsize=8, uniformtext_mode='hide')
    st.plotly_chart(fig, use_container_width=True)

# --- Tabela de Dados Detalhada ---
st.header("Itens da Seleção")
df_para_exibicao = df_final.copy()

if not df_para_exibicao.empty:
    df_para_exibicao.insert(0, "selecionar", False)
    st.info("Para ver as estatísticas de uma ou mais linhas, marque as caixas de seleção correspondentes.")
    
    df_editado = st.data_editor(
        df_para_exibicao,
        column_config={
            "selecionar": st.column_config.CheckboxColumn("Selecionar", required=True),
            "id": st.column_config.Column("ID", width="small"),
            "item_padrao": st.column_config.Column("Item Padrão", width="large"),
            "nome_cliente": st.column_config.Column("Cliente", width="medium"),
            "nome_obra": st.column_config.Column("Obra", width="medium"),
            "descricao": st.column_config.Column("Descrição Original", width="large"),
            "arquivo_original": st.column_config.Column("Arquivo", width="medium"),
            "valor_unitario": st.column_config.NumberColumn("Valor Unitário", format="R$ %.2f"),
            "valor_total": st.column_config.NumberColumn("Valor Total", format="R$ %.2f"),
            "importado_em": st.column_config.DatetimeColumn("Importado em", format="D/MM/YYYY", width="small")
        },
        column_order=[
            "selecionar", "item_padrao", "nome_cliente", "nome_obra", "unidade", "quantidade", 
            "valor_unitario", "valor_total", "importado_em", "descricao", "arquivo_original", "id"
        ],
        hide_index=True,
        disabled=df_para_exibicao.columns.drop("selecionar")
    )
    df_selecionado = df_editado[df_editado['selecionar']]
else:
    st.write("Nenhum item encontrado para os filtros aplicados.")
    df_selecionado = pd.DataFrame()

# --- Métricas e Estatísticas ---
st.header("Estatísticas da Seleção")
st.markdown("As estatísticas abaixo refletem os itens marcados na tabela acima. Se nada for marcado, refletem todos os itens da busca atual.")

df_para_stats = df_selecionado if not df_selecionado.empty else df_final

if not df_para_stats.empty:
    preco_medio = df_para_stats['valor_unitario'].mean()
    preco_mediana = df_para_stats['valor_unitario'].median()
    preco_minimo = df_para_stats['valor_unitario'].min()
    preco_maximo = df_para_stats['valor_unitario'].max()
    num_registros = len(df_para_stats)
    
    metric_values = [f"R$ {v:,.2f}" for v in [preco_medio, preco_mediana, preco_minimo, preco_maximo]]
    metric_values.append(num_registros)
else:
    metric_values = ["N/A"] * 4 + [0]

labels = ["Preço Médio", "Mediana", "Preço Mínimo", "Preço Máximo", "Nº de Registros"]
cols = st.columns(5)
for col, label, value in zip(cols, labels, metric_values):
    col.metric(label=label, value=value)