# Samsung Health — Análise de dados do Galaxy Watch

Ferramentas para transformar o export do **Samsung Health** (Galaxy Watch) em
análise de verdade: sono, coração, treino, HRV, ECG — em SQLite consultável,
JSONs e gráficos.

Não é um aplicativo e não se conecta a nada. Você baixa o export, aponta o
caminho e roda os scripts. **Todo processamento é local.**

> **Nunca mexeu com terminal?** Comece pelo **[QuickStart.md](QuickStart.md)** —
> guia passo a passo, com os textos prontos para colar em um assistente de IA
> (Hermes, Claude Code, Codex, Antigravity, OpenCode) que faz o trabalho por você.

---

## O que este projeto resolve

O export do Samsung Health é um `.zip` com centenas de CSVs mal comportados. Ler
isso na mão dá trabalho e leva a erros que **não aparecem** — você só descobre
meses depois, quando um número no relatório está errado. As armadilhas reais
estão documentadas em [`references/armadilhas.md`](references/armadilhas.md) e
resumidas abaixo.

| Armadilha | O que acontece se você não tratar |
|---|---|
| Cabeçalho de **2 linhas** + **vírgula sobrando** no fim de cada linha | `pandas.read_csv` desalinha as colunas **em silêncio** — você acaba lendo UUID como se fosse horário |
| Versão do app (`create_sh_ver`) muda o **algoritmo de estadiagem** | Uma "piora do sono profundo" que é só o app medindo diferente |
| Dois pacotes gravam sono (`com.sec.android.app.shealth` e `com.urbandroid.sleep`) | Misturar as fontes **fabrica** uma quebra que não existe |
| Soneca não é noite | Sonecas quase não têm REM e distorcem a mediana de REM% |
| Velocidade **máxima** ≠ média | Corrida com média 8 km/h pode ter picos de 14 km/h |
| Códigos de exercício fora da tabela oficial | Treino aparece rotulado errado (ou some) |

---

## Requisitos

- Python **3.11+**
- `pip install -r requirements.txt` (pandas, numpy, scipy, plotly, kaleido)

Opcional: `sqlite3` para consultar o banco, e um navegador (Chromium) se você
quiser exportar gráficos como PDF — o `kaleido` já resolve PNG.

---

## Como obter o export

1. No celular: **Samsung Health → Configurações → Baixar dados pessoais**
2. Escolha o período e confirme — a Samsung manda um e-mail com o link
3. Baixe o `.zip` e descompacte em `data/`:

```bash
mkdir -p data
unzip -q ~/Downloads/samsunghealth_*.zip -d data/
```

Qualquer um dos dois serve — os scripts aceitam o caminho do diretório ou do
`.zip` descompactado:

- `SH_EXPORT=/caminho/do/export` (variável de ambiente), ou
- `SH_DATA_DIR=/caminho/onde/esta` (procura o `samsunghealth_*` mais recente), ou
- primeiro argumento na linha de comando.

---

## Uso

### Pipeline principal

A ordem importa: as análises geram os JSONs que o banco consome.

```bash
cd scripts
export SH_EXPORT=../data/samsunghealth_XXXXXX

python3 analise_sono.py     "$SH_EXPORT" ../report/sono.json
python3 analise_vitality.py "$SH_EXPORT" ../report/vitality.json
python3 analise_extras.py   "$SH_EXPORT" ../report/extras.json
python3 build_sqlite.py     "$SH_EXPORT" ../report      # -> ../report/saude.db
```

### Consultar o banco

```bash
sqlite3 ../report/saude.db "SELECT data, horas, pct_rem, fc_repouso FROM dia LIMIT 10"
```

Tabelas: `dia`, `semana`, `mes`, `semestre`, `treino`, `noite`, `origem`.

### Primeiro diagnóstico: a série é homogênea?

**Rode isto antes de qualquer análise temporal.** Se a estrutura da noite mudou
no meio do histórico, comparações antes/depois não valem.

```bash
python3 analise_granularidade.py "$SH_EXPORT" ../report
```

### Análises disponíveis

Todas leem o `saude.db` (ou o export, quando indicado) e imprimem + gravam JSON.

- `analise_granularidade.py` — estrutura da noite por mês; detecta mudança de algoritmo *(export, out)*
- `analise_versao_app.py` — **versão do app × fases do sono**; separa fisiologia de artefato *(export, out)*
- `analise_sono.py` — sono, eficiência, fases, fragmentação *(export, sono.json)*
- `analise_vitality.py` — HRV, readiness, respiração, calorias, atividade *(export, vitality.json)*
- `analise_extras.py` — métricas complementares *(export, extras.json)*
- `analise_quebras.py` — detecção de pontos de quebra na FC de repouso *(out)*
- `analise_medicacao.py` — efeito antes/depois de um evento datado (medicamento, rotina, lesão) *(out)*
- `analise_rem.py`, `analise_rem_lag.py` — REM: tendência, relação com duração e FC *(out)*
- `analise_rem_avancada.py` — REM em janela limpa, separada do período de uso esparso *(out, + SH_LIMPO_INI/SH_LIMPO_FIM/SH_RECENTE_INI)*
- `analise_acoplamento.py` — acoplamento entre séries (ex.: stress do dia anterior × sono) *(export, sono.json, saída.json)*
- `ecg_summary.py` — extrai a classificação de ritmo dos PDFs de ECG *(export, out)*
- `val_sono.py` — validação cruzada: o que calculamos × o que a Samsung já traz pronto *(export, sono.json)*
- `grafico_hist.py`, `grafico_hist_semanal.py`, `grafico_alertas.py`, `grafico_rem.py` — gráficos
- `diag_duplicatas.py` — diagnóstico de linhas duplicadas no export

Precisa da variável de janela (senão o script explica o que fazer):

```bash
SH_LIMPO_INI=2025-06-01 SH_LIMPO_FIM=2026-03-31 SH_RECENTE_INI=2026-04-01 \
  python3 analise_rem_avancada.py ../report
```

---

## Estrutura

```
Reports_Samsung_Health/
├── scripts/
│   ├── shtools.py            # configuração, mapa de exercícios, heurísticas
│   ├── sh_load.py            # leitor do export (o coração do projeto)
│   ├── build_sqlite.py       # export -> SQLite
│   └── analise_*.py, grafico_*.py, val_*.py, diag_*.py
└── references/
    └── armadilhas.md         # o que já deu errado, e por quê
```

`sh_load.py` é o único lugar que fala com o formato cru do export. Se a Samsung
mudar o layout, é o único arquivo que precisa mudar.

---

## Fontes

Tudo que está aqui veio de fontes públicas ou foi verificado contra elas. O que
é convenção nossa está marcado como tal.

### Oficial — Samsung Developer

| Fonte | Usada para |
|---|---|
| [Predefined Exercise Type](https://developer.samsung.com/health/android/data/api-reference/EXERCISE_TYPE.html) — developer.samsung.com | **Tabela de códigos de exercício** (`EXERCISE_TYPE_OFICIAL` em `shtools.py`). Os 91 códigos foram transcritos verbatim da tabela oficial e conferidos em 2026-09-26 |

Os nomes ficaram **em inglês, exatamente como publicados**. Traduzir à mão 91
entradas é convite a erro; os rótulos em português existem só para os códigos que
este projeto realmente usa (`EXERCISE_TYPE_PT`).

> Um pacote do PyPI tem uma tabela de códigos de exercício **incorreta** — foi de
> lá que veio o mapa errado que este projeto usou por um tempo. Se você comparar
> e divergir, a tabela do developer.samsung.com é a que vale.

### Formato do export

O layout do `.zip` **não é documentado pela Samsung**. Foi levantado lendo o
próprio export, e é isso que `sh_load.py` codifica: cabeçalho de 2 linhas,
vírgula final em cada linha, valores que só existem nos `jsons/`, `datauuid` com
namespace. Cada um desses detalhes tem um comentário no código explicando por que
está ali — se você encontrar um caso que quebra, é aí que se mexe.

Códigos de estágio de sono (`40001` Acordado · `40002` Leve · `40003` Profundo ·
`40004` REM): confirmados em **três fontes independentes** e consistentes com os
campos `total_*_duration` que o próprio Samsung Health fornece
(`val_sono.py` compara os dois — é a sua checagem de sanidade).

### Projetos que inspiraram

Nada foi copiado; as ideias foram reimplementadas.

| Projeto | O que tirou de lá |
|---|---|
| [tcgoetz/GarminDB](https://github.com/tcgoetz/GarminDB) | **Arquitetura**: espelho SQLite consultável com tabelas diária/semanal/mensal/semestral, e a separação entre *importar* (parse cru) e *analisar* |
| [Devasy/samsung-health-sdk](https://github.com/Devasy/samsung-health-sdk) | **Engenharia de features**: sessões de sono com eficiência/fragmentação, HRV contra baseline móvel, acoplamento stress×sono, perfil diário de atividade |
| [lionheart/health-csv-importer-samsung](https://github.com/lionheart/health-csv-importer-samsung) | **Mapa de códigos de estágio de sono** e mapa de tipos de exercício |
| [charlesbel/samsung-re-health](https://github.com/charlesbel/samsung-re-health) | **Prática de proveniência**: rotular cada número como `direto`, `derivado` ou `inferido` |

### Bibliotecas

`pandas` · `numpy` · `scipy` (testes estatísticos: Mann-Whitney, Welch, permutação)
· `plotly` + `kaleido` (gráficos) · `sqlite3` (stdlib)

### Convenções nossas (não vêm de fonte externa)

- Corrida × caminhada por **velocidade máxima > 10 km/h** (a média engana)
- Sono principal separado de sonecas
- Fases em **porcentagem**, não em minutos absolutos, quando o objetivo é comparar
  noites de durações diferentes
- Faixas de referência adultas usadas nos relatórios: profundo **13–23%**,
  REM **20–25%**, leve **50–60%**

---

## Privacidade

Este repositório **não contém dado de saúde de ninguém**. Sem exports, sem banco,
sem relatórios, sem coordenadas. Os caminhos são resolvidos em tempo de execução
e o `.gitignore` bloqueia `data/`, `report/`, `*.db`, `*.zip`.

Antes de publicar qualquer coisa gerada aqui, lembre-se de que **o seu export
contém dado sensível** — e que o nome do arquivo do export costuma carregar o seu
nome.

---

## Licença

MIT — veja [`LICENSE`](LICENSE).
