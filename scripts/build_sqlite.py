"""
build_sqlite.py — Espelho SQLite consultável + tabelas de resumo.

Padrão arquitetural de tcgoetz/GarminDB: importa o bruto, deriva uma tabela de fatos
diária e publica resumos por semana / mês / semestre + views.

Cada agregação traz também a tabela `origem`, que declara a proveniência de cada
coluna (`direto` = Samsung armazenou · `derivado` = calculado aqui · `inferido`).

Uso: python build_sqlite.py <export> <dir_saida>
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
from datetime import datetime

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sh_load import SamsungExport

from shtools import export_dir  # noqa: E402

EXPORT = sys.argv[1] if len(sys.argv) > 1 else str(export_dir())
OUTDIR = sys.argv[2] if len(sys.argv) > 2 else "report"
DB = os.path.join(OUTDIR, "saude.db")
e = SamsungExport(EXPORT)
num = lambda s: pd.to_numeric(s, errors="coerce")


def ler_json(nome, chave=None):
    p = os.path.join(OUTDIR, nome)
    if not os.path.exists(p):
        return None
    d = json.load(open(p, encoding="utf-8"))
    return d if chave is None else d.get(chave)


def semestre(d: str) -> str:
    return f"{d[:4]}-S{1 if int(d[5:7]) <= 6 else 2}"


def semana(d: str) -> str:
    return pd.Timestamp(d).to_period("W-SUN").start_time.date().isoformat()


def mes(d: str) -> str:
    return d[:7]


# ============================================================ tabela de fatos
sono = pd.DataFrame(ler_json("sono.json", "noites") or [])
# Uma DATA pode ter mais de uma sessão (soneca). A tabela `dia` tem de ficar com UMA
# linha por data: usa-se o sono principal e a sonega vira coluna agregada.
if len(sono) and "principal" in sono.columns:
    # `soneca_min` já vem no registro do sono principal (gravado por analise_sono.py);
    # aqui só falta a CONTAGEM de sonecas, que não pode colidir com a coluna existente.
    sonecas = (sono[~sono.principal.fillna(False)]
               .groupby("data").agg(sonecas=("horas", "size")).reset_index())
    sono = sono[sono.principal.fillna(True)].copy()
    sono = sono.merge(sonecas, on="data", how="left")
    sono["sonecas"] = sono.sonecas.fillna(0).astype(int)
    if "soneca_min" not in sono.columns:
        sono["soneca_min"] = 0.0
    sono["soneca_min"] = pd.to_numeric(sono.soneca_min, errors="coerce").fillna(0)
else:
    sono["sonecas"], sono["soneca_min"] = 0, 0.0
vit = ler_json("vitality.json") or {}
respi = pd.DataFrame(vit.get("respiracao", {}).get("por_noite") or [])
cal = pd.DataFrame(vit.get("calorias", {}).get("por_dia") or [])
ativ = pd.DataFrame(vit.get("atividade", {}).get("por_dia") or [])
vserie = pd.DataFrame(vit.get("vitality", {}).get("serie") or [])
extras = ler_json("extras.json") or {}

ex = pd.DataFrame(e.exercise())
sess = pd.DataFrame([dict(
    data=str(r.get("start"))[:10], grupo=r.get("grupo"), tipo=r.get("type"),
    inicio=str(r.get("start")), duracao_min=r.get("duration_min"),
    distancia_km=r.get("distance_km"), pace_min_km=r.get("pace_min_km"),
    fc_media=r.get("mean_hr"), fc_max=r.get("max_hr"),
    velocidade_max_kmh=r.get("max_speed_kmh"), vo2_max=r.get("vo2_max"),
    em_foco=bool(r.get("em_foco")),
    fonte="com.samsung.shealth.exercise", proveniencia="direto") for r in ex.to_dict("records")])

# stress diário
sr = pd.DataFrame(e.table("com.samsung.shealth.stress"))
sr["ts"] = pd.to_datetime(sr.start_time, errors="coerce")
sr["score"] = num(sr.score)
sr = sr.dropna(subset=["ts", "score"])
sr["data"] = (sr.ts + pd.to_timedelta((sr.ts.dt.hour >= 18).astype(int), unit="D")).dt.date.astype(str)
stress = sr.groupby("data").agg(
    stress_medio=("score", "mean"), stress_max=("score", "max"),
    stress_n=("score", "size"), stress_n_alto=("score", lambda s: int((s >= 80).sum()))).reset_index()

# monta o dia
dias = pd.DataFrame({"data": sorted(set(
    (sono.data.tolist() if len(sono) else []) + (respi.data.tolist() if len(respi) else []) +
    (cal.data.tolist() if len(cal) else []) + (ativ.data.tolist() if len(ativ) else []) +
    (vserie.data.tolist() if len(vserie) else []) + stress.data.tolist()))})
for df, cols in [(sono, ["sleep_score", "eficiencia", "rec_mental", "rec_fisica",
                         "despertares_mov", "horas", "min_dormido", "pct_profundo",
                         "pct_rem", "pct_leve", "waso_min", "fragmentacao",
                         "ronco_episodios", "ronco_min", "sonecas", "soneca_min"]),
                 (respi, ["irpm_mediana", "irpm_p10", "irpm_p90", "pct_baixo"]),
                 (cal, ["repouso", "ativa", "tef", "total"]),
                 (ativ, ["passos", "tempo_ativo_min"]),
                 (vserie, ["readiness", "sono", "atividade", "shrv", "shr", "desvio_pct",
                           "baseline_meio"]),
                 (stress, ["stress_medio", "stress_max", "stress_n", "stress_n_alto"])]:
    if df is not None and len(df):
        dias = dias.merge(df, on="data", how="left")

# treino por dia (sempre cria as colunas, mesmo sem treino em_foco)
agr = pd.DataFrame(columns=["data", "treinos", "km", "min_treino"])
if len(sess):
    tf = sess[sess.em_foco]
    if len(tf):
        agr = tf.groupby("data").agg(
            treinos=("grupo", "size"), km=("distancia_km", "sum"),
            min_treino=("duracao_min", "sum")).reset_index()
dias = dias.merge(agr, on="data", how="left")

dias = dias.sort_values("data").reset_index(drop=True)
dias["ano"] = dias.data.str[:4]
dias["mes"] = dias.data.apply(mes)
dias["semana"] = dias.data.apply(semana)
dias["semestre"] = dias.data.apply(semestre)

# =============================================================== resumos
def resumo(chave: str, rotulo: str) -> pd.DataFrame:
    g = dias.groupby(chave)
    out = g.agg(
        dias=("data", "count"),
        noites=("sleep_score", "count"),
        sleep_score=("sleep_score", "median"),
        eficiencia=("eficiencia", "median"),
        horas_sono=("horas", "median"),
        pct_profundo=("pct_profundo", "median"),
        pct_rem=("pct_rem", "median"),
        waso_min=("waso_min", "median"),
        fragmentacao=("fragmentacao", "median"),
        irpm=("irpm_mediana", "median"),
        readiness=("readiness", "median"),
        shrv=("shrv", "median"),
        hrv_desvio_pct=("desvio_pct", "median"),
        stress_medio=("stress_medio", "median"),
        stress_n_alto=("stress_n_alto", "sum"),
        passos=("passos", "median"),
        tempo_ativo_min=("tempo_ativo_min", "median"),
        cal_ativa=("ativa", "median"),
        treinos=("treinos", "sum"), km=("km", "sum")).reset_index()
    return out.rename(columns={chave: "periodo"}).assign(tipo=rotulo)


sem = resumo("semana", "semana")
mesr = resumo("mes", "mes")
semr = resumo("semestre", "semestre")

ORIGEM = [
    ("sleep_score", "direto", "com.samsung.shealth.sleep", ""),
    ("eficiencia", "direto", "com.samsung.shealth.sleep", ""),
    ("rec_mental", "direto", "com.samsung.shealth.sleep", ""),
    ("rec_fisica", "direto", "com.samsung.shealth.sleep", ""),
    ("despertares_mov", "direto", "com.samsung.shealth.sleep", "PROXY de restlessness — a Samsung não expõe esse índice"),
    ("horas", "derivado", "com.samsung.shealth.sleep", "fim − início"),
    ("min_dormido", "derivado", "com.samsung.health.sleep_stage", "soma de leve+profundo+REM"),
    ("pct_profundo", "derivado", "com.samsung.health.sleep_stage", "profundo / dormido · ref. adulto 13–23%"),
    ("pct_rem", "derivado", "com.samsung.health.sleep_stage", "REM / dormido · ref. adulto 20–25%"),
    ("pct_leve", "derivado", "com.samsung.health.sleep_stage", "leve / dormido · ref. adulto 50–60%"),
    ("waso_min", "derivado", "com.samsung.health.sleep_stage", "acordado entre 1º e último trecho de sono"),
    ("fragmentacao", "derivado", "com.samsung.health.sleep_stage", "transições de estágio por hora"),
    ("ronco_episodios", "direto", "com.samsung.shealth.sleep_snoring", "série encerrada em out/2025"),
    ("irpm_mediana", "derivado", "jsons/com.samsung.health.respiratory_rate", "mediana da noite · ref. adulto 12–20 irpm"),
    ("passos", "direto", "com.samsung.shealth.activity.day_summary", ""),
    ("tempo_ativo_min", "direto", "com.samsung.shealth.activity.day_summary", "convertido de ms"),
    ("repouso", "direto", "com.samsung.shealth.calories_burned.details", "TMB"),
    ("ativa", "direto", "com.samsung.shealth.calories_burned.details", ""),
    ("readiness", "direto", "com.samsung.shealth.vitality_score", "total_score"),
    ("shrv", "direto", "com.samsung.shealth.vitality_score", "HRV da Samsung"),
    ("shr", "direto", "com.samsung.shealth.vitality_score", "FC de repouso da Samsung"),
    ("desvio_pct", "derivado", "com.samsung.shealth.vitality_score", "(shrv − baseline_meio)/baseline_meio · baseline é da própria Samsung"),
    ("stress_medio", "direto", "com.samsung.shealth.stress", "dia fisiológico começa às 18h"),
    ("stress_n_alto", "derivado", "com.samsung.shealth.stress", "contagem de score ≥ 80"),
    ("treinos", "derivado", "com.samsung.shealth.exercise", "apenas corrida e natação (em_foco)"),
    ("km", "direto", "com.samsung.shealth.exercise", "apenas corrida e natação"),
]

# =================================================================== gravar
os.makedirs(OUTDIR, exist_ok=True)
if os.path.exists(DB):
    os.remove(DB)
con = sqlite3.connect(DB)
dias.to_sql("dia", con, index=False)
sem.to_sql("semana", con, index=False)
mesr.to_sql("mes", con, index=False)
semr.to_sql("semestre", con, index=False)
if len(sess):
    sess.to_sql("treino", con, index=False)
if len(sono):
    sono.to_sql("noite", con, index=False)
pd.DataFrame(ORIGEM, columns=["coluna", "proveniencia", "fonte", "nota"]).to_sql(
    "origem", con, index=False)

con.executescript("""
CREATE VIEW v_resumo_mensal AS
  SELECT periodo, dias, noites, sleep_score, eficiencia, horas_sono,
         pct_profundo, pct_rem, waso_min, fragmentacao, irpm,
         readiness, shrv, hrv_desvio_pct, stress_medio, stress_n_alto,
         passos, tempo_ativo_min, treinos, km
  FROM mes ORDER BY periodo;

CREATE VIEW v_semestre AS
  SELECT periodo AS semestre, dias, noites, sleep_score, pct_profundo, pct_rem,
         waso_min, fragmentacao, readiness, shrv, stress_medio, km
  FROM semestre ORDER BY periodo;

CREATE VIEW v_proveniencia AS
  SELECT coluna, proveniencia, fonte, nota FROM origem ORDER BY proveniencia, coluna;

-- ---------------------------------------------------------------------------
-- Views "amigáveis": nomes legíveis em português, para consulta a olho nu
-- (e para navegar numa GUI sem precisar decorar 55 colunas cruas).
-- A coluna `tabela` em v_proveniencia continua valendo: estas views só renomeiam.
-- ---------------------------------------------------------------------------
CREATE VIEW v_dia AS
  SELECT data                                   AS data,
         passos                                 AS passos,
         tempo_ativo_min                        AS min_ativo,
         ROUND(ativa)                           AS kcal_ativa,
         ROUND(repouso)                          AS kcal_repouso,
         treinos                                AS treinos,
         ROUND(km, 2)                           AS km,
         sleep_score                            AS sono_score,
         eficiencia                             AS sono_eficiencia_pct,
         horas                                  AS horas_na_cama,
         ROUND(min_dormido)                     AS min_dormido,
         pct_profundo                           AS sono_profundo_pct,
         pct_rem                                AS sono_rem_pct,
         pct_leve                               AS sono_leve_pct,
         waso_min                               AS waso_min,
         fragmentacao                           AS fragmentacao_por_h,
         despertares_mov                        AS despertares_mov,
         sonecas                                AS sonecas,
         soneca_min                             AS soneca_min,
         ROUND(irpm_mediana, 1)                 AS resp_irpm,
         ROUND(readiness, 1)                    AS readiness,
         ROUND(shrv, 1)                         AS hrv,
         ROUND(shr, 1)                          AS fc_repouso,
         ROUND(desvio_pct, 1)                   AS hrv_desvio_pct,
         ROUND(stress_medio)                    AS stress_medio,
         stress_n_alto                          AS stress_picos_80
  FROM dia ORDER BY data DESC;

CREATE VIEW v_treino AS
  SELECT data                                   AS data,
         grupo                                  AS modalidade,
         ROUND(duracao_min)                     AS min,
         ROUND(distancia_km, 2)                 AS km,
         ROUND(pace_min_km, 2)                  AS pace_min_km,
         fc_media                               AS fc_media,
         fc_max                                 AS fc_max,
         ROUND(velocidade_max_kmh, 1)           AS vel_max_kmh,
         ROUND(vo2_max, 1)                      AS vo2max,
         em_foco                                AS no_relatorio
  FROM treino ORDER BY data DESC;

CREATE VIEW v_noite AS
  SELECT data                                   AS data,
         horas                                  AS horas_na_cama,
         ROUND(min_dormido)                     AS min_dormido,
         pct_profundo                           AS profundo_pct,
         pct_rem                                AS rem_pct,
         pct_leve                               AS leve_pct,
         ROUND(min_profundo)                    AS min_profundo,
         ROUND(min_rem)                         AS min_rem,
         waso_min                               AS waso_min,
         transicoes                             AS transicoes,
         fragmentacao                           AS fragmentacao_por_h,
         sleep_score                            AS sono_score,
         eficiencia                             AS eficiencia_pct,
         rec_mental                             AS rec_mental,
         rec_fisica                             AS rec_fisica,
         despertares_mov                        AS despertares_mov,
         ronco_episodios                        AS ronco_episodios
  FROM noite ORDER BY data DESC;
""")
con.commit()

print(f"→ {DB}")
for t in ["dia", "semana", "mes", "semestre", "treino", "noite", "origem"]:
    try:
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"   {t:<10} {n:>6} linhas")
    except Exception:
        pass
print("   views:", ", ".join(
    r[0] for r in con.execute(
        "SELECT name FROM sqlite_master WHERE type='view' ORDER BY name")))
print(f"\nperíodo coberto: {dias.data.min()} → {dias.data.max()} ({len(dias)} dias)")
cols = [c for c in dias.columns if c not in ("data", "ano", "mes", "semana", "semestre")]
preenchidas = [(c, int(dias[c].notna().sum())) for c in cols]
print("\npreenchimento das colunas do dia:")
for c, n in sorted(preenchidas, key=lambda x: -x[1]):
    print(f"   {c:<20} {n:>4}/{len(dias)}")
con.close()
