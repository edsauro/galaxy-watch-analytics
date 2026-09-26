# Armadilhas do dados do Samsung Health

Cada item aqui **já produziu um número errado** em uma análise real. Não são
hipóteses. Se você for mexer nos scripts, leia isto antes.

---

## 1. O CSV não é CSV de verdade

O export tem duas coisas que quebram `pandas.read_csv`:

```
com.samsung.health.sleep_stage,7006011,7          <- linha 1: metadados
create_sh_ver,start_time,sleep_id,...,pkg_name    <- linha 2: cabeçalho REAL
,2023-08-22 07:12:56.992,8bbb0efa-...,            <- linha 3+: dados
```

1. **Linha de metadados antes do cabeçalho.** Precisa de `skiprows=1`.
2. **Vírgula sobrando no fim de cada linha** — 14 campos para 13 nomes de coluna.

O problema não é o erro: é que às vezes o pandas **não** dá erro. Ele usa a
primeira coluna como índice, desloca tudo em uma posição e você segue lendo
**UUID de sessão achando que é horário**. O traceback só aparece muito depois,
em outro lugar, quando um `to_datetime` reclama de um valor que não é data.

**Regra:** `sh_load.py` lê com o módulo `csv` (`dict(zip(cabecalho, linha))`), que
tolera o campo extra. Não troque por `read_csv` sem conferir
`list(df.columns)` e uma linha de dados.

---

## 2. A versão do app pode ser a explicação inteira

O CSV de estágios traz `create_sh_ver` (versão do app) e `pkg_name` (pacote). O
Samsung Health é atualizado algumas vezes por ano, e **a atualização pode mudar o
algoritmo de estadiagem** — inclusive a granularidade da noite (mais segmentos,
cada um mais curto).

O efeito: uma "queda do REM" ou uma "melhora do sono profundo" que é o app
medindo diferente. Isso já foi confundido com um evento clínico real, que
**coincidia em data** com a troca de versão.

**Como testar (`analise_versao_app.py`):**

- Compare as % de cada fase **por versão**, não só ao longo do tempo.
- **Teste decisivo:** ache meses com **duas versões coexistindo** e compare dentro
  do mesmo mês. É o único arranjo em que a versão varia sem o tempo variar junto.
- Teste **todas** as fronteiras entre versões consecutivas, não só a que você
  suspeita. Se várias fronteiras deslocam as fases, o efeito não é específico.

Se as versões nunca coexistem, versão e tempo são a **mesma variável** e você não
consegue separar as duas. Diga isso no relatório em vez de afirmar causalidade.

---

## 3. Duas fontes de sono gravam no mesmo export

`pkg_name` pode ser:

- `com.sec.android.app.shealth` — o app oficial da Samsung
- `com.urbandroid.sleep` — *Sleep as Android*, um app de terceiro

Os dois têm **algoritmos diferentes**. Somar as duas fontes é fabricar uma
quebra que não existe no seu sono. Filtre por um pacote (o oficial) e diga qual
usou.

---

## 4. Soneca não é noite

Uma data pode ter várias sessões de sono. Sonecas quase não têm REM nem sono
profundo, então incluí-las puxa a mediana de REM% para baixo.

**Regra:** escolha o sono principal por data (maior duração) e trate as sonecas
como coluna agregada. Filtro por duração mínima (ex.: 240 min) é um bom segundo
corte.

---

## 5. Corrida × caminhada: use o PICO, não a média

Um treino com média 8 km/h pode ter picos de 14 km/h — é corrida. Classificar
pela média põe corrida leve na cesta de caminhada e mistura as séries.

**Regra:** se em algum momento passou de **10 km/h**, é corrida. Os tipos de
esteira (`15005` = treadmill, combinação de trote e caminhada) são ambíguos por
natureza e precisam dessa regra.

---

## 6. Códigos de exercício: use a tabela oficial

A tabela correta está em
[developer.samsung.com](https://developer.samsung.com/health/android/data/api-reference/EXERCISE_TYPE.html)
e está transcrita em `shtools.EXERCISE_TYPE_OFICIAL`.

**Um pacote do PyPI traz uma tabela errada**, e códigos como `15001`, `15002`,
`15003` acabam rotulados como musculação/treino funcional quando são, na
verdade, *step machine*, *weight machine* e *exercise bike*. Vale conferir a sua
antes de confiar.

O relógio também emite códigos que **não estão** na tabela (já apareceu `1007`).
Por isso `shtools.nome_exercicio()` devolve `Outro (<n>)` em vez de `None`: um
treino novo deve **aparecer** no relatório, não virar buraco silencioso.

---

## 7. Fuso horário e sessão que atravessa a meia-noite

`sleep_id` agrupa os segmentos de uma sessão, e a sessão pode começar antes da
meia-noite e terminar depois. Agrupar por **data** achata isso.

**Regra:** agrupe por `sleep_id`, não por data. Atribua a noite à data de
**início**, e seja consistente.

`time_offset` vem como `UTC-0300` — trate explicitamente em vez de assumir UTC.

---

## 8. Períodos parciais não são queda

Se o export termina no meio do mês, ou se você parou de usar o relógio, a
"queda" no gráfico é do calendário, não sua. O mesmo vale para a borda inicial,
quando o relógio acabou de ser pareado e os primeiros dias vêm incompletos.

**Regra:** marque os períodos truncados no gráfico e nunca os trate como
tendência. `SH_PERIODO_INICIO` existe para cortar a borda inicial.

---

## 9. HRV não se lê sozinho

HRV (RMSSD) é **inversamente relacionado à frequência cardíaca**: quando a FC
sobe, o HRV cai por razão puramente mecânica. Uma queda de HRV que desaparece
quando você controla pela FC **não é** mudança autonômica — é a FC mudando.

**Regra:** sempre calcule a correlação de HRV com FC e, se quiser afirmar algo
sobre o sistema nervoso, reporte o efeito **controlando pela FC**.

---

## 10. Poucos dados não sustentam conclusão

Antes de afirmar qualquer coisa, olhe os `n`. Um mês com 3 noites não sustenta
mediana. E o erro clássico de detecção de quebra é **olhar em todos os pontos e
escolher o pior** — o máximo de um teste sobre muitos pontos é sempre
"significativo".

**Regra:** `analise_medicacao.py` usa teste de permutação exatamente para isso
(reembaralha a série e mede o máximo do |t| sob a hipótese nula). Se você fizer
detecção de quebra na mão, faça o mesmo.

---

## 11. Ruído do algoritmo > efeito que você procura

Se a amplitude de REM% **entre versões do app** (mesma pessoa, mesma cama, mesmo
relógio) for maior que o efeito que você está investigando, então o efeito não é
interpretável com esses dados — ponto.

Rode `analise_versao_app.py` e **compare a amplitude com o efeito** antes de
escrever a conclusão. É o teste mais barato e o mais frequentemente esquecido.
