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
if "prev_map" not in st.session_state:
    st.session_state.prev_map = {}
if "import_resumo" not in st.session_state:
    st.session_state.import_resumo = None

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
           leitura_ant_default = 0
if st.session_state.prev_map and nomes_inquilinos[i] in st.session_state.prev_map:
    leitura_ant_default = float(st.session_state.prev_map[nomes_inquilinos[i]])
ant = st.number_input("Leitura anterior (kWh)", min_value=0, step=1, value=leitura_ant_default, key=f"ant_{i}")
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
    
# ===================== ABA MÊS ANTERIOR (IMPORTAÇÃO) =====================
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
        st.session_state.leitura_predio_ant = get_item("Consumo total (kWh)") or 0.0

        st.success("Backup importado! Configurações e leituras anteriores aplicadas automaticamente.")
        st.write("Resumo do mês anterior:")
        st.dataframe(resumo_imp)
        st.write("Rateio do mês anterior (usado como leitura anterior):")
        st.dataframe(rateio_imp)

    except Exception as e:
        st.error(f"Erro ao importar backup: {e}")
        
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
with st.expander("📂 Importação do mês anterior", expanded=False):
    st.markdown("""
    • Ao final de cada mês, baixe o relatório em Excel.  
    • No mês seguinte, importe esse arquivo na aba **Mês anterior**.  
    • O sistema vai recuperar automaticamente:  
      – Bandeira tarifária, método de rateio e fonte do consumo total  
      – Consumo (kWh) de cada quitinete do mês anterior, que passa a ser a **leitura anterior** deste mês.  
    • Mantenha os nomes das quitinetes consistentes entre os meses para que a importação funcione corretamente.
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
