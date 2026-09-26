"""Diagnóstico correto: sessões de sono por data — sono principal vs soneca.

Nota: a tabela `dia` tem uma coluna chamada `n` (contagem de amostras de respiração),
então usar `COUNT(*) n` + `HAVING n > 1` comparava a COLUNA, não a contagem. Daí o
resultado anterior mostrar linhas com n=1.
"""
import sqlite3
import pandas as pd

c = sqlite3.connect("report/saude.db")

d = pd.read_sql("""SELECT data, COUNT(*) AS qtd FROM dia
                   GROUP BY data HAVING COUNT(*) > 1 ORDER BY data""", c)
print(f"datas com mais de uma linha em `dia`: {len(d)}")
if len(d):
    print(d.head(10).to_string(index=False))

n = pd.read_sql("""SELECT data, COUNT(*) AS qtd FROM noite
                   GROUP BY data HAVING COUNT(*) > 1 ORDER BY data""", c)
print(f"\ndatas com mais de uma sessão de sono: {len(n)}  de {n.data.nunique()} datas")

# impacto: principal (maior sessão do dia) vs secundárias
s = pd.read_sql("""SELECT data, horas, min_dormido, pct_profundo, pct_rem, waso_min,
                          fragmentacao, sleep_score
                   FROM noite WHERE horas IS NOT NULL""", c)
s["ordem"] = s.groupby("data").horas.rank(ascending=False, method="first")
princ = s[s.ordem == 1]
outras = s[s.ordem > 1]
print(f"\nsono principal : {len(princ)} sessões · mediana {princ.horas.median():.2f} h")
print(f"outras sessões : {len(outras)} · mediana {outras.horas.median():.2f} h "
      f"· {int((outras.horas < 1).sum())} abaixo de 1 h")
print(f"\nIMPACTO nas medianas (todas as sessões → só a principal):")
for col, rot in [("pct_profundo", "% profundo"), ("pct_rem", "% REM"),
                 ("waso_min", "WASO (min)"), ("fragmentacao", "fragmentação/h"),
                 ("sleep_score", "sleep_score")]:
    a, b = s[col].median(), princ[col].median()
    print(f"   {rot:<16} {a:>7.1f}  →  {b:>7.1f}   ({b-a:+.1f})")
