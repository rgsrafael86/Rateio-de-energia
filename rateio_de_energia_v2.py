import streamlit as st
import pandas as pd
import plotly.express as px
import io
from datetime import datetime
from openpyxl.styles import Font, Alignment, PatternFill, Border, Side
from openpyxl.utils import get_column_letter

# Configuração da página
st.set_page_config(page_title="Rateio de Energia", page_icon="💡", layout="wide")
st.title("💡 Rateio de Energia - Quitinetes")

# Inicializa histórico
if "historico" not in st.session_state:
    st.session_state.historico = pd.DataFrame()

# Sidebar: Configurações
st.sidebar.header("⚙️ Tarifas (R$/kWh) por faixa")
tarifas = {
    "te_ate_150": st.sidebar.number_input("TE até 150 kWh", value=0.392200, format="%.6f"),
    "te_acima_150": st.sidebar.number_input("TE acima 150 kWh", value=0.456583, format="%.6f"),
    "tusd_ate_150": st.sidebar.number_input("TUSD até 150 kWh", value=0.455833, format="%.6f"),
    "tusd_acima_150": st.sidebar.number_input("TUSD acima de 150 kWh", value=0.456583, format="%.6f"),
}

st.sidebar.header("🚩 Bandeiras (R$/kWh)")
bandeiras = {
    "verde": st.sidebar.number_input("Verde", value=0.000000, format="%.6f"),
    "amarela": st.sidebar.number_input("Amarela", value=0.018660, format="%.6f"),
    "vermelha1": st.sidebar.number_input("Vermelha 1", value=0.044630, format="%.6f"),
    "vermelha2": st.sidebar.number_input("Vermelha 2", value=0.075660, format="%.6f"),
}

st.sidebar.header("🏛️ Tributos")
pis_percent = st.sidebar.number_input("PIS (%)", value=1.20, format="%.2f")
cofins_percent = st.sidebar.number_input("COFINS (%)", value=5.53, format="%.2f")
pis_cofins_base = st.sidebar.number_input("Base de cálculo PIS/COFINS (R$)", value=193.65, format="%.2f")

icms_base_1 = st.sidebar.number_input("Base ICMS 1 (R$)", value=135.29, format="%.2f")
icms_aliquota_1 = st.sidebar.number_input("Alíquota ICMS 1 (%)", value=12.00, format="%.2f")
icms_base_2 = st.sidebar.number_input("Base ICMS 2 (R$)", value=89.88, format="%.2f")
icms_aliquota_2 = st.sidebar.number_input("Alíquota ICMS 2 (%)", value=17.00, format="%.2f")

st.sidebar.header("🏙️ Outras taxas")
cosip = st.sidebar.number_input("COSIP (R$)", value=17.01, format="%.2f")

# Funções
def fatura_energia(consumo_kwh: float, bandeira_key: str) -> dict:
    c1 = min(consumo_kwh, 150)
    c2 = max(consumo_kwh - 150, 0)
    te = c1 * tarifas["te_ate_150"] + c2 * tarifas["te_acima_150"]
    tusd = c1 * tarifas["tusd_ate_150"] + c2 * tarifas["tusd_acima_150"]
    band = consumo_kwh * bandeiras[bandeira_key]
    return {"consumo": consumo_kwh, "te": te, "tusd": tusd, "bandeira": band}

def calcular_tributos():
    pis_val = pis_cofins_base * (pis_percent / 100.0)
    cofins_val = pis_cofins_base * (cofins_percent / 100.0)
    icms1_val = icms_base_1 * (icms_aliquota_1 / 100.0)
    icms2_val = icms_base_2 * (icms_aliquota_2 / 100.0)
    return {
        "pis": round(pis_val, 2),
        "cofins": round(cofins_val, 2),
        "icms_1": round(icms1_val, 2),
        "icms_2": round(icms2_val, 2),
        "icms_total": round(icms1_val + icms2_val, 2),
    }

def calcular_fatura_total(leitura_ant: int, leitura_at: int, bandeira_key: str):
    consumo = max(leitura_at - leitura_ant, 0)
    base = fatura_energia(consumo, bandeira_key)
    valor_base = base["te"] + base["tusd"] + base["bandeira"]
    trib = calcular_tributos()
    total = round(valor_base + trib["pis"] + trib["cofins"] + trib["icms_total"] + cosip, 2)
    return total, consumo, {"base": base, "tributos": trib}

def adicionar_historico(nome_simulacao: str, df: pd.DataFrame, valor_total: float, consumo_total: float):
    linha = df.copy()
    linha["Identificação"] = nome_simulacao
    linha["Consumo Total"] = consumo_total
    linha["Valor Total"] = valor_total
    st.session_state.historico = pd.concat([st.session_state.historico, linha.reset_index()], ignore_index=True)

# Interface
st.header("🔢 Leituras do prédio")
col1, col2 = st.columns(2)
with col1:
    leitura_predio_ant = st.number_input("Leitura anterior do prédio", min_value=0, step=1)
with col2:
    leitura_predio_at = st.number_input("Leitura atual do prédio", min_value=0, step=1)

bandeira_sel = st.radio("Bandeira vigente", list(bandeiras.keys()))
nome_simulacao = st.text_input("Identificação da simulação (ex.: Conta Nov/2025)", value=datetime.now().strftime("%d/%m/%Y %H:%M"))

st.header("🏠 Leituras das quitinetes")
n = st.slider("Número de quitinetes", 1, 20, value=2)
consumos_individuais, valores_individuais = [], []

for i in range(n):
    with st.expander(f"Quitinete {i+1}", expanded=True):
        c1, c2 = st.columns(2)
        with c1:
            ant = st.number_input(f"Leitura anterior Q{i+1}", min_value=0, step=1, key=f"ant_{i}")
        with c2:
            at = st.number_input(f"Leitura atual Q{i+1}", min_value=0, step=1, key=f"at_{i}")
        consumo_q = max(at - ant, 0)
        consumos_individuais.append(consumo_q)
        base_q = fatura_energia(consumo_q, bandeira_sel)
        valores_individuais.append(round(base_q["te"] + base_q["tusd"] + base_q["bandeira"], 2))

if st.button("Calcular"):
    valor_total, consumo_total, detalhamento = calcular_fatura_total(leitura_predio_ant, leitura_predio_at, bandeira_sel)
    soma_ind = sum(consumos_individuais)
    saldo_consumo = consumo_total - soma_ind
    valor_ind_sum = sum(valores_individuais)
    base_areas = fatura_energia(max(saldo_consumo, 0), bandeira_sel)
    valor_areas = round(base_areas["te"] + base_areas["tusd"] + base_areas["bandeira"], 2)

    df = pd.DataFrame({
        "Consumo (kWh)": consumos_individuais + [saldo_consumo],
        "Valor base (R$)": valores_individuais + [valor_areas],
    }, index=[f"Quitinete {i+1}" for i in range(n)] + ["Áreas Comuns"])

    st.success(f"Consumo total do prédio: {consumo_total} kWh")
    st.success(f"Valor base (TE+TUSD+Bandeira): R$ {round(valor_ind_sum + valor_areas, 2)}")
    st.info(f"Tributos: PIS R$ {detalhamento['tributos']['pis']}, COFINS R$ {detalhamento['tributos']['cofins']}, "
            f"ICMS total R$ {detalhamento['tributos']['icms_total']} | COSIP: R$ {cosip}")
    st.success(f"Valor total da fatura: R$ {valor_total}")

    st.subheader("📊 Rateio detalhado (valores base,
