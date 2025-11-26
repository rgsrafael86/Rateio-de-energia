import streamlit as st
import pandas as pd
import plotly.express as px
import io
from datetime import datetime

# Configuração da página
st.set_page_config(page_title="Rateio de Energia", page_icon="💡", layout="wide")
st.title("💡 Rateio de Energia - Quitinetes")

# Inicializa histórico
if "historico" not in st.session_state:
    st.session_state.historico = pd.DataFrame()

# Sidebar: Configuração de tarifas (valores já com tributos embutidos, iguais à fatura real)
st.sidebar.header("⚙️ Tarifas e Bandeiras")
tarifas = {
    'te_ate_150': st.sidebar.number_input("TE até 150 kWh", value=0.392200, format="%.6f"),
    'te_acima_150': st.sidebar.number_input("TE acima de 150 kWh", value=0.456583, format="%.6f"),
    'tusd_ate_150': st.sidebar.number_input("TUSD até 150 kWh", value=0.455833, format="%.6f"),
    'tusd_acima_150': st.sidebar.number_input("TUSD acima de 150 kWh", value=0.456583, format="%.6f"),
    'cosip': st.sidebar.number_input("COSIP (R$)", value=17.01, format="%.2f")
}
bandeiras = {
    "verde": 0.00000,
    "amarela": 0.01866,
    "vermelha1": 0.04463,
    "vermelha2": 0.075660  # valor unitário da bandeira vermelha 2
}

# Funções de cálculo
def calcular_valor_consumo(consumo, tarifas, bandeira):
    consumo_1 = min(consumo, 150)
    consumo_2 = max(consumo - 150, 0)

    # Usa tarifas já com tributos embutidos
    valor_te = (consumo_1 * tarifas['te_ate_150']) + (consumo_2 * tarifas['te_acima_150'])
    valor_tusd = (consumo_1 * tarifas['tusd_ate_150']) + (consumo_2 * tarifas['tusd_acima_150'])
    valor_bandeira = consumo * bandeiras[bandeira]

    total = valor_te + valor_tusd + valor_bandeira
    return round(total, 2)

def calcular_fatura_total(leitura_anterior, leitura_atual, tarifas, bandeira):
    consumo_total = leitura_atual - leitura_anterior
    valor_total = calcular_valor_consumo(consumo_total, tarifas, bandeira) + tarifas['cosip']
    return round(valor_total, 2), consumo_total

def adicionar_historico(mes, df, valor_total, consumo_total):
    linha = df.copy()
    linha["Mês"] = mes
    linha["Consumo Total"] = consumo_total
    linha["Valor Total"] = valor_total
    st.session_state.historico = pd.concat([st.session_state.historico, linha.reset_index()], ignore_index=True)

# Seção: Leituras do prédio
st.header("🔢 Leituras do Prédio")
col1, col2 = st.columns(2)
with col1:
    leitura_anterior = st.number_input("Leitura anterior do prédio", min_value=0, step=1)
with col2:
    leitura_atual = st.number_input("Leitura atual do prédio", min_value=0, step=1)

bandeira = st.radio("Bandeira vigente", list(bandeiras.keys()))

# Seção: Leituras das quitinetes
st.header("🏠 Leituras das Quitinetes")
n = st.slider("Número de quitinetes", 1, 20)
consumos_individuais = []
valores_individuais = []

for i in range(n):
    with st.expander(f"Quitinete {i+1}", expanded=True):
        colA, colB = st.columns(2)
        with colA:
            leitura_ant = st.number_input(f"Leitura anterior Q{i+1}", min_value=0, step=1, key=f"ant_{i}")
        with colB:
            leitura_at = st.number_input(f"Leitura atual Q{i+1}", min_value=0, step=1, key=f"at_{i}")
        consumo = leitura_at - leitura_ant
        consumos_individuais.append(consumo)
        valores_individuais.append(calcular_valor_consumo(consumo, tarifas, bandeira))

# Botão de cálculo
if st.button("Calcular"):
    valor_total, consumo_total = calcular_fatura_total(leitura_anterior, leitura_atual, tarifas, bandeira)
    soma_individuais = sum(consumos_individuais)
    saldo_consumo = consumo_total - soma_individuais
    saldo_valor = round(valor_total - sum(valores_individuais), 2)

    df = pd.DataFrame({
        "Consumo (kWh)": consumos_individuais + [saldo_consumo],
        "Valor (R$)": valores_individuais + [saldo_valor]
    }, index=[f"Quitinete {i+1}" for i in range(n)] + ["Áreas Comuns"])

    st.success(f"Consumo total do prédio: {consumo_total} kWh")
    st.success(f"Valor total da fatura: R$ {valor_total}")

    # Exibe tabela
    st.subheader("📊 Rateio detalhado")
    st.dataframe(df.style.format({"Valor (R$)": "R${:,.2f}"}))

    # Gráfico com Plotly
    st.subheader("📈 Consumo por unidade")
    fig = px.bar(df.reset_index(), x="index", y="Consumo (kWh)",
                 text="Consumo (kWh)", color="index",
                 labels={"index": "Unidade", "Consumo (kWh)": "Consumo (kWh)"})
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)

    # Adiciona ao histórico
    mes = datetime.now().strftime("%m/%Y")
    adicionar_historico(mes, df, valor_total, consumo_total)

    # Download Excel
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Rateio", index=True)
    buffer.seek(0)
    st.download_button(
        label="⬇️ Baixar relatório em Excel",
        data=buffer,
        file_name=f"rateio_{mes}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )

# Seção: Histórico acumulado
if not st.session_state.historico.empty:
    st.header("📅 Histórico de Rateios")
    st.dataframe(st.session_state.historico)
