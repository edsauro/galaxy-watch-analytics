"""
sh_load.py — Loaders para export do Samsung Health (Samsung Health CSV/JSON export).

Formato do export:
  - Cada métrica tem um CSV com 2 linhas de cabeçalho:
      linha 1: "<tabela>,<versao>,<n>"  (metadados)
      linha 2: nomes das colunas
      linha 3+: dados
  - Muitos valores de sensores (FC, live data de exercício) ficam em
    jsons/<metric>/<bucket>/<uuid>.*.json
"""

from __future__ import annotations

import csv
import glob
import json
import os
import re
import warnings
from typing import Optional

import pandas as pd

warnings.filterwarnings("ignore")

# ----------------------------------------------------------------------------
# Mapa OFICIAL de códigos de exercício (Samsung Developer — Predefined Exercise Type)
# ----------------------------------------------------------------------------
EXERCISE_TYPE_MAP: dict[int, str] = {
    0: "Personalizado",
    1001: "Caminhada",
    1002: "Corrida (rua)",
    9001: "Pilates",
    9002: "Yoga",
    10001: "Alongamento",
    11007: "Ciclismo",
    13001: "Trilha (hiking)",
    14001: "Natação",
    14006: "Snorkel",
    15002: "Musculação (aparelho)",
    15003: "Bicicleta ergométrica",
    15005: "Esteira (jog/caminhada)",
}

# Grupos usados nas análises
RUN_TYPES = {1002, 15005}     # corrida de rua + esteira
SWIM_TYPES = {14001, 14006}   # natação (+ snorkel)
BIKE_TYPES = {11007, 15003}

# Modalidades EM FOCO (definido pelo usuário): apenas corrida e natação.
# Ciclismo, musculação, personalizado, caminhada, yoga etc. ficam fora do relatório.
FOCO_GRUPOS = {"Corrida", "Natação"}


def _read_csv(path: str) -> list[dict]:
    """Lê um CSV do export Samsung Health (pula a linha 1 de metadados)."""
    with open(path, newline="", encoding="utf-8-sig", errors="ignore") as fh:
        fh.readline()                      # metadados
        header = next(fh).rstrip("\n").split(",")
        return [dict(zip(header, row)) for row in csv.reader(fh)]


class SamsungExport:
    """Carrega e normaliza um diretório de export do Samsung Health."""

    def __init__(self, export_dir: str):
        self.dir = export_dir
        self.json_dir = os.path.join(export_dir, "jsons")
        self._csv = {os.path.basename(p): p for p in glob.glob(os.path.join(export_dir, "*.csv"))}

    # -- helpers ---------------------------------------------------------
    def _path(self, prefix: str) -> Optional[str]:
        """Caminho do CSV da tabela, por casamento EXATO.

        Dois cuidados, ambos por bugs já vistos:
        1) O sufixo de versão (".2", ".3") NÃO faz parte do nome do arquivo — as
           chamadas internas usam `com.samsung.shealth.exercise.2`, então ele é
           removido antes de casar.
        2) Comparar só com `startswith(prefix)` é um bug silencioso: "…shealth.sleep"
           casaria com "…shealth.sleep_combined.…csv" (31 linhas em vez de 737), e a
           ordem do glob não é determinística, então o resultado mudava.
        """
        d = re.sub(r"\.\d+$", "", prefix.rstrip("."))
        for name, p in self._csv.items():
            if name == f"{d}.csv":
                return p
        for name, p in self._csv.items():
            if name.startswith(d + ".") and name[len(d) + 1:].removesuffix(".csv").isdigit():
                return p
        return None

    def table(self, prefix: str) -> list[dict]:
        p = self._path(prefix)
        return _read_csv(p) if p else []

    @staticmethod
    def _num(v):
        try:
            f = float(v)
            return f
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _dt(v):
        if not v:
            return pd.NaT
        return pd.to_datetime(v, errors="coerce")

    # -- exercício -------------------------------------------------------
    def exercise(self) -> pd.DataFrame:
        """Todas as sessões de exercício, com tipo nomeado e métricas derivadas."""
        rows = self.table("com.samsung.shealth.exercise.2")
        K = "com.samsung.health.exercise."
        out = []
        for r in rows:
            t = self._num(r.get(K + "exercise_type"))
            dur = self._num(r.get(K + "duration"))       # ms
            dist = self._num(r.get(K + "distance"))      # m
            sp = self._num(r.get(K + "mean_speed"))      # m/s
            d = {
                "uuid": r.get(K + "datauuid"),
                "type_code": int(t) if t is not None else None,
                "start": self._dt(r.get(K + "start_time")),
                "end": self._dt(r.get(K + "end_time")),
                "duration_min": (dur / 60000.0) if dur else None,
                "distance_km": (dist / 1000.0) if dist is not None else None,
                "speed_kmh": (sp * 3.6) if sp is not None else None,
                "mean_hr": self._num(r.get(K + "mean_heart_rate")),
                "max_hr": self._num(r.get(K + "max_heart_rate")),
                "calories": self._num(r.get(K + "calorie")),
                "max_speed_kmh": (self._num(r.get(K + "max_speed")) or 0) * 3.6 or None,
                "altitude_gain": self._num(r.get(K + "altitude_gain")),
                "comment": (r.get(K + "comment") or "").strip() or None,
                "title": (r.get("title") or "").strip() or None,
                "vo2_max": self._num(r.get(K + "vo2_max")),
            }
            d["type"] = EXERCISE_TYPE_MAP.get(d["type_code"], f"código {d['type_code']}")
            # Separação corrida × caminhada: se em algum momento passou de 10 km/h, é corrida
            # (a modalidade "esteira" do Samsung mistura jogging e caminhada).
            vmax = d["max_speed_kmh"] or 0
            if d["type_code"] == 1002:
                d["grupo"] = "Corrida"
            elif d["type_code"] in (1001, 15005):
                d["grupo"] = "Corrida" if vmax > 10 else "Caminhada"
            else:
                d["grupo"] = d["type"]

            # Classificação fina do ciclismo (falsos positivos de carro no trânsito).
            # É um módulo OPCIONAL e deliberadamente externo ao repositório: a
            # regra dele depende de coordenadas pessoais (que trechos são
            # deslocamento de carro e não pedal). Sem o módulo, todo ciclismo
            # conta como treino real — que é o comportamento conservador.
            if d["type_code"] == 11007:
                try:
                    from correcoes import classificar_ciclismo  # type: ignore
                except ImportError:
                    d["situacao"], d["motivo"] = "real", None
                else:
                    dia = (d["start"].strftime("%Y-%m-%d")
                           if d["start"] is not pd.NaT else "")
                    d["situacao"], d["motivo"] = classificar_ciclismo(dia)
                    if d["situacao"] != "real":
                        d["grupo"] = "(ciclismo descartado)"
            else:
                d["situacao"], d["motivo"] = "real", None

            # Foco do relatório: só corrida e natação (pedido do usuário).
            d["em_foco"] = d["grupo"] in FOCO_GRUPOS
            if d["distance_km"] and d["duration_min"]:
                d["pace_min_km"] = d["duration_min"] / d["distance_km"]
            else:
                d["pace_min_km"] = None
            out.append(d)
        df = pd.DataFrame(out)
        if not df.empty:
            df = df.sort_values("start").reset_index(drop=True)
            df["ano"] = df["start"].dt.year
            df["mes"] = df["start"].dt.to_period("M").astype(str)
        return df

    def livedata(self, uuid: str) -> pd.DataFrame:
        """Série temporal (1 Hz) de uma sessão: FC, velocidade, cadência, distância."""
        from samsung_health_sdk import SamsungHealthParser
        from samsung_health_sdk.metrics.exercise import ExerciseMetric
        em = ExerciseMetric(os.path.join(self.dir))
        try:
            return em.load_run_livedata(uuid)
        except Exception:
            return pd.DataFrame()

    # -- frequência cardíaca --------------------------------------------
    def hr_bins(self) -> pd.DataFrame:
        """Todos os bins de FC (tipicamente 1 min) do export."""
        pat = os.path.join(self.json_dir, "com.samsung.shealth.tracker.heart_rate", "*", "*.json")
        recs = []
        for p in glob.glob(pat):
            try:
                with open(p, encoding="utf-8") as fh:
                    data = json.load(fh)
            except Exception:
                continue
            for b in data:
                if "start_time" not in b:
                    continue
                recs.append({
                    "ts": pd.to_datetime(b["start_time"], unit="ms", utc=True),
                    "hr": b.get("heart_rate"),
                    "hr_min": b.get("heart_rate_min"),
                    "hr_max": b.get("heart_rate_max"),
                })
        df = pd.DataFrame(recs)
        if not df.empty:
            # horário local (America/Sao_Paulo, UTC-3)
            df["ts"] = df["ts"].dt.tz_convert("America/Sao_Paulo").dt.tz_localize(None)
            df = df.sort_values("ts").reset_index(drop=True)
        return df

    # -- sono ------------------------------------------------------------
    def sleep(self) -> pd.DataFrame:
        rows = self.table("com.samsung.shealth.sleep.2")
        K = "com.samsung.health.sleep."
        out = []
        for r in rows:
            st, en = self._dt(r.get(K + "start_time")), self._dt(r.get(K + "end_time"))
            out.append({
                "uuid": r.get(K + "datauuid"),
                "start": st, "end": en,
                "horas": ((en - st).total_seconds() / 3600.0) if (st is not pd.NaT and en is not pd.NaT) else None,
                "score": self._num(r.get("sleep_score")),
                "eficiencia": self._num(r.get("efficiency")),
                "fonte": r.get(K + "pkg_name"),
            })
        df = pd.DataFrame(out)
        if not df.empty:
            df = df.dropna(subset=["start"]).sort_values("start").reset_index(drop=True)
        return df

    def sleep_stages(self) -> pd.DataFrame:
        rows = self.table("com.samsung.health.sleep_stage.2")
        STAGE = {40001: "Acordado", 40002: "Leve", 40003: "Profundo", 40004: "REM"}
        out = []
        for r in rows:
            st, en = self._dt(r.get("start_time")), self._dt(r.get("end_time"))
            s = self._num(r.get("stage"))
            out.append({
                "sleep_id": r.get("sleep_id"), "stage_code": int(s) if s else None,
                "stage": STAGE.get(int(s) if s else -1, str(s)),
                "start": st, "end": en,
                "min": ((en - st).total_seconds() / 60.0) if (st is not pd.NaT and en is not pd.NaT) else None,
            })
        return pd.DataFrame(out)

    # -- diários ---------------------------------------------------------
    def daily_steps(self) -> pd.DataFrame:
        rows = self.table("com.samsung.shealth.step_daily_trend.2")
        out = []
        for r in rows:
            out.append({
                "dia": (r.get("day_time") or "")[:10],
                "passos": self._num(r.get("count")),
                "dist_km": (self._num(r.get("distance")) or 0) / 1000.0 or None,
                "cal": self._num(r.get("calorie")),
            })
        df = pd.DataFrame(out)
        if not df.empty:
            df["dia"] = pd.to_datetime(df["dia"], errors="coerce")
            df = df.dropna(subset=["dia"]).sort_values("dia").reset_index(drop=True)
        return df

    def weight(self) -> pd.DataFrame:
        rows = self.table("com.samsung.health.weight.2")
        out = []
        for r in rows:
            out.append({
                "ts": self._dt(r.get("start_time")),
                "peso": self._num(r.get("weight")),
                "imc": self._num(r.get("body_fat")),
                "gordura_pct": self._num(r.get("body_fat")),
                "massa_magra": self._num(r.get("fat_free_mass")),
                "tmb": self._num(r.get("basal_metabolic_rate")),
                "musculo_esq": self._num(r.get("skeletal_muscle_mass")),
            })
        df = pd.DataFrame(out)
        if not df.empty:
            df = df.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)
        return df

    def simple_series(self, prefix: str, value_col: str, time_col: str = "start_time") -> pd.DataFrame:
        """Série genérica: ts + valor (ex.: SpO2, temperatura, HRV, stress)."""
        rows = self.table(prefix)
        out = [{"ts": self._dt(r.get(time_col)), "valor": self._num(r.get(value_col))} for r in rows]
        df = pd.DataFrame(out)
        if not df.empty:
            df = df.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True)
        return df

    def exercise_max_hr(self) -> pd.DataFrame:
        rows = self.table("com.samsung.shealth.exercise.max_heart_rate.2")
        out = [{"ts": self._dt(r.get("start_time")),
                "fc_max": self._num(r.get("max_heart_rate")),
                "fc_limiar": self._num(r.get("at_heart_rate"))} for r in rows]
        df = pd.DataFrame(out)
        return df.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True) if not df.empty else df

    def recovery_hr(self) -> pd.DataFrame:
        rows = self.table("com.samsung.shealth.exercise.recovery_heart_rate.2")
        out = [{"ts": self._dt(r.get("start_time")),
                "exercise_id": r.get("exercise_id"),
                "fc_recuperacao": self._num(r.get("heart_rate"))} for r in rows]
        df = pd.DataFrame(out)
        return df.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True) if not df.empty else df

    def alerted_stress(self) -> pd.DataFrame:
        """Momentos em que o relógio disparou alerta de stress alto (sem valor de score)."""
        rows = self.table("com.samsung.shealth.alerted_stress.2")
        out = [{"ts": self._dt(r.get("start_time"))} for r in rows]
        df = pd.DataFrame(out)
        return df.dropna(subset=["ts"]).sort_values("ts").reset_index(drop=True) if not df.empty else df
