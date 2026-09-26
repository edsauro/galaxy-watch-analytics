"""Validação cruzada: REM/profundo calculados por nós × campos da Samsung.

Compara as medianas que NÓS calculamos a partir dos estágios com os campos que o
próprio Samsung Health já traz prontos. É a checagem de sanidade do parser: se as
duas colunas não baterem, ou o mapeamento de estágios está errado ou a leitura
do export perdeu linha.

Uso: python3 val_sono.py [export_dir] [sono.json]
"""
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pandas as pd

from sh_load import SamsungExport
from shtools import export_dir

EXP = sys.argv[1] if len(sys.argv) > 1 else str(export_dir())
SONO = (sys.argv[2] if len(sys.argv) > 2
        else str(Path("report") / "sono.json"))

e = SamsungExport(EXP)
sl = pd.DataFrame(e.table("com.samsung.shealth.sleep"))
num = lambda s: pd.to_numeric(s, errors="coerce")

sam_rem = num(sl["total_rem_duration"]).dropna()
sam_leve = num(sl["total_light_duration"]).dropna()
print("Samsung  total_rem_duration  mediana:", round(sam_rem.median(), 1), "min  (n=%d)" % len(sam_rem))
print("Samsung  total_light_duration mediana:", round(sam_leve.median(), 1), "min  (n=%d)" % len(sam_leve))

d = json.load(open(SONO, encoding="utf-8"))
rem = [n["min_rem"] for n in d["noites"] if n.get("min_rem")]
leve = [n["min_leve"] for n in d["noites"] if n.get("min_leve")]
prof = [n["min_profundo"] for n in d["noites"] if n.get("min_profundo")]
print("Nosso    min_rem    mediana:", round(statistics.median(rem), 1), "min  (n=%d)" % len(rem))
print("Nosso    min_leve   mediana:", round(statistics.median(leve), 1), "min  (n=%d)" % len(leve))
print("Nosso    min_profundo mediana:", round(statistics.median(prof), 1), "min  (n=%d)" % len(prof))
print()
print("Diferença REM  :", round(statistics.median(rem) - sam_rem.median(), 1), "min")
print("Diferença leve :", round(statistics.median(leve) - sam_leve.median(), 1), "min")
print()
tot = [n["min_dormido"] for n in d["noites"] if n.get("min_dormido")]
print("soma dormido (leve+prof+rem) mediana:", round(statistics.median(tot), 1), "min")
print("horas dormidas mediana (do JSON)    :", d["resumo"]["horas_dormidas"]["mediana"] if "horas_dormidas" in d["resumo"] else "n/d")
print()
print("faixa de referência adulto: profundo 13-23% · REM 20-25% · leve 50-60%")
print("nosso: profundo %.1f%% · REM %.1f%% · leve %.1f%%" % (
    d["resumo"]["pct_profundo"]["mediana"], d["resumo"]["pct_rem"]["mediana"],
    d["resumo"]["pct_leve"]["mediana"]))
