#!/usr/bin/env python3
"""
analise_rem_lag.py — Testa se o REM alto é REBOTE (compensação de noite curta)
ou simplesmente consequência de dormir mais.

Rebote de REM = noite de privação → REM acima do normal na(s) noite(s) seguinte(s).
Se for rebote: REM% sobe quando o sono total é CURTO (ou após noite curta).
Se for duração: REM absoluto acompanha o sono, e o REM% fica estável.

Uso: python analysis/analise_rem_lag.py report
"""
import sqlite3
import sys

import numpy as np
import pandas as pd
from scipy import stats

OUT = sys.argv[1] if len(sys.argv) > 1 else "report"

con = sqlite3.connect(f"{OUT}/saude.db")
df = pd.read_sql("SELECT * FROM dia", con)
con.close()

d = df[(df["principal"] == 1) & (df["tem_fases"] == 1) & df["min_rem"].notna()].copy()
d["data"] = pd.to_datetime(d["data"])
d = d.sort_values("data").reset_index(drop=True)

# lags de sono
for lag in (1, 2):
    d[f"sono_lag{lag}"] = d["min_dormido"].shift(lag)
    d[f"data_lag{lag}"] = (d["data"] - d["data"].shift(lag)).dt.days

# só lags de noites consecutivas (evita buraco de vários dias)
d["sono_lag1_ok"] = np.where(d["data_lag1"] == 1, d["sono_lag1"], np.nan)
d["sono_lag2_ok"] = np.where(d["data_lag2"] == 2, d["sono_lag2"], np.nan)

# dívida de sono acumulada em 3 noites anteriores
d["divida3"] = 3 * 420 - (d["sono_lag1_ok"].fillna(0) + d["sono_lag2_ok"].fillna(0) + d["min_dormido"].shift(3))

print("=" * 72)
print("  REM: rebote (compensação) ou consequência da duração?")
print("=" * 72)


def sp(a, b, rot):
    m = pd.notna(a) & pd.notna(b)
    x, y = np.asarray(a)[m], np.asarray(b)[m]
    if len(x) < 20:
        print(f"  {rot:44s} n insuficiente ({len(x)})")
        return
    rho, p = stats.spearmanr(x, y)
    print(f"  {rot:44s} rho={rho:+.3f}  p={p:.1e}  n={len(x)}")


print("\n1) Noite curta PREDIZ REM alto na noite seguinte?")
sp(d["sono_lag1_ok"], d["min_rem"], "sono de ontem  →  REM de hoje (min)")
sp(d["sono_lag1_ok"], d["pct_rem"], "sono de ontem  →  REM de hoje (%)")
print("   (rebote apareceria como rho NEGATIVO no primeiro, POSITIVO no segundo)")

print("\n2) O REM% sobe quando o sono é curto? (rebote intra-noite)")
sp(d["min_dormido"], d["pct_rem"], "sono de hoje  →  REM% de hoje")

print("\n3) REM% por faixa de duração do sono")
faixas = [(0, 300, "< 5h"), (300, 360, "5–6h"), (360, 420, "6–7h"),
          (420, 480, "7–8h"), (480, 9999, "> 8h")]
print(f"   {'faixa':8s} {'n':>5s} {'REM med':>8s} {'REM% med':>9s} {'%noites REM>90':>15s}")
for lo, hi, rot in faixas:
    g = d[(d["min_dormido"] >= lo) & (d["min_dormido"] < hi)]
    if not len(g):
        continue
    print(f"   {rot:8s} {len(g):5d} {g['min_rem'].median():8.1f} "
          f"{g['pct_rem'].median():9.1f} {100*(g['min_rem']>90).mean():14.1f}%")

print("\n4) Noites com REM% acima de 30% — o que são?")
alto = d[d["pct_rem"] > 30]
resto = d[d["pct_rem"] <= 30]
print(f"   n = {len(alto)} de {len(d)} ({100*len(alto)/len(d):.1f}%)")
for c, rot in [("min_dormido", "horas dormidas (min)"), ("min_rem", "REM (min)"),
               ("sleep_score", "score"), ("waso_min", "WASO"), ("fragmentacao", "fragmentação")]:
    print(f"   {rot:24s} alto={alto[c].median():7.1f}  resto={resto[c].median():7.1f}  "
          f"p={stats.mannwhitneyu(alto[c].dropna(), resto[c].dropna())[1]:.1e}")

print("\n5) Efeito do dia da semana no REM (recuperação de fim de semana)")
dias = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
print(f"   {'dia':5s} {'n':>4s} {'sono med':>9s} {'REM med':>8s} {'REM%':>6s}")
for i, rot in enumerate(dias):
    g = d[d["data"].dt.dayofweek == i]
    if len(g):
        print(f"   {rot:5s} {len(g):4d} {g['min_dormido'].median():9.1f} "
              f"{g['min_rem'].median():8.1f} {g['pct_rem'].median():6.1f}")

print("\n6) sHRV (HRV noturna da Samsung) vs REM — o REM 'vale' quanto de HRV?")
for c, rot in [("shrv", "sHRV"), ("baseline_meio", "baseline HRV")]:
    if c in d.columns:
        sp(d["min_rem"], d[c], f"REM (min) → {rot}")
        sp(d["pct_rem"], d[c], f"REM (%)  → {rot}")

print("\n7) O que 'recuperação mental' realmente mede?")
sp(d["rec_mental"], d["min_rem"], "rec_mental → REM (min)")
sp(d["rec_mental"], d["pct_rem"], "rec_mental → REM (%)")
sp(d["rec_mental"], d["min_profundo"], "rec_mental → profundo (min)")
sp(d["rec_mental"], d["sleep_score"], "rec_mental → sleep_score")
print("   (rho ~0,99 com REM indica que a Samsung DERIVA recuperação mental do REM,")
print("    não é um sinal independente)")

print("\n" + "=" * 72)
