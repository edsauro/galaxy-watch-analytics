# Começando do zero

Guia para quem **nunca mexeu com terminal** e quer analisar os dados do próprio
Galaxy Watch.

A ideia é simples: você instala um assistente de IA que roda no seu computador,
cola os textos prontos que estão aqui, e ele faz o trabalho. Você não precisa
saber programar — precisa saber copiar e colar.

Tudo acontece na sua máquina. Seus dados de saúde **não saem do seu computador**
em momento nenhum.

---

## Antes de começar: o que você vai precisar

- **Um computador** com Linux ou macOS. No Windows, use o WSL (o próprio
  instalador do Windows tem, é um programa comum).
- **Python 3.11 ou mais novo** — [python.org/downloads](https://www.python.org/downloads/)
- **Um assistente de IA** (veja abaixo)
- **Uns 30 minutos** na primeira vez. Depois leva menos.

---

## Passo 1 — escolha um assistente de IA

As três opções abaixo funcionam **sem pagar nada**. Escolha pela conta que você
já tem.

### Opção A — Codex CLI, com sua conta ChatGPT gratuita ⭐

Se você já usa o ChatGPT, é o caminho mais curto. O Codex está incluído nos
planos do ChatGPT, **inclusive o gratuito** — o limite de uso é menor, mas dá
conta desta tarefa.

```bash
npm i -g @openai/codex
codex
```

Na primeira vez ele abre o navegador para você entrar com sua conta. Precisa do
[Node.js](https://nodejs.org) instalado antes.

### Opção B — Antigravity CLI, com sua conta Google gratuita ⭐

O agente do Google. Gratuito para uso individual, com acesso aos modelos Gemini.
Boa escolha se você não tem conta no ChatGPT.

Instalação e login: **[antigravity.google/docs/cli/install](https://antigravity.google/docs/cli/install/)**

Depois de instalar, é só digitar `agy` no terminal.

### Opção C — OpenCode, com um modelo gratuito

O OpenCode é código aberto e não cobra pelo programa. Ele se conecta a um
provedor de modelo — e o **OpenCode Zen** oferece vários modelos de custo zero.

```bash
curl -fsSL https://opencode.ai/install | bash
opencode
```

Dentro do OpenCode:

1. Digite `/connect` e escolha **OpenCode Zen**
2. Crie a conta em [opencode.ai](https://opencode.ai) — **pule a parte de
   pagamento**, não precisa de cartão
3. Cole a chave que ele mostrar
4. Digite `/models` e escolha **`deepseek-v4-flash-free`**

O `deepseek-v4-flash-free` é a melhor escolha entre os gratuitos para este
projeto: é forte em código e em análise de dados. Se quiser alternativa, o
`nemotron-3-ultra-free` também está na lista.

> A lista de modelos gratuitos muda com o tempo. Se algum não aparecer, rode
> `/models` e escolha outro que termine em `-free`.

### Também funcionam, mas dão mais trabalho

| Assistente | Por que ficou de fora da lista de cima |
|---|---|
| **Hermes Agent** (Nous Research) | Precisa configurar uma chave de API do provedor que você escolher — mais passos na instalação |
| **Claude Code** (Anthropic) | **Não tem plano gratuito** — exige assinatura paga |

Se você já usa um deles, funciona igual: os textos dos Passos 2 e 4 são os
mesmos.

---

## Passo 2 — peça para ele instalar o projeto

Abra o assistente e **cole este texto inteiro**:

```
Baixe o projeto https://github.com/edsauro/galaxy-watch-analytics para a pasta
~/Code/galaxy-watch-analytics. Leia o README.md e o SKILL.md, crie um ambiente
virtual Python e instale as dependências do requirements.txt.

Me diga se algum comando falhou e o que eu preciso fazer.

Ainda não tenho os dados: vou baixar o export do meu relógio e, quando chegar,
te passo o caminho do arquivo .zip para você mesmo descompactar e configurar.
Deixe tudo pronto até lá.
```

Ele vai trabalhar sozinho por alguns minutos. Se reclamar que falta Python ou
Node, instale o que ele pedir e peça para continuar.

---

## Passo 3 — baixe seus dados do Galaxy Watch

Isso é feito no **celular**, no aplicativo Samsung Health. Leva alguns minutos, e
a Samsung manda o arquivo por e-mail depois — às vezes leva algumas horas.

1. Abra o **Samsung Health** no celular
2. Toque nos **três pontinhos** (canto superior direito) → **Configurações**
3. Entre em **Baixar dados pessoais**
4. Escolha o período — **quanto mais longo, melhor**. Um ano já permite ver
   tendências; três meses é o mínimo para alguma coisa fazer sentido
5. Confirme e aguarde o e-mail

Quando o e-mail chegar:

6. Baixe o arquivo `.zip` no computador — **não precisa descompactar**, o
   assistente faz isso
7. Anote o caminho do arquivo (no Linux e no macOS costuma cair em `~/Downloads`)

O nome do arquivo é parecido com `samsunghealth_seunome_20260917073135.zip`.
**Esse arquivo tem o seu nome e o seu histórico de saúde.** Não mande para
ninguém, não suba em nuvem pública, não coloque no GitHub.

---

## Passo 4 — peça a análise

Com o zip baixado, **cole este texto** no assistente, trocando o caminho pelo do
seu arquivo:

```
O export do meu relógio chegou. O arquivo está em:
COLE_AQUI_O_CAMINHO_DO_ARQUIVO.zip

Descompacte você mesmo e aponte o projeto para a pasta correta. Depois leia o
SKILL.md do projeto em ~/Code/galaxy-watch-analytics e faça:

1. Rode, nesta ordem: analise_sono.py, analise_vitality.py, analise_extras.py e
   build_sqlite.py, escrevendo os resultados em ~/Code/galaxy-watch-analytics/report/

2. ANTES de qualquer análise ao longo do tempo, rode analise_granularidade.py e
   analise_versao_app.py. Me diga se houve troca de versão do aplicativo que
   quebra a comparação entre períodos — isso muda a leitura de tudo o que vem depois.

3. Só então monte um relatório em português com:
   - sono: horas dormidas, tempo em cada fase, eficiência, quantas noites ruins
   - frequência cardíaca de repouso
   - variabilidade cardíaca (HRV)
   - treinos: quanto, quando, e evolução

4. Para cada número, diga quantos dias ou noites ele usou. Se for menos de dez,
   me avise que não dá para concluir nada.

5. Não apresente nada como diagnóstico médico. Se algo parecer fora do comum,
   diga que é motivo para eu levar ao meu médico, não o que fazer.

No fim, me diga onde estão os arquivos gerados e me mostre os 10 achados mais
relevantes e mais bem sustentados pelos dados.
```

---

## O que você vai receber

- Uma pasta `report/` com os resultados
- Um **banco de dados consultável** — uma linha por dia, com resumos por semana,
  mês e semestre. O assistente pode consultar por você: *"quantas noites eu dormi
  menos de 6 horas em maio?"*
- **Análises** de sono, coração, HRV, respiração e treino
- **Gráficos**
- **Seu ECG**, se você tiver feito — o projeto lê os PDFs que a Samsung manda

---

## Se algo der errado

**"Não encontrei nenhum export"** — o caminho está errado, ou o zip não foi
descompactado. Diga ao assistente onde o arquivo está e peça para ele resolver.

**"No module named pandas"** — as dependências não instalaram. Peça para o
assistente refazer o Passo 2.

**O relatório saiu estranho, com números que não batem com o seu relógio** —
peça para ele rodar `val_sono.py`, que compara o que o projeto calculou com o que
a própria Samsung já traz pronto. Se os dois não baterem, alguma coisa saiu
errada na leitura e ele precisa investigar.

**Ele tirou uma conclusão muito forte de poucos dados** — desconfie. Peça:
*"quantas noites sustentam essa afirmação?"* Menos de dez não sustenta quase nada.

**Acabou o limite de uso do assistente** — espere o período renovar. O trabalho
não se perde: os dados e os resultados já estão no seu computador.

---

## Duas coisas que você precisa saber

**Não é aparelho médico.** O que o relógio mede vem do pulso, com precisão
limitada, e nada aqui substitui avaliação de um profissional de saúde. Se algo
aparecer fora do comum, leve ao seu médico — não tome decisão de saúde com base
nisso.

**O arquivo que você baixa é sensível.** Ele contém seu sono, seu coração e seus
treinos de anos. O projeto não guarda nada disso no repositório, mas você tem o
arquivo no seu computador — trate como documento pessoal.

---

## Para quem quer entender os detalhes

- `README.md` — o projeto, as análises e as fontes de onde tiramos cada informação
- `references/armadilhas.md` — onze armadilhas que já produziram número errado de
  verdade. Vale ler antes de tirar conclusões fortes.
