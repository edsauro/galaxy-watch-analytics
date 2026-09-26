"""
grafico_hist_semanal.py — Histograma SEMANAL do gráfico de alertas × "muito alto".

Duas séries agregadas por semana (segunda a domingo):
  - 155 registros com score na faixa "Muito alto" (80-100)
  - 40 alertas de stress alto disparados pelo relógio
"""
from __future__ import annotations

import os
import sys

import pandas as pd
import plotly.graph_objects as go

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sh_load import SamsungExport, _read_csv

from shtools import export_dir  # noqa: E402

EXPORT = sys.argv[1] if len(sys.argv) > 1 else str(export_dir())
OUT = sys.argv[2] if len(sys.argv) > 2 else "report"

e = SamsungExport(EXPORT)

# --- dados -----------------------------------------------------------------
al = _read_csv(e._path("com.samsung.shealth.alerted_stress.2"))
alertas = pd.DataFrame([{"ts": pd.to_datetime(r.get("start_time"))} for r in al]).dropna()

sr = _read_csv(e._path("com.samsung.shealth.stress.2"))
st = pd.DataFrame([{"ts": pd.to_datetime(r.get("start_time")), "score": float(r["score"])}
                   for r in sr if r.get("score") not in (None, "")]).dropna()
muito = st[st.score >= 80]

# --- agregação semanal (semana ISO: segunda a domingo) ---------------------
ini = min(muito.ts.min(), alertas.ts.min())
fim = max(muito.ts.max(), alertas.ts.max())
semanas = pd.date_range(ini.normalize() - pd.Timedelta(days=ini.weekday()),
                        fim.normalize(), freq="W-MON")

def semanal(df):
    if df.empty:
        return pd.Series(dtype=int)
    w = df.ts.dt.to_period("W-SUN").apply(lambda p: p.start_time)
    return w.value_counts().sort_index()

s_muito = semanal(muito)
s_alerta = semanal(alertas)

idx = pd.date_range(min(s_muito.index.min(), s_alerta.index.min()),
                    max(s_muito.index.max(), s_alerta.index.max()), freq="7D")
muito_w = s_muito.reindex(idx, fill_value=0)
alerta_w = s_alerta.reindex(idx, fill_value=0)

# --- gráfico ---------------------------------------------------------------
fig = go.Figure()
fig.add_bar(x=muito_w.index, y=muito_w.values, name="Score 'Muito alto' (80–100)",
            marker_color="#e67700", opacity=.9,
            hovertemplate="Semana de %{x|%d/%m/%Y}<br>%{y} registro(s) 'muito alto'<extra></extra>")
fig.add_bar(x=alerta_w.index, y=alerta_w.values, name="Alertas de stress alto",
            marker_color="#c92a2a",
            hovertemplate="Semana de %{x|%d/%m/%Y}<br>%{y} alerta(s)<extra></extra>")

# linha de média móvel de 4 semanas sobre os "muito alto"
if len(muito_w) >= 4:
    mm = muito_w.rolling(4, min_periods=1).mean()
    fig.add_trace(go.Scatter(x=mm.index, y=mm.values, name="Média móvel 4 semanas ('muito alto')",
                             mode="lines", line=dict(color="#7d1a1a", width=2.5, dash="dot")))

fig.update_layout(
    title=dict(text="Histograma semanal — alertas de stress alto × registros 'Muito alto'<br>"
                    "<sup>Samsung Health · contagem por semana (segunda a domingo)</sup>",
               font=dict(size=17)),
    barmode="group",
    xaxis=dict(title="Semana", gridcolor="#e9ecef", dtick="M3", tickformat="%b/%Y"),
    yaxis=dict(title="Nº de eventos na semana", gridcolor="#e9ecef", dtick=1),
    paper_bgcolor="#fff", plot_bgcolor="#fff",
    font=dict(family="Inter, Segoe UI, Arial", size=12),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0),
    height=560, margin=dict(l=70, r=40, t=110, b=60), hovermode="x unified",
)

os.makedirs(OUT, exist_ok=True)
png = os.path.join(OUT, "stress-histograma-semanal.png")
html = os.path.join(OUT, "stress-histograma-semanal.html")
fig.write_image(png, width=1500, height=560, scale=2)
fig.write_html(html, include_plotlyjs="inline", config={"displaylogo": False})

# --- números ---------------------------------------------------------------
print(f"semanas no eixo: {len(idx)}")
print(f"'muito alto': {int(muito_w.sum())} registros em {int((muito_w > 0).sum())} semanas "
      f"(média {muito_w.mean():.2f}/semana, mediana {muito_w.median():.0f}, máx {int(muito_w.max())})")
print(f"alertas: {int(alerta_w.sum())} em {int((alerta_w > 0).sum())} semanas "
      f"(média {alerta_w.mean():.2f}/semana, máx {int(alerta_w.max())})")
print("\nTOP 10 semanas por 'muito alto':")
for d, v in muito_w.nlargest(10).items():
    a = int(alerta_w.get(d, 0))
    print(f"  semana de {d:%d/%m/%Y}: {v} registros 'muito alto' | {a} alerta(s)")
print("\nTOP 10 semanas por alertas:")
for d, v in alerta_w.nlargest(10).items():
    m_ = int(muito_w.get(d, 0))
    print(f"  semana de {d:%d/%m/%Y}: {v} alerta(s) | {m_} 'muito alto'")
print(f"\nPNG  → {png}")
print(f"HTML → {html}")
