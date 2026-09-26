"""
ecg_summary.py — Extrai e resume os ECG do export (Samsung Health Monitor).

Cada ECG é um PDF de 30 s (500 Hz, 1 derivação) com a classificação automática do
próprio aparelho. O CSV traz a data/hora e a FC média; o PDF traz o veredito.
Casa os dois pelo `datauuid`.

Gera: <out_dir>/ecg_registros.json
"""
from __future__ import annotations

import glob
import json
import os
import re
import subprocess
import sys
from collections import Counter

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from sh_load import SamsungExport

from shtools import export_dir  # noqa: E402

CLASSIF = {
    "Ritmo sinusal": "Ritmo sinusal (normal)",
    "Inconclusivo": "Inconclusivo",
    "Registro insatisfatório": "Registro insatisfatório (sinal ruim)",
    "Fibrilação atrial": "Fibrilação atrial",
}


def extrair_pdf(path: str) -> dict:
    try:
        txt = subprocess.run(["pdftotext", path, "-"], capture_output=True,
                             text=True, timeout=40).stdout
    except Exception:
        txt = ""
    classe = "?"
    if re.search(r"Ritmo sinusal", txt):
        classe = "Ritmo sinusal"
    elif re.search(r"Fibrila[çc][ãa]o atrial", txt, re.I) and "não exibe" not in txt.lower():
        classe = "Fibrilação atrial"
    elif re.search(r"Inconclusivo", txt):
        classe = "Inconclusivo"
    elif re.search(r"insatisfat[óo]ri", txt, re.I):
        classe = "Registro insatisfatório"
    m = re.search(r"Frequ[êe]ncia card[íi]aca m[ée]dia:\s*([\d,\.]+)", txt)
    fc = float(m.group(1).replace(",", ".")) if m else None
    sem_fa = bool(re.search(r"n[ãa]o exibe sinais de\s*f[ií]brila[çc][ãa]o", txt, re.I))
    return {"classificacao": classe, "fc_media_pdf": fc, "sem_fa": sem_fa}


def main():
    export = sys.argv[1] if len(sys.argv) > 1 else str(export_dir())
    out_dir = sys.argv[2] if len(sys.argv) > 2 else "report"
    os.makedirs(out_dir, exist_ok=True)

    e = SamsungExport(export)
    rows = e.table("com.samsung.health.ecg.2")
    pdfs = {os.path.basename(p).split(".")[0]: p
            for p in glob.glob(os.path.join(export, "files", "com.samsung.health.ecg", "*.pdf"))}

    regs = []
    for r in rows:
        uid = r.get("datauuid")
        info = extrair_pdf(pdfs[uid]) if uid in pdfs else {}
        regs.append({
            "uuid": uid,
            "data": r.get("start_time"),
            "fc_media_csv": float(r["mean_heart_rate"]) if r.get("mean_heart_rate") else None,
            "n_amostras": int(float(r["sample_count"])) if r.get("sample_count") else None,
            "freq_hz": int(float(r["sample_frequency"])) if r.get("sample_frequency") else None,
            **info,
        })
    df = pd.DataFrame(regs).sort_values("data").reset_index(drop=True)
    df.to_json(os.path.join(out_dir, "ecg_registros.json"), orient="records",
               force_ascii=False, indent=1)

    fcs = df["fc_media_pdf"].dropna()
    resumo = {
        "total": int(len(df)),
        "periodo": [str(df["data"].min())[:10], str(df["data"].max())[:10]],
        "duracao_s": int(df["n_amostras"].dropna().median() / df["freq_hz"].dropna().median())
                     if df["n_amostras"].notna().any() else None,
        "classificacoes": {k: int(v) for k, v in df["classificacao"].value_counts().items()},
        "sem_fibrilacao_confirmada": int(df["sem_fa"].sum()),
        "fc_media_mediana": float(fcs.median()) if len(fcs) else None,
        "fc_media_min": float(fcs.min()) if len(fcs) else None,
        "fc_media_max": float(fcs.max()) if len(fcs) else None,
        "n_bradicardia_lt60": int((fcs < 60).sum()),
        "n_normal_60_100": int(((fcs >= 60) & (fcs <= 100)).sum()),
        "inconclusivos_fc": [float(x) for x in df[df.classificacao == "Inconclusivo"]["fc_media_pdf"].dropna()],
    }
    with open(os.path.join(out_dir, "ecg_resumo.json"), "w", encoding="utf-8") as f:
        json.dump(resumo, f, ensure_ascii=False, indent=2)
    print(json.dumps(resumo, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
