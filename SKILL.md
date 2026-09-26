---
name: samsung-health-analysis
description: Use when analyzing Samsung Health / Galaxy Watch export data (sleep, heart rate, HRV, workouts, ECG). Loads the export into SQLite and produces stats, charts and reports while avoiding the known data traps.
---

# Análise do export do Samsung Health (Galaxy Watch)

Ferramentas para transformar o export do Samsung Health em análise: sono,
coração, HRV, treino, ECG. Tudo local, nada enviado para fora.

## Antes de qualquer coisa

**Rode o diagnóstico de homogeneidade primeiro.** Se a estrutura da noite mudou
no meio do histórico (troca de versão do app), comparações antes/depois não
valem — e o erro passa despercebido.

```bash
python3 analise_granularidade.py "$SH_EXPORT" report
python3 analise_versao_app.py  "$SH_EXPORT" report
```

`analise_versao_app.py` é o teste mais barato e mais frequentemente esquecido:
se a amplitude de REM% **entre versões do app** for maior que o efeito que você
investiga, o efeito não é interpretável com esses dados. Ponto.

## Localizar o export

Precedência: argumento na linha de comando → `SH_EXPORT` → `samsunghealth_*`
mais recente sob `SH_DATA_DIR` (padrão `data/`).

O export vem como `samsunghealth_<nome>_<timestamp>.zip`. Descompactado, vira um
diretório com esse nome — **que carrega o nome da pessoa**. Nunca comite, nunca
cite em relatório compartilhável.

## Pipeline

A ordem importa: as análises geram os JSONs que o banco consome.

```bash
cd scripts
python3 analise_sono.py     "$SH_EXPORT" ../report/sono.json
python3 analise_vitality.py "$SH_EXPORT" ../report/vitality.json
python3 analise_extras.py   "$SH_EXPORT" ../report/extras.json
python3 build_sqlite.py     "$SH_EXPORT" ../report     # -> saude.db
```

Depois disso, as demais análises leem `saude.db` e recebem só o diretório:
`analise_quebras.py`, `analise_medicacao.py`, `analise_rem.py`,
`analise_rem_lag.py`, `grafico_*.py`.

Conferir os argumentos: `analise_granularidade.py`, `grafico_hist.py`,
`grafico_alertas.py` e `ecg_summary.py` querem `(export, out)`;
`analise_acoplamento.py` quer `(export, sono.json, arquivo.json)`.

## Armadilhas

Leia `references/armadilhas.md` antes de mexer nos scripts — são 11 itens, cada
um já produziu um número errado em análise real. Os que mais pegam:

1. **CSV com cabeçalho de 2 linhas e vírgula sobrando.** `read_csv` desalinha as
   colunas em silêncio e você lê UUID como se fosse horário. Use o leitor de
   `sh_load.py` (módulo `csv`).
2. **Versão do app muda o algoritmo** de estadiagem → falso achado fisiológico.
3. **Dois pacotes gravam sono** (`com.sec.android.app.shealth` e
   `com.urbandroid.sleep`). Misturar fabrica uma quebra.
4. **Soneca não é noite** — distorce REM%.
5. **Corrida × caminhada pelo PICO** de velocidade (>10 km/h), não pela média.
6. **Tabela de exercícios:** use a oficial (`shtools.EXERCISE_TYPE_OFICIAL`). Um
   pacote do PyPI traz uma errada.
7. **HRV precisa de controle pela FC** — a correlação é parcialmente mecânica.
8. **Detecção de quebra:** o máximo de um teste sobre muitos pontos é sempre
   "significativo". Use teste de permutação (`analise_medicacao.py`).

## Regras de análise

- **Proveniência:** rotule todo número como `direto`, `derivado` ou `inferido`.
  Medida digitada à mão vira `manual:<instrumento>`.
- **Compare percentuais**, não minutos absolutos, entre noites de durações
  diferentes.
- **Diga os `n`.** Mediana de 3 noites não sustenta conclusão.
- **Período parcial não é tendência.** Marque bordas truncadas no gráfico.
- **Nunca apresente como diagnóstico.** PPG de pulso não é dispositivo médico,
  e não se orienta medicação a partir disso.

## Dependências

`pandas`, `numpy`, `scipy`, `plotly`, `kaleido` (ver `requirements.txt`).

## Módulo opcional

`sh_load.py` tenta importar `correcoes.classificar_ciclismo` para descartar
falsos positivos de ciclismo (relógio marcando pedalada em deslocamento de
carro). O módulo é **opcional e deliberadamente externo** ao repositório: a
regra depende de coordenadas pessoais. Sem ele, todo ciclismo conta como treino
real — o comportamento conservador.
