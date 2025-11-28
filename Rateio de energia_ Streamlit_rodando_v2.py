# ===================== IMPORTAÇÕES =====================
import streamlit as st
import pandas as pd
import plotly.express as px
import io
from datetime import datetime
from zoneinfo import ZoneInfo
from openpyxl.utils import get_column_letter

# ===================== CONFIGURAÇÃO DA PÁGINA =====================
st.set_page_config(page_title="Rateio de Energia", page_icon="💡", layout="wide")
st.title("💡 Rateio de Energia - Quitinetes")

# ===================== ESTADO (SESSION_STATE) =====================
if "historico" not in st.session_state:
    st.session_state.historico = pd.DataFrame()
if "df_resultado" not in st.session_state:
    st.session_state.df_resultado = None
if "resumo_resultado" not in st.session_state:
    st.session_state.resumo_resultado = None
if "alertas_resultado" not in st.session_state:
    st.session_state.alertas_resultado = []
if "prev_map" not in st.session_state:
    st.session_state.prev_map = {}
if "import_resumo" not in st.session_state:
    st.session_state.import_resumo = None

# ===================== IMPORTAÇÃO DO MÊS ANTERIOR =====================
st.header("📂 Mês anterior (importar backup)")
arquivo = st.file_uploader("Carregue o arquivo Excel do mês anterior", type=["xlsx"])

if arquivo is not None:
    try:
        xls = pd.ExcelFile(arquivo)
        resumo_imp = pd.read_excel(xls, sheet_name="Resumo")
        rateio_imp = pd.read_excel(xls, sheet_name="Rateio")

        st.session_state.import_resumo = resumo_imp
        st.session_state.prev_map = dict(zip(rateio_imp["Quitinete"], rateio_imp["Consumo (kWh)"]))

        def get_item(item):
            ser = resumo_imp.loc[resumo_imp["Item"] == item, "Valor"]
            return ser.values[0] if len(ser.values) else None

        st.session_state.bandeira_tarifaria = get_item("Bandeira por faixa") or "Vermelha 1"
        st.session_state.metodo_rateio = get_item("Método de rateio") or "Proporcional ao total da fatura"
        st.session_state.fonte_consumo = get_item("Fonte do consumo total") or "Leituras do prédio"
        st.session_state.leitura_predio_ant = get_item("Consumo total (kWh)") or 0

        st.success("Backup importado! Configurações e leituras anteriores aplicadas automaticamente.")
        st.write("Resumo do mês anterior:")
        st.dataframe(resumo_imp)
        st.write("Rateio do mês anterior (usado como leitura anterior):")
        st.dataframe(rateio_imp)

    except Exception as e:
        st.error(f"Erro ao importar backup: {e}")

# ===================== SIDEBAR: CONFIGURAÇÕES =====================
st.sidebar.header("⚙️ Tarifas Celesc (R$/kWh com tributos)")
tarifas = {
    "te_ate_150": st.sidebar.number_input("TE até 150 kWh", value=0.392200, format="%.6f"),
    "te_acima_150": st.sidebar.number_input("TE acima 150 kWh", value=0.415851, format="%.6f"),
    "tusd_ate_150": st.sidebar.number_input("TUSD até 150 kWh", value=0.455333, format="%.6f"),
    "tusd_acima_150": st.sidebar.number_input("TUSD acima 150 kWh", value=0.482660, format="%.6f"),
}
cosip = st.sidebar.number_input("COSIP (R$)", value=17.01, format="%.2f")

st.sidebar.header("🚩 Bandeira tarifária")
bandeira_sel = st.sidebar.radio(
    "Selecione a bandeira",
    ["Verde", "Amarela", "Vermelha 1", "Vermelha 2"],
    index=2,
    key="bandeira_tarifaria"
)
usar_bandeira_por_faixa = st.sidebar.checkbox("Usar bandeira por faixa (como na fatura)", value=True)
bandeira_valor_unico = {
    "Verde": 0.000000,
    "Amarela": 0.018660,
    "Vermelha 1": 0.044630,
    "Vermelha 2": 0.075660,
}[bandeira_sel]
bandeira_por_faixa = {
    "ate_150": st.sidebar.number_input("Bandeira até 150 kWh", value=0.054400, format="%.6f"),
    "acima_150": st.sidebar.number_input("Bandeira acima 150 kWh", value=0.057660, format="%.6f"),
}

st.sidebar.header("📊 Método de rateio")
metodo_rateio = st.sidebar.radio("Escolha o método:", ["Proporcional ao total da fatura", "Faixas individuais"])

st.sidebar.header("📏 Fonte do consumo total")
fonte_consumo = st.sidebar.radio("Definir consumo total por:", ["Leituras do prédio", "Soma das quitinetes"])

# ===================== FUNÇÕES DE CÁLCULO =====================
def calcular_valor_base(consumo_kwh: float) -> float:
    c1 = min(consumo_kwh, 150.0)
    c2 = max(consumo_kwh - 150.0, 0.0)
    te = c1 * tarifas["te_ate_150"] + c2 * tarifas["te_acima_150"]
    tusd = c1 * tarifas["tusd_ate_150"] + c2 * tarifas["tusd_acima_150"]
    bandeira = (
        c1 * bandeira_por_faixa["ate_150"] + c2 * bandeira_por_faixa["acima_150"]
        if usar_bandeira_por_faixa else consumo_kwh * bandeira_valor_unico
    )
    return round(te + tusd + bandeira, 2)

def calcular_fatura_total(consumo_total_kwh: float) -> tuple[float, float]:
    valor_base = calcular_valor_base(consumo_total_kwh)
    total = round(valor_base + cosip, 2)
    return total, valor_base

def adicionar_historico(nome_simulacao: str, df: pd.DataFrame, valor_total: float, consumo_total: float) -> None:
    linha = df.copy()
    linha["Identificação"] = nome_simulacao
    linha["Consumo Total"] = consumo_total
    linha["Valor Total"] = valor_total
    st.session_state.historico = pd.concat([st.session_state.historico, linha.reset_index()], ignore_index=True)

# ===================== INTERFACE PRINCIPAL =====================
st.header("🔢 Leituras do prédio")
col1, col2 = st.columns(2)
with col1:
    leitura_predio_ant = st.number_input("Leitura anterior do prédio (kWh)", min_value=0, step=1)
with col2:
    leitura_predio_at = st.number_input("Leitura atual do prédio (kWh)", min_value=0, step=1)

hora_local = datetime.now(ZoneInfo("America/Sao_Paulo"))
nome_simulacao = st.text_input("Identificação da simulação", value=hora_local.strftime("%d/%m/%Y %H:%M"))

st.header("🏠 Leituras das quitinetes")
n = st.slider("Número de quitinetes", 1, 5, value=1)
consumos_individuais = []
nomes_inquilinos = []

for i in range(n):
    with st.expander(f"Quitinete {i+1}", expanded=True):
        nome = st.text_input(f"Nome do inquilino Q{i+1}", key=f"nome_{i}")
        nomes_inquilinos.append(nome.strip() if nome.strip() else f"Q{i+1}")

        c1col, c2col = st.columns(2)
        with c1col:
            leitura_ant_default = 0
            if st.session_state.prev_map and nomes_inquilinos[i] in st.session_state.prev_map:
                try:
                    leitura_ant_default = int(float(st.session_state.prev_map[nomes_inquil
