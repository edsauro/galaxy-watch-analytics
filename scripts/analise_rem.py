#!/usr/bin/env python3
"""
analise_rem.py — Relação do sono REM (minutos e %) com as demais métricas do export.

Pergunta do usuário: noites com REM total > 1,5 h (90 min) são preocupantes?
O que esse grupo tem de diferente?

Saída: report/rem.json  +  resumo no stdout.

Uso: python analysis/analise_rem.py report
"""
import json
import sqlite3
import sys
from datetime import datetime

import numpy as np
import pandas as pd
from scipy import stats

LIMIAR_REM_MIN = 90.0  # 1,5 h

OUT = sys.argv[1] if len(sys.argv) > 1 else "report"
DB = f"{OUT}/saude.db"


def sp(x, y):
    """Spearman + Pearson, ignorando NaN e exigindo n mínimo."""
    m = pd.notna(x) & pd.notna(y)
    x, y = np.asarray(x)[m], np.asarray(y)[m]
    if len(x) < 20 or np.std(x) == 0 or np.std(y) == 0:
        return dict(n=int(len(x)), rho=None, p=None, r=None)
    rho, p = stats.spearmanr(x, y)
    r, _ = stats.pearsonr(x, y)
    return dict(n=int(len(x)), rho=round(float(rho), 3),
                p=float(f"{p:.2e}"), r=round(float(r), 3))


def mw(a, b):
    """Mann-Whitney + tamanho de efeito (r de rank-biserial)."""
    a, b = np.asarray(a)[pd.notna(a)], np.asarray(b)[pd.notna(b)]
    if len(a) < 5 or len(b) < 5:
        return dict(n_a=len(a), n_b=len(b), p=None, efeito=None)
    u, p = stats.mannwhitneyu(a, b, alternative="two-sided")
    rb = 2 * u / (len(a) * len(b)) - 1
    return dict(n_a=int(len(a)), n_b=int(len(b)), p=float(f"{p:.2e}"),
                efeito=round(float(rb), 3))


con = sqlite3.connect(DB)
df = pd.read_sql(
    "SELECT d.*, v.fc_repouso FROM dia d LEFT JOIN v_dia v ON d.data = v.data", con)
con.close()

# ---- Noites válidas: sono principal, com estágios, e REM medido -------------
d = df[(df["principal"] == 1) & (df["tem_fases"] == 1) & df["min_rem"].notna()].copy()
d["data"] = pd.to_datetime(d["data"])
d = d.sort_values("data").reset_index(drop=True)

# soneca não entra (já excluída por principal==1, mas garantimos)
d = d[(d["soneca_min"].fillna(0) == 0) | (d["min_rem"] > 0)]

d["rem_h"] = d["min_rem"] / 60.0
d["alto_rem"] = d["min_rem"] > LIMIAR_REM_MIN

# dia de treino anterior (o treino de hoje afeta a noite de hoje)
d["treinou"] = (d["treinos"].fillna(0) > 0).astype(int)
d["treino_km_ant"] = d["km"].shift(1)
d["tef_ant"] = d["tef"].shift(1)
d["dia_semana"] = d["data"].dt.dayofweek

res = {}
res["gerado_em"] = datetime.now().isoformat(timespec="seconds")
res["limiar_rem_min"] = LIMIAR_REM_MIN
res["n_noites"] = int(len(d))
res["janela"] = [str(d["data"].min().date()), str(d["data"].max().date())]

# ---- 1. Distribuição do REM total ------------------------------------------
res["distribuicao"] = {
    "mediana_min": round(float(d["min_rem"].median()), 1),
    "media_min": round(float(d["min_rem"].mean()), 1),
    "p10_min": round(float(d["min_rem"].quantile(.10)), 1),
    "p90_min": round(float(d["min_rem"].quantile(.90)), 1),
    "max_min": round(float(d["min_rem"].max()), 1),
    "min_min": round(float(d["min_rem"].min()), 1),
    "mediana_pct": round(float(d["pct_rem"].median()), 1),
    "pct_acima_90min": round(100 * float(d["alto_rem"].mean()), 1),
    "n_acima_90min": int(d["alto_rem"].sum()),
    "n_acima_120min": int((d["min_rem"] > 120).sum()),
    "n_acima_25pct": int((d["pct_rem"] > 25).sum()),
    "n_acima_30pct": int((d["pct_rem"] > 30).sum()),
}

# ---- 2. REM depende do tempo total de sono? --------------------------------
res["rem_vs_horas"] = {
    "min_rem ~ horas_dormidas": sp(d["min_rem"], d["min_dormido"]),
    "pct_rem ~ horas_dormidas": sp(d["pct_rem"], d["min_dormido"]),
}

# ---- 3. Correlações: REM (min e %) contra o resto ---------------------------
colunas = {
    "min_dormido": "horas dormidas",
    "sleep_score": "score de sono",
    "eficiencia": "eficiência (%)",
    "min_profundo": "sono profundo (min)",
    "pct_profundo": "sono profundo (%)",
    "waso_min": "tempo acordado (WASO)",
    "fragmentacao": "fragmentação (despertares/h)",
    "despertares_mov": "despertares por movimento",
    "transicoes": "transições entre fases",
    "rec_mental": "recuperação mental",
    "rec_fisica": "recuperação física",
    "readiness": "prontidão (readiness)",
    "shrv": "HRV noturna (sHRV)",
    "baseline_meio": "linha de base HRV",
    "fc_repouso": "FC de repouso",
    "repouso": "calorias de repouso",
    "stress_medio": "stress médio do dia",
    "stress_n_alto": "nº de picos de stress",
    "irpm_mediana": "respiração noturna (irpm)",
    "passos": "passos do dia",
    "tef": "gasto energético total",
    "treinos": "nº de treinos no dia",
    "km": "km treinados no dia",
    "treino_km_ant": "km treinados no dia anterior",
}
res["correlacoes"] = {}
for c, nome in colunas.items():
    if c not in d.columns:
        continue
    res["correlacoes"][c] = {
        "nome": nome,
        "com_min_rem": sp(d["min_rem"], d[c]),
        "com_pct_rem": sp(d["pct_rem"], d[c]),
    }

# ---- 4. Grupo REM alto vs o resto ------------------------------------------
a = d[d["alto_rem"]]
b = d[~d["alto_rem"]]
res["grupos"] = {"n_alto": int(len(a)), "n_normal": int(len(b))}
res["comparacao_grupos"] = {}
for c, nome in colunas.items():
    if c not in d.columns or c not in ("min_dormido", "sleep_score", "eficiencia",
                                       "min_profundo", "pct_profundo", "waso_min",
                                       "fragmentacao", "despertares_mov", "rec_mental",
                                       "rec_fisica", "readiness", "shrv", "fc_repouso",
                                       "stress_medio", "irpm_mediana",
                                       "treino_km_ant", "km"):
        continue
    res["comparacao_grupos"][c] = {
        "nome": nome,
        "mediana_rem_alto": round(float(a[c].median()), 1) if a[c].notna().any() else None,
        "mediana_rem_normal": round(float(b[c].median()), 1) if b[c].notna().any() else None,
        "teste": mw(a[c].values, b[c].values),
    }

# ---- 5. Tendência temporal do REM (testa se o REM deriva ao longo dos anos) ---
d["t"] = (d["data"] - d["data"].min()).dt.days
res["tendencia_temporal"] = {
    "min_rem ~ tempo": sp(d["min_rem"], d["t"]),
    "pct_rem ~ tempo": sp(d["pct_rem"], d["t"]),
    "horas ~ tempo": sp(d["min_dormido"], d["t"]),
}
por_ano = {}
for ano, g in d.groupby(d["data"].dt.year):
    por_ano[int(ano)] = {
        "n": int(len(g)),
        "rem_mediana_min": round(float(g["min_rem"].median()), 1),
        "rem_mediana_pct": round(float(g["pct_rem"].median()), 1),
        "horas_mediana": round(float(g["min_dormido"].median()) / 60, 2),
        "prof_pct": round(float(g["pct_profundo"].median()), 1),
        "score": round(float(g["sleep_score"].median()), 1),
        "pct_noites_acima_90": round(100 * float((g["min_rem"] > 90).mean()), 1),
    }
res["por_ano"] = por_ano

# por semestre, para ver a forma da curva
por_sem = []
for (ano, sem), g in d.groupby([d["data"].dt.year, (d["data"].dt.month > 6).map({False: 1, True: 2})]):
    por_sem.append({
        "periodo": f"{ano}-S{sem}", "n": int(len(g)),
        "rem_mediana_min": round(float(g["min_rem"].median()), 1),
        "rem_mediana_pct": round(float(g["pct_rem"].median()), 1),
        "pct_acima_90": round(100 * float((g["min_rem"] > 90).mean()), 1),
    })
res["por_semestre"] = por_sem

# ---- 6. As noites de REM mais alto (quem são elas?) -------------------------
top = d.nlargest(15, "min_rem")[["data", "min_rem", "pct_rem", "min_dormido",
                                 "min_profundo", "waso_min", "fragmentacao",
                                 "sleep_score", "fc_repouso", "shrv", "stress_medio",
                                 "irpm_mediana", "km"]].copy()
top["data"] = top["data"].dt.strftime("%Y-%m-%d")
res["top15_rem"] = json.loads(top.to_json(orient="records"))

with open(f"{OUT}/rem.json", "w") as f:
    json.dump(res, f, ensure_ascii=False, indent=1)

# ============================ RELATÓRIO ====================================
print("=" * 74)
print("  REM — relação com as demais métricas do Samsung Health")
print("=" * 74)
D = res["distribuicao"]
print(f"\nNoites válidas (sono principal, com estágios): {res['n_noites']}")
print(f"Janela: {res['janela'][0]} → {res['janela'][1]}")
print(f"\nREM mediano: {D['mediana_min']} min ({D['mediana_pct']}% do sono)")
print(f"Faixa p10–p90: {D['p10_min']}–{D['p90_min']} min   máx: {D['max_min']} min")
print(f"\nNoites com REM > 90 min (1,5 h): {D['n_acima_90min']}  ({D['pct_acima_90min']}%)")
print(f"Noites com REM > 120 min (2 h):  {D['n_acima_120min']}")
print(f"Noites com REM% > 25%:           {D['n_acima_25pct']}")
print(f"Noites com REM% > 30%:           {D['n_acima_30pct']}")

print("\n" + "-" * 74)
print("1) O REM alto é só sono longo?")
for k, v in res["rem_vs_horas"].items():
    print(f"   {k:34s} rho={v['rho']:+.3f}  p={v['p']:.1e}  n={v['n']}")

print("\n" + "-" * 74)
print("2) Correlações com REM (min e %) — ordenado por |rho| em min_rem")
print(f"   {'métrica':30s} {'rho(min_rem)':>13s} {'p':>9s}  {'rho(%REM)':>10s}")
linhas = [(c, v) for c, v in res["correlacoes"].items() if v["com_min_rem"]["rho"] is not None]
linhas.sort(key=lambda kv: -abs(kv[1]["com_min_rem"]["rho"]))
for c, v in linhas:
    a_ = v["com_min_rem"]; b_ = v["com_pct_rem"]
    print(f"   {v['nome']:30s} {a_['rho']:+13.3f} {a_['p']:9.1e}  "
          f"{(b_['rho'] if b_['rho'] is not None else float('nan')):+10.3f}")

print("\n" + "-" * 74)
print(f"3) REM alto (>{LIMIAR_REM_MIN:.0f} min, n={res['grupos']['n_alto']}) "
      f"vs normal (n={res['grupos']['n_normal']})")
print(f"   {'métrica':28s} {'REM alto':>10s} {'normal':>10s} {'p':>9s} {'efeito':>7s}")
for c, v in res["comparacao_grupos"].items():
    t = v["teste"]
    if t["p"] is None:
        continue
    marca = "  <<" if t["p"] < 0.05 else ""
    print(f"   {v['nome']:28s} {v['mediana_rem_alto']:10.1f} {v['mediana_rem_normal']:10.1f} "
          f"{t['p']:9.1e} {t['efeito']:+7.2f}{marca}")

print("\n" + "-" * 74)
print("4) Tendência do REM ao longo do tempo")
for k, v in res["tendencia_temporal"].items():
    print(f"   {k:22s} rho={v['rho']:+.3f}  p={v['p']:.1e}  n={v['n']}")

print(f"\n   {'ano':6s} {'n':>5s} {'REM min':>8s} {'REM %':>7s} {'horas':>7s} "
      f"{'prof%':>6s} {'score':>6s} {'>90min':>7s}")
for ano, v in res["por_ano"].items():
    print(f"   {ano:6d} {v['n']:5d} {v['rem_mediana_min']:8.1f} {v['rem_mediana_pct']:7.1f} "
          f"{v['horas_mediana']:7.2f} {v['prof_pct']:6.1f} {v['score']:6.1f} "
          f"{v['pct_noites_acima_90']:6.1f}%")

print(f"\n   {'semestre':9s} {'n':>5s} {'REM min':>8s} {'REM %':>7s} {'>90min':>8s}")
for v in res["por_semestre"]:
    print(f"   {v['periodo']:9s} {v['n']:5d} {v['rem_mediana_min']:8.1f} "
          f"{v['rem_mediana_pct']:7.1f} {v['pct_acima_90']:7.1f}%")

print("\n" + "-" * 74)
print("5) As 15 noites de maior REM absoluto")
print(f"   {'data':11s} {'REM':>6s} {'%':>5s} {'h':>5s} {'prof':>5s} {'WASO':>5s} "
      f"{'frag':>5s} {'score':>5s} {'FCrep':>6s} {'HRV':>5s}")
for r in res["top15_rem"]:
    def g(k, casas=1):
        v = r.get(k)
        return "  -  " if v is None or (isinstance(v, float) and np.isnan(v)) else f"{v:.{casas}f}"
    print(f"   {r['data']:11s} {g('min_rem'):>6s} {g('pct_rem'):>5s} "
          f"{g('min_dormido',0):>5s} {g('min_profundo',0):>5s} {g('waso_min',0):>5s} "
          f"{g('fragmentacao',1):>5s} {g('sleep_score',0):>5s} {g('fc_repouso',0):>6s} "
          f"{g('shrv',0):>5s}")

print("\n" + "=" * 74)
print(f"  salvo em {OUT}/rem.json")
print("=" * 74)
