#!/usr/bin/env python3
"""
analise_medicacao.py — Localiza uma QUEBRA na curva de FC de repouso e mede o
efeito ANTES/DEPOIS em sono (REM, profundo), HRV, readiness, stress e carga de
treino.

Serve para qualquer evento datado que você queira testar: início ou retirada
de um medicamento, mudança de rotina, férias, lesão. O ponto de quebra é
ESTIMADO a partir dos dados, não presumido — então o script também funciona
como verificação: se ele apontar uma data diferente da que você esperava, isso
é informação, não erro.

Método da quebra: para cada ponto candidato, t de Welch entre os dois segmentos;
o ponto de máximo |t| é a quebra estimada. Significância por teste de permutação
(reembaralha a série 2000x e mede o |t| máximo — controla o "olhar em todos os
pontos", que é o erro clássico de change-point detection). O t é calculado de
forma vetorizada via somas cumulativas (um loop Python aqui seria inviável).

Uso: python analysis/analise_medicacao.py report
"""
import json
import sqlite3
import sys
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats

OUT = sys.argv[1] if len(sys.argv) > 1 else "report"
MIN_SEG = 45
N_PERM = 2000
SEED = 20260918

con = sqlite3.connect(f"{OUT}/saude.db")
d = pd.read_sql("SELECT * FROM dia", con)
con.close()
d["data"] = pd.to_datetime(d["data"])
d = d.sort_values("data").reset_index(drop=True)


def t_todos(x, min_seg=MIN_SEG):
    """|t| de Welch para TODOS os pontos de quebra de uma vez (vetorizado)."""
    n = len(x)
    if n < 2 * min_seg:
        return None
    c = np.cumsum(x)
    c2 = np.cumsum(x * x)
    ks = np.arange(min_seg, n - min_seg + 1)
    soma_a = c[ks - 1]
    soma_b = c[-1] - soma_a
    na, nb = ks.astype(float), (n - ks).astype(float)
    ma, mb = soma_a / na, soma_b / nb
    ssa = c2[ks - 1] - soma_a ** 2 / na
    ssb = (c2[-1] - c2[ks - 1]) - soma_b ** 2 / nb
    va = ssa / (na - 1)
    vb = ssb / (nb - 1)
    se = np.sqrt(va / na + vb / nb)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(se > 0, (ma - mb) / se, 0.0)
    return ks, np.nan_to_num(t)


def melhor_quebra(v, min_seg=MIN_SEG, n_perm=N_PERM, rng=None):
    x = np.asarray(v, dtype=float)
    ok = ~np.isnan(x)
    idx_ok = np.where(ok)[0]
    x = x[idx_ok]
    r = t_todos(x, min_seg)
    if r is None:
        return None
    ks, t = r
    j = int(np.argmax(np.abs(t)))
    t_obs = float(t[j])
    k_obs = int(ks[j])
    if rng is None:
        rng = np.random.default_rng(SEED)
    extremos = np.empty(n_perm)
    for i in range(n_perm):
        rr = t_todos(rng.permutation(x), min_seg)
        extremos[i] = np.max(np.abs(rr[1]))
    p = float((1 + (extremos >= abs(t_obs)).sum()) / (n_perm + 1))
    return dict(pos=k_obs, t=round(t_obs, 2), p=p,
                idx_real=int(idx_ok[k_obs]),
                data_quebra=str(d["data"].iloc[idx_ok[k_obs]].date()))


print("=" * 78)
print("  QUEBRA NA CURVA DE FC DE REPOUSO — evento datado pelo usuário")
print("=" * 78)

s = d[["data", "shr", "shrv", "readiness", "min_rem", "pct_rem", "pct_profundo",
       "min_dormido", "sleep_score", "stress_medio", "km", "fragmentacao",
       "baseline_meio", "waso_min", "repouso", "min_profundo"]].copy()

res = {"gerado_em": datetime.now().isoformat(timespec="seconds"),
       "min_seg_dias": MIN_SEG, "n_permutacoes": N_PERM}
rng = np.random.default_rng(SEED)

print("\n1) Quebra na FC de repouso (série diária, n=%d)" % s["shr"].notna().sum())
q = melhor_quebra(s["shr"].values, rng=rng)
res["quebra_fc_repouso"] = q
if q:
    i = q["idx_real"]
    antes = d.loc[:i, "shr"].dropna()
    depois = d.loc[i + 1:, "shr"].dropna()
    print(f"   data estimada ....... {q['data_quebra']}")
    print(f"   t de Welch .......... {q['t']:+.2f}")
    print(f"   p (permutação) ...... {q['p']:.4f}   "
          f"{'SIGNIFICATIVO' if q['p'] < .05 else 'não significativo'}")
    print(f"   ANTES  (n={len(antes):3d}) .... FC repouso {antes.median():.1f} bpm")
    print(f"   DEPOIS (n={len(depois):3d}) .... FC repouso {depois.median():.1f} bpm")
    print(f"   diferença ........... {depois.median()-antes.median():+.1f} bpm")
    res["fc_antes_depois"] = dict(
        antes=round(float(antes.median()), 1), depois=round(float(depois.median()), 1),
        delta=round(float(depois.median() - antes.median()), 1),
        n_antes=int(len(antes)), n_depois=int(len(depois)))

print("\n2) Detecção CEGA nas outras séries — onde mais aparece quebra?")
for c, rot in [("shrv", "HRV noturna"), ("baseline_meio", "baseline HRV"),
               ("readiness", "readiness"), ("pct_rem", "REM %"), ("min_rem", "REM min"),
               ("pct_profundo", "profundo %"), ("min_dormido", "sono total"),
               ("sleep_score", "score de sono"), ("km", "km/dia"),
               ("stress_medio", "stress médio"), ("repouso", "calorias repouso")]:
    r = melhor_quebra(s[c].values, rng=rng)
    if r:
        print(f"   {rot:16s} {r['data_quebra']}  t={r['t']:+6.2f}  p={r['p']:.4f}"
              f"{'  <-- significativo' if r['p'] < .05 else ''}")
        res.setdefault("quebras_outras", {})[c] = r

print("\n3) Efeito ANTES/DEPOIS ancorado na quebra da FC de repouso")
if q:
    i = q["idx_real"]
    metricas = [("shr", "FC de repouso"), ("shrv", "HRV noturna"),
                ("baseline_meio", "baseline HRV"), ("readiness", "readiness"),
                ("min_rem", "REM (min)"), ("pct_rem", "REM %"),
                ("min_profundo", "profundo (min)"), ("pct_profundo", "profundo %"),
                ("min_dormido", "sono total (min)"), ("sleep_score", "score de sono"),
                ("waso_min", "WASO (min)"), ("fragmentacao", "fragmentação"),
                ("stress_medio", "stress médio"), ("km", "km/dia"),
                ("repouso", "calorias de repouso")]
    print(f"   {'métrica':22s} {'antes':>9s} {'depois':>9s} {'delta':>8s} "
          f"{'p':>9s} {'d':>7s}")
    res["antes_depois"] = {}
    for c, rot in metricas:
        if c not in d.columns:
            continue
        a = d.loc[:i, c].dropna()
        b = d.loc[i + 1:, c].dropna()
        if len(a) < 15 or len(b) < 15:
            continue
        _, p = stats.mannwhitneyu(a, b, alternative="two-sided")
        dp = (b.mean() - a.mean()) / np.sqrt((a.std() ** 2 + b.std() ** 2) / 2)
        print(f"   {rot:22s} {a.median():9.1f} {b.median():9.1f} "
              f"{b.median()-a.median():+8.1f} {p:9.1e} {dp:+7.2f}"
              f"{'  <<' if p < .05 else ''}")
        res["antes_depois"][c] = dict(
            nome=rot, antes=round(float(a.median()), 1),
            depois=round(float(b.median()), 1),
            delta=round(float(b.median() - a.median()), 1),
            p=float(f"{p:.2e}"), d=round(float(dp), 2),
            n_antes=int(len(a)), n_depois=int(len(b)))

print("\n4) FC de repouso e sono andam juntos? (série inteira)")
res["fc_vs_sono"] = {}
for c, rot in [("min_rem", "FC repouso → REM (min)"), ("pct_rem", "FC repouso → REM %"),
               ("pct_profundo", "FC repouso → profundo %"),
               ("min_dormido", "FC repouso → sono total"),
               ("shrv", "FC repouso → HRV"),
               ("sleep_score", "FC repouso → score"),
               ("readiness", "FC repouso → readiness")]:
    m = pd.notna(s["shr"]) & pd.notna(s[c])
    x, y = s["shr"][m], s[c][m]
    rho, p = stats.spearmanr(x, y)
    print(f"   {rot:34s} rho={rho:+.3f}  p={p:.1e}  n={len(x)}")
    res["fc_vs_sono"][c] = dict(rho=round(float(rho), 3), p=float(f"{p:.2e}"),
                                n=int(len(x)))

print("\n5) Mediana móvel de 30 dias da FC de repouso (forma da curva)")
mv = s.set_index("data")["shr"].rolling(30, min_periods=15).median().dropna()
for i in range(0, len(mv), 30):
    v = mv.iloc[i]
    print(f"   {mv.index[i].date()}  {v:5.1f}  {'#' * int(max(0, (v - 45) * 3))}")

with open(f"{OUT}/medicacao.json", "w") as f:
    json.dump(res, f, ensure_ascii=False, indent=1, default=str)
print(f"\n  salvo em {OUT}/medicacao.json")
