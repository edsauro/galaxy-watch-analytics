"""shtools — configuração e utilitários comuns da suíte.

Nada aqui é específico de uma pessoa: o diretório do export do Samsung Health é
resolvido em tempo de execução, nesta ordem de precedência:

  1. variável de ambiente ``SH_EXPORT`` (caminho completo do diretório);
  2. o diretório ``samsunghealth_*`` mais recente dentro de ``SH_DATA_DIR``
     (padrão: ``data/``), que é onde o export costuma ser descompactado;
  3. erro explícito, dizendo exatamente o que fazer.

Os scripts também aceitam o diretório como primeiro argumento na linha de
comando, o que tem precedência sobre tudo.
"""
from __future__ import annotations

import os
import re
from pathlib import Path

__all__ = [
    "DATA_DIR", "OUT_DIR", "export_dir", "out_dir", "db_path",
    "EXERCISE_TYPE_OFICIAL", "EXERCISE_TYPE_PT", "nome_exercicio",
    "RUN_TYPES", "SWIM_TYPES", "BIKE_TYPES",
    "descobrir_exports", "classificar_atividade", "parametros_do_zip",
]

# --------------------------------------------------------------------------- #
# Diretórios
# --------------------------------------------------------------------------- #
DATA_DIR = Path(os.environ.get("SH_DATA_DIR", "data"))
OUT_DIR = Path(os.environ.get("SH_OUT_DIR", "report"))


def descobrir_exports(base: str | Path | None = None) -> list[Path]:
    """Todos os diretórios de export ``samsunghealth_*`` sob ``base``, do mais
    novo para o mais antigo.

    O export da Samsung vem como ``samsunghealth_<nome>_<timestamp>.zip``. Ao
    descompactar, sai um diretório com esse mesmo nome — que carrega o nome da
    pessoa. Por isso nada aqui depende dele: casamos só pelo prefixo.
    """
    b = Path(base) if base else DATA_DIR
    if not b.exists():
        return []
    achados = [p for p in b.iterdir()
               if p.is_dir() and p.name.startswith("samsunghealth")]
    achados.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return achados


def export_dir(explicito: str | Path | None = None) -> Path:
    """Resolve o diretório do export. Ver o docstring do módulo."""
    if explicito:
        p = Path(explicito)
        if not p.exists():
            raise SystemExit(f"[shtools] diretório do export não existe: {p}")
        return p
    do_ambiente = os.environ.get("SH_EXPORT")
    if do_ambiente:
        p = Path(do_ambiente)
        if not p.exists():
            raise SystemExit(f"[shtools] SH_EXPORT aponta para algo inexistente: {p}")
        return p
    achados = descobrir_exports()
    if achados:
        return achados[0]
    zips = sorted(DATA_DIR.glob("samsunghealth_*.zip")) if DATA_DIR.exists() else []
    if zips:
        raise SystemExit(
            f"[shtools] achei o zip {zips[0].name} mas ele não está descompactado.\n"
            f"  Rode:  unzip -q '{zips[0]}' -d {DATA_DIR}/")
    raise SystemExit(
        "[shtools] não encontrei nenhum export do Samsung Health.\n"
        "  1. Peça o export em Samsung Health > Configurações > Baixar dados pessoais;\n"
        f"  2. Descompacte em '{DATA_DIR}/' (ou aponte SH_DATA_DIR para o lugar certo);\n"
        "  3. Ou passe o caminho como primeiro argumento do script.")


def out_dir(explicito: str | Path | None = None) -> Path:
    """Diretório de saída (relatórios, gráficos, banco). Criado se faltar."""
    p = Path(explicito) if explicito else OUT_DIR
    p.mkdir(parents=True, exist_ok=True)
    return p


def db_path(out: str | Path | None = None) -> Path:
    """Caminho do SQLite gerado por build_sqlite.py."""
    return out_dir(out) / "saude.db"


# --------------------------------------------------------------------------- #
# Códigos de exercício — tabela OFICIAL da Samsung
# --------------------------------------------------------------------------- #
# Fonte: Samsung Developer, "Predefined Exercise Type"
#   https://developer.samsung.com/health/android/data/api-reference/EXERCISE_TYPE.html
# Nomes transcritos VERBATIM da tabela oficial (em inglês, como publicado) para
# não introduzir erro de tradução. Conferido em 2026-09-26.
EXERCISE_TYPE_OFICIAL: dict[int, str] = {
    1001: 'Walking',
    1002: 'Running',
    2001: 'Baseball, general',
    2002: 'Softball, general',
    2003: 'Cricket',
    3001: 'Golf, general',
    3002: 'Billiards',
    3003: 'Bowling, alley',
    4001: 'Hockey',
    4002: 'Rugby, touch, non-competitive',
    4003: 'Basketball, general',
    4004: 'Football, general (Soccer)',
    4005: 'Handball, general',
    4006: 'American football, general, touch',
    5002: 'Beach volleyball',
    6001: 'Squash, general',
    6002: 'Tennis, general',
    6003: 'Badminton, competitive',
    6004: 'Table tennis',
    7002: 'Boxing, in ring',
    7003: 'Martial arts, moderate pace (Judo, Jujitsu, Karate, Taekwondo)',
    8001: 'Ballet, general, rehearsal or class',
    8002: 'Dancing, general (Fork, Irish step, Polka)',
    8003: 'Ballroom dancing, fast',
    9001: 'Pilates',
    9002: 'Yoga',
    10001: 'Stretching',
    10003: 'Hula-hooping',
    10004: 'Push-ups (Press-ups)',
    10005: 'Pull-ups (Chin-up)',
    10006: 'Sit-ups',
    10007: 'Circuit training, moderate effort',
    10008: 'Mountain climbers',
    10009: 'Jumping Jacks',
    10010: 'Burpee',
    10011: 'Bench press',
    10012: 'Squats',
    10013: 'Lunges',
    10014: 'Leg presses',
    10015: 'Leg extensions',
    10016: 'Leg curls',
    10017: 'Back extensions',
    10018: 'Lat pull-downs',
    10019: 'Deadlifts',
    10020: 'Shoulder presses',
    10021: 'Front raises',
    10022: 'Lateral raises',
    10023: 'Crunches',
    10024: 'Leg raises',
    10025: 'Plank',
    10026: 'Arm curls',
    10027: 'Arm extensions',
    11001: 'Inline skating, moderate pace',
    11002: 'Hang gliding',
    11003: 'Pistol shooting',
    11004: 'Archery, non-hunting',
    11005: 'Horseback riding, general',
    11007: 'Cycling',
    11008: 'Flying disc, general, playing',
    11009: 'Roller skating',
    12001: 'Aerobics, general',
    13001: 'Hiking',
    13002: 'Rock climbing, low to moderate difficulty',
    13003: 'Backpacking',
    13004: 'Mountain biking, general',
    13005: 'Orienteering',
    14001: 'Swimming, general, leisurely, not lap swimming',
    14002: 'Aquarobics',
    14003: 'Canoeing, general, for pleasure',
    14004: 'Sailing, leisure, ocean sailing',
    14005: 'Scuba diving, general',
    14006: 'Snorkeling',
    14007: 'Kayaking, moderate effort',
    14008: 'Kitesurfing',
    14009: 'Rafting',
    14010: 'Rowing machine, general, for pleasure',
    14011: 'Windsurfing, general',
    14012: 'Yachting, leisure',
    14013: 'Water skiing',
    15001: 'Step machine',
    15002: 'Weight machine',
    15003: 'Exercise bike, Moderate to vigorous effort (90-100 watts)',
    15004: 'Rowing machine',
    15005: 'Treadmill, combination of jogging and walking',
    15006: 'Elliptical trainer, moderate effort',
    16002: 'Skiing, general, downhill, moderate effort',
    16003: 'Ice dancing',
    16004: 'Ice skating, general',
    16006: 'Ice hockey, general',
    16007: 'Snowboarding, general, moderate effort',
    16008: 'Alpine skiing, general, moderate effort',
}

# Rótulos em português para os códigos que este projeto realmente usa. Os
# demais caem no nome oficial em inglês, e um código desconhecido (o relógio
# emite alguns que não estão na tabela, ex.: 1007) vira "Outro (<n>)" em vez de
# sumir — treino novo deve APARECER no relatório, não virar buraco silencioso.
EXERCISE_TYPE_PT: dict[int, str] = {
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


def nome_exercicio(codigo: int | str | None) -> str:
    """Nome legível do tipo de exercício: PT-BR > oficial (EN) > 'Outro (<n>)'."""
    if codigo is None:
        return "(sem tipo)"
    try:
        n = int(codigo)
    except (TypeError, ValueError):
        return "(sem tipo)"
    return EXERCISE_TYPE_PT.get(n) or EXERCISE_TYPE_OFICIAL.get(n) or f"Outro ({n})"


# --------------------------------------------------------------------------- #
# Heurísticas compartilhadas (documentadas porque são decisões, não código)
# --------------------------------------------------------------------------- #
def classificar_atividade(vel_max_kmh: float | None, tipo: str = "") -> str:
    """Corrida ou caminhada?

    A média engana: um treino com média 8 km/h pode ter picos acima de 10 km/h.
    A regra usada aqui é o PICO, não a média — se em algum momento passou de
    10 km/h, é corrida.
    """
    if vel_max_kmh is None:
        return "caminhada" if "Caminhada" in tipo else "outro"
    return "corrida" if vel_max_kmh > 10.0 else "caminhada"


PADRAO_ZIP = re.compile(r"^samsunghealth_(?P<nome>.+)_(?P<ts>\d{14})\.zip$")


def parametros_do_zip(nome: str) -> dict:
    """Extrai o timestamp de um nome de zip, sem depender do nome da pessoa."""
    m = PADRAO_ZIP.match(nome)
    return {"nome": m.group("nome"), "timestamp": m.group("ts")} if m else {}
