"""
grafico_hist.py — Histograma de ALERTAS de stress alto × registros "Muito alto".

Uso:
    python grafico_hist.py <export> <outdir> [semana|mes|semestre]

Séries (agregadas no período escolhido):
  - registros com score na faixa "Muito alto" (80-100)
  - alertas de stress alto disparados pelo relógio (sem score)

Atenção: o primeiro e o último período costumam ser PARCIAIS (o export começa e
termina no meio deles). O script reporta quantos dias cada período cobre e marca
os parciais, porque comparar totais brutos de períodos com durações diferentes
é uma leitura errada.
"""
from __future__ import annotations

import calendar
import os
import sys

import pandas as pd
import plotly.graph_objects as go

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sh_load import SamsungExport, _read_csv

from shtools import export_dir  # noqa: E402

EXPORT = sys.argv[1] if len(sys.argv) > 1 else str(export_dir())
OUT = sys.argv[2] if len(sys.argv) > 2 else "report"
PERIODO = (sys.argv[3] if len(sys.argv) > 3 else "semana").lower()
# Opcional: ano mínimo (ex.: 2025 descarta 2024, que é incompleto).
DESDE = int(sys.argv[4]) if len(sys.argv) > 4 and sys.argv[4].isdigit() else None

CONF = {
    "semana":   dict(freq="7D",  dtick="M3", mm=4, dias=lambda d: 7,
                     rotulo="semana (segunda a domingo)", plural="semanas"),
    "mes":      dict(freq="MS",  dtick="M3", mm=3, dias=lambda d: calendar.monthrange(d.year, d.month)[1],
                     rotulo="mês", plural="meses"),
    "semestre": dict(freq="6MS", dtick="M6", mm=0, dias=lambda d: 184,
                     rotulo="semestre (jan–jun / jul–dez)", plural="semestres"),
}
KEY = ("semestre" if PERIODO.startswith("semes")
       else "semana" if PERIODO.startswith("sem")
       else "mes" if PERIODO[:3] in ("mes", "mês")
       else None)
if KEY is None:
    sys.exit(f"período inválido: {PERIODO!r} (use 'semana', 'mes' ou 'semestre')")
PERIODO = KEY
C = CONF[PERIODO]

# --- dados -----------------------------------------------------------------
e = SamsungExport(EXPORT)

al = _read_csv(e._path("com.samsung.shealth.alerted_stress.2"))
alertas = pd.DataFrame([{"ts": pd.to_datetime(r.get("start_time"))} for r in al]).dropna()

sr = _read_csv(e._path("com.samsung.shealth.stress.2"))
st = pd.DataFrame([{"ts": pd.to_datetime(r.get("start_time")), "score": float(r["score"])}
                   for r in sr if r.get("score") not in (None, "")]).dropna()
muito = st[st.score >= 80]


# --- agregação -------------------------------------------------------------
def rotula(df: pd.DataFrame) -> pd.Series:
    """Data de INÍCIO do período a que cada registro pertence."""
    if PERIODO == "semana":
        return df.ts.dt.to_period("W-SUN").apply(lambda p: p.start_time)
    if PERIODO == "mes":
        return df.ts.dt.to_period("M").apply(lambda p: p.start_time)
    return df.ts.apply(lambda t: pd.Timestamp(t.year, 1 if t.month <= 6 else 7, 1))


def agrega(df: pd.DataFrame) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=int)
    return rotula(df).value_counts().sort_index()


s_muito, s_alerta = agrega(muito), agrega(alertas)
idx = pd.date_range(min(s_muito.index.min(), s_alerta.index.min()),
                    max(s_muito.index.max(), s_alerta.index.max()), freq=C["freq"])
if DESDE:
    idx = idx[idx >= pd.Timestamp(DESDE, 1, 1)]
muito_p = s_muito.reindex(idx, fill_value=0)
alerta_p = s_alerta.reindex(idx, fill_value=0)

# --- cobertura real de cada período (flag de parcial) ----------------------
ini_d, fim_d = st.ts.min(), st.ts.max()
dur = {d: max(0, (min(d + pd.DateOffset(days=C["dias"](d)), fim_d) - max(d, ini_d)).days)
       for d in idx}
parcial = {d for d in idx if dur[d] < C["dias"](d)}

# --- gráfico ---------------------------------------------------------------
fig = go.Figure()
fig.add_bar(x=muito_p.index, y=muito_p.values, name="Score 'Muito alto' (80–100)",
            marker_color="#e67700", opacity=.9,
            customdata=[[dur[d]] for d in muito_p.index],
            hovertemplate="%{x|%b/%Y}<br>%{y} registro(s) 'muito alto'"
                          "<br>%{customdata[0]} dia(s) coberto(s)<extra></extra>")
fig.add_bar(x=alerta_p.index, y=alerta_p.values, name="Alertas de stress alto",
            marker_color="#c92a2a",
            hovertemplate="%{x|%b/%Y}<br>%{y} alerta(s)<extra></extra>")

if C["mm"] and len(muito_p) >= C["mm"]:
    mm = muito_p.rolling(C["mm"], min_periods=1).mean()
    fig.add_trace(go.Scatter(
        x=mm.index, y=mm.values, name=f"Média móvel {C['mm']} {C['plural']} ('muito alto')",
        mode="lines", line=dict(color="#7d1a1a", width=2.5, dash="dot")))

extra_x, fmt = {}, "%b/%Y"
if PERIODO == "semestre":
    extra_x = dict(tickmode="array", tickvals=list(idx),
                   ticktext=[f"{d.year}-S{1 if d.month <= 6 else 2}" for d in idx])
    fmt = "%Y-S"

fig.update_layout(
    title=dict(text=f"Total por {PERIODO} — alertas de stress alto × registros 'Muito alto'"
                    f"<br><sup>Samsung Health · contagem por {C['rotulo']}"
                    + (" · ⚠ períodos de borda são PARCIAIS" if parcial else "") + "</sup>",
               font=dict(size=17)),
    barmode="group",
    xaxis=dict(title=PERIODO.capitalize(), gridcolor="#e9ecef",
               dtick=C["dtick"], tickformat=fmt, **extra_x),
    yaxis=dict(title=f"Nº de eventos no {PERIODO}", gridcolor="#e9ecef",
               dtick=1 if int(max(muito_p.max(), alerta_p.max())) <= 25 else None),
    paper_bgcolor="#fff", plot_bgcolor="#fff",
    font=dict(family="Inter, Segoe UI, Arial", size=12),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    height=560, margin=dict(l=70, r=40, t=110, b=60), hovermode="x unified",
    bargap=0.25, bargroupgap=0.05,
)

os.makedirs(OUT, exist_ok=True)
png = os.path.join(OUT, f"stress-histograma-{PERIODO}.png")
html = os.path.join(OUT, f"stress-histograma-{PERIODO}.html")
fig.write_image(png, width=1500, height=560, scale=2)
fig.write_html(html, include_plotlyjs="inline", config={"displaylogo": False})

# --- números ---------------------------------------------------------------
rot = lambda d: (f"{d.year}-S{1 if d.month <= 6 else 2}" if PERIODO == "semestre" else f"{d:%b/%Y}")
print(f"período: {PERIODO} · {len(idx)} {C['plural']} no eixo "
      f"(dados de {ini_d:%d/%m/%Y} a {fim_d:%d/%m/%Y})")
print(f"'muito alto': {int(muito_p.sum())} registros em {int((muito_p > 0).sum())} {C['plural']} "
      f"(média {muito_p.mean():.2f}, mediana {muito_p.median():.0f}, máx {int(muito_p.max())})")
print(f"alertas: {int(alerta_p.sum())} em {int((alerta_p > 0).sum())} {C['plural']} "
      f"(média {alerta_p.mean():.2f}, máx {int(alerta_p.max())})")

print(f"\n{'período':<10} {'muito alto':>10} {'alertas':>8} {'dias':>6} {'taxa/30d':>9}")
for d in idx:
    n = dur[d]
    taxa = muito_p[d] / n * 30.4 if n else 0
    print(f"{rot(d):<10} {int(muito_p[d]):>10} {int(alerta_p[d]):>8} {n:>6} {taxa:>9.1f}"
          + ("   ⚠ PARCIAL" if d in parcial else ""))

print(f"\nPNG  → {png}")
print(f"HTML → {html}")
