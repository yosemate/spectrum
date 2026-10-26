"""
Estado dos quatro indicadores (intensidade, pico, razão de banda e razão de espessura) e das
temperaturas. Sem Qt: testado em tests/test_kpi_status.py.

ISA-101: o estado normal é discreto; só o que sai da faixa ganha cor. Os limites abaixo são
faixas de referência do projeto para chamar a atenção do operador, não limites analíticos.
"""
import math
from dataclasses import dataclass

WAVELENGTHS = (610, 680, 730, 760, 810, 860)
SATURATION_ADC = 65500        # mesmo limite de chemometrics.validate_raw
NEAR_SATURATION_ADC = 58000   # cerca de 88 % do fundo de escala de 16 bits
LOW_SIGNAL_ADC = 500          # abaixo disso o sensor praticamente não vê luz
FLAT_SPECTRUM_RATIO = 1.15    # máximo / mínimo abaixo disso: espectro sem contraste
RATIO_RANGE = (0.2, 3.0)      # faixa de referência das razões (é também o eixo do gráfico de dispersão)

KINDS = ("energy", "peak", "ratio_cel", "ratio_water")
TITLES = {
    "energy": "Intensidade global",
    "peak": "Pico espectral",
    "ratio_cel": "Razão de banda · R680 / R730",
    "ratio_water": "Razão de banda · R860 / R760",
}
SHORT_TITLES = {
    "energy": "Intensidade",
    "peak": "Pico espectral",
    "ratio_cel": "Razão de banda",
    "ratio_water": "Razão R860 / R760",
}
EXPLANATION = {
    "energy": "Soma das contagens dos seis canais. Indica se há luz suficiente e se algum canal está perto de saturar.",
    "peak": "Comprimento de onda do canal mais intenso. Um espectro sem contraste costuma indicar amostra ausente ou LED apagado.",
    "ratio_cel": "R680 / R730 sobre o espectro normalizado pela soma. Razão espectral; seletividade físico-química não validada.",
    "ratio_water": "R860 / R760 sobre o espectro normalizado pela soma. Razão espectral; não mede espessura ou concentração de água.",
}

NONE, OK, ATTENTION, ERROR = "none", "ok", "attention", "error"
LEVEL_LABEL = {NONE: "Sem leitura", OK: "Normal", ATTENTION: "Atenção", ERROR: "Erro"}
# Chave da paleta (appearance.PALETTES) usada para pintar cada nível.
LEVEL_COLOR_KEY = {NONE: "muted", OK: "muted", ATTENTION: "warning", ERROR: "danger"}


@dataclass(frozen=True)
class Status:
    level: str
    headline: str
    hints: tuple = ()
    channels: tuple = ()   # índices dos canais envolvidos (destacados no gráfico)


def _clean(values):
    if values is None:
        return None
    try:
        out = [float(v) for v in values]
    except (TypeError, ValueError):
        return None
    return out if len(out) == 6 else None


def _names(indexes):
    return ", ".join(f"{WAVELENGTHS[i]} nm" for i in indexes)


def ratio_value(kind, r_snv):
    """Razão do indicador a partir do espectro normalizado, ou None se não houver como calcular."""
    values = _clean(r_snv)
    if values is None or any(not math.isfinite(v) or v <= 0 for v in values):
        return None
    if kind == "ratio_cel":
        return values[1] / values[2]
    if kind == "ratio_water":
        return values[5] / values[3]
    return None


def evaluate(kind, raw, r_snv=None):
    """Estado de um indicador para a leitura atual (contagens brutas e espectro normalizado)."""
    values = _clean(raw)
    if values is None:
        return Status(NONE, "Ainda não há leitura nesta sessão.")
    if any(not math.isfinite(v) or v < 0 for v in values):
        return Status(ERROR, "Há canais com valor inválido.",
                      ("Repita a leitura.", "Se persistir, confira o cabo do sensor e o terminal."))
    saturated = tuple(i for i, v in enumerate(values) if v >= SATURATION_ADC)
    near = tuple(i for i, v in enumerate(values) if NEAR_SATURATION_ADC <= v < SATURATION_ADC)
    peak = max(values)
    if kind in ("energy", "peak"):
        if saturated:
            return Status(ERROR, f"Saturação em {_names(saturated)}.",
                          ("Reduza o ganho ou a corrente do LED, ou afaste o sensor da amostra.",
                           "Depois de ajustar, refaça a calibração de branco e escuro."), saturated)
        if peak < LOW_SIGNAL_ADC:
            return Status(ERROR, "Sinal óptico muito baixo.",
                          ("Confira se a lâmina está sob o sensor e se a gaveta fechou.",
                           "Confira se o LED acende e se a calibração de branco ainda vale."))
        if kind == "peak":
            low = min(values)
            if low > 0 and peak / low < FLAT_SPECTRUM_RATIO:
                return Status(ATTENTION, "Espectro sem contraste entre os canais.",
                              ("Pode ser amostra ausente, LED apagado ou lâmina fora do foco.",))
        if near:
            return Status(ATTENTION, f"Perto da saturação em {_names(near)}.",
                          ("Considere reduzir o ganho ou a corrente do LED.",), near)
        if kind == "peak":
            return Status(OK, f"Pico em {WAVELENGTHS[values.index(peak)]} nm.")
        return Status(OK, "Sinal dentro da faixa.")
    if kind in ("ratio_cel", "ratio_water"):
        used = (1, 2) if kind == "ratio_cel" else (5, 3)
        ratio = ratio_value(kind, r_snv)
        if ratio is None:
            return Status(ERROR, "A razão não pôde ser calculada.",
                          ("Algum canal do espectro normalizado é zero ou inválido.",
                           "Repita a leitura e confira o branco e o escuro da calibração."), used)
        low, high = RATIO_RANGE
        if not low <= ratio <= high:
            return Status(ATTENTION, f"Fora da faixa de referência ({low:.1f} a {high:.1f}).",
                          ("Confira o posicionamento da amostra e a calibração.",
                           "Compare com a leitura anterior no gráfico de histórico."), used)
        return Status(OK, "Dentro da faixa de referência.", (), used)
    raise ValueError(f"Indicador desconhecido: {kind}")


def evaluate_all(raw, r_snv=None):
    return {kind: evaluate(kind, raw, r_snv) for kind in KINDS}


# ---- temperaturas -------------------------------------------------------------------------
COLD, WARM_OK = "cold", OK
THERMAL_LIMITS = {          # (frio abaixo de, normal até, atenção até); acima, erro
    "esp32": (10.0, 60.0, 75.0),
    "sensor": (10.0, 50.0, 65.0),
}
THERMAL_COLOR_KEY = {NONE: "muted", COLD: "sky", OK: "positive", ATTENTION: "warning", ERROR: "danger"}
THERMAL_LABEL = {NONE: "Indisponível", COLD: "Frio", OK: "Normal", ATTENTION: "Quente", ERROR: "Alarme"}


def temperature_level(kind, celsius):
    """Nível de uma temperatura em °C: none, cold, ok, attention ou error."""
    try:
        value = float(celsius)
    except (TypeError, ValueError):
        return NONE
    if not math.isfinite(value):
        return NONE
    cold, ok_max, attention_max = THERMAL_LIMITS[kind]
    if value < cold:
        return COLD
    if value <= ok_max:
        return OK
    if value <= attention_max:
        return ATTENTION
    return ERROR


# ---- escala dos gráficos ------------------------------------------------------------------
def nice_ticks(low, high, target=5):
    """Marcas redondas (1, 2, 5 × 10^n) entre low e high, com cerca de `target` intervalos."""
    low, high = float(low), float(high)
    if not (math.isfinite(low) and math.isfinite(high)) or high <= low:
        return [low]
    raw = (high - low) / max(1, target)
    magnitude = 10 ** math.floor(math.log10(raw))
    for factor in (1, 2, 5, 10):
        step = factor * magnitude
        if step >= raw:
            break
    first = math.ceil(low / step) * step
    ticks = []
    value = first
    while value <= high + step * 1e-9:
        ticks.append(round(value, 10))
        value += step
    return ticks
