#!/usr/bin/env python3
"""
analise_quebras.py — Segmentação binária: encontra TODAS as quebras relevantes,
não só a mais forte.

Por que binária: o teste de quebra única esconde o segundo evento. Ele acha o
maior, remove, e procura de novo dentro de cada segmento. Cada candidato passa
por teste de permutação.

ATENÇÃO ao interpretar: com ~12 séries × várias quebras, o p<0,05 aplicado
recursivamente acumula falsos positivos. Trate a saída como TRIAGEM de
candidatos, não como lista de eventos confirmados — e só acredite numa quebra
que (a) tenha p muito baixo e (b) apareça em mais de uma série independente na
mesma janela.

As funções t_todos() e segmentar() são importáveis; o resto só roda como script.

Uso: python analysis/analise_quebras.py report
"""
import json
import sqlite3
import sys
from datetime import datetime

import numpy as np
import pandas as pd

MIN_SEG = 40
N_PERM = 1500
SEED = 20260918


def t_todos(x, min_seg):
    """|t| de Welch para TODOS os pontos de quebra de uma vez (vetorizado)."""
    n = len(x)
    if n < 2 * min_seg:
        return None
    c, c2 = np.cumsum(x), np.cumsum(x * x)
    ks = np.arange(min_seg, n - min_seg + 1)
    sa, sb = c[ks - 1], c[-1] - c[ks - 1]
    na, nb = ks.astype(float), (n - ks).astype(float)
    ma, mb = sa / na, sb / nb
    va = (c2[ks - 1] - sa ** 2 / na) / (na - 1)
    vb = ((c2[-1] - c2[ks - 1]) - sb ** 2 / nb) / (nb - 1)
    se = np.sqrt(va / na + vb / nb)
    with np.errstate(divide="ignore", invalid="ignore"):
        t = np.where(se > 0, (ma - mb) / se, 0.0)
    return ks, np.nan_to_num(t)


def melhor(x, min_seg, rng, n_perm=N_PERM):
    r = t_todos(x, min_seg)
    if r is None:
        return None
    ks, t = r
    j = int(np.argmax(np.abs(t)))
    obs, k = float(t[j]), int(ks[j])
    ext = np.empty(n_perm)
    for i in range(n_perm):
        ext[i] = np.max(np.abs(t_todos(rng.permutation(x), min_seg)[1]))
    p = float((1 + (ext >= abs(obs)).sum()) / (n_perm + 1))
    return k, obs, p


def segmentar(v, datas, min_seg=MIN_SEG, rng=None):
    """Segmentação binária recursiva. Retorna lista de quebras ordenadas."""
    if rng is None:
        rng = np.random.default_rng(SEED)
    x = np.asarray(v, dtype=float)
    ok = ~np.isnan(x)
    xv, dv = x[ok], np.asarray(datas)[ok]

    def rec(xs, ds):
        m = melhor(xs, min_seg, rng)
        if m is None:
            return []
        k, t, p = m
        if p >= 0.05:
            return []
        return ([dict(data=str(pd.Timestamp(ds[k]).date()), t=round(t, 2), p=p)]
                + rec(xs[:k], ds[:k]) + rec(xs[k:], ds[k:]))

    return sorted(rec(xv, dv), key=lambda q: q["data"])


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "report"
    con = sqlite3.connect(f"{out}/saude.db")
    d = pd.read_sql("SELECT * FROM dia", con)
    con.close()
    d["data"] = pd.to_datetime(d["data"])
    d = d.sort_values("data").reset_index(drop=True)

    res = {"gerado_em": datetime.now().isoformat(timespec="seconds"),
           "min_seg_dias": MIN_SEG, "n_permutacoes": N_PERM, "series": {}}
    rng = np.random.default_rng(SEED)

    print("=" * 78)
    print("  SEGMENTAÇÃO BINÁRIA — candidatos a quebra (p < 0,05, TRIAGEM)")
    print("=" * 78)
    series = [("shr", "FC de repouso"), ("shrv", "HRV noturna"),
              ("baseline_meio", "baseline HRV"), ("pct_rem", "REM %"),
              ("min_rem", "REM min"), ("pct_profundo", "profundo %"),
              ("min_dormido", "sono total"), ("sleep_score", "score de sono"),
              ("readiness", "readiness"), ("km", "km/dia"),
              ("stress_medio", "stress médio"), ("fragmentacao", "fragmentação")]
    for c, rot in series:
        if c not in d.columns:
            continue
        qs = segmentar(d[c].values, d["data"].values, rng=rng)
        res["series"][c] = dict(nome=rot, quebras=qs)
        print(f"  {rot:16s} " + ("  ".join(
            f"{q['data']}(t={q['t']:+.1f},p={q['p']:.3f})" for q in qs)
            if qs else "(nenhuma)"))

    print("\n" + "=" * 78)
    print("  FC DE REPOUSO — médias por segmento")
    print("=" * 78)
    # Os extremos saem dos DADOS, não do calendário de uma pessoa: o primeiro
    # segmento começa no primeiro dia com FC de repouso e o último termina no
    # fim da série.
    cortes = [pd.Timestamp(d["data"].min())]
    cortes += [pd.Timestamp(q["data"]) for q in res["series"]["shr"]["quebras"]]
    cortes += [pd.Timestamp(d["data"].max()) + pd.Timedelta(days=1)]
    for i in range(len(cortes) - 1):
        a, b = cortes[i], cortes[i + 1]
        g = d[(d["data"] >= a) & (d["data"] < b)]["shr"].dropna()
        if len(g) < 5:
            continue
        print(f"  {str(a.date())} → {str(b.date())}  n={len(g):3d}  "
              f"mediana {g.median():.1f} bpm  (média {g.mean():.1f})")

    with open(f"{out}/quebras.json", "w") as f:
        json.dump(res, f, ensure_ascii=False, indent=1, default=str)
    print(f"\n  salvo em {out}/quebras.json")


if __name__ == "__main__":
    main()
