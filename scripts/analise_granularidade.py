#!/usr/bin/env python3
"""
analise_granularidade.py — Testa se a mudança na arquitetura do sono (profundo
subindo, REM estável/caindo) é fisiológica ou artefato de mudança de algoritmo.

Dois testes:
  1. ESTRUTURA: quantos segmentos de estágio o app grava por noite e qual a
     duração mediana de um segmento. Um salto aqui = mudança de resolução do
     algoritmo, e as % de fase deixam de ser comparáveis entre antes/depois.
  2. VERSÃO: agrupa as noites por versão do app Samsung Health (create_sh_ver)
     e compara %profundo e %REM. Se a % salta na fronteira de versão, é
     algoritmo, não fisiologia.

Uso: python analysis/analise_granularidade.py <export_dir> report
"""
import glob
import json
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sh_load import SamsungExport  # noqa: E402

from shtools import export_dir  # noqa: E402

EXP = sys.argv[1] if len(sys.argv) > 1 else glob.glob(str(export_dir()))[0]
OUT = sys.argv[2] if len(sys.argv) > 2 else "report"

e = SamsungExport(EXP)
rows = e.table("com.samsung.health.sleep_stage")
df = pd.DataFrame(rows)
df = df[df["pkg_name"] == "com.sec.android.app.shealth"].copy()
df["st"] = pd.to_datetime(df["start_time"], errors="coerce")
df["en"] = pd.to_datetime(df["end_time"], errors="coerce")
df["dur"] = (df["en"] - df["st"]).dt.total_seconds() / 60.0
df["ym"] = df["st"].dt.to_period("M")
df["ver"] = df["create_sh_ver"].astype(str)

COD = {"40001": "acordado", "40002": "leve", "40003": "profundo", "40004": "REM"}

print("=" * 78)
print("  GRANULARIDADE DA ESTADIAGEM — artefato de algoritmo?")
print("=" * 78)

# ---- 1. estrutura por mês ---------------------------------------------------
print("\n1) Segmentos por noite e duração mediana do segmento, por mês")
print(f"   {'mês':8s} {'noites':>7s} {'segs/noite':>11s} {'dur.med.seg':>12s} "
      f"{'%profundo':>10s} {'%REM':>7s}")
g = df.groupby(["ym", "sleep_id"]).agg(segs=("dur", "size"), durmed=("dur", "median"))
por_mes = g.groupby("ym").agg(noites=("segs", "size"), segs=("segs", "median"),
                              durmed=("durmed", "median"))

# % de fase por noite (a partir dos segmentos)
dur_stage = df.groupby(["ym", "sleep_id", "stage"])["dur"].sum().unstack(fill_value=0)
for c in ["40001", "40002", "40003", "40004"]:
    if c not in dur_stage.columns:
        dur_stage[c] = 0.0
tot = dur_stage[["40002", "40003", "40004"]].sum(axis=1)
pct = pd.DataFrame({
    "prof": 100 * dur_stage["40003"] / tot.replace(0, np.nan),
    "rem": 100 * dur_stage["40004"] / tot.replace(0, np.nan),
})
pm = pct.groupby(level=0).median()
por_mes = por_mes.join(pm)

estrutura_mes = []
for ym, r in por_mes.iterrows():
    print(f"   {ym} {int(r.noites):7d} {r.segs:11.1f} {r.durmed:12.2f} "
          f"{r.prof:10.1f} {r.rem:7.1f}")
    estrutura_mes.append(dict(mes=str(ym), noites=int(r.noites),
                              segs_noite=round(float(r.segs), 1),
                              dur_med_seg_min=round(float(r.durmed), 2),
                              pct_profundo=round(float(r.prof), 1),
                              pct_rem=round(float(r.rem), 1)))

# ---- 2. por versão do app ---------------------------------------------------
print("\n2) Por VERSÃO do app Samsung Health (a fronteira decide a hipótese)")
noite_ver = df.groupby(["sleep_id", "ver"]).agg(
    n=("dur", "size")).reset_index().sort_values("n", ascending=False)
noite_ver = noite_ver.drop_duplicates("sleep_id")          # versão dominante da noite
noite_ver = noite_ver.merge(pct.reset_index().rename(columns={"level_1": "sleep_id"}),
                            on="sleep_id", how="inner")
por_ver = noite_ver.groupby("ver").agg(
    noites=("sleep_id", "size"), segs=("n", "median"),
    prof=("prof", "median"), rem=("rem", "median")).sort_index()

por_versao = []
for v, r in por_ver.iterrows():
    if r.noites < 5:
        continue
    print(f"   versão {v:10s}  noites={int(r.noites):3d}  segs/noite={r.segs:6.1f}  "
          f"%profundo={r.prof:5.1f}  %REM={r.rem:5.1f}")
    por_versao.append(dict(versao=v, noites=int(r.noites), segs_noite=round(float(r.segs), 1),
                           pct_profundo=round(float(r.prof), 1), pct_rem=round(float(r.rem), 1)))

# ---- 3. o ponto crítico -----------------------------------------------------
print("\n3) Conclusão do teste")
jun = df[df["ym"] >= "2025-06"]
mai = df[df["ym"] < "2025-06"]
s_jun = jun.groupby("sleep_id").size().median()
s_mai = mai.groupby("sleep_id").size().median()
d_jun = jun.groupby("sleep_id")["dur"].median().median()
d_mai = mai.groupby("sleep_id")["dur"].median().median()
print(f"   ANTES de jun/2025: {s_mai:.0f} segmentos/noite, segmento de {d_mai:.2f} min")
print(f"   DEPOIS            : {s_jun:.0f} segmentos/noite, segmento de {d_jun:.2f} min")
print(f"   -> a resolução da estadiagem mudou. %profundo e %REM NÃO são")
print("      diretamente comparáveis antes/depois dessa fronteira.")

res = dict(gerado_em=datetime.now().isoformat(timespec="seconds"),
           estrutura_por_mes=estrutura_mes, por_versao=por_versao,
           antes=dict(segs_noite=float(s_mai), dur_seg=float(d_mai)),
           depois=dict(segs_noite=float(s_jun), dur_seg=float(d_jun)),
           fronteira="2025-06")
with open(f"{OUT}/granularidade.json", "w") as f:
    json.dump(res, f, ensure_ascii=False, indent=1)
print(f"\n  salvo em {OUT}/granularidade.json")
