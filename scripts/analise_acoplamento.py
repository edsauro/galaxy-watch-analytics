"""
analise_acoplamento.py — Testa o acoplamento stress ⇄ sono.

Hipótese levantada na análise médica: os picos de stress "muito alto" de madrugada
e o sono ruim seriam o mesmo fenômeno. Aqui isso é testado, não assumido.

Testes (Spearman, robusto a outliers e não-linearidade):
  A) stress do dia D      → qualidade do sono da noite D (desperta no dia D+1)
  B) sono da noite D      → stress do dia D+1   (direção inversa)
  C) noite seguinte a um pico "muito alto" vs. noite seguinte a um dia calmo

Inspirado em Devasy/samsung-health-sdk (`stress_impact_on_sleep`).

Uso: python analise_acoplamento.py <export> <sono.json> <saida.json>
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sh_load import SamsungExport

from shtools import export_dir  # noqa: E402

EXPORT = sys.argv[1] if len(sys.argv) > 1 else str(export_dir())
SONO = sys.argv[2] if len(sys.argv) > 2 else "report/sono.json"
OUT = sys.argv[3] if len(sys.argv) > 3 else "report/acoplamento.json"

e = SamsungExport(EXPORT)
num = lambda s: pd.to_numeric(s, errors="coerce")

# ------------------------------------------------------------------- stress
sr = pd.DataFrame(e.table("com.samsung.shealth.stress"))
sr["ts"] = pd.to_datetime(sr.start_time, errors="coerce")
sr["score"] = num(sr.score)
sr = sr.dropna(subset=["ts", "score"])
# o dia "fisiológico" começa às 18h: uma amostra das 02h pertence à noite anterior
sr["dia"] = (sr.ts + pd.to_timedelta((sr.ts.dt.hour >= 18).astype(int), unit="D")).dt.date.astype(str)
st_dia = sr.groupby("dia").agg(
    stress_medio=("score", "mean"), stress_mediano=("score", "median"),
    stress_max=("score", "max"), n=("score", "size"),
    n_alto=("score", lambda s: int((s >= 80).sum())),
    n_muito_alto=("score", lambda s: int((s >= 80).sum()))).reset_index()

al = pd.DataFrame(e.table("com.samsung.shealth.alerted_stress"))
al["dia"] = pd.to_datetime(al.start_time, errors="coerce").dt.date.astype(str)
al_dia = al.groupby("dia").size().rename("n_alertas").reset_index()
print(f"stress: {len(sr):,} amostras em {len(st_dia)} dias · alertas em {len(al_dia)} dias")

# --------------------------------------------------------------------- sono
sono = pd.DataFrame(json.load(open(SONO))["noites"])
sono = sono[sono.tem_fases == True].copy()          # noqa: E712
sono["despertar"] = sono.data
print(f"sono: {len(sono)} noites com fases")

# junta: stress do dia D  ×  sono da noite que desperta em D
m = sono.merge(st_dia, left_on="despertar", right_on="dia", how="inner")
m = m.merge(al_dia, on="dia", how="left").fillna({"n_alertas": 0})
print(f"pareado: {len(m)} dias/noites em comum\n")

VARS_SONO = {"sleep_score": "sleep_score", "eficiencia": "eficiência",
             "waso_min": "WASO", "fragmentacao": "fragmentação",
             "pct_profundo": "% profundo", "pct_rem": "% REM",
             "horas": "horas na cama", "despertares_mov": "despertares (proxy)"}
VARS_STRESS = {"stress_medio": "stress médio do dia", "stress_max": "stress máx do dia",
               "n_alto": "nº de registros ≥80", "n_alertas": "nº de alertas"}


def spearman(a, b, dados):
    d = dados[[a, b]].dropna()
    if len(d) < 12:
        return None
    r, p = stats.spearmanr(d[a], d[b])
    return dict(r=round(float(r), 3), p=round(float(p), 4), n=len(d))


print("A) stress do dia → sono da mesma noite (≠ da hipótese, é o lag 0)")
res_a = []
for sk, srk in VARS_STRESS.items():
    for nk, nrk in VARS_SONO.items():
        r = spearman(sk, nk, m)
        if r:
            res_a.append(dict(stress=srk, sono=nrk, r=r["r"], p=r["p"], n=r["n"],
                              significativo=bool(r["p"] < 0.05)))
sig = [x for x in res_a if x["significativo"] and abs(x["r"]) >= 0.2]
print(f"   {len(res_a)} pares testados · {len(sig)} com p<0,05 e |r|≥0,2")
for x in sorted(sig, key=lambda z: -abs(z["r"]))[:8]:
    print(f"      {x['stress']:<26} × {x['sono']:<22} r={x['r']:+.3f}  p={x['p']:.4f}  n={x['n']}")

print("\nB) sono da noite D → stress do dia SEGUINTE (D+1)")
m2 = m.copy()
m2["despertar_dt"] = pd.to_datetime(m2.despertar)
prox = st_dia.copy()
prox["despertar_dt"] = pd.to_datetime(prox.dia) - pd.Timedelta(days=1)
m2 = m2.merge(prox[["despertar_dt", "stress_medio", "stress_max", "n_alto"]],
              on="despertar_dt", suffixes=("", "_d1"))
res_b = []
for sk in ["stress_medio", "stress_max", "n_alto"]:
    for nk, nrk in VARS_SONO.items():
        r = spearman(nk, sk + "_d1", m2)
        if r:
            res_b.append(dict(sono=nrk, stress=srk + " (D+1)", r=r["r"], p=r["p"], n=r["n"],
                              significativo=bool(r["p"] < 0.05)))
sigb = [x for x in res_b if x["significativo"] and abs(x["r"]) >= 0.2]
print(f"   {len(res_b)} pares testados · {len(sigb)} com p<0,05 e |r|≥0,2")
for x in sorted(sigb, key=lambda z: -abs(z["r"]))[:8]:
    print(f"      {x['sono']:<22} → {x['stress']:<28} r={x['r']:+.3f}  p={x['p']:.4f}  n={x['n']}")

# ------------------------------------------- C) noite após pico vs. dia calmo
pico = set(st_dia[st_dia.n_alto >= 1].dia)
calmo = set(st_dia[st_dia.n_alto == 0].dia)
m["pos_pico"] = m.despertar.isin(pico)
m["pos_calmo"] = m.despertar.isin(calmo)
print(f"\nC) noites após dia com pico ≥80: {int(m.pos_pico.sum())} · "
      f"após dia calmo: {int(m.pos_calmo.sum())}")
comp = []
for nk, nrk in VARS_SONO.items():
    a = m[m.pos_pico][nk].dropna()
    b = m[m.pos_calmo][nk].dropna()
    if len(a) >= 10 and len(b) >= 10:
        u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
        comp.append(dict(variavel=nrk,
                         mediana_pos_pico=round(float(a.median()), 1),
                         mediana_pos_calmo=round(float(b.median()), 1),
                         diferenca=round(float(a.median() - b.median()), 1),
                         p=round(float(p), 4), significativo=bool(p < 0.05),
                         n_pos_pico=len(a), n_pos_calmo=len(b)))
        print(f"   {nrk:<22} pico {comp[-1]['mediana_pos_pico']:>7}  "
              f"calmo {comp[-1]['mediana_pos_calmo']:>7}  "
              f"dif {comp[-1]['diferenca']:>+6}  p={p:.4f}"
              + ("  ← significativo" if p < 0.05 else ""))

# ------------------------------------------------------------ alertas madruga
madruga = sr[(sr.ts.dt.hour <= 5)]
n_top = int((sr.score >= 80).sum())
n_top_madruga = int(((sr.score >= 80) & (sr.ts.dt.hour <= 5)).sum())
print(f"\nPicos ≥80: {n_top} no total · {n_top_madruga} entre 00h-05h "
      f"({n_top_madruga/n_top*100:.0f}%)")

json.dump(dict(
    gerado_em=datetime.now().isoformat(timespec="seconds"),
    pareamento=f"{len(m)} dias/noites em comum",
    metodo="Spearman (robusto a outliers); dia fisiológico começa às 18h",
    leitura="r é correlação, não causalidade. Ausência de correlação com este n "
            "não prova ausência de efeito — apenas que não é detectável aqui.",
    a_stress_para_sono=res_a, b_sono_para_stress=res_b, c_comparacao_grupos=comp,
    picos_madrugada=dict(total=n_top, entre_0h_5h=n_top_madruga,
                         pct=round(n_top_madruga / n_top * 100, 1) if n_top else None)),
    open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\n→ {OUT}")
