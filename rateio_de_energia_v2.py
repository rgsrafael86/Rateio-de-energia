import streamlit as st
import pandas as pd
import plotly.express as px
import io
from datetime import datetime
from zoneinfo import ZoneInfo
from openpyxl.utils import get_column_letter

# Configuração inicial
st.set_page_config(page_title="Rateio de Energia", page_icon="💡", layout="wide")
st.title("💡 Rateio de Energia - Quitinetes")

# Estado: histórico
if "historico" not in st.session_state:
    st.session_state.historico = pd.DataFrame()

# ---------------- Sidebar: Tarifas e configurações ----------------
st.sidebar.header("⚙️ Tarifas Celesc (R$/kWh com tributos)")
tarifas = {
    "te_ate_150": st.sidebar.number_input("TE até 150 kWh", value=0.392200, format="%.6f"),
    "te_acima_150": st.sidebar.number_input("TE acima 150 kWh", value=0.415851, format="%.6f"),
    "tusd_ate_150": st.sidebar.number_input("TUSD até 150 kWh", value=0.455333, format="%.6f"),
    "tusd_acima_150": st.sidebar.number_input("TUSD acima 150 kWh", value=0.482660, format="%.6f"),
}

st.sidebar.header("🚩 Bandeira tarifária")
bandeira_sel = st.sidebar.radio("Selecione a bandeira", ["Verde", "Amarela", "Vermelha 1", "Vermelha 2"])
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

cosip = st.sidebar.number_input("COSIP (R$)", value=17.01, format="%.2f")

st.sidebar.header("📊 Método de rateio")
metodo_rateio = st.sidebar.radio("Escolha o método:", ["Faixas individuais", "Proporcional ao total da fatura"])

st.sidebar.header("📏 Fonte do consumo total")
fonte_consumo = st.sidebar.radio("Definir consumo total por:", ["Leituras do prédio", "Soma das quitinetes"])

# ---------------- Funções de cálculo ----------------
def calcular_valor_base(consumo_kwh: float) -> float:
    """Calcula TE + TUSD + Bandeira (sem COSIP), com faixas e bandeira conforme configuração."""
    c1 = min(consumo_kwh, 150.0)
    c2 = max(consumo_kwh - 150.0, 0.0)

    te = c1 * tarifas["te_ate_150"] + c2 * tarifas["te_acima_150"]
    tusd = c1 * tarifas["tusd_ate_150"] + c2 * tarifas["tusd_acima_150"]

    if usar_bandeira_por_faixa:
        band = c1 * bandeira_por_faixa["ate_150"] + c2 * bandeira_por_faixa["acima_150"]
    else:
        band = consumo_kwh * bandeira_valor_unico

    return round(te + tusd + band, 2)

def calcular_fatura_total(consumo_total_kwh: float) -> tuple[float, float]:
    """Retorna (total_fatura, valor_base_sem_cosip)."""
    valor_base = calcular_valor_base(consumo_total_kwh)
    total = round(valor_base + cosip, 2)
    return total, valor_base

def adicionar_historico(nome_simulacao: str, df: pd.DataFrame, valor_total: float, consumo_total: float) -> None:
    linha = df.copy()
    linha["Identificação"] = nome_simulacao
    linha["Consumo Total"] = consumo_total
    linha["Valor Total"] = valor_total
    st.session_state.historico = pd.concat([st.session_state.historico, linha.reset_index()], ignore_index=True)

# ---------------- Interface: Leituras do prédio ----------------
st.header("🔢 Leituras do prédio")
col1, col2 = st.columns(2)
with col1:
    leitura_predio_ant = st.number_input("Leitura anterior do prédio (kWh)", min_value=0, step=1)
with col2:
    leitura_predio_at = st.number_input("Leitura atual do prédio (kWh)", min_value=0, step=1)

# Identificador com horário local
hora_local = datetime.now(ZoneInfo("America/Sao_Paulo"))
nome_simulacao = st.text_input("Identificação da simulação", value=hora_local.strftime("%d/%m/%Y %H:%M"))

# ---------------- Interface: Quitinetes ----------------
st.header("🏠 Leituras das quitinetes")
n = st.slider("Número de quitinetes", 1, 20, value=2)
consumos_individuais: list[float] = []
nomes_inquilinos: list[str] = []

for i in range(n):
    with st.expander(f"Quitinete {i+1}", expanded=True):
        nome = st.text_input(f"Nome do inquilino Q{i+1}", key=f"nome_{i}")
        nomes_inquilinos.append(nome.strip() if nome.strip() else f"Q{i+1}")

        c1, c2 = st.columns(2)
        with c1:
            ant = st.number_input("Leitura anterior (kWh)", min_value=0, step=1, key=f"ant_{i}")
        with c2:
            at = st.number_input("Leitura atual (kWh)", min_value=0, step=1, key=f"at_{i}")

        consumo = max(at - ant, 0)
        consumos_individuais.append(float(consumo))

# ---------------- Ação: Calcular ----------------
if st.button("Calcular"):
    # Consumo total conforme fonte
    if fonte_consumo == "Leituras do prédio":
        consumo_total = float(max(leitura_predio_at - leitura_predio_ant, 0))
    else:
        consumo_total = float(sum(consumos_individuais))

    valor_total, valor_base = calcular_fatura_total(consumo_total)

    # Rateio
    if metodo_rateio == "Faixas individuais":
        valores_individuais = [calcular_valor_base(c) for c in consumos_individuais]
    else:
        # Proporcional ao total da fatura (proteção para total zero)
        if consumo_total > 0:
            valores_individuais = [round((c / consumo_total) * valor_total, 2) for c in consumos_individuais]
        else:
            valores_individuais = [0.0 for _ in consumos_individuais]

    # DataFrame base
    df = pd.DataFrame(
        {"Consumo (kWh)": consumos_individuais, "Valor (R$)": valores_individuais},
        index=[f"Quitinete {i+1} - {nomes_inquilinos[i]}" for i in range(n)]
    )

    # Áreas Comuns: consumo e valor com proteções
    soma_consumo_individual = float(sum(consumos_individuais))
    soma_valores_individuais = float(sum(valores_individuais))

    consumo_areas_comuns = round(consumo_total - soma_consumo_individual, 2)
    valor_areas_comuns = round(valor_total - soma_valores_individuais, 2)

    # Normaliza ruídos de arredondamento
    if abs(consumo_areas_comuns) < 0.01:
        consumo_areas_comuns = 0.0
    if abs(valor_areas_comuns) < 0.01:
        valor_areas_comuns = 0.0

    alertas = []
    # Corrige inconsistências negativas
    if consumo_areas_comuns < 0:
        alertas.append("Consumo das quitinetes excede o consumo total do prédio. Ajustei Áreas Comuns para 0 kWh.")
        consumo_areas_comuns = 0.0
    if valor_areas_comuns < 0:
        alertas.append("Soma dos valores individuais excede o total da fatura. Ajustei Áreas Comuns para R$ 0,00.")
        valor_areas_comuns = 0.0

    # Adiciona Áreas Comuns se relevante
    if (consumo_areas_comuns != 0.0) or (valor_areas_comuns != 0.0):
        df.loc["Áreas Comuns"] = [consumo_areas_comuns, valor_areas_comuns]

    # Exibe totais e alertas
    st.success(f"Consumo total do prédio: {consumo_total} kWh")
    st.success(f"Valor base (TE+TUSD+Bandeira): R$ {valor_base:.2f}")
    st.success(f"Valor total da fatura: R$ {valor_total:.2f}")
    for msg in alertas:
        st.warning(msg)

    # Tabela
    st.subheader("📊 Rateio detalhado")
    st.dataframe(df.style.format({"Valor (R$)": "R${:,.2f}"}))

    # Gráfico
    st.subheader("📈 Consumo por unidade")
    df_plot = df.reset_index().rename(columns={"index": "Unidade"})
    fig = px.bar(
        df_plot, x="Unidade", y="Consumo (kWh)",
        text="Consumo (kWh)", color="Unidade",
        labels={"Unidade": "Unidade", "Consumo (kWh)": "Consumo (kWh)"}
    )
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)

    # Histórico
    adicionar_historico(nome_simulacao, df, valor_total, consumo_total)

    # Exportação Excel
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        # Aba Rateio
        df.to_excel(writer, sheet_name="Rateio", index=True)

        # Aba Resumo
        resumo = pd.DataFrame({
            "Item": [
                "Consumo total (kWh)",
                "Valor base (R$)",
                "COSIP (R$)",
                "Total fatura (R$)",
                "Bandeira por faixa",
                "Método de rateio",
                "Fonte do consumo total"
            ],
            "Valor": [
                consumo_total,
                valor_base,
                cosip,
                valor_total,
                "Sim" if usar_bandeira_por_faixa else "Não",
                metodo_rateio,
                fonte_consumo
            ]
        })
        resumo.to_excel(writer, sheet_name="Resumo", index=False)

        # Aba Histórico
        if not st.session_state.historico.empty:
            st.session_state.historico.to_excel(writer, sheet_name="Histórico", index=False)

        # Ajuste simples de largura das colunas
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

# ---------------- Histórico ----------------
if not st.session_state.historico.empty:
    st.header("📅 Histórico de Rateios")

    historico = st.session_state.historico.copy()
    historico.index.name = "Index"
    historico.reset_index(inplace=True)

    # Seleção de linhas
    linhas_selecionadas = st.multiselect(
        "Selecione os registros que deseja excluir:",
        options=historico["Index"].tolist(),
        format_func=lambda x: f"{historico.loc[x, 'Identificação']} — {historico.loc[x, 'Consumo Total']} kWh"
    )

    if linhas_selecionadas and st.button("🗑️ Excluir selecionados"):
        st.session_state.historico = historico[~historico["Index"].isin(linhas_selecionadas)].drop(columns=["Index"])
        st.success(f"{len(linhas_selecionadas)} registro(s) excluído(s) com sucesso.")

    st.dataframe(historico.drop(columns=["Index"]))
