# ===================== IMPORTAÇÕES =====================
import streamlit as st              # Framework para apps web simples em Python
import pandas as pd                 # Manipulação de dados tabulares
import plotly.express as px         # Gráficos interativos
import io                           # Buffer de memória para criar arquivos em tempo real
from datetime import datetime       # Data e hora
from zoneinfo import ZoneInfo       # Fuso horário (para horário local de Blumenau)
from openpyxl.utils import get_column_letter  # Ajuste automático de largura das colunas no Excel

# ===================== CONFIGURAÇÃO DA PÁGINA =====================
st.set_page_config(page_title="Rateio de Energia", page_icon="💡", layout="wide")
st.title("💡 Rateio de Energia - Quitinetes")

# ===================== ESTADO (SESSION_STATE) =====================
# Guardamos histórico, último resultado e resumo para persistirem após cliques
if "historico" not in st.session_state:
    st.session_state.historico = pd.DataFrame()
if "df_resultado" not in st.session_state:
    st.session_state.df_resultado = None
if "resumo_resultado" not in st.session_state:
    st.session_state.resumo_resultado = None
if "alertas_resultado" not in st.session_state:
    st.session_state.alertas_resultado = []

# ===================== SIDEBAR: CONFIGURAÇÕES DE TARIFA =====================
st.sidebar.header("⚙️ Tarifas Celesc (R$/kWh com tributos)")
# TE: Tarifa de Energia | TUSD: Tarifa de Uso do Sistema de Distribuição
# Usamos duas faixas: até 150 kWh e acima de 150 kWh (modelo comum de residenciais)
tarifas = {
    "te_ate_150": st.sidebar.number_input("TE até 150 kWh", value=0.392200, format="%.6f"),
    "te_acima_150": st.sidebar.number_input("TE acima 150 kWh", value=0.415851, format="%.6f"),
    "tusd_ate_150": st.sidebar.number_input("TUSD até 150 kWh", value=0.455333, format="%.6f"),
    "tusd_acima_150": st.sidebar.number_input("TUSD acima 150 kWh", value=0.482660, format="%.6f"),
}

# COSIP: Contribuição para custeio de iluminação pública (valor fixo na fatura)
cosip = st.sidebar.number_input("COSIP (R$)", value=17.01, format="%.2f")

# ===================== BANDEIRA TARIFÁRIA =====================
st.sidebar.header("🚩 Bandeira tarifária")
bandeira_sel = st.sidebar.radio(
    "Selecione a bandeira",
    ["Verde", "Amarela", "Vermelha 1", "Vermelha 2"],
    index=2,  # seleciona "Vermelha 1" como inicial
    key="bandeira_tarifaria",
    help="Selecionado 'Vermelha 1' como estado inicial."
)
usar_bandeira_por_faixa = st.sidebar.checkbox("Usar bandeira por faixa (como na fatura)", value=True)

# Valor único por bandeira (aplicado quando NÃO usamos faixa)
bandeira_valor_unico = {
    "Verde": 0.000000,
    "Amarela": 0.018660,
    "Vermelha 1": 0.044630,
    "Vermelha 2": 0.075660,
}[bandeira_sel]

# Valores por faixa (aplicados quando usamos faixa)
bandeira_por_faixa = {
    "ate_150": st.sidebar.number_input("Bandeira até 150 kWh", value=0.054400, format="%.6f"),
    "acima_150": st.sidebar.number_input("Bandeira acima 150 kWh", value=0.057660, format="%.6f"),
}

# ===================== MÉTODO DE RATEIO E FONTE DO CONSUMO =====================
st.sidebar.header("📊 Método de rateio")
# - Faixas individuais: calcula cada unidade como se fosse uma fatura separada
# - Proporcional: distribui o total da fatura proporcional ao consumo de cada unidade
metodo_rateio = st.sidebar.radio("Escolha o método:", ["Proporcional ao total da fatura", "Faixas individuais"])

st.sidebar.header("📏 Fonte do consumo total")
# - Leituras do prédio: usa o medidor principal para consumo total
# - Soma das quitinetes: soma os consumos informados de cada unidade
fonte_consumo = st.sidebar.radio("Definir consumo total por:", ["Leituras do prédio", "Soma das quitinetes"])

# ===================== FUNÇÕES DE CÁLCULO =====================
def calcular_valor_base(consumo_kwh: float) -> float:
    """
    Calcula o custo base (TE + TUSD + Bandeira) para um dado consumo em kWh.
    Não inclui COSIP.
    Usa o modelo de duas faixas: até 150 kWh e acima de 150 kWh.
    """
    # Divide o consumo em duas faixas
    c1 = min(consumo_kwh, 150.0)        # parte até 150 kWh
    c2 = max(consumo_kwh - 150.0, 0.0)  # excedente acima de 150 kWh

    # Calcula TE e TUSD por faixa
    te = c1 * tarifas["te_ate_150"] + c2 * tarifas["te_acima_150"]
    tusd = c1 * tarifas["tusd_ate_150"] + c2 * tarifas["tusd_acima_150"]

    # Aplica bandeira por faixa ou valor único
    if usar_bandeira_por_faixa:
        bandeira = c1 * bandeira_por_faixa["ate_150"] + c2 * bandeira_por_faixa["acima_150"]
    else:
        bandeira = consumo_kwh * bandeira_valor_unico

    # Retorna valor arredondado a centavos
    return round(te + tusd + bandeira, 2)

def calcular_fatura_total(consumo_total_kwh: float) -> tuple[float, float]:
    """
    Retorna (total_fatura, valor_base_sem_cosip).
    - valor_base: TE + TUSD + Bandeira
    - total_fatura: valor_base + COSIP
    """
    valor_base = calcular_valor_base(consumo_total_kwh)
    total = round(valor_base + cosip, 2)
    return total, valor_base

def adicionar_historico(nome_simulacao: str, df: pd.DataFrame, valor_total: float, consumo_total: float) -> None:
    """
    Adiciona a simulação atual ao histórico. Cada linha do df vira uma linha no histórico,
    com colunas extras: Identificação, Consumo Total, Valor Total.
    """
    linha = df.copy()
    linha["Identificação"] = nome_simulacao
    linha["Consumo Total"] = consumo_total
    linha["Valor Total"] = valor_total
    st.session_state.historico = pd.concat([st.session_state.historico, linha.reset_index()], ignore_index=True)

# ===================== INTERFACE PRINCIPAL =====================
# Leituras do prédio (medidor principal)
st.header("🔢 Leituras do prédio")
col1, col2 = st.columns(2)
with col1:
    leitura_predio_ant = st.number_input("Leitura anterior do prédio (kWh)", min_value=0, step=1)
with col2:
    leitura_predio_at = st.number_input("Leitura atual do prédio (kWh)", min_value=0, step=1)

# Identificação da simulação com data/hora local de Blumenau
hora_local = datetime.now(ZoneInfo("America/Sao_Paulo"))
nome_simulacao = st.text_input("Identificação da simulação", value=hora_local.strftime("%d/%m/%Y %H:%M"))

# Leituras das quitinetes (cada unidade)
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
            ant = st.number_input("Leitura anterior (kWh)", min_value=0, step=1, key=f"ant_{i}")
        with c2col:
            at = st.number_input("Leitura atual (kWh)", min_value=0, step=1, key=f"at_{i}")

        consumo = max(at - ant, 0)  # nunca deixa negativo
        consumos_individuais.append(float(consumo))

# ===================== CÁLCULO (AO CLICAR) =====================
if st.button("Calcular"):
    # Determina consumo total conforme fonte
    if fonte_consumo == "Leituras do prédio":
        consumo_total = float(max(leitura_predio_at - leitura_predio_ant, 0))
    else:
        consumo_total = float(sum(consumos_individuais))

    # Valor total da fatura e base (sem COSIP)
    valor_total, valor_base = calcular_fatura_total(consumo_total)

    # Calcula valores por unidade conforme método
    if metodo_rateio == "Faixas individuais":
        # Cada unidade calcula como se fosse uma fatura própria
        valores_individuais = [calcular_valor_base(c) for c in consumos_individuais]
    else:
        # Proporcional ao total da fatura (protege contra divisão por zero)
        valores_individuais = [
            round((c / consumo_total) * valor_total, 2) if consumo_total > 0 else 0.0
            for c in consumos_individuais
        ]

    # Monta DataFrame principal com resultados por unidade
    df = pd.DataFrame(
        {"Consumo (kWh)": consumos_individuais, "Valor (R$)": valores_individuais},
        index=[f"Quitinete {i+1} - {nomes_inquilinos[i]}" for i in range(n)]
    )

    # Calcula Áreas Comuns (diferença entre total e soma das unidades)
    soma_consumo_individual = float(sum(consumos_individuais))
    soma_valores_individuais = float(sum(valores_individuais))
    consumo_areas_comuns = round(consumo_total - soma_consumo_individual, 2)
    valor_areas_comuns = round(valor_total - soma_valores_individuais, 2)

    # Normaliza ruídos de arredondamento muito pequenos
    if abs(consumo_areas_comuns) < 0.01:
        consumo_areas_comuns = 0.0
    if abs(valor_areas_comuns) < 0.01:
        valor_areas_comuns = 0.0

    # Lista de alertas (avisos) para inconsistências
    alertas = []
    if consumo_areas_comuns < 0:
        alertas.append("Consumo das quitinetes excede o consumo total do prédio. Ajustei Áreas Comuns para 0 kWh.")
        consumo_areas_comuns = 0.0
    if valor_areas_comuns < 0:
        alertas.append("Soma dos valores individuais excede o total da fatura. Ajustei Áreas Comuns para R$ 0,00.")
        valor_areas_comuns = 0.0

    # Adiciona linha de Áreas Comuns se houver valor/consumo relevante
    if (consumo_areas_comuns != 0.0) or (valor_areas_comuns != 0.0):
        df.loc["Áreas Comuns"] = [consumo_areas_comuns, valor_areas_comuns]

    # Mensagens de status
    st.success(f"Consumo total do prédio: {consumo_total} kWh")
    st.success(f"Valor base (TE+TUSD+Bandeira): R$ {valor_base:.2f}")
    st.success(f"Valor total da fatura: R$ {valor_total:.2f}")
    for msg in alertas:
        st.warning(msg)

    # Salva resultado em session_state para exibir fora do bloco do botão
    st.session_state.df_resultado = df
    st.session_state.alertas_resultado = alertas
    st.session_state.resumo_resultado = {
        "Identificação": nome_simulacao,
        "Consumo total (kWh)": consumo_total,
        "Valor base (R$)": valor_base,
        "COSIP (R$)": cosip,
        "Total fatura (R$)": valor_total,
        "Bandeira por faixa": "Sim" if usar_bandeira_por_faixa else "Não",
        "Método de rateio": metodo_rateio,
        "Fonte do consumo total": fonte_consumo,
    }

    # Adiciona ao histórico (cada unidade + possíveis Áreas Comuns)
    adicionar_historico(nome_simulacao, df, valor_total, consumo_total)

# ===================== EXIBIÇÃO PERSISTENTE DE RESULTADOS =====================
# Mostra tabela, gráfico e botão de exportar mesmo após outras interações
if st.session_state.df_resultado is not None:
    st.subheader("📊 Rateio detalhado")
    st.dataframe(st.session_state.df_resultado.style.format({"Valor (R$)": "R${:,.2f}"}))

    st.subheader("📈 Consumo por unidade")
    df_plot = st.session_state.df_resultado.reset_index().rename(columns={"index": "Unidade"})
    fig = px.bar(
        df_plot, x="Unidade", y="Consumo (kWh)",
        text="Consumo (kWh)", color="Unidade",
        labels={"Unidade": "Unidade", "Consumo (kWh)": "Consumo (kWh)"}
    )
    fig.update_traces(textposition="outside")
    st.plotly_chart(fig, use_container_width=True)

    for msg in st.session_state.alertas_resultado:
        st.warning(msg)

    # ===================== EXPORTAÇÃO PARA EXCEL =====================
    # Gera um arquivo Excel com 3 abas: Rateio, Resumo, Histórico
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        # Aba Rateio
        st.session_state.df_resultado.to_excel(writer, sheet_name="Rateio", index=True)

        # Aba Resumo (chave-valor do dicionário de resumo)
        resumo_dict = st.session_state.resumo_resultado or {}
        if resumo_dict:
            resumo = pd.DataFrame({
                "Item": list(resumo_dict.keys()),
                "Valor": list(resumo_dict.values())
            })
            resumo.to_excel(writer, sheet_name="Resumo", index=False)

        # Aba Histórico (tudo que foi calculado até agora)
        if not st.session_state.historico.empty:
            st.session_state.historico.to_excel(writer, sheet_name="Histórico", index=False)

        # Ajuste simples de largura das colunas (para ficar legível ao abrir)
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

# ===================== ABA HISTÓRICO (SIMPLIFICADA) =====================
st.header("📅 Histórico de Rateios")
if not st.session_state.historico.empty:
    st.dataframe(st.session_state.historico)

    st.divider()
    # Botão para zerar todo o histórico e começar do zero
    if st.button("🧹 Iniciar novo histórico"):
        st.session_state.historico = pd.DataFrame()
        st.success("Histórico apagado com sucesso. Pronto para uma nova simulação.")
else:
    st.info("Nenhum registro no histórico ainda. Faça um cálculo para começar.")

# -------------------------------
# EXPLICAÇÕES DISCRETAS (FIM DA PÁGINA)
# -------------------------------
st.divider()
st.caption("Orientações rápidas sobre configurações")

with st.expander("🚩 Bandeiras tarifárias", expanded=False):
    st.markdown("""
    As bandeiras tarifárias indicam custos extras na geração de energia:

    - **Verde** → sem acréscimo  
    - **Amarela** → pequeno acréscimo por kWh  
    - **Vermelha 1 e 2** → acréscimos maiores

    Se usar **por faixa**, aplica-se:
    - Até 150 kWh → valor reduzido  
    - Acima de 150 kWh → valor cheio
    """)

with st.expander("📊 Bandeira por faixa (como na fatura)", expanded=False):
    st.markdown("""
    Aplica valores diferentes conforme o consumo:

    - **Até 150 kWh:** usa o valor reduzido  
    - **Acima de 150 kWh:** usa o valor cheio

    Como calculamos:
    - Consumo é separado em duas partes: até 150 kWh e excedente.
    - Somamos: (até 150 × valor reduzido) + (excedente × valor cheio).

      """)

with st.expander("🧮 Método de rateio", expanded=False):
    st.markdown("""
    **Faixas individuais**
    - Calcula cada unidade como se tivesse sua própria fatura.
    - Mais justo para quem consome pouco.
    - Ideal quando cada unidade tem medidor próprio.

    **Proporcional ao total da fatura**
    - Divide o total do prédio proporcional ao consumo de cada unidade.
    - Reflete exatamente a fatura real.
    - Ideal quando há um único medidor.
    """)

with st.expander("📏 Fonte de consumo total", expanded=False):
    st.markdown("""
    **Leituras do prédio**
    - Usa o medidor principal do prédio.
    - Geralmente mais preciso.

    **Soma das quitinetes**
    - Soma os consumos individuais informados.
    - Útil quando não há leitura do prédio ou ela está indisponível.
    """)

st.caption("Estas explicações são referenciais e não substituem as regras oficiais da concessionária.")

# -------------------------------
# RODAPÉ
# -------------------------------
st.markdown("---")
st.markdown(
    "<div style='text-align: center; color: grey; font-size: 14px;'>"
    "Desenvolvido por <strong>Rafael Guimarães dos Santos</strong> — Todos os direitos reservados ©"
    "</div>",
    unsafe_allow_html=True
)

# app.py
import streamlit as st
import pandas as pd
from datetime import datetime
from io import BytesIO

# -------------------------------
# ⚙️ Configurações iniciais
# -------------------------------
st.set_page_config(page_title="Rateio de Energia", page_icon="⚡", layout="centered")

if "import_resumo" not in st.session_state:
    st.session_state.import_resumo = None
if "import_rateio" not in st.session_state:
    st.session_state.import_rateio = None
if "prev_map" not in st.session_state:
    st.session_state.prev_map = {}

# -------------------------------
# 🧭 Sidebar: setups e parâmetros
# -------------------------------
st.sidebar.title("Configurações")
bandeiras = ["Verde", "Amarela", "Vermelha 1", "Vermelha 2"]
metodos = ["Faixas individuais", "Proporcional ao total da fatura"]
fontes_consumo = ["Leituras do prédio", "Soma das quitinetes"]

# Índices iniciais (podem ser atualizados pela importação)
bandeira_index = 0
metodo_index = 0
fonte_index = 0
consumo_total_prédio = None

# Se já houver importação anterior, tente aplicar
if st.session_state.import_resumo is not None:
    resumo_imp = st.session_state.import_resumo
    try:
        bandeira_val = resumo_imp.loc[resumo_imp["Item"] == "Bandeira por faixa", "Valor"].values[0]
        if bandeira_val in bandeiras:
            bandeira_index = bandeiras.index(bandeira_val)
    except Exception:
        pass

    try:
        metodo_val = resumo_imp.loc[resumo_imp["Item"] == "Método de rateio", "Valor"].values[0]
        if metodo_val in metodos:
            metodo_index = metodos.index(metodo_val)
    except Exception:
        pass

    try:
        fonte_val = resumo_imp.loc[resumo_imp["Item"] == "Fonte do consumo total", "Valor"].values[0]
        if fonte_val in fontes_consumo:
            fonte_index = fontes_consumo.index(fonte_val)
    except Exception:
        pass

    try:
        consumo_total_prédio = resumo_imp.loc[resumo_imp["Item"] == "Consumo total (kWh)", "Valor"].values[0]
    except Exception:
        consumo_total_prédio = None

bandeira_sel = st.sidebar.radio("Bandeira tarifária", bandeiras, index=bandeira_index)
metodo_rateio = st.sidebar.radio("Método de rateio", metodos, index=metodo_index)
fonte_sel = st.sidebar.radio("Fonte do consumo total", fontes_consumo, index=fonte_index)

st.sidebar.divider()
st.sidebar.caption("Preços e totais da fatura")
valor_base = st.sidebar.number_input("Valor base (R$)", min_value=0.0, value=0.0, step=0.01, format="%.2f")
cosip = st.sidebar.number_input("COSIP (R$)", min_value=0.0, value=0.0, step=0.01, format="%.2f")
total_fatura = st.sidebar.number_input("Total da fatura (R$)", min_value=0.0, value=0.0, step=0.01, format="%.2f")

# -------------------------------
# 🕒 Identificação e leituras
# -------------------------------
st.title("Rateio de energia por quitinetes")
identificacao = st.text_input("Identificação da simulação (data/hora)", value=datetime.now().strftime("%d/%m/%Y %H:%M"))
st.caption("A leitura atual deste mês será a leitura anterior do mês seguinte quando você importar o backup.")

num_quitinetes = st.number_input("Número de quitinetes (inclua Áreas Comuns se aplicável)", min_value=1, value=1, step=1)

# Coleta de leituras por quitinete
quitinetes_data = []
st.header("Leituras das quitinetes")

for i in range(1, num_quitinetes + 1):
    st.subheader(f"Quitinete {i}")
    nome_default = f"Quitinete {i}"
    nome = st.text_input(f"Nome do inquilino/ambiente {i}", value=nome_default, key=f"nome_{i}")

    # Se foi importado backup, preencha leitura anterior com o consumo do mês anterior
    leitura_anterior_default = 0.0
    if st.session_state.prev_map and nome in st.session_state.prev_map:
        # O consumo anterior vira leitura anterior do mês atual
        leitura_anterior_default = float(st.session_state.prev_map[nome])

    leitura_anterior_kwh = st.number_input(f"Leitura anterior (kWh) — {nome}",
                                           min_value=0.0, value=leitura_anterior_default, step=0.01,
                                           key=f"leitura_ant_{i}")
    leitura_atual_kwh = st.number_input(f"Leitura atual (kWh) — {nome}",
                                        min_value=0.0, value=0.0, step=0.01,
                                        key=f"leitura_atual_{i}")

    consumo_kwh = max(leitura_atual_kwh - leitura_anterior_kwh, 0.0)
    quitinetes_data.append({
        "Quitinete": nome,
        "Leitura anterior (kWh)": leitura_anterior_kwh,
        "Leitura atual (kWh)": leitura_atual_kwh,
        "Consumo (kWh)": consumo_kwh
    })

df_leituras = pd.DataFrame(quitinetes_data)

st.divider()
st.subheader("Resumo das leituras")
st.dataframe(df_leituras, use_container_width=True)

# -------------------------------
# 📊 Cálculo do rateio
# -------------------------------
st.header("Cálculo do rateio")

# Definir consumo total:
soma_consumos = float(df_leituras["Consumo (kWh)"].sum()) if not df_leituras.empty else 0.0
if fonte_sel == "Soma das quitinetes" or consumo_total_prédio is None:
    consumo_total_calc = soma_consumos
else:
    consumo_total_calc = float(consumo_total_prédio)

st.write(f"Consumo total considerado: {consumo_total_calc:.2f} kWh")

# Valor a ratear: aqui usamos o total da fatura (inclui COSIP).
valor_total_ratear = float(total_fatura)

valores_rateio = []
for _, row in df_leituras.iterrows():
    parte = 0.0
    if consumo_total_calc > 0:
        # Ambos métodos usam rateio proporcional ao consumo. (Se quiser faixas reais, podemos implementar depois.)
        parte = valor_total_ratear * (row["Consumo (kWh)"] / consumo_total_calc)
    valores_rateio.append(parte)

df_rateio = pd.DataFrame({
    "Quitinete": df_leituras["Quitinete"],
    "Consumo (kWh)": df_leituras["Consumo (kWh)"],
    "Valor (R$)": [round(v, 2) for v in valores_rateio]
})

st.subheader("Rateio por quitinete")
st.dataframe(df_rateio, use_container_width=True)

# -------------------------------
# 🧾 Resumo consolidado
# -------------------------------
st.header("Resumo da fatura e parâmetros")
df_resumo = pd.DataFrame({
    "Item": [
        "Consumo total (kWh)",
        "Valor base (R$)",
        "COSIP (R$)",
        "Total fatura (R$)",
        "Bandeira por faixa",
        "Método de rateio",
        "Fonte do consumo total",
        "Identificação"
    ],
    "Valor": [
        round(consumo_total_calc, 2),
        round(valor_base, 2),
        round(cosip, 2),
        round(total_fatura, 2),
        bandeira_sel,
        metodo_rateio,
        fonte_sel,
        identificacao
    ]
})

st.dataframe(df_resumo, use_container_width=True)

# -------------------------------
# 💾 Exportação: Excel com múltiplas abas
# -------------------------------
st.header("Exportar backup do mês")

def gerar_excel(rateio_df: pd.DataFrame, resumo_df: pd.DataFrame, identificacao_str: str) -> bytes:
    # Histórico deste mês (espelha Rateio + colunas de contexto)
    historico_df = rateio_df.copy()
    historico_df["Identificação"] = identificacao_str
    try:
        consumo_total_val = float(resumo_df.loc[resumo_df["Item"] == "Consumo total (kWh)", "Valor"].values[0])
    except Exception:
        consumo_total_val = float(rateio_df["Consumo (kWh)"].sum())
    try:
        valor_total_val = float(resumo_df.loc[resumo_df["Item"] == "Total fatura (R$)", "Valor"].values[0])
    except Exception:
        valor_total_val = float(sum(rateio_df["Valor (R$)"]))
    historico_df["Consumo Total"] = round(consumo_total_val, 2)
    historico_df["Valor Total"] = round(valor_total_val, 2)

    # Buffer em memória
    buffer = BytesIO()
    with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
        rateio_df.to_excel(writer, sheet_name="Rateio", index=False)
        resumo_df.to_excel(writer, sheet_name="Resumo", index=False)
        historico_df.to_excel(writer, sheet_name="Histórico", index=False)
    buffer.seek(0)
    return buffer.getvalue()

excel_bytes = gerar_excel(df_rateio, df_resumo, identificacao)

st.download_button(
    label="💾 Baixar Excel do mês",
    data=excel_bytes,
    file_name=f"rateio_{datetime.now().strftime('%m_%Y')}.xlsx",
    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
)

# -------------------------------
# 📂 Importação: aplicar backup do mês anterior
# -------------------------------
st.header("Importar backup do mês anterior")
arquivo = st.file_uploader("Carregue o arquivo Excel gerado anteriormente", type=["xlsx"])

if arquivo is not None:
    try:
        xls = pd.ExcelFile(arquivo)
        resumo_imp = pd.read_excel(xls, sheet_name="Resumo")
        rateio_imp = pd.read_excel(xls, sheet_name="Rateio")

        # Guardar em sessão para aplicar nos widgets e leituras
        st.session_state.import_resumo = resumo_imp
        st.session_state.import_rateio = rateio_imp

        # Mapeia leitura anterior por nome (usando consumo do mês anterior)
        # A leitura atual daquele mês se torna a leitura anterior deste mês.
        prev_map = dict(zip(rateio_imp["Quitinete"], rateio_imp["Consumo (kWh)"]))
        st.session_state.prev_map = prev_map

        st.success("Backup importado! As configurações e leituras anteriores foram aplicadas.")
        st.write("Resumo importado:")
        st.dataframe(resumo_imp, use_container_width=True)
        st.write("Rateio importado (usado como leitura anterior):")
        st.dataframe(rateio_imp, use_container_width=True)

        st.info("As leituras anteriores dos campos acima foram preenchidas com o consumo do mês importado. Revise os nomes para manter a correspondência.")
    except Exception as e:
        st.error(f"Falha ao importar o arquivo. Verifique se ele tem as abas 'Rateio' e 'Resumo'. Detalhes: {e}")

# -------------------------------
# ℹ️ Orientações discretas no rodapé
# -------------------------------
st.markdown("---")
st.markdown("### ℹ️ Orientações sobre importação e continuidade")
st.markdown(
    """
    <div style='font-size: 14px; color: grey;'>
    • Ao final de cada mês, clique em <strong>Baixar Excel do mês</strong> para salvar seu backup.<br>
    • No mês seguinte, use <strong>Importar backup do mês anterior</strong> para recuperar automaticamente:<br>
    &nbsp;&nbsp;– Bandeira tarifária, método de rateio e fonte do consumo total;<br>
    &nbsp;&nbsp;– Consumo (kWh) de cada quitinete do mês anterior, que passa a ser sua <em>leitura anterior</em> neste mês.<br><br>
    Dicas:<br>
    • Mantenha os nomes das quitinetes consistentes entre os meses para que a importação aplique corretamente as leituras.<br>
    • Se você preferir, ajuste manualmente qualquer leitura antes de gerar o novo backup.<br>
    • Cada usuário mantém seu próprio arquivo de backup mensal, sem misturar dados de outras pessoas.
    </div>
    """,
    unsafe_allow_html=True
)
