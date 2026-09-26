#!/usr/bin/env python3
"""
analise_rem_avancada.py — Investigação de 2ª rodada do REM.

Motivo: a 1ª rodada tratou a série inteira como homogênea. Não é.
A granularidade da estadiagem muda em algum ponto do histórico (mais
segmentos por noite, cada um mais curto), e isso quebra a comparabilidade
de %REM e %profundo entre antes e depois. Aqui a análise é refeita em duas
janelas que você define:
  JANELA LIMPA   : período com algoritmo estável E uso bom do relógio
  JANELA RECENTE : período de uso esparso, tratado à parte

As fronteiras vêm das variáveis SH_LIMPO_INI, SH_LIMPO_FIM e SH_RECENTE_INI
— descubra as suas rodando analise_granularidade.py e olhando onde a
estrutura da noite muda.

Hipóteses testadas:
  H1 o REM absoluto acompanha a duração do sono          (re-testada)
  H2 houve rebote de REM depois do evento de medicação    (testada)
  H3 FC de repouso / HRV estão acoplados ao REM%          (testada)
  H4 a mudança de arquitetura é artefato de algoritmo     (medida)
  H5 treino influencia REM                                (re-testada)

Uso: python analysis/analise_rem_avancada.py report
"""
import json
import os
import sqlite3
import sys
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats

OUT = sys.argv[1] if len(sys.argv) > 1 else "report"
# A série NÃO é homogênea: a granularidade da estadiagem mudou em algum ponto
# (mais segmentos por noite, cada um mais curto), e isso quebra a comparabilidade
# de %REM e %profundo antes/depois. Aqui a análise é refeita em uma JANELA LIMPA
# e o período recente é tratado à parte.
#
# Os limites são configuração. Descubra os seus rodando analise_granularidade.py
# e olhando onde "segmentos por noite" salta.
LIMPO_INI = os.environ.get("SH_LIMPO_INI", "")
LIMPO_FIM = os.environ.get("SH_LIMPO_FIM", "")
RECENTE_INI = os.environ.get("SH_RECENTE_INI", "")
if not (LIMPO_INI and LIMPO_FIM and RECENTE_INI):
    raise SystemExit(
        "[rem_avancada] defina SH_LIMPO_INI, SH_LIMPO_FIM e SH_RECENTE_INI.\n"
        "  São as fronteiras do SEU histórico: rode primeiro\n"
        "  analise_granularidade.py e veja onde a estrutura da noite muda.\n"
        "  Ex.:  SH_LIMPO_INI=2024-01-01 SH_LIMPO_FIM=2025-06-30 \\\n"
        "        SH_RECENTE_INI=2025-07-01 python3 analise_rem_avancada.py")

con = sqlite3.connect(f"{OUT}/saude.db")
d = pd.read_sql("SELECT * FROM dia", con)
con.close()
d["data"] = pd.to_datetime(d["data"])
d = d.sort_values("data").reset_index(drop=True)

sono = d[(d["principal"] == 1) & (d["tem_fases"] == 1) & d["min_rem"].notna()].copy()


def sp(a, b, rot=None):
    m = pd.notna(a) & pd.notna(b)
    x, y = np.asarray(a)[m], np.asarray(b)[m]
    if len(x) < 15 or np.std(x) == 0 or np.std(y) == 0:
        return dict(n=int(len(x)), rho=None, p=None)
    rho, p = stats.spearmanr(x, y)
    return dict(n=int(len(x)), rho=round(float(rho), 3), p=float(f"{p:.2e}"))


def parcial(df, c1, c2, ctrl):
    """Correlação parcial de Spearman de c1 e c2 controlando por ctrl."""
    g = df[[c1, c2, ctrl]].dropna()
    if len(g) < 20:
        return dict(n=len(g), rho=None, p=None)
    r12 = stats.spearmanr(g[c1], g[c2]).statistic
    r13 = stats.spearmanr(g[c1], g[ctrl]).statistic
    r23 = stats.spearmanr(g[c2], g[ctrl]).statistic
    num = r12 - r13 * r23
    den = np.sqrt((1 - r13 ** 2) * (1 - r23 ** 2))
    rp = num / den if den else np.nan
    n = len(g)
    if n > 3 and not np.isnan(rp):
        t = rp * np.sqrt((n - 3) / (1 - rp ** 2))
        p = 2 * (1 - stats.t.cdf(abs(t), n - 3))
    else:
        p = np.nan
    return dict(n=int(n), rho=round(float(rp), 3) if not np.isnan(rp) else None,
                p=float(f"{p:.2e}") if not np.isnan(p) else None)


res = {"gerado_em": datetime.now().isoformat(timespec="seconds"),
       "janela_limpa": [LIMPO_INI, LIMPO_FIM], "janela_recente": [RECENTE_INI, None]}

limpo = sono[(sono["data"] >= LIMPO_INI) & (sono["data"] <= LIMPO_FIM)].copy()
per = sono[(sono["data"] >= RECENTE_INI)].copy()
res["n_limpo"] = int(len(limpo))
res["n_perto"] = int(len(per))

print("=" * 78)
print("  REM — 2ª RODADA, EM JANELA LIMPA (algoritmo estável + uso bom)")
print("=" * 78)
print(f"\n  janela limpa   {LIMPO_INI} → {LIMPO_FIM}   n = {len(limpo)} noites")
print(f"  janela recente {RECENTE_INI} → fim           n = {len(per)} noites")
print(f"  (toda a série: {len(sono)} noites)")

# ------------------------------------------------ H1 ------------------------
print("\n" + "-" * 78)
print("H1 — REM absoluto acompanha a duração do sono?")
res["H1"] = {
    "limpo_min_rem~dormido": sp(limpo["min_rem"], limpo["min_dormido"]),
    "limpo_pct_rem~dormido": sp(limpo["pct_rem"], limpo["min_dormido"]),
    "recente_min_rem~dormido": sp(per["min_rem"], per["min_dormido"]),
    "recente_pct_rem~dormido": sp(per["pct_rem"], per["min_dormido"]),
}
for k, v in res["H1"].items():
    print(f"   {k:34s} rho={v['rho']}  p={v['p']}  n={v['n']}")

# ------------------------------------------------ H3 ------------------------
print("\n" + "-" * 78)
print("H3 — FC de repouso e HRV estão acoplados ao REM?")
pares = [("shr", "FC de repouso"), ("shrv", "HRV noturna"),
         ("baseline_meio", "baseline HRV"), ("readiness", "readiness")]
res["H3_zerada"] = {}
res["H3_parcial"] = {}
print(f"   {'par':22s} {'rho (limpo)':>12s} {'rho (recente)':>14s} {'rho parcial|sono':>18s}")
for c, rot in pares:
    a = sp(limpo["shr"] if False else limpo[c], limpo["pct_rem"])
    b = sp(per[c], per["pct_rem"])
    pc = parcial(limpo, c, "pct_rem", "min_dormido")
    res["H3_zerada"][c] = dict(nome=rot, limpo=a, recente=b)
    res["H3_parcial"][c] = pc
    print(f"   {rot+' → REM%':22s} {str(a['rho']):>12s} {str(b['rho']):>14s} "
          f"{str(pc['rho']):>18s}")

print(f"\n   {'par':22s} {'rho (limpo)':>12s} {'rho (recente)':>14s}")
res["H3_min"] = {}
for c, rot in pares:
    a = sp(limpo[c], limpo["min_rem"])
    b = sp(per[c], per["min_rem"])
    res["H3_min"][c] = dict(nome=rot, limpo=a, recente=b)
    print(f"   {rot+' → REM min':22s} {str(a['rho']):>12s} {str(b['rho']):>14s}")

# ------------------------------------------------ H5 ------------------------
print("\n" + "-" * 78)
print("H5 — treino influencia o REM?")
res["H5"] = {}
for c, rot in [("km", "km no dia"), ("treinos", "nº treinos no dia")]:
    a = sp(limpo[c], limpo["pct_rem"])
    b = sp(limpo[c], limpo["min_rem"])
    res["H5"][c] = dict(nome=rot, com_pct=a, com_min=b)
    print(f"   {rot:18s} → REM%  rho={a['rho']} p={a['p']}   |  → REM min rho={b['rho']} p={b['p']}")

# lag do treino (dia anterior)
limpo["km_ant"] = limpo["km"].shift(1)
limpo["treinou_ant"] = (limpo["treinos"].shift(1).fillna(0) > 0).astype(int)
for c, rot in [("km_ant", "km no dia anterior")]:
    a = sp(limpo[c], limpo["pct_rem"])
    print(f"   {rot:18s} → REM%  rho={a['rho']} p={a['p']}")
    res["H5"][c] = a

# ------------------------------------------------ H2 ------------------------
print("\n" + "-" * 78)
print("H2 — houve rebote de REM depois do evento de medicação?")
print("   (rebote = REM% subindo DEPOIS do evento, não antes)")
q = {}
try:
    q = json.load(open(f"{OUT}/medicacao.json"))["quebra_fc_repouso"]
    print(f"   quebra da FC de repouso: {q['data_quebra']}  (t={q['t']}, p={q['p']})")
except Exception:
    pass
if q:
    corte = pd.Timestamp(q["data_quebra"])
    a = sono[sono["data"] < corte]["pct_rem"].dropna()
    b = sono[sono["data"] >= corte]["pct_rem"].dropna()
    _, p = stats.mannwhitneyu(a, b, alternative="two-sided")
    print(f"   REM% antes ({len(a)} noites): mediana {a.median():.1f}%")
    print(f"   REM% depois ({len(b)} noites): mediana {b.median():.1f}%")
    print(f"   delta {b.median()-a.median():+.1f} pp   p={p:.1e}")
    print("   -> rebote exigiria delta POSITIVO e significativo")
    res["H2"] = dict(corte=q["data_quebra"], antes=round(float(a.median()), 1),
                     depois=round(float(b.median()), 1),
                     delta=round(float(b.median() - a.median()), 1), p=float(f"{p:.2e}"))

# ------------------------------------------------ H4 ------------------------
print("\n" + "-" * 78)
print("H4 — a mudança de arquitetura é artefato de algoritmo? (granularidade)")
try:
    gran = json.load(open(f"{OUT}/granularidade.json"))
    print("   (ver report/granularidade.json)")
    res["H4"] = gran
except Exception:
    print("   granularidade.json ainda não gerado — rodar analise_granularidade.py")

# ------------------------------------------------ extra ---------------------
print("\n" + "-" * 78)
print("EXTRA — distribuição de REM% nas duas janelas")
for nome, g in [("limpa", limpo), ("recente", per)]:
    r = g["pct_rem"].dropna()
    if len(r) < 5:
        continue
    print(f"   {nome:8s} n={len(r):3d}  mediana {r.median():5.1f}%  "
          f"p25 {r.quantile(.25):5.1f}  p75 {r.quantile(.75):5.1f}  "
          f"| acima de 25%: {100*(r>25).mean():5.1f}%  abaixo de 20%: {100*(r<20).mean():5.1f}%")
    res.setdefault("distribuicao", {})[nome] = dict(
        n=int(len(r)), mediana=round(float(r.median()), 1),
        p25=round(float(r.quantile(.25)), 1), p75=round(float(r.quantile(.75)), 1),
        pct_acima25=round(100 * float((r > 25).mean()), 1),
        pct_abaixo20=round(100 * float((r < 20).mean()), 1))

with open(f"{OUT}/rem_avancado.json", "w") as f:
    json.dump(res, f, ensure_ascii=False, indent=1, default=str)
print(f"\n  salvo em {OUT}/rem_avancado.json")
