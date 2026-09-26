"""
analise_sono.py — Fases, qualidade e ronco por noite.

Fontes:
  com.samsung.health.sleep_stage   48.083 segmentos  (40001 acordado, 40002 leve,
                                                      40003 profundo, 40004 REM)
  com.samsung.shealth.sleep         737 noites       (sleep_score, efficiency,
                                                      recuperação, movement_awakening)
  com.samsung.shealth.sleep_snoring  57 episódios

Ligação: sleep_stage.sleep_id == sleep.datauuid  (652 noites casam).

Inspirado em Devasy/samsung-health-sdk (`sleep_sessions`), reimplementado aqui.
`movement_awakening` é usado como PROXY de "restlessness score" — a Samsung não
expõe esse índice; está documentado como proxy, não como a métrica do repo.

Uso: python analise_sono.py <export> <saida.json>
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sh_load import SamsungExport

from shtools import export_dir  # noqa: E402

EXPORT = sys.argv[1] if len(sys.argv) > 1 else str(export_dir())
OUT = sys.argv[2] if len(sys.argv) > 2 else "report/sono.json"

ESTAGIOS = {40001: "acordado", 40002: "leve", 40003: "profundo", 40004: "rem"}
ACORDADO, LEVE, PROFUNDO, REM = 40001, 40002, 40003, 40004
PROXY_RESTLESS = "movement_awakening"   # proxy rotulado de restlessness

e = SamsungExport(EXPORT)


def num(s):
    return pd.to_numeric(s, errors="coerce")


# ---------------------------------------------------------------- carregar
st = pd.DataFrame(e.table("com.samsung.health.sleep_stage"))
st["start"] = pd.to_datetime(st.start_time, errors="coerce")
st["end"] = pd.to_datetime(st.end_time, errors="coerce")
st["stage"] = num(st.stage).astype("Int64")
st["dur_min"] = (st.end - st.start).dt.total_seconds() / 60
st = st.dropna(subset=["start", "end"]).sort_values(["sleep_id", "start"])

# Só estágios medidos pelo RELÓGIO. O app "Sleep as Android" (celular) usa outro
# algoritmo e produz séries incompatíveis (ex.: 63% de profundo em 2023).
n_todos = len(st)
st = st[st.pkg_name == "com.sec.android.app.shealth"].copy()
print(f"segmentos: {n_todos} → {len(st)} (descartados {n_todos-len(st)} do Sleep as Android)")

sl = pd.DataFrame(e.table("com.samsung.shealth.sleep"))
COL = {c.split(".")[-1]: c for c in sl.columns}
sl["inicio"] = pd.to_datetime(sl[COL["start_time"]], errors="coerce")
sl["fim"] = pd.to_datetime(sl[COL["end_time"]], errors="coerce")
sl["uuid"] = sl[COL["datauuid"]]
for c in ["sleep_score", "efficiency", "mental_recovery", "physical_recovery",
          "movement_awakening", "deep_score", "rem_score", "total_rem_duration",
          "total_light_duration", "sleep_duration", "wake_score"]:
    sl[c] = num(sl[c]) if c in sl.columns else np.nan

sn = pd.DataFrame(e.table("com.samsung.shealth.sleep_snoring"))
if len(sn):
    sn["inicio"] = pd.to_datetime(sn.start_time, errors="coerce")
    sn["dur_min"] = num(sn.duration) / 60000.0


# ------------------------------------------------- fases por noite (sleep_id)
def fases(g: pd.DataFrame) -> dict:
    g = g.sort_values("start")
    por = g.groupby("stage").dur_min.sum()
    leve, prof, rem, acord = (por.get(LEVE, 0.0), por.get(PROFUNDO, 0.0),
                              por.get(REM, 0.0), por.get(ACORDADO, 0.0))
    dormido = leve + prof + rem
    # WASO: tempo acordado ENTRE o 1º e o último trecho de sono (exclui latência)
    sono = g[g.stage.isin([LEVE, PROFUNDO, REM])]
    waso = 0.0
    if len(sono) > 1:
        ini, fim = sono.start.iloc[0], sono.end.iloc[-1]
        waso = g[(g.stage == ACORDADO) & (g.start >= ini) & (g.end <= fim)].dur_min.sum()
    trans = int((g.stage != g.stage.shift()).sum() - 1)
    return dict(
        min_leve=round(leve, 1), min_profundo=round(prof, 1),
        min_rem=round(rem, 1), min_acordado=round(acord, 1),
        min_dormido=round(dormido, 1),
        pct_profundo=round(prof / dormido * 100, 1) if dormido else None,
        pct_rem=round(rem / dormido * 100, 1) if dormido else None,
        pct_leve=round(leve / dormido * 100, 1) if dormido else None,
        waso_min=round(waso, 1),
        transicoes=trans,
        fragmentacao=round(trans / (dormido / 60), 1) if dormido else None,
    )


fases_por_id = {sid: fases(g) for sid, g in st.groupby("sleep_id") if sid}

# -------------------------------------------------------------- montar noites
noites = []
for _, r in sl.iterrows():
    if pd.isna(r["inicio"]) or pd.isna(r["fim"]):
        continue
    # a noite pertence à data do DESPERTAR (manhã)
    data = r["fim"].date().isoformat()
    f = fases_por_id.get(r["uuid"], {})
    ron = sn[(sn.inicio >= r["inicio"]) & (sn.inicio <= r["fim"])] if len(sn) else sn
    noites.append(dict(
        data=data,
        uuid=r["uuid"],
        inicio=r["inicio"].isoformat(timespec="minutes"),
        fim=r["fim"].isoformat(timespec="minutes"),
        horas=round((r["fim"] - r["inicio"]).total_seconds() / 3600, 2),
        sleep_score=r["sleep_score"], eficiencia=r["efficiency"],
        rec_mental=r["mental_recovery"], rec_fisica=r["physical_recovery"],
        despertares_mov=r["movement_awakening"],   # PROXY de restlessness
        prof_score=r["deep_score"], rem_score=r["rem_score"],
        tem_fases=bool(f),
        ronco_episodios=int(len(ron)) if len(sn) else 0,
        ronco_min=round(float(ron.dur_min.sum()), 1) if len(ron) else 0.0,
        **f))
noites.sort(key=lambda n: n["data"])
# Janela do relatório: o export começa em 10/12/2024.
# Início do período analisado (ISO, ex.: "2025-01-01"). Vazio = todo o histórico.
# Vale cortar os primeiros dias de um relógio recém-pareado: vêm incompletos e
# puxam as médias. Como isso varia por pessoa, é configuração, não data fixa.
PERIODO_INICIO = os.environ.get("SH_PERIODO_INICIO", "")
if PERIODO_INICIO:
    noites = [n for n in noites if n["data"] >= PERIODO_INICIO]

# Uma DATA pode ter mais de uma sessão de sono (soneca, ou sono dividido). O "sono
# principal" é a sessão mais longa do dia; as outras viram sonega. Sem separar, 93
# sonecas (mediana 1,7 h) entravam nas medianas como se fossem noites — o que
# puxava % profundo, % REM e WASO para baixo.
def _horas(n):
    return n.get("horas") or 0.0


por_dia: dict = {}
for n in noites:
    por_dia.setdefault(n["data"], []).append(n)
n_sonega = 0
for data, g in por_dia.items():
    if len(g) == 1:
        g[0]["principal"], g[0]["soneca_min"] = True, 0.0
        continue
    g.sort(key=lambda x: -_horas(x))
    g[0]["principal"] = True
    g[0]["soneca_min"] = round(sum(_horas(x) * 60 for x in g[1:]))
    for x in g[1:]:
        x["principal"], x["soneca_min"] = False, 0.0
        n_sonega += 1

com_fases = [n for n in noites if n["tem_fases"]]
principais = [n for n in noites if n.get("principal") and n["tem_fases"]]
print(f"sessões de sono: {len(noites)} · sendo {n_sonega} sonecas descartadas das medianas")
print(f"noites principais com fases: {len(principais)}")


def med(vals):
    v = [x for x in vals if x is not None and not (isinstance(x, float) and np.isnan(x))]
    return (round(float(np.median(v)), 1), round(float(np.mean(v)), 1), len(v)) if v else (None, None, 0)


print(f"noites totais: {len(noites)} · com fases: {len(com_fases)} "
      f"({com_fases[0]['data']} → {com_fases[-1]['data']})" if com_fases else "sem fases")

resumo = {}
for k, rot in [("sleep_score", "sleep_score"), ("eficiencia", "eficiência"),
               ("rec_mental", "recuperação mental"), ("rec_fisica", "recuperação física"),
               ("despertares_mov", "despertares por movimento (proxy)"),
               ("pct_profundo", "% profundo"), ("pct_rem", "% REM"), ("pct_leve", "% leve"),
               ("waso_min", "WASO (min)"), ("fragmentacao", "fragmentação (/h)"),
               ("horas", "horas na cama"), ("min_dormido", "horas dormidas (min)")]:
    m, mu, n = med([x.get(k) for x in (principais or com_fases or noites)])
    if n:
        resumo[k] = dict(rotulo=rot, mediana=m, media=mu, n=n)
        print(f"   {rot:<36} mediana {m:>7}   (n={n})")

# ------------------------------------------------------------ por semestre
def semestre(d: str) -> str:
    dt = datetime.fromisoformat(d)
    return f"{dt.year}-S{1 if dt.month <= 6 else 2}"


por_sem = {}
for n in principais:
    s = por_sem.setdefault(semestre(n["data"]), [])
    s.append(n)
sem_out = []
for k in sorted(por_sem):
    g = por_sem[k]
    sem_out.append(dict(
        semestre=k, noites=len(g),
        horas=round(float(np.median([x["horas"] for x in g])), 2),
        sleep_score=med([x["sleep_score"] for x in g])[0],
        eficiencia=med([x["eficiencia"] for x in g])[0],
        pct_profundo=med([x["pct_profundo"] for x in g])[0],
        pct_rem=med([x["pct_rem"] for x in g])[0],
        waso_min=med([x["waso_min"] for x in g])[0],
        fragmentacao=med([x["fragmentacao"] for x in g])[0],
        despertares=med([x["despertares_mov"] for x in g])[0]))
print("\npor semestre:")
for s in sem_out:
    print(f"   {s['semestre']}  n={s['noites']:>3}  score {s['sleep_score']}  "
          f"prof {s['pct_profundo']}%  rem {s['pct_rem']}%  waso {s['waso_min']}min  "
          f"frag {s['fragmentacao']}/h")

# ronco
ron_total = sum(n["ronco_episodios"] for n in noites)
ron_min = sum(n["ronco_min"] for n in noites)
noites_com_ronco = [n for n in noites if n["ronco_episodios"]]
print(f"\nronco: {ron_total} episódios em {len(noites_com_ronco)} noites · {ron_min:.1f} min totais")
if noites_com_ronco:
    print(f"   período: {noites_com_ronco[0]['data']} → {noites_com_ronco[-1]['data']}")

json.dump(dict(
    gerado_em=datetime.now().isoformat(timespec="seconds"),
    fontes=dict(
        fases="com.samsung.health.sleep_stage (40001 acordado, 40002 leve, 40003 profundo, 40004 REM)",
        qualidade="com.samsung.shealth.sleep",
        ronco="com.samsung.shealth.sleep_snoring",
        ligacao="sleep_stage.sleep_id == sleep.datauuid",
        atribuicao="noite pertence à data do despertar",
        proveniencia="direto (Samsung) — exceto pct_*, waso, transicoes, fragmentacao = derivado",
        proxy_restlessness="movement_awakening (a Samsung não expõe índice de restlessness)"),
    resumo=resumo, por_semestre=sem_out,
    ronco=dict(episodios=ron_total, minutos=round(ron_min, 1),
               noites=len(noites_com_ronco),
               periodo=[noites_com_ronco[0]["data"], noites_com_ronco[-1]["data"]]
               if noites_com_ronco else None),
    noites=noites),
    open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\n→ {OUT}")
