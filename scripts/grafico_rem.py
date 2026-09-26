#!/usr/bin/env python3
"""
grafico_rem.py — Gráficos do REM.

1) REM absoluto (min) vs duração do sono — mostra que REM > 1,5 h = noite longa.
2) Arquitetura do sono ao longo do tempo — REM% e profundo% por trimestre,
   contra as faixas de referência (REM 20–25%, profundo 13–23%).

Uso: python analysis/grafico_rem.py report
"""
import sqlite3
import sys

import numpy as np
import pandas as pd
import plotly.graph_objects as go

OUT = sys.argv[1] if len(sys.argv) > 1 else "report"

con = sqlite3.connect(f"{OUT}/saude.db")
df = pd.read_sql("SELECT * FROM dia", con)
con.close()

d = df[(df["principal"] == 1) & (df["tem_fases"] == 1) & df["min_rem"].notna()].copy()
d["data"] = pd.to_datetime(d["data"])
d["h"] = d["min_dormido"] / 60.0

CINZA = "#5b6b7c"
AZUL = "#2f6fb5"
VERDE = "#2e8b57"
LARANJA = "#d1622b"

# ============ 1. REM absoluto vs duração do sono =============================
fig = go.Figure()
fig.add_trace(go.Scatter(
    x=d["h"], y=d["min_rem"], mode="markers",
    marker=dict(size=6, color=d["sleep_score"], colorscale="RdYlGn",
                cmin=50, cmax=95, opacity=.8,
                colorbar=dict(title="score<br>de sono", len=.7, thickness=14)),
    text=[f"{r.data:%d/%m/%Y}<br>{r.h:.1f} h · REM {r.min_rem:.0f} min "
          f"({r.pct_rem:.0f}%)<br>score {r.sleep_score:.0f}"
          for r in d.itertuples()],
    hoverinfo="text", name="noites"))

# linha de tendência
z = np.polyfit(d["h"], d["min_rem"], 1)
xx = np.linspace(d["h"].min(), d["h"].max(), 50)
fig.add_trace(go.Scatter(x=xx, y=np.polyval(z, xx), mode="lines",
                         name=f"tendência ({z[0]:.0f} min de REM por hora de sono)",
                         line=dict(color="#222", width=2.5)))

fig.add_hline(y=90, line=dict(color=LARANJA, width=2, dash="dash"),
              annotation_text="1,5 h de REM", annotation_position="top left",
              annotation_font=dict(color=LARANJA, size=13))
fig.add_vline(x=7, line=dict(color=CINZA, width=1.5, dash="dot"),
              annotation_text="7 h de sono", annotation_position="bottom right",
              annotation_font=dict(color=CINZA, size=12))

fig.update_layout(
    title="<b>REM absoluto acompanha a duração do sono</b>"
          "<br><sup>477 noites. Quanto mais tempo dormido, mais REM.<br>"
          "91% das noites com REM acima de 1,5 h são noites de 7 h ou mais.</sup>",
    xaxis_title="horas dormidas", yaxis_title="REM total (min)",
    template="plotly_white", height=560, margin=dict(t=140, r=40),
    legend=dict(orientation="h", yanchor="bottom", y=-0.22, x=0))
fig.write_image(f"{OUT}/rem-1-dispersao.png", scale=2)
fig.write_html(f"{OUT}/rem-1-dispersao.html")

# ============ 2. Arquitetura do sono por trimestre ===========================
d["q"] = d["data"].dt.to_period("Q")
g = d.groupby("q").agg(n=("pct_rem", "size"), rem=("pct_rem", "median"),
                       prof=("pct_profundo", "median")).reset_index()
g = g[g["n"] >= 10]
g["x"] = g["q"].dt.to_timestamp(how="start")

fig2 = go.Figure()
fig2.add_hrect(y0=20, y1=25, fillcolor="rgba(47,111,181,.10)", line_width=0,
               annotation_text="REM normal 20–25%", annotation_position="bottom left",
               annotation_font=dict(color=AZUL, size=12))
fig2.add_hrect(y0=13, y1=23, fillcolor="rgba(46,139,87,.10)", line_width=0,
               annotation_text="profundo normal 13–23%",
               annotation_position="bottom right",
               annotation_font=dict(color=VERDE, size=12))

fig2.add_trace(go.Scatter(
    x=g["x"], y=g["rem"], mode="lines+markers+text", name="REM %",
    text=[f"{v:.1f}" for v in g["rem"]], textposition="top right",
    textfont=dict(color=AZUL, size=11),
    line=dict(color=AZUL, width=3), marker=dict(size=9)))
fig2.add_trace(go.Scatter(
    x=g["x"], y=g["prof"], mode="lines+markers+text", name="sono profundo %",
    text=[f"{v:.1f}" for v in g["prof"]], textposition="bottom right",
    textfont=dict(color=VERDE, size=11),
    line=dict(color=VERDE, width=3), marker=dict(size=9)))

fig2.add_annotation(x=g["x"].iloc[-1], y=g["rem"].iloc[-1] - 3.2,
                    text=f"n={int(g['n'].iloc[-1])} noites<br>(período parcial)",
                    showarrow=False, font=dict(size=10, color=CINZA))

fig2.update_layout(
    title="<b>A arquitetura do sono mudou em 2025: mais sono profundo, REM estável</b>"
          "<br><sup>Mediana por trimestre (10+ noites). O sono profundo saiu de fora da faixa e entrou nela.<br>"
          "O REM ficou em 22–24% até 2026Q2; o último trimestre (28 noites) caiu para 18,4%.</sup>",
    xaxis_title="", yaxis_title="% do tempo dormido",
    template="plotly_white", height=560, margin=dict(t=140, r=60),
    yaxis=dict(range=[5, 28]),
    legend=dict(orientation="h", yanchor="bottom", y=-0.18, x=0))
fig2.write_image(f"{OUT}/rem-2-arquitetura.png", scale=2)
fig2.write_html(f"{OUT}/rem-2-arquitetura.html")

print("gerados:")
print(f"  {OUT}/rem-1-dispersao.png  + .html")
print(f"  {OUT}/rem-2-arquitetura.png + .html")
print()
print("trimestres usados no gráfico 2:")
for r in g.itertuples():
    print(f"  {r.q}  n={r.n:3d}  REM%={r.rem:5.1f}  profundo%={r.prof:5.1f}")
