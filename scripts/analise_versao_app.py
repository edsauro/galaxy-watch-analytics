#!/usr/bin/env python3
"""
analise_versao_app.py — Uma mudança nos seus dados é fisiologia ou artefato de
versão do aplicativo?

O PROBLEMA
    O Samsung Health grava, em cada linha do export de sono, a versão do app e o
    pacote que gerou aquela medida (``create_sh_ver`` / ``pkg_name``). O app é
    atualizado algumas vezes por ano, e cada atualização pode mudar o ALGORITMO
    de estadiagem. Resultado: você vê uma "melhora do sono profundo" ou uma
    "queda do REM" que é só o app medindo diferente, não o seu corpo mudando.

    Isso já causou erro de análise de verdade — inclusive contra um evento
    clínico real que coincidia em data com a troca de versão.

O MÉTODO
    1. Recalcula as % de cada fase direto do CSV de estágios, por noite. NÃO usa
       a tabela diária: ela agrega por noite e esconde a versão.
    2. Agrupa por versão do app e mostra as medianas de cada fase.
    3. TESTE DECISIVO — procura meses em que DUAS versões coexistem e compara
       dentro do mesmo mês. É o único arranjo em que a versão varia sem o tempo
       variar junto (sem confundir "mudou o app" com "passaram 6 meses").
    4. Testa cada fronteira entre versões consecutivas, não só a que você
       suspeita. Se uma fronteira qualquer desloca as fases em vários pontos
       percentuais, o efeito suspeito provavelmente é artefato.

LEITURA DO RESULTADO
    - Δ grande (diga-se, > 3-4 pontos de REM%) entre versões na MESMA janela
      → artefato. Não reporte como mudança fisiológica.
    - Medianas por versão com amplitude total grande ao longo do histórico
      → o ruído do algoritmo é maior que o efeito que você procura.
    - Sem versões coexistindo → você não consegue separar versão de tempo.
      Colete mais dados ou aceite a limitação e diga isso no relatório.

Uso:
    python3 analise_versao_app.py [export_dir] [out_dir]
"""
from __future__ import annotations

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd
from scipy import stats

from shtools import export_dir, out_dir

MIN_NOITES_VERSAO = 8        # versões com menos noites que isso não entram na tabela
MIN_NOITES_MESMA_JANELA = 3  # mínimo por versão para o teste dentro do mesmo mês
DURACAO_MIN_NOITE = 240      # min; abaixo disso é soneca/fragmento, não noite


def carregar(exp: Path) -> pd.DataFrame:
    """CSV de estágios -> uma linha por segmento, com duração em minutos.

    Lido com o módulo ``csv``, e não com ``pandas.read_csv``, de propósito: o
    export da Samsung tem uma linha de metadados antes do cabeçalho E vírgula
    sobrando no fim de cada linha (14 campos para 13 nomes de coluna). O
    ``read_csv`` desalinha as colunas nesse caso — silenciosamente, o que é pior,
    porque aí você acaba lendo o UUID da sessão como se fosse um horário.
    """
    arquivos = sorted(exp.glob("com.samsung.health.sleep_stage.*.csv"))
    if not arquivos:
        raise SystemExit(
            f"[versao_app] não achei 'com.samsung.health.sleep_stage.*.csv' em {exp}\n"
            "  Confira se o export está descompactado por completo.")
    registros: list[dict] = []
    with arquivos[0].open(encoding="utf-8-sig", newline="") as fh:
        next(fh)                                    # linha 1: metadados
        cabecalho = next(fh).rstrip("\n").split(",")  # linha 2: cabeçalho real
        for linha in csv.reader(fh):
            if not linha:
                continue
            # zip descarta o campo extra que a vírgula final produz
            registros.append(dict(zip(cabecalho, linha)))

    df = pd.DataFrame(registros)
    df["start_time"] = pd.to_datetime(df["start_time"], format="mixed")
    df["end_time"] = pd.to_datetime(df["end_time"], format="mixed")
    df["min"] = (df["end_time"] - df["start_time"]).dt.total_seconds() / 60
    df["stage"] = pd.to_numeric(df["stage"], errors="coerce").map(
        {40001: "Acordado", 40002: "Leve", 40003: "Profundo", 40004: "REM"})
    return df[df["stage"].notna() & (df["min"] > 0)].copy()


def por_noite(df: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por noite: % de cada fase + versão do app + duração."""
    meta = df.groupby("sleep_id").agg(
        ini=("start_time", "min"),
        dur=("min", "sum"),
        ver=("create_sh_ver", lambda s: s.mode().iloc[0] if len(s.mode()) else None),
        src=("pkg_name", lambda s: s.mode().iloc[0] if len(s.mode()) else None))
    piv = df.pivot_table(index="sleep_id", columns="stage", values="min",
                         aggfunc="sum").fillna(0)
    pct = piv.div(piv.sum(axis=1), axis=0) * 100
    j = pct.join(meta)
    j["ym"] = j["ini"].dt.to_period("M")

    # Só o app oficial e noites de verdade. Soneca quase não tem REM e distorce a
    # mediana de REM%; outros pacotes (ex.: Sleep as Android) gravam junto e usam
    # outro algoritmo — misturar as duas fontes FABRICA uma quebra que não existe.
    j = j[(j["src"] == "com.sec.android.app.shealth") & (j["dur"] >= DURACAO_MIN_NOITE)]
    return j[j["ver"].notna()]


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("export", nargs="?", default=None)
    ap.add_argument("out", nargs="?", default=None)
    a = ap.parse_args()

    exp = Path(a.export) if a.export else export_dir()
    out = out_dir(a.out)
    j = por_noite(carregar(exp))
    if j.empty:
        raise SystemExit("[versao_app] nenhuma noite válida após os filtros.")

    res: dict = {"gerado_em": datetime.now().isoformat(timespec="seconds"),
                 "base_noites": int(len(j))}

    print("=" * 78)
    print("  VERSÃO DO APP vs FASES DO SONO — isto é fisiologia ou artefato?")
    print("=" * 78)
    print(f"\n  base: noites >= {DURACAO_MIN_NOITE} min, só com.sec.android.app.shealth"
          f"  (n={len(j)})")

    # ---- 1. tabela por versão -------------------------------------------- #
    print(f"\n1) Fases por VERSÃO do app (só versões com >= {MIN_NOITES_VERSAO} noites)")
    print(f"   {'versão':>12s} {'noites':>7s} {'janela':>20s} {'REM%':>7s} "
          f"{'Prof%':>7s} {'Leve%':>7s} {'dur':>6s}")
    res["por_versao"] = {}
    for v, g in j.groupby("ver"):
        if len(g) < MIN_NOITES_VERSAO:
            continue
        jan = f"{g.ym.min()}→{g.ym.max()}"
        print(f"   {v:>12s} {len(g):7d} {jan:>20s} {g['REM'].median():7.1f} "
              f"{g['Profundo'].median():7.1f} {g['Leve'].median():7.1f} "
              f"{g.dur.median():6.0f}")
        res["por_versao"][v] = {
            "n": int(len(g)), "rem": round(float(g["REM"].median()), 1),
            "profundo": round(float(g["Profundo"].median()), 1),
            "leve": round(float(g["Leve"].median()), 1),
            "dur_min": round(float(g.dur.median())), "janela": jan}
    if len(res["por_versao"]) >= 2:
        rems = [d["rem"] for d in res["por_versao"].values()]
        amp = max(rems) - min(rems)
        res["amplitude_rem_entre_versoes"] = round(amp, 1)
        print(f"\n   amplitude de REM% entre versões: {amp:.1f} pontos")
        print("   → se isso for maior que o efeito que você investiga, o ruído do")
        print("     algoritmo domina e a comparação simples não conclui nada.")

    # ---- 2. teste decisivo: versões na MESMA janela mensal ---------------- #
    print("\n2) TESTE DECISIVO — versões DIFERENTES no MESMO mês")
    print("   (aqui a versão muda sem o tempo mudar junto)")
    res["mesma_janela"] = {}
    achou = False
    for ym, g in j.groupby("ym"):
        cont = g.groupby("ver").size()
        cont = cont[cont >= MIN_NOITES_MESMA_JANELA]
        if len(cont) < 2:
            continue
        achou = True
        print(f"\n   {ym}:")
        for v in cont.index:
            s = g[g["ver"] == v]
            print(f"      ver={v:<12s} n={len(s):3d}  REM%={s['REM'].median():5.1f}  "
                  f"Prof%={s['Profundo'].median():5.1f}  dur={s.dur.median():5.0f}")
        vs = list(cont.index)
        for i in range(len(vs)):
            for k in range(i + 1, len(vs)):
                aa = g[g["ver"] == vs[i]]["REM"]
                bb = g[g["ver"] == vs[k]]["REM"]
                if (len(aa) >= MIN_NOITES_MESMA_JANELA
                        and len(bb) >= MIN_NOITES_MESMA_JANELA):
                    _, p = stats.mannwhitneyu(aa, bb)
                    d = aa.median() - bb.median()
                    print(f"      → {vs[i]} vs {vs[k]}: ΔREM%={d:+.1f}  p={p:.3f}")
                    res["mesma_janela"][f"{ym}|{vs[i]}|{vs[k]}"] = {
                        "delta_rem": round(float(d), 1), "p": round(float(p), 4),
                        "n": [int(len(aa)), int(len(bb))]}
    if not achou:
        print("   nenhum mês com 2 versões com noites suficientes.")
        print("   → sem isso, versão e tempo são a MESMA variável. Reporte a")
        print("     limitação; não afirme causalidade.")
    res["tem_versao_coexistente"] = achou

    # ---- 3. todas as fronteiras, não só a suspeita ------------------------ #
    print("\n3) TODAS as fronteiras entre versões consecutivas")
    print("   Comparar só a fronteira que você suspeita é o erro clássico:")
    print("   se várias fronteiras deslocam as fases, o efeito não é específico.")
    ordem = (j.groupby("ver")["ini"].min().sort_values().index.tolist())
    res["fronteiras"] = {}
    for ant, nov in zip(ordem, ordem[1:]):
        aa = j[j["ver"] == ant]["REM"].dropna()
        bb = j[j["ver"] == nov]["REM"].dropna()
        if len(aa) < 5 or len(bb) < 5:
            continue
        _, p = stats.mannwhitneyu(aa, bb)
        da = j[j["ver"] == ant]["Profundo"].dropna()
        db = j[j["ver"] == nov]["Profundo"].dropna()
        if len(da) >= 5 and len(db) >= 5:
            _, pp = stats.mannwhitneyu(da, db)
        else:
            pp = float("nan")
        d_rem = bb.median() - aa.median()
        d_prof = db.median() - da.median()
        print(f"   {ant} → {nov}")
        print(f"      REM%      {aa.median():5.1f} → {bb.median():5.1f}  "
              f"Δ={d_rem:+5.1f}  p={p:.4f}  (n={len(aa)},{len(bb)})")
        print(f"      Profundo% {da.median():5.1f} → {db.median():5.1f}  "
              f"Δ={d_prof:+5.1f}  p={pp:.4f}")
        res["fronteiras"][f"{ant}->{nov}"] = {
            "delta_rem": round(float(d_rem), 1), "p_rem": round(float(p), 4),
            "delta_profundo": round(float(d_prof), 1),
            "p_profundo": round(float(pp), 4)}

    destino = Path(out) / "versao_app.json"
    destino.write_text(json.dumps(res, ensure_ascii=False, indent=1, default=str),
                       encoding="utf-8")
    print(f"\n  salvo em {destino}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
