# pages/4_Orçamentador.py
import streamlit as st
import pandas as pd
import numpy as np
from scripts import processador
import io
import time

# --- Configuração da Página ---
st.set_page_config(page_title="SIO | Orçamentador e Simulador", layout="wide")
st.title("💡 Orçamentador e Simulador de Preços")

# --- FUNÇÃO DE INICIALIZAÇÃO ROBUSTA ---
def inicializar_session_state():
    """
    Inicializa o estado da sessão de forma robusta, garantindo que os
    valores padrão do BDI sejam definidos apenas uma vez por sessão.
    """
    if 'bdi_valores_iniciados' not in st.session_state:
        st.session_state.orcamento_df = pd.DataFrame(columns=[
            "Item Padrão", "Unidade", "Quantidade", "Custo Unit. Material", "Custo Unit. M.O."
        ])
        st.session_state.distribuicao_df = pd.DataFrame()
        
        # BDI Mão de Obra (5 campos) - Atribuição Direta
        st.session_state.bdi_ac_mo = 0.0
        st.session_state.bdi_cf_mo = 0.0
        st.session_state.bdi_mi_mo = 0.0
        st.session_state.bdi_tributos_mo = 27.0
        st.session_state.bdi_lucro_mo = 30.0

        # BDI Material (5 campos) - Atribuição Direta
        st.session_state.bdi_ac_mat = 0.0
        st.session_state.bdi_cf_mat = 0.0
        st.session_state.bdi_mi_mat = 0.0
        st.session_state.bdi_tributos_mat = 13.0
        st.session_state.bdi_lucro_mat = 30.0
        
        st.session_state.custo_total_material = 0.0
        st.session_state.custo_total_mo = 0.0
        st.session_state.preco_venda_total = 0.0
        
        st.session_state.bdi_valores_iniciados = True

inicializar_session_state()


# --- Carregar Dados ---
@st.cache_data
def carregar_dados_orcamentador():
    return processador.consultar_itens_por_grupo()

# --- Estrutura de Abas ---
tab1, tab2, tab3 = st.tabs([
    "1. Montagem do Custo Direto",
    "2. Definindo o Faturamento",
    "3. Distribuição e Finalização"
])

# =================================================================================================
# --- ABA 1: MONTAGEM DO CUSTO DIRETO ---
# =================================================================================================
with tab1:
    st.header("Montagem do Custo Direto")
    st.info("Selecione os serviços e defina as quantidades para compor os custos de Material e Mão de Obra.")
    
    with st.container(border=True):
        dados_orcamento = carregar_dados_orcamentador()
        grupos_disponiveis = ["Todos"] + sorted(list(dados_orcamento.keys()))

        col1, col2 = st.columns([1, 3])
        with col1:
            grupo_selecionado = st.selectbox("Filtrar por Grupo:", options=grupos_disponiveis, key="filtro_grupo")
        with col2:
            opcoes_servicos = sorted([item for sublist in dados_orcamento.values() for item in sublist]) if grupo_selecionado == "Todos" else sorted(dados_orcamento.get(grupo_selecionado, []))
            servicos_selecionados = st.multiselect("Pesquise e adicione serviços:", options=opcoes_servicos, placeholder="Digite para buscar um serviço...")

        if st.button("Adicionar Serviços Selecionados", type="primary", use_container_width=True):
            novos_itens_para_adicionar, servicos_com_falha = [], []
            for servico in servicos_selecionados:
                if servico not in st.session_state.orcamento_df["Item Padrão"].values:
                    custo_info = processador.consultar_custo_por_item(servico)
                    if custo_info:
                        novos_itens_para_adicionar.append({
                            "Item Padrão": servico, "Unidade": custo_info.get("unidade_de_medida", "N/D"),
                            "Quantidade": 1.0, "Custo Unit. Material": custo_info.get("custo_material", 0),
                            "Custo Unit. M.O.": custo_info.get("custo_mao_de_obra", 0),
                        })
                    else:
                        servicos_com_falha.append(servico)
            if novos_itens_para_adicionar:
                novos_itens_df = pd.DataFrame(novos_itens_para_adicionar)
                st.session_state.orcamento_df = pd.concat([st.session_state.orcamento_df, novos_itens_df], ignore_index=True)
                st.session_state.distribuicao_df = pd.DataFrame()
            if servicos_com_falha:
                st.error(f"Não foi possível encontrar os detalhes de custo para: {', '.join(servicos_com_falha)}.")
            if novos_itens_para_adicionar:
                st.rerun()

        if not st.session_state.orcamento_df.empty:
            st.markdown("##### Planilha de Custos")
            
            df_para_editar = st.session_state.orcamento_df.copy()
            df_para_editar['Custo Unit. Total'] = df_para_editar['Custo Unit. Material'] + df_para_editar['Custo Unit. M.O.']
            df_para_editar['Custo Total Item'] = df_para_editar['Quantidade'] * df_para_editar['Custo Unit. Total']
            
            df_editado = st.data_editor(df_para_editar, column_config={"Item Padrão": st.column_config.TextColumn("Serviço", disabled=True, width="large"), "Unidade": st.column_config.TextColumn("Un.", disabled=True, width="small"), "Quantidade": st.column_config.NumberColumn("Quantidade", min_value=0.0, format="%.2f"), "Custo Unit. Material": st.column_config.NumberColumn("Custo Mat. Unit.", disabled=True, format="R$ %.2f"), "Custo Unit. M.O.": st.column_config.NumberColumn("Custo M.O. Unit.", disabled=True, format="R$ %.2f"), "Custo Unit. Total": st.column_config.NumberColumn("Custo Total Unit.", disabled=True, format="R$ %.2f"), "Custo Total Item": st.column_config.NumberColumn("Custo Total do Item", disabled=True, format="R$ %.2f"), }, hide_index=True, use_container_width=True, key="orcamento_editor")

            if not df_editado.equals(df_para_editar):
                st.session_state.orcamento_df = df_editado.drop(columns=['Custo Unit. Total', 'Custo Total Item'])
                st.session_state.distribuicao_df = pd.DataFrame() 
                st.rerun()

            st.session_state.custo_total_material = (df_editado["Quantidade"] * df_editado["Custo Unit. Material"]).sum()
            st.session_state.custo_total_mo = (df_editado["Quantidade"] * df_editado["Custo Unit. M.O."]).sum()
            custo_total_geral = st.session_state.custo_total_material + st.session_state.custo_total_mo

            st.markdown("##### Totais de Custo Direto")
            total_cols = st.columns(3)
            with total_cols[0]: st.metric("Custo de Material", f"R$ {st.session_state.custo_total_material:,.2f}")
            with total_cols[1]: st.metric("Custo de Mão de Obra", f"R$ {st.session_state.custo_total_mo:,.2f}")
            with total_cols[2]: st.metric("Custo Total Direto", f"R$ {custo_total_geral:,.2f}")
        else:
            st.warning("Nenhum serviço adicionado ao orçamento ainda.")

# =================================================================================================
# --- ABA 2: DEFININDO O FATURAMENTO ---
# =================================================================================================
with tab2:
    st.header("Formação do Preço e Simulação de Faturamento")
    custo_total_ab2 = st.session_state.get('custo_total_material', 0) + st.session_state.get('custo_total_mo', 0)
    if custo_total_ab2 == 0:
        st.warning("É necessário primeiro montar o Custo Direto na Aba 1."); st.stop()

    def desenhar_calculadora_bdi(tipo, custo_base, chaves_ss):
        st.subheader(f"BDI - {tipo}")
        
        st.markdown("**1. Componentes do BDI (%)**")
        entradas_cols = st.columns(5)
        with entradas_cols[0]: st.number_input("Administração Central e Local", key=chaves_ss['ac'], value=float(st.session_state.get(chaves_ss['ac'], 0)), format="%.2f")
        with entradas_cols[1]: st.number_input("Custo Financeiro", key=chaves_ss['cf'], value=float(st.session_state.get(chaves_ss['cf'], 0)), format="%.2f")
        with entradas_cols[2]: st.number_input("Margem de Incerteza", key=chaves_ss['mi'], value=float(st.session_state.get(chaves_ss['mi'], 0)), format="%.2f")
        with entradas_cols[3]: st.number_input("Tributos", key=chaves_ss['tributos'], value=float(st.session_state.get(chaves_ss['tributos'], 0)), format="%.2f")
        with entradas_cols[4]: st.number_input("Lucro", key=chaves_ss['lucro'], value=float(st.session_state.get(chaves_ss['lucro'], 0)), format="%.2f")
        
        soma_percentuais = sum([st.session_state.get(k, 0) for k in chaves_ss.values()]) / 100.0
        
        if soma_percentuais >= 1: 
            bdi, pv, lucro_valor = 0, 0, 0
            st.error("A soma dos componentes do BDI não pode ser >= 100%.", icon="🚨")
        else:
            bdi = soma_percentuais / (1 - soma_percentuais) if (1 - soma_percentuais) != 0 else 0
            pv = custo_base * (1 + bdi)
            lucro_valor = pv * (st.session_state.get(chaves_ss['lucro'], 0) / 100.0)
        
        st.markdown("**2. Resultados Calculados**")
        # Alterado para 5 colunas para incluir o Custo Direto
        resultados_cols = st.columns(5)
        with resultados_cols[0]: st.metric(f"Custo {tipo}", f"R$ {custo_base:,.2f}")
        with resultados_cols[1]: st.metric("Preço de Venda", f"R$ {pv:,.2f}")
        with resultados_cols[2]: st.metric("Lucro Bruto (R$)", f"R$ {lucro_valor:,.2f}")
        with resultados_cols[3]: st.metric("BDI", f"{bdi * 100:.2f}%")
        with resultados_cols[4]:
            margem_lucro = (lucro_valor / pv) * 100 if pv > 0 else 0
            st.metric("Margem de Lucro", f"{margem_lucro:.2f}%")
        
        # Novo expander com a tabela de detalhamento
        with st.expander("Ver detalhamento dos cálculos"):
            valor_menos_imposto = pv * (1 - (st.session_state.get(chaves_ss['tributos'], 0) / 100.0))
            data_detalhe = {
                'Descrição': ["Custo Direto", "Preço de Venda (Valor Total)", "Valor Total - Imposto", "Lucro", "Margem de Lucro"],
                'Valor': [custo_base, pv, valor_menos_imposto, lucro_valor, f"{margem_lucro:.2f}%"]
            }
            df_detalhe = pd.DataFrame(data_detalhe)
            st.dataframe(df_detalhe.style.format({'Valor': lambda x: f'R$ {x:,.2f}' if isinstance(x, (int, float)) else x}), hide_index=True, use_container_width=True)

        return pv, lucro_valor

    chaves_mo = {'ac': 'bdi_ac_mo', 'cf': 'bdi_cf_mo', 'mi': 'bdi_mi_mo', 'tributos': 'bdi_tributos_mo', 'lucro': 'bdi_lucro_mo'}
    chaves_mat = {'ac': 'bdi_ac_mat', 'cf': 'bdi_cf_mat', 'mi': 'bdi_mi_mat', 'tributos': 'bdi_tributos_mat', 'lucro': 'bdi_lucro_mat'}
    
    with st.container(border=True):
        pv_mo, lucro_mo = desenhar_calculadora_bdi("Mão de Obra", st.session_state.get('custo_total_mo', 0), chaves_mo)
    
    with st.container(border=True):
        pv_mat, lucro_mat = desenhar_calculadora_bdi("Material", st.session_state.get('custo_total_material', 0), chaves_mat)

    with st.container(border=True):
        st.subheader("Resumo do Faturamento Previsto")
        pv_total = pv_mo + pv_mat
        st.session_state.preco_venda_total = pv_total
        custo_total = st.session_state.get('custo_total_mo', 0) + st.session_state.get('custo_total_material', 0)
        lucro_total_previsto = lucro_mo + lucro_mat
        margem_media = (lucro_total_previsto / pv_total) * 100 if pv_total > 0 else 0
        
        resumo_detalhado = st.columns(4)
        with resumo_detalhado[0]: st.metric("Valor Total do Projeto", f"R$ {pv_total:,.2f}")
        with resumo_detalhado[1]: st.metric("Custo Direto Total", f"R$ {custo_total:,.2f}")
        with resumo_detalhado[2]: st.metric("Lucro Bruto Previsto", f"R$ {lucro_total_previsto:,.2f}")
        with resumo_detalhado[3]: st.metric("% Margem Média Prevista", f"{margem_media:.2f}%")

    with st.container(border=True):
        st.subheader("Simulação de Lucro Real")
        st.markdown("Use os controles abaixo para simular como a distribuição do faturamento e as alíquotas reais de imposto afetam seu lucro líquido.")
        
        sim_cols = st.columns(3)
        with sim_cols[0]:
            percent_faturamento_material_sim = st.slider("Distribuição do Faturamento (% Material)", 0, 100, 50, help="Defina qual percentual do valor total será faturado como 'Material'.")
        with sim_cols[1]:
            taxa_mo_sim = st.number_input("Alíquota Real Imposto M.O. (%)", value=float(st.session_state.get('bdi_tributos_mo', 0)), format="%.2f")
        with sim_cols[2]:
            taxa_material_sim = st.number_input("Alíquota Real Imposto Mat. (%)", value=float(st.session_state.get('bdi_tributos_mat', 0)), format="%.2f")
        
        valor_faturado_material_sim = pv_total * (percent_faturamento_material_sim / 100.0)
        valor_faturado_mo_sim = pv_total * ((100 - percent_faturamento_material_sim) / 100.0)
        imposto_real_material = valor_faturado_material_sim * (taxa_material_sim / 100.0)
        imposto_real_mo = valor_faturado_mo_sim * (taxa_mo_sim / 100.0)
        imposto_total_real = imposto_real_material + imposto_real_mo
        lucro_liquido_real = pv_total - custo_total - imposto_total_real
        margem_lucro_real_percent = (lucro_liquido_real / pv_total) * 100 if pv_total > 0 else 0
        bdi_efetivo = (pv_total / custo_total) - 1 if custo_total > 0 else 0
        
        st.markdown("**Resultados da Simulação:**")
        # Alterado para 3 colunas para incluir o BDI Efetivo
        sim_res_cols = st.columns(3)
        with sim_res_cols[0]: st.metric("Lucro Líquido Real (R$)", f"R$ {lucro_liquido_real:,.2f}")
        with sim_res_cols[1]: st.metric("Margem de Lucro Real (%)", f"{margem_lucro_real_percent:.2f}%", delta=f"{(margem_lucro_real_percent - margem_media):.2f}% vs. Previsto")
        with sim_res_cols[2]: st.metric("BDI Efetivo do Projeto", f"{bdi_efetivo * 100:.2f}%")

        with st.expander("Ver detalhamento da simulação de faturamento"):
            sim_data = {
                '': ['Mão de Obra', 'Material', 'Total'],
                'Valor Faturado (R$)': [valor_faturado_mo_sim, valor_faturado_material_sim, pv_total],
                'Imposto Pago (R$)': [imposto_real_mo, imposto_real_material, imposto_total_real],
                'Valor - Imposto (R$)': [valor_faturado_mo_sim - imposto_real_mo, valor_faturado_material_sim - imposto_real_material, pv_total - imposto_total_real]
            }
            sim_df = pd.DataFrame(sim_data)
            st.dataframe(sim_df.style.format({'Valor Faturado (R$)': 'R$ {:,.2f}', 'Imposto Pago (R$)': 'R$ {:,.2f}', 'Valor - Imposto (R$)': 'R$ {:,.2f}'}), hide_index=True, use_container_width=True)


# =================================================================================================
# --- ABA 3: DISTRIBUIÇÃO E FINALIZAÇÃO ---
# =================================================================================================
with tab3:
    st.header("Distribuição do Preço de Venda por Item")
    if st.session_state.preco_venda_total == 0 or st.session_state.orcamento_df.empty:
        st.warning("É necessário primeiro montar o custo (Aba 1) e calcular o preço de venda (Aba 2)."); st.stop()
    
    st.info("A tabela abaixo sugere um preço para cada item. Ajuste a coluna 'PV Unitário Final' se necessário.")
    
    custo_total_geral_aba3 = st.session_state.get('custo_total_material', 0) + st.session_state.get('custo_total_mo', 0)
    
    if st.session_state.distribuicao_df.empty or not set(st.session_state.orcamento_df['Item Padrão']) == set(st.session_state.distribuicao_df['Item Padrão']):
        df_dist = st.session_state.orcamento_df.copy()
        if custo_total_geral_aba3 > 0:
            df_dist['Custo Unitário Total'] = df_dist['Custo Unit. Material'] + df_dist['Custo Unit. M.O.']
            df_dist['Custo Total Item'] = df_dist['Quantidade'] * df_dist['Custo Unitário Total']
            df_dist['Peso Custo'] = df_dist['Custo Total Item'] / custo_total_geral_aba3
            df_dist['PV Sugerido Item'] = st.session_state.preco_venda_total * df_dist['Peso Custo']
            
            if not df_dist.empty:
                soma_parcial = df_dist['PV Sugerido Item'].sum()
                diferenca_arredondamento = st.session_state.preco_venda_total - soma_parcial
                if not df_dist.empty:
                    df_dist.loc[df_dist.index[-1], 'PV Sugerido Item'] += diferenca_arredondamento

            df_dist['PV Unitário Sugerido'] = df_dist['PV Sugerido Item'] / df_dist['Quantidade'].replace(0, 1)
        else:
            df_dist['Custo Unitário Total'], df_dist['Custo Total Item'], df_dist['Peso Custo'], df_dist['PV Sugerido Item'], df_dist['PV Unitário Sugerido'] = [0.0] * 5
        
        df_dist['PV Unitário Final'] = df_dist['PV Unitário Sugerido']
        st.session_state.distribuicao_df = df_dist

    df_para_editar_pv = st.session_state.distribuicao_df.copy()
    df_para_editar_pv['PV Total Final Item'] = df_para_editar_pv['PV Unitário Final'] * df_para_editar_pv['Quantidade']
    
    df_editado_pv = st.data_editor(df_para_editar_pv, key="pv_editor", column_config={"Item Padrão": st.column_config.TextColumn("Serviço", disabled=True, width="large"), "Quantidade": st.column_config.NumberColumn("Qtd.", disabled=True, format="%.2f"), "Custo Unitário Total": st.column_config.NumberColumn("Custo Unit. Total", disabled=True, format="R$ %.2f"), "Custo Total Item": st.column_config.NumberColumn("Custo Item Total", disabled=True, format="R$ %.2f"), "PV Unitário Sugerido": st.column_config.NumberColumn("PV Unit. Sugerido", disabled=True, format="R$ %.2f"), "PV Unitário Final": st.column_config.NumberColumn("PV Unitário Final", format="R$ %.2f", min_value=0.0, help="Ajuste o Preço de Venda Unitário aqui."), "PV Total Final Item": st.column_config.NumberColumn("PV Total Final", disabled=True, format="R$ %.2f"), "Unidade": None, "Custo Unit. Material": None, "Custo Unit. M.O.": None, "Peso Custo": None, "PV Sugerido Item": None}, column_order=["Item Padrão", "Quantidade", "Custo Unitário Total", "Custo Total Item", "PV Unitário Sugerido", "PV Unitário Final", "PV Total Final Item"], use_container_width=True, hide_index=True)

    if not df_editado_pv.equals(df_para_editar_pv):
        st.session_state.distribuicao_df = df_editado_pv
        st.rerun()

    novo_pv_total = df_editado_pv['PV Total Final Item'].sum()
    diferenca = novo_pv_total - st.session_state.preco_venda_total
    
    st.markdown("##### Controle de Fechamento")
    total_cols = st.columns(3)
    with total_cols[0]: st.metric("Preço de Venda (Meta)", f"R$ {st.session_state.preco_venda_total:,.2f}")
    with total_cols[1]: st.metric("Preço de Venda (Ajustado)", f"R$ {novo_pv_total:,.2f}")
    with total_cols[2]: st.metric("Diferença", f"R$ {diferenca:,.2f}")

    if not np.isclose(novo_pv_total, st.session_state.preco_venda_total):
        col_info, col_btn = st.columns([0.7, 0.3])
        with col_info:
            st.info("Ajuste a tabela para que a 'Diferença' seja R$ 0,00 ou use o reajuste.")
        with col_btn:
            if st.button("⚙️ Reajustar Preços Automaticamente", use_container_width=True):
                if novo_pv_total > 0:
                    fator_ajuste = st.session_state.preco_venda_total / novo_pv_total
                    st.session_state.distribuicao_df['PV Unitário Final'] *= fator_ajuste
                    st.rerun()
                else:
                    st.warning("Não é possível reajustar com um total de R$ 0,00.")
    else:
        st.success("O total ajustado corresponde à meta. Orçamento pronto para ser finalizado.")

    st.divider()
    st.subheader("Finalizar e Salvar Orçamento")

    with st.form(key="form_salvar_orcamento"):
        st.markdown("**Preencha os dados para salvar o orçamento no histórico.**")
        col_form1, col_form2 = st.columns(2)
        with col_form1:
            nome_cliente_input = st.text_input("Nome do Cliente")
        with col_form2:
            nome_obra_input = st.text_input("Nome da Obra")
        
        observacao_input = st.text_area("Observações (Opcional)", height=100)
        submitted = st.form_submit_button("Salvar Orçamento Final no Banco de Dados", type="primary", use_container_width=True)

        if submitted:
            if not nome_cliente_input.strip():
                st.error("O campo 'Nome do Cliente' é obrigatório.", icon="🚨")
            elif not nome_obra_input.strip():
                st.error("O campo 'Nome da Obra' é obrigatório.", icon="🚨")
            elif not np.isclose(novo_pv_total, st.session_state.preco_venda_total):
                st.error("O 'Preço de Venda (Ajustado)' deve ser igual ao 'Preço de Venda (Meta)'. Ajuste a tabela ou use o botão 'Reajustar'.", icon="🚨")
            else:
                with st.spinner("Salvando orçamento no banco de dados..."):
                    df_para_salvar = df_editado_pv.rename(columns={"Item Padrão": "descricao", "Unidade": "unidade", "Quantidade": "quantidade", "PV Unitário Final": "valor_unitario", "PV Total Final Item": "valor_total"})
                    df_para_salvar = df_para_salvar[["descricao", "unidade", "quantidade", "valor_unitario", "valor_total"]]
                    
                    try:
                        itens_salvos = processador.salvar_orcamento_gerado(df_orcamento=df_para_salvar, nome_obra=nome_obra_input, nome_cliente=nome_cliente_input, observacao=observacao_input)
                        st.success(f"Sucesso! {itens_salvos} itens foram salvos para a obra '{nome_obra_input}'.", icon="✅")
                        st.balloons()
                        # Limpa a sessão para um novo orçamento
                        del st.session_state.bdi_valores_iniciados
                        st.rerun()
                    except Exception as e:
                        st.error(f"Ocorreu um erro ao salvar: {e}", icon="🔥")

    st.divider()
    st.subheader("Exportar Orçamento")
    
    if df_editado_pv is not None and not df_editado_pv.empty:
        output = io.BytesIO()
        df_export = df_editado_pv.rename(columns={"Item Padrão": "Descrição", "Unidade": "Unidade de Medida", "PV Unitário Final": "Preço Unitário", "PV Total Final Item": "Preço Total"})
        df_export.insert(0, "Item", np.arange(1, len(df_export) + 1))
        df_export = df_export[["Item", "Descrição", "Unidade de Medida", "Quantidade", "Preço Unitário", "Preço Total"]]
        
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_export.to_excel(writer, index=False, sheet_name='Orçamento')
        
        st.download_button(label="📥 Baixar Orçamento em Excel", data=output.getvalue(), file_name="orcamento_final.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", use_container_width=True)