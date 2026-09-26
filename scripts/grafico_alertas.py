"""
grafico_alertas.py — 40 alertas de stress alto × 155 registros na faixa "Muito alto".

Gera PNG + HTML autocontido.
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import plotly.graph_objects as go
from plotly.offline import get_plotlyjs

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sh_load import SamsungExport, _read_csv

from shtools import export_dir  # noqa: E402

EXPORT = sys.argv[1] if len(sys.argv) > 1 else str(export_dir())
OUT = sys.argv[2] if len(sys.argv) > 2 else "report"

e = SamsungExport(EXPORT)

# --- Série 1: os 40 alertas (só timestamp, sem score) ----------------------
al = _read_csv(e._path("com.samsung.shealth.alerted_stress.2"))
alertas = pd.DataFrame([{"ts": pd.to_datetime(r.get("start_time"))} for r in al]).dropna()
alertas = alertas.sort_values("ts")

# --- Série 2: registros com score na faixa "Muito alto" (80-100) ------------
sr = _read_csv(e._path("com.samsung.shealth.stress.2"))
st = pd.DataFrame([
    {"ts": pd.to_datetime(r.get("start_time")), "score": float(r["score"])}
    for r in sr if r.get("score") not in (None, "")
]).dropna()
muito_alto = st[st.score >= 80].sort_values("ts")

# --- Período comum do eixo X ------------------------------------------------
ini = min(alertas.ts.min(), muito_alto.ts.min())
fim = max(alertas.ts.max(), muito_alto.ts.max())

Y_ALERTA = 108  # faixa própria no topo para os alertas (não têm score)

fig = go.Figure()

# Alertas — marcadores em uma faixa acima da escala de score
fig.add_trace(go.Scatter(
    x=alertas.ts, y=[Y_ALERTA] * len(alertas),
    mode="markers", name=f"🔔 Alertas de stress alto ({len(alertas)})",
    marker=dict(symbol="triangle-down", size=13, color="#c92a2a",
                line=dict(width=1, color="#7d1a1a")),
    hovertemplate="<b>Alerta de stress alto</b><br>%{x|%d/%m/%Y %H:%M}<extra></extra>",
))

# Registros "Muito alto" — posicionados no score real
fig.add_trace(go.Scatter(
    x=muito_alto.ts, y=muito_alto.score,
    mode="markers", name=f"Score 'Muito alto' 80–100 ({len(muito_alto)})",
    marker=dict(size=8, color="#e67700", opacity=.75),
    hovertemplate="<b>Score %{y:.0f}</b> (muito alto)<br>%{x|%d/%m/%Y %H:%M}<extra></extra>",
))

# Faixa visual do "muito alto"
fig.add_hrect(y0=80, y1=100, fillcolor="#e67700", opacity=0.07, line_width=0)
fig.add_hline(y=80, line_dash="dot", line_color="#e67700",
              annotation_text="80 = início da faixa 'Muito alto'",
              annotation_position="top left", annotation_xshift=8)

fig.update_layout(
    title=dict(
        text="Alertas de stress alto × registros na faixa 'Muito alto'<br>"
             "<sup>Samsung Health · o relógio só registra alertas a partir de 17/11/2025</sup>",
        font=dict(size=17)),
    xaxis=dict(title="Data", gridcolor="#e9ecef"),
    yaxis=dict(title="Score de stress (0–100)", range=[-2, 116],
               tickvals=[0, 20, 40, 60, 80, 100, Y_ALERTA],
               ticktext=["0", "20", "40", "60", "80", "100", "alertas"],
               gridcolor="#e9ecef"),
    paper_bgcolor="#fff", plot_bgcolor="#fff",
    font=dict(family="Inter, Segoe UI, Arial", size=12),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    height=560, margin=dict(l=70, r=40, t=110, b=60), hovermode="closest",
)

os.makedirs(OUT, exist_ok=True)
png = os.path.join(OUT, "stress-alertas-vs-muito-alto.png")
html = os.path.join(OUT, "stress-alertas-vs-muito-alto.html")
fig.write_image(png, width=1400, height=560, scale=2)

# HTML autocontido
fig2 = go.Figure(fig)
fig2.write_html(html, include_plotlyjs="inline", config={"displaylogo": False})

print(f"alertas: {len(alertas)} ({alertas.ts.min():%d/%m/%Y} → {alertas.ts.max():%d/%m/%Y})")
print(f"'muito alto' (>=80): {len(muito_alto)} ({muito_alto.ts.min():%d/%m/%Y} → {muito_alto.ts.max():%d/%m/%Y})")
print(f"PNG  → {png} ({os.path.getsize(png)/1000:.0f} KB)")
print(f"HTML → {html} ({os.path.getsize(html)/1e6:.1f} MB)")

# Alguns cruzamentos úteis
meses = set(muito_alto.ts.dt.to_period("M"))
print("\nmeses com registro 'muito alto':", len(meses))
comum = muito_alto.ts.dt.to_period("M").value_counts().sort_index()
print(comum.to_string())
