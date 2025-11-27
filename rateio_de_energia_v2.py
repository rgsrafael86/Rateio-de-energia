import streamlit as st
import pandas as pd
import plotly.express as px
import io
from openpyxl.utils import get_column_letter
from datetime import datetime

# Inicialização de variáveis de sessão
if "df_resultado" not in st.session_state:
    st.session_state.df_resultado = None
if "alertas_resultado" not in st.session_state:
    st.session_state.alertas_resultado = []
if "resumo_resultado" not in st.session_state:
    st.session_state.resumo_resultado = {}
if "historico" not in st.session_state:
    st.session_state.historico = pd.DataFrame()
if "prev_map" not in st.session_state:
    st.session_state.prev_map = {}
if "import_resumo" not in st.session_state:
    st.session_state.import_resumo = None

hora_local = datetime.now()

# ===================== IMPORTAÇÃO DO MÊS ANTERIOR =====================
st.header("📂 Mês anterior (importar backup)")
arquivo = st.file_uploader("Carregue o arquivo Excel do mês anterior", type=["xlsx"])

if arquivo is not None:
    try:
        xls = pd.ExcelFile(arquivo)
        resumo_imp = pd.read_excel(xls, sheet_name="Resumo")
        rateio_imp = pd.read_excel(xls, sheet_name="Rateio")

        # Guardar em sessão
        st.session_state.import_resumo = resumo_imp
        st.session_state.prev_map = dict(zip(rateio_imp["Quitinete"], rateio_imp["Consumo (kWh)"]))

        # Aplicar setups automaticamente
        try:
            st.session_state.bandeira_sel = resumo_imp.loc[resumo_imp["Item"] == "Bandeira por faixa", "Valor"].values[0]
            st.session_state.metodo_rateio = resumo_imp.loc[resumo_imp["Item"] == "Método de rateio", "Valor"].values[0]
            st.session_state.fonte_sel = resumo_imp.loc[resumo_imp["Item"] == "Fonte do consumo total", "Valor"].values[0]
            st.session_state.consumo_total_prédio = resumo_imp.loc[resumo_imp["Item"] == "Consumo total (kWh)", "Valor"].values[0]
        except Exception:
            pass

        st.success("Backup importado! Configurações e leituras anteriores aplicadas automaticamente.")
        st.write("Resumo do mês anterior:")
        st.dataframe(resumo_imp)
        st.write("Rateio do mês anterior (usado como leitura anterior):")
        st.dataframe(rateio_imp)

    except Exception as e:
        st.error(f"Erro ao importar backup: {e}")

# ===================== SIDEBAR COM MEMORIAL DE SETUP =====================
st.sidebar.title("Configurações")
bandeiras = ["Verde", "Amarela", "Vermelha 1", "Vermelha 2"]
metodos = ["Faixas individuais", "Proporcional ao total da fatura"]
fontes_consumo = ["Leituras do prédio", "Soma das quitinetes"]

bandeira_index = bandeiras.index(st.session_state.get("bandeira_sel", bandeiras[0])) if st.session_state.get("bandeira_sel") in bandeiras else 0
metodo_index = metodos.index(st.session_state.get("metodo_rateio", metodos[0])) if st.session_state.get("metodo_rateio") in metodos else 0
fonte_index = fontes_consumo.index(st.session_state.get("fonte_sel", fontes_consumo[0])) if st.session_state.get("fonte_sel") in fontes_consumo else 0

st.sidebar.radio("Bandeira tarifária", bandeiras, index=bandeira_index, key="bandeira_sel")
st.sidebar.radio("Método de rateio", metodos, index=metodo_index, key="metodo_rateio")
st.sidebar.radio("Fonte do consumo total", fontes_consumo, index=fonte_index, key="fonte_sel")

if "consumo_total_prédio" in st.session_state:
    st.sidebar.write(f"⚡ Consumo anterior: **{st.session_state.consumo_total_prédio} kWh**")

# ===================== EXPORTAÇÃO PARA EXCEL =====================
if st.session_state.df_resultado is not None:
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        st.session_state.df_resultado.to_excel(writer, sheet_name="Rateio", index=True)

        resumo_dict = st.session_state.resumo_resultado or {}
        if resumo_dict:
            resumo = pd.DataFrame({
                "Item": list(resumo_dict.keys()),
                "Valor": list(resumo_dict.values())
            })
            resumo.to_excel(writer, sheet_name="Resumo", index=False)

        if not st.session_state.historico.empty:
            st.session_state.historico.to_excel(writer, sheet_name="Histórico", index=False)

        for ws in writer.sheets.values():
            for col in ws.columns:
                max_length = 0
                col_letter = get_column_letter(col[0].column)
                for cell in col:
                    if cell.value is not None:
                        max_length = max(max_length, len(str(cell.value)))
                ws.column_dimensions[col_letter].width = max_length + 2

    buffer.seek(0)
    nome_id = (st.session_state.resumo_resultado or {}).get("Identificação", hora_local.strftime("%d-%m-%Y_%H-%M"))
    st.download_button(
        label="⬇️ Baixar relatório em Excel",
        data=buffer,
        file_name=f"rateio_{str(nome_id).replace('/', '-').replace(':', '-')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# ===================== EXPLICAÇÕES DISCRETAS =====================
st.divider()
with st.expander("📂 Importação do mês anterior", expanded=False):
    st.markdown("""
    • Ao final de cada mês, baixe o relatório em Excel.  
    • No mês seguinte, importe esse arquivo na aba **Mês anterior**.  
    • O sistema vai recuperar automaticamente:  
      – Bandeira tarifária, método de rateio e fonte do consumo total  
      – Consumo (kWh) de cada quitinete do mês anterior, que passa a ser a **leitura anterior** deste mês.  
    • Mantenha os nomes das quitinetes consistentes entre os meses para que a importação funcione corretamente.
    """)

st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: grey; font-size: 14px;'>"
    "Desenvolvido por <strong>Rafael Guimarães dos Santos</strong> — Todos os direitos reservados ©"
    "</div>",
    unsafe_allow_html=True
)
