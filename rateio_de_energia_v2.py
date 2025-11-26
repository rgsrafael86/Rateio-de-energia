import streamlit as st
import pandas as pd
import plotly.express as px
import io
from datetime import datetime
from openpyxl.utils import get_column_letter

st.set_page_config(page_title="Rateio de Energia", page_icon="💡", layout="wide")
st.title("💡 Rateio de Energia - Quitinetes")

# Inicializa histórico
if "historico" not in st.session_state:
    st.session_state.historico = pd.DataFrame()

# Sidebar: Configurações
st.sidebar.header("⚙️ Tarifas Celesc (R$/kWh, já com tributos)")
tarifas = {
    "te_ate_150": st.sidebar.number_input("TE até 150 kWh", value=0.392200, format="%.6f"),
    "te_acima_150": st.sidebar.number_input("TE acima 150 kWh", value=0.415851, format="%.6f"),
    "tusd_ate_150": st.sidebar.number_input("TUSD até 150 kWh", value=0.455333, format="%.6f"),
    "tusd_acima_150": st.sidebar.number_input("TUSD acima 150 kWh", value=0.482660, format="%.6f"),
}
cosip = st.sidebar.number_input("COSIP (R$)", value=17.01, format="%.2f")

# Bandeira tarifária
st.sidebar.header("🚩 Bandeira Tarifária")
bandeira_sel = st.sidebar.radio("Selecione a bandeira vigente", ["Verde", "Amarela", "Vermelha 1", "Vermelha 2"])
bandeira_valor = {
    "Verde": 0.000000,
    "Amarela": 0.018660,
    "Vermelha 1": 0.044630,
    "Vermelha 2": 0.075660
}[bandeira_sel]

# Método de rateio
st.sidebar.header("📊 Método de Rateio")
metodo_rateio = st.sidebar.radio("Escolha o método:", ["Faixas individuais", "Proporcional ao total da fatura"])

# Funções
def calcular_valor(consumo):
    c1 = min(consumo, 150)
    c2 = max(consumo - 150, 0)
    te = c1 * tarifas["te_ate_150"] + c2 * tarifas["te_acima_150"]
    tusd = c1 * tarifas["tusd_ate_150"] + c2 * tarifas["tusd_acima_150"]
    band = consumo * bandeira_valor
    return round(te + tusd + band, 2)

def calcular_fatura_total(consumo_total):
    valor_base = calcular_valor(consumo_total)
    return round(valor_base + cosip, 2), valor_base

def adicionar_historico(nome_simulacao, df, valor_total, consumo_total):
    linha = df.copy()
    linha["Identificação"] = nome_simulacao
    linha["Consumo Total"] = consumo_total
    linha["Valor Total"] = valor_total
    st.session_state.historico = pd.concat([st.session_state.historico, linha.reset_index()], ignore_index=True)

# Interface
st.header("🔢 Leituras do prédio")
col1, col2 = st.columns(2)
with col1:
    leitura_ant = st.number_input("Leitura anterior do prédio", min_value=0, step=1)
with col2:
    leitura_at = st.number_input("Leitura atual do prédio", min_value=0, step=1)

nome_simulacao = st.text_input("Identificação da simulação", value=datetime.now().strftime("%d/%m/%Y %H:%M"))

st.header("🏠 Leituras das quitinetes")
n = st.slider("Número de quitinetes", 1, 20, value=2)
consumos_individuais = []
nomes_inquilinos = []

for i in range(n):
    with st.expander(f"Quitinete {i+1}", expanded=True):
        nome = st.text_input(f"Nome do inquilino Q{i+1}", key=f"nome_{i}")
        nomes_inquilinos.append(nome if nome else f"Q{i+1}")
        c1, c2 = st.columns(2)
        with c1:
            ant = st.number_input("Leitura anterior", min_value=0, step=1, key=f"ant_{i}")
        with c2:
            at = st.number_input("Leitura atual", min_value=0, step=1, key=f"at_{i}")
        consumos_individuais.append(max(at - ant, 0))

if st.button("Calcular"):
    consumo_total = sum(consumos_individuais)
    valor_total, valor_base = calcular_fatura_total(consumo_total)

    if metodo_rateio == "Faixas individuais":
        valores_individuais = [calcular_valor(c) for c in consumos_individuais]
    else:  # proporcional
        valores_individuais = [round(c / consumo_total * valor_total, 2) if consumo_total > 0 else 0 for c in consumos_individuais]

    df = pd.DataFrame({
        "Consumo (kWh)": consumos_individuais,
        "Valor (R$)": valores_individuais
    }, index=[f"Quitinete {i+1} - {nomes_inquilinos[i]}" for i in range(n)])

    st.success(f"Consumo total do prédio: {consumo_total} kWh")
    st.success(f"Valor total da fatura: R$ {valor_total}")

    st.subheader("📊 Rateio detalhado")
    st.dataframe(df.style.format({"Valor (R$)": "R${:,.2f}"}))

    st.subheader("📈 Consumo por unidade")
    fig = px.bar(df.reset_index(), x="index", y="Consumo (kWh)",
                 text="Consumo (kWh)", color="index",
                 labels={"index": "Unidade", "Consumo (kWh)": "Consumo (kWh)"})
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)

    adicionar_historico(nome_simulacao, df, valor_total, consumo_total)

    # Excel export
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Rateio", index=True)
        resumo = pd.DataFrame({
            "Item": ["Consumo total (kWh)", "Valor base (R$)", "COSIP (R$)", "Total fatura (R$)"],
            "Valor": [consumo_total, valor_base, cosip, valor_total]
        })
        resumo.to_excel(writer, sheet_name="Resumo", index=False)
        if not st.session_state.historico.empty:
            st.session_state.historico.to_excel(writer, sheet_name="Histórico", index=False)

        # Ajusta largura das colunas
        for ws in writer.sheets.values():
            for col in ws.columns:
                max_length = max(len(str(cell.value)) if cell.value else 0 for cell in col)
                ws.column_dimensions[get_column_letter(col[0].column)].width = max_length + 2

    buffer.seek(0)
    st.download_button(
        label="⬇️ Baixar relatório em Excel",
        data=buffer,
        file_name=f"rateio_{nome_simulacao.replace('/', '-')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# Histórico
if not st.session_state.historico.empty:
    st.header("📅 Histórico de Rateios")
    st.dataframe(st.session_state.historico)
