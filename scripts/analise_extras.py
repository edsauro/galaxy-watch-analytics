"""
analise_extras.py — HRV (SDNN/RMSSD), recuperação de FC pós-esforço e stress.

Gera report/extras.json com as séries e os resumos usados nos relatórios.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import Counter

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sh_load import SamsungExport, _read_csv

from shtools import export_dir  # noqa: E402

EXPORT = sys.argv[1] if len(sys.argv) > 1 else str(export_dir())
OUT = sys.argv[2] if len(sys.argv) > 2 else "report/extras.json"


def indexar_jsons(base: str) -> dict:
    """basename -> caminho completo, para achar os binning/live JSONs."""
    idx = {}
    for root, _, files in os.walk(base):
        for f in files:
            idx[f] = os.path.join(root, f)
    return idx


def serie_por_basename(idx, nome):
    p = idx.get(nome)
    if not p:
        return None
    try:
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def main():
    e = SamsungExport(EXPORT)
    idx = indexar_jsons(e.json_dir)
    out = {}

    # ---------------- HRV ----------------
    rows = _read_csv(e._path("com.samsung.health.hrv.2"))
    recs = []
    for r in rows:
        bn = r.get("binning_data")
        d = serie_por_basename(idx, bn) if bn else None
        if not isinstance(d, list):
            continue
        for x in d:
            if "sdnn" not in x:
                continue
            recs.append({"ts": pd.to_datetime(x.get("start_time"), unit="ms", utc=True),
                         "sdnn": x.get("sdnn"), "rmssd": x.get("rmssd")})
    hrv = pd.DataFrame(recs)
    if not hrv.empty:
        hrv["ts"] = hrv["ts"].dt.tz_convert("America/Sao_Paulo").dt.tz_localize(None)
        hrv = hrv.sort_values("ts").reset_index(drop=True)
        hrv["dia"] = hrv["ts"].dt.normalize()
        hrv["hora"] = hrv["ts"].dt.hour
        diario = hrv.groupby("dia").agg(sdnn=("sdnn", "median"), rmssd=("rmssd", "median"),
                                        n=("sdnn", "count")).reset_index()
        diario = diario[diario["n"] >= 5]
        out["hrv"] = {
            "n_amostras": int(len(hrv)),
            "n_dias": int(len(diario)),
            "sdnn_mediana": round(float(hrv.sdnn.median()), 1),
            "rmssd_mediana": round(float(hrv.rmssd.median()), 1),
            "sdnn_p10": round(float(hrv.sdnn.quantile(.10)), 1),
            "sdnn_p90": round(float(hrv.sdnn.quantile(.90)), 1),
            "rmssd_p10": round(float(hrv.rmssd.quantile(.10)), 1),
            "rmssd_p90": round(float(hrv.rmssd.quantile(.90)), 1),
            "por_hora": {int(k): round(float(v), 1) for k, v in
                         hrv.groupby("hora")["rmssd"].median().items()},
            "primeiros_90d": round(float(diario.head(90)["rmssd"].median()), 1) if len(diario) > 20 else None,
            "ultimos_90d": round(float(diario.tail(90)["rmssd"].median()), 1) if len(diario) > 20 else None,
            "diario": [{"dia": str(d)[:10], "rmssd": round(float(r), 1), "sdnn": round(float(s), 1)}
                       for d, r, s in zip(diario.dia, diario.rmssd, diario.sdnn)],
        }
        hrv.to_pickle(os.path.join(os.path.dirname(OUT), ".cache", "hrv.pkl")) if False else None

    # ---------------- Recuperação de FC ----------------
    rows = _read_csv(e._path("com.samsung.shealth.exercise.recovery_heart_rate.2"))
    # mapa exercício -> tipo
    exrows = _read_csv(e._path("com.samsung.shealth.exercise.2"))
    K = "com.samsung.health.exercise."
    tipo_por_uuid = {r.get(K + "datauuid"): r.get(K + "exercise_type") for r in exrows}
    TIPO = {0: "Personalizado", 1001: "Caminhada", 1002: "Corrida (rua)", 9002: "Yoga",
            11007: "Ciclismo", 14001: "Natação", 15002: "Musculação", 15005: "Esteira"}

    rec = []
    for r in rows:
        bn = r.get("heart_rate")
        d = serie_por_basename(idx, bn) if bn else None
        if not isinstance(d, dict):
            continue
        cd = d.get("chart_data") or []
        if len(cd) < 5:
            continue
        t = np.array([x.get("elapsed_time", 0) for x in cd], dtype=float) / 1000.0
        hr = np.array([x.get("heart_rate", np.nan) for x in cd], dtype=float)
        ok = ~np.isnan(hr)
        if ok.sum() < 5:
            continue
        t, hr = t[ok], hr[ok]
        pico = float(np.nanmax(hr))
        i0 = int(np.nanargmax(hr))
        t0 = t[i0]
        def fc_em(seg):
            m = (t - t0) >= seg
            if not m.any():
                return None
            j = int(np.argmin(np.abs(t - (t0 + seg))))
            return float(hr[j])
        fc60, fc120 = fc_em(60), fc_em(120)
        rec.append({
            "ts": pd.to_datetime(r.get("start_time"), errors="coerce"),
            "exercicio": TIPO.get(int(tipo_por_uuid.get(r.get("exercise_id")) or -1), "?"),
            "fc_pico": pico, "fc_60s": fc60, "fc_120s": fc120,
            "hrr1": (pico - fc60) if fc60 else None,
            "hrr2": (pico - fc120) if fc120 else None,
            "duracao_curva_s": float(t[-1] - t[0]),
        })
    recd = pd.DataFrame(rec).dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)
    if not recd.empty:
        v1 = recd["hrr1"].dropna()
        v2 = recd["hrr2"].dropna()
        out["recuperacao"] = {
            "n": int(len(recd)),
            "hrr1_mediana": round(float(v1.median()), 1),
            "hrr1_p25": round(float(v1.quantile(.25)), 1),
            "hrr1_p75": round(float(v1.quantile(.75)), 1),
            "hrr1_min": round(float(v1.min()), 1), "hrr1_max": round(float(v1.max()), 1),
            "hrr1_abaixo_12": int((v1 < 12).sum()), "hrr1_total": int(len(v1)),
            "hrr2_mediana": round(float(v2.median()), 1) if len(v2) else None,
            "por_modalidade": {k: {"n": int(g["hrr1"].notna().sum()),
                                   "hrr1_mediana": round(float(g["hrr1"].median()), 1)}
                               for k, g in recd.groupby("exercicio") if g["hrr1"].notna().any()},
            "piores": [{"data": str(r.ts)[:16], "modalidade": r.exercicio, "hrr1": round(r.hrr1, 1)}
                       for r in recd.nlargest(0, "hrr1").itertuples()] if False else
                      [{"data": str(r.ts)[:16], "modalidade": r.exercicio,
                        "hrr1": round(float(r.hrr1), 1)}
                       for r in recd.dropna(subset=["hrr1"]).nsmallest(5, "hrr1").itertuples()],
            "serie": [{"data": str(r.ts)[:10], "hrr1": round(float(r.hrr1), 1),
                       "modalidade": r.exercicio}
                      for r in recd.dropna(subset=["hrr1"]).itertuples()],
        }

    # ---------------- Stress ----------------
    rows = _read_csv(e._path("com.samsung.shealth.stress.2"))
    st = pd.DataFrame([{
        "ts": pd.to_datetime(r.get("start_time"), errors="coerce"),
        "score": float(r["score"]) if r.get("score") not in (None, "") else None,
        "min": float(r["min"]) if r.get("min") not in (None, "") else None,
        "max": float(r["max"]) if r.get("max") not in (None, "") else None,
        "algorithm": r.get("algorithm"),
    } for r in rows]).dropna(subset=["ts"])
    st = st.sort_values("ts").reset_index(drop=True)
    st["hora"] = st.ts.dt.hour
    st["dia"] = st.ts.dt.normalize()
    validos = st.dropna(subset=["score"])
    faixas = pd.cut(validos.score, [-0.1, 29, 59, 79, 100],
                    labels=["Baixo (0-29)", "Normal (30-59)", "Alto (60-79)", "Muito alto (80-100)"])
    out["stress"] = {
        "n_registros": int(len(st)),
        "n_com_score": int(len(validos)),
        "periodo": [str(st.ts.min())[:10], str(st.ts.max())[:10]],
        "mediana": round(float(validos.score.median()), 1),
        "media": round(float(validos.score.mean()), 1),
        "p90": round(float(validos.score.quantile(.90)), 1),
        "max": round(float(validos.score.max()), 1),
        "faixas": {str(k): int(v) for k, v in faixas.value_counts().sort_index().items()},
        "pct_alto_ou_mais": round(float((validos.score >= 60).mean() * 100), 1),
        "por_hora": {int(k): round(float(v), 1) for k, v in validos.groupby("hora")["score"].median().items()},
        "algoritmo": st.algorithm.dropna().value_counts().to_dict() if "algorithm" in st else {},
        "top_piores": [{"data": str(r.ts)[:16], "score": float(r.score)}
                       for r in validos.nlargest(10, "score").itertuples()],
        "serie_diaria": [{"dia": str(d)[:10], "score": round(float(v), 1)}
                         for d, v in validos.groupby("dia")["score"].median().items()],
    }

    # alerted_stress (eventos de stress alto)
    try:
        al = _read_csv(e._path("com.samsung.shealth.alerted_stress.2"))
        out["stress"]["alertas"] = len(al)
    except Exception:
        out["stress"]["alertas"] = None

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2, default=str)
    print("OK →", OUT)
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk not in ("diario", "serie", "por_hora")}
                      for k, v in out.items()}, ensure_ascii=False, indent=1)[:3500])


if __name__ == "__main__":
    main()
