"""
analise_vitality.py — Baseline de HRV + readiness composto, taxa respiratória noturna,
gasto calórico, atividade diária e FC máxima medida.

Fontes:
  com.samsung.shealth.vitality_score        475 dias (baseline de HRV da própria Samsung)
  jsons/com.samsung.health.respiratory_rate 564 arquivos (~207k valores noturnos)
  com.samsung.shealth.calories_burned.details
  com.samsung.shealth.activity.day_summary
  com.samsung.shealth.exercise.max_heart_rate

Inspirado em Devasy/samsung-health-sdk (`hrv_readiness`, `daily_activity_profile`) e
tcgoetz/GarminDB (tabelas de resumo diário).

Uso: python analise_vitality.py <export> <saida.json>
"""
from __future__ import annotations

import glob
import json
import os
import sys
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sh_load import SamsungExport

from shtools import export_dir  # noqa: E402

EXPORT = sys.argv[1] if len(sys.argv) > 1 else str(export_dir())
OUT = sys.argv[2] if len(sys.argv) > 2 else "report/vitality.json"
# Início do período analisado (ISO, ex.: "2025-01-01"). Vazio = todo o histórico.
# Vale cortar os primeiros dias de um relógio recém-pareado: vêm incompletos e
# puxam as médias. Como isso varia por pessoa, é configuração, não data fixa.
PERIODO_INICIO = os.environ.get("SH_PERIODO_INICIO", "")

e = SamsungExport(EXPORT)
num = lambda s: pd.to_numeric(s, errors="coerce")
med = lambda v: (round(float(np.median(v)), 2), len(v)) if len(v) else (None, 0)


def noite_de(ts: pd.Timestamp) -> str:
    """Data do DESPERTAR: amostra após 18h pertence à noite seguinte."""
    return (ts + timedelta(days=1) if ts.hour >= 18 else ts).date().isoformat()


# ==================================================== 1. vitality / readiness
v = pd.DataFrame(e.table("com.samsung.shealth.vitality_score"))
v["data"] = pd.to_datetime(v.day_time, errors="coerce").dt.date.astype(str)
for c in ["total_score", "activity_score", "sleep_score", "shrv_score", "shr_score",
          "shrv_value", "shr_value", "shr_baseline_min", "shr_baseline_max",
          "shrv_baseline_min", "shrv_baseline_max", "sleep_regularity", "sleep_timing",
          "stable_hr_time_rate", "max_hr", "active_time", "mvpa_time", "sleep_duration"]:
    v[c] = num(v[c]) if c in v.columns else np.nan
if PERIODO_INICIO:
    v = v[v.data >= PERIODO_INICIO].sort_values("data")

# desvio do HRV contra o baseline que a PRÓPRIA Samsung calcula (não janela fixa)
v["baseline_meio"] = (v.shrv_baseline_min + v.shrv_baseline_max) / 2
v["hrv_desvio_pct"] = (v.shrv_value - v.baseline_meio) / v.baseline_meio * 100

print(f"vitality_score: {len(v)} dias ({v.data.min()} → {v.data.max()})")
for k, rot in [("total_score", "readiness composto"), ("sleep_score", "componente sono"),
               ("activity_score", "componente atividade"), ("shrv_score", "score HRV (shrv)"),
               ("shr_score", "score FC repouso (shr)"), ("shrv_value", "HRV (shrv_value)"),
               ("shr_value", "FC repouso (shr_value)"), ("sleep_regularity", "regularidade do sono"),
               ("sleep_timing", "horário do sono"), ("stable_hr_time_rate", "taxa FC estável"),
               ("max_hr", "FC máx configurada")]:
    m, n = med(v[k].dropna())
    if n:
        print(f"   {rot:<28} mediana {m:>8}   (n={n})")
m, n = med(v.hrv_desvio_pct.dropna())
print(f"   {'desvio de HRV vs baseline':<28} mediana {m:>7.1f}%  (n={n})")


# ============================================== 2. taxa respiratória noturna
ps = glob.glob(os.path.join(EXPORT, "jsons", "com.samsung.health.respiratory_rate",
                            "**", "*.binning_data.json"), recursive=True)
rr = []
for p in ps:
    try:
        with open(p, encoding="utf-8") as f:
            j = json.load(f)
    except Exception:
        continue
    for it in j:
        val = it.get("respiratory_rate") or 0
        t = it.get("start_time")
        if not t or not (4 <= val <= 60):
            continue
        rr.append((pd.Timestamp(t, unit="ms"), val))
df_rr = pd.DataFrame(rr, columns=["ts", "irpm"])
df_rr["data"] = df_rr.ts.apply(noite_de)
if PERIODO_INICIO:
    df_rr = df_rr[df_rr.data >= PERIODO_INICIO]
por_noite = df_rr.groupby("data").irpm.agg(
    irpm_mediana="median", irpm_p10=lambda s: s.quantile(.10),
    irpm_p90=lambda s: s.quantile(.90), n="count").reset_index()
por_noite["pct_baixo"] = df_rr[df_rr.irpm < 12].groupby("data").size().reindex(
    por_noite.data).fillna(0).values / por_noite.n.values * 100
print(f"\ntaxa respiratória: {len(df_rr):,} valores · {len(por_noite)} noites "
      f"({por_noite.data.min()} → {por_noite.data.max()})")
m, _ = med(por_noite.irpm_mediana.values)
print(f"   mediana por noite: {m} irpm")
print(f"   faixa entre noites: p10 {por_noite.irpm_mediana.quantile(.10):.1f} · "
      f"p90 {por_noite.irpm_mediana.quantile(.90):.1f}")
# ronco + respiração baixa = triagem de apneia
pct_baixo_geral = df_rr[df_rr.irpm < 12].shape[0] / len(df_rr) * 100
print(f"   amostras < 12 irpm: {pct_baixo_geral:.1f}%")


# ============================================================ 3. gasto calórico
cal = pd.DataFrame(e.table("com.samsung.shealth.calories_burned.details"))
cc = {c.split(".")[-1]: c for c in cal.columns}
cal["data"] = pd.to_datetime(cal[cc["create_time"]], errors="coerce").dt.date.astype(str)
cal["repouso"] = num(cal[cc["rest_calorie"]])
cal["ativa"] = num(cal[cc["active_calorie"]])
cal["tef"] = num(cal[cc["tef_calorie"]])
if PERIODO_INICIO:
    cal = cal[cal.data >= PERIODO_INICIO]
cal_dia = cal.groupby("data")[["repouso", "ativa", "tef"]].max().reset_index()
cal_dia["total"] = cal_dia[["repouso", "ativa", "tef"]].sum(axis=1)
m, n = med(cal_dia.ativa.dropna())
print(f"\ncalorias: {len(cal_dia)} dias · ativa mediana {m} kcal (n={n}) · "
      f"repouso {med(cal_dia.repouso.dropna())[0]} kcal")


# ========================================================== 4. atividade diária
ac = pd.DataFrame(e.table("com.samsung.shealth.activity.day_summary"))
ca = {c.split(".")[-1]: c for c in ac.columns}
ac["data"] = pd.to_datetime(ac[ca["create_time"]], errors="coerce").dt.date.astype(str)
ac["passos"] = num(ac[ca["step_count"]])
ac["tempo_ativo_min"] = num(ac[ca["active_time"]]) / 60000.0
if PERIODO_INICIO:
    ac = ac[ac.data >= PERIODO_INICIO]
ac_dia = ac.groupby("data")[["passos", "tempo_ativo_min"]].max().reset_index()
mp, np_ = med(ac_dia.passos.dropna())
mt, _ = med(ac_dia.tempo_ativo_min.dropna())
print(f"atividade: {len(ac_dia)} dias · passos mediana {mp:,.0f}/dia · "
      f"tempo ativo {mt:.0f} min/dia")


# ============================================================ 5. FC máx medida
mh = pd.DataFrame(e.table("com.samsung.shealth.exercise.max_heart_rate"))
if len(mh):
    mh["fc_max"] = num(mh.max_heart_rate)
    mh["data"] = pd.to_datetime(mh.start_time, errors="coerce").dt.date.astype(str)
    print(f"\nFC máx medida: {len(mh)} registros · máx {mh.fc_max.max():.0f} · "
          f"mediana {mh.fc_max.median():.0f}")
    print(f"   datas: {', '.join(mh.data.tolist()[:8])}")


# ===================================================== resumo por semestre
def sem(d):
    return f"{d[:4]}-S{1 if int(d[5:7]) <= 6 else 2}"


v["semestre"] = v.data.apply(sem)
sem_out = []
for k, g in v.groupby("semestre"):
    m_tot, _ = med(g.total_score.dropna())
    m_hrv, _ = med(g.shrv_value.dropna())
    m_des, _ = med(g.hrv_desvio_pct.dropna())
    sem_out.append(dict(semestre=k, dias=len(g), readiness=m_tot, shrv=m_hrv,
                        hrv_desvio_pct=m_des,
                        regularidade_sono=med(g.sleep_regularity.dropna())[0]))
print("\npor semestre (readiness / HRV / desvio vs baseline):")
for s in sorted(sem_out, key=lambda x: x["semestre"]):
    print(f"   {s['semestre']}  n={s['dias']:>3}  readiness {s['readiness']:>6}  "
          f"shrv {s['shrv']:>6}  desvio {s['hrv_desvio_pct']:>6}%")

json.dump(dict(
    gerado_em=datetime.now().isoformat(timespec="seconds"),
    proveniencia=dict(
        vitality="direto (Samsung)",
        desvio_hrv="derivado — (shrv_value − baseline_meio)/baseline_meio",
        rr_por_noite="direto (Samsung) agregado por nós; noite = data do despertar",
        baseline="baseline é da PRÓPRIA Samsung (shrv_baseline_min/max), não janela fixa"),
    vitality=dict(
        dias=len(v), resumo={k: med(v[k].dropna())[0] for k in
                             ["total_score", "sleep_score", "activity_score", "shrv_score",
                              "shr_score", "shrv_value", "shr_value", "sleep_regularity",
                              "sleep_timing", "stable_hr_time_rate", "max_hr",
                              "hrv_desvio_pct"]},
        por_semestre=sem_out,
        serie=[dict(data=r.data, readiness=r.total_score, sono=r.sleep_score,
                    atividade=r.activity_score, shrv=r.shrv_value, shr=r.shr_value,
                    desvio_pct=round(r.hrv_desvio_pct, 1) if pd.notna(r.hrv_desvio_pct) else None,
                    baseline_meio=round(r.baseline_meio, 1) if pd.notna(r.baseline_meio) else None)
               for r in v.itertuples()]),
    respiracao=dict(
        amostras=len(df_rr), noites=len(por_noite),
        mediana_geral=med(df_rr.irpm.values)[0],
        pct_abaixo_12=round(pct_baixo_geral, 1),
        por_noite=por_noite.round(2).to_dict("records")),
    calorias=dict(dias=len(cal_dia),
                  ativa_mediana=med(cal_dia.ativa.dropna())[0],
                  repouso_mediana=med(cal_dia.repouso.dropna())[0],
                  por_dia=cal_dia.round(1).to_dict("records")),
    atividade=dict(dias=len(ac_dia), passos_mediana=mp, tempo_ativo_min_mediana=mt,
                   por_dia=ac_dia.round(1).to_dict("records")),
    fc_max_medida=(dict(n=len(mh), maxima=float(mh.fc_max.max()),
                        mediana=float(mh.fc_max.median()),
                        registros=mh[["data", "fc_max"]].to_dict("records"))
                   if len(mh) else None)),
    open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\n→ {OUT}")
