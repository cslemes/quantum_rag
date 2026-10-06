# 5. Resultados medidos

Este capítulo apresenta o que foi medido, sob qual protocolo, e com quais
limites de interpretação. A taxa de sucesso do gerador local é baixa. Ela é
apresentada como diagnóstico do gargalo, não como resultado do sistema: o
objeto de avaliação aqui é a cascata de verificação e o loop de reparo, e um
gerador que falha muito é precisamente o regime em que esses componentes podem
ser observados funcionando.

Nenhum número neste capítulo vem de julgamento de modelo de linguagem. Todo
veredito de sucesso é produto da cascata determinística descrita no capítulo 3.

---

## 5.1 Protocolo e definições

As métricas usadas no capítulo, todas apuradas a partir dos registros de
execução:

| métrica | definição |
|---|---|
| **sucesso** | status final `success`: todas as camadas aplicáveis passaram, incluindo corretude funcional contra a referência verificada independentemente |
| **`compila@1`** | a primeira tentativa executa e transpila sem erro |
| **loop engajado** | houve pelo menos uma iteração de reparo |
| **convergido** | terminou em sucesso *tendo* engajado o loop |
| **veredito semântico alcançado** | status final em `success` ou `failed_semantic` |
| **regressão** | alcançou verificação semântica em alguma tentativa e terminou em falha estática |

O limite é de cinco tentativas por tarefa. A suíte tem 120 tarefas: 60
canônicas e 60 perturbadas (capítulo 4).

**Ambiente.** Todas as medidas deste capítulo vieram do *venv* do sandbox com
Ollama no host, nunca em container. O ambiente canônico declarado prevê a
aplicação containerizada; essa divergência é registrada aqui e tratada no
capítulo 7, e não é a primeira vez que o ambiente declarado antecedeu o
ambiente usado. O modelo de GPU não é gravado nos registros de execução, de
modo que "mesmo hardware" entre rodadas é declaração, não verificação.

---

## 5.2 Baseline com gerador local

Gerador: `qwen2.5-coder:7b`. Suíte completa, uma semente.

| | 2026-09-26 | rodada atual |
|---|---|---|
| sucesso | 1/120 | **7/120** (5,8%; IC 95% 2,9–11,6%) |
| `compila@1` | 20/120 | 20/120 |
| terminaram em falha | 119/120 | 112/120 |
| veredito semântico alcançado | 34/120 | 58/120 |

Composição das 112 falhas: 61 terminaram em falha estática e 51 em falha
semântica. Uma execução (`ghz_linear5_mixed_perturbed`) foi abortada na quinta
iteração por excesso de recursos — o único caso de `ResourceExcess` terminal em
120 execuções.

### A leitura

O número que não se moveu é o informativo. `compila@1` ficou idêntico, e no
subconjunto onde a comparação é limpa — as 67 tarefas cujo enunciado não mudou
entre as rodadas — é 13/67 nas duas, **sem uma única troca de tarefa**. A
primeira tentativa do gerador local não melhorou em nada.

O que mudou está depois dela:

- nenhuma tarefa acertou na primeira tentativa, nas duas rodadas;
- **seis dos sete sucessos só compilaram após reparo estático**;
- a fração de execuções que TERMINAM em falha estática caiu de 84% (287/341,
  baseline de 19/09) para 51% (61/120, run C).

Ou seja: o contador de sucesso do braço local é integralmente atribuível ao
loop de reparo. Não há componente de "o gerador ficou melhor" nele.

Um segundo sinal aponta na mesma direção. Chamando de **regressão** a execução
que alcança verificação semântica e depois volta a falhar em estático, a taxa
caiu de 40 em 74 (54,1%; rodada B, fatia da semente 1 — 120 tarefas, 74 com checagem semântica; as três sementes dão o mesmo 74/40) para 29 em 88 (33,0%; rodada C): o loop não só avança mais,
destrói menos do que já havia conseguido. O baseline de 19/09 (anterior ao
*trace*; contagem por `error_history`, limite inferior) dá 63 em 113 (55,8%):
estável entre os dois estados anteriores, com a ressalva de que eles diferem em
protocolo e corpus.

A métrica é apurada a partir do *trace* de execução, não da contagem de
`error_history`. A contagem anterior deixava escapar uma tarefa
(`vqe_h2_r055_perturbed`), cuja falha na primeira tentativa era classificada
como erro estático embora a verificação semântica tivesse rodado. Diferente das
duas afirmações acima, esta é comparação entre rodadas e está sujeita ao
confundimento de versão de servidor tratado em §5.7.

### O que estes números não permitem afirmar

A atribuição por mudança está fechada. As cinco alterações relevantes — T115,
T116, T117, T118 e T090d — entraram juntas entre as duas rodadas, de modo que o
delta de 1 para 7 é do pacote e não de nenhuma delas. T090d é a única isolada,
e só no braço de 30B (§5.5).

Além disso, T116 reescreveu 52 enunciados de tarefa, e a versão do servidor
Ollama mudou de 0.34.4 para 0.35.1 entre as rodadas. O delta portanto confunde
três coisas: mudanças no loop, mudanças na suíte e mudança de servidor. A
extensão desta última está tratada em §5.7.

Cabe distinguir o que depende disso e o que não depende. As duas afirmações
centrais desta seção — `compila@1` estável em 13/67 sem troca de tarefa, e seis
dos sete sucessos obtidos somente após reparo estático — são apuradas **dentro
de uma única rodada** e não envolvem comparação. Elas sustentam a conclusão de
que o contador de sucesso do braço local é atribuível ao loop, e nenhum
confundimento entre rodadas as alcança. O delta de 1 para 7 e a taxa de
regressão são comparações entre rodadas, e são apresentados como contexto, não
como evidência.

---

## 5.3 Determinismo

Zero divergências em 360 execuções, em quatro métricas apuradas. O protocolo
que viabiliza esse resultado é parte da contribuição e não é automático:

- `reset_per_run` — reinício do servidor entre execuções;
- `temperature=0` fixada explicitamente no cliente;
- `num_ctx` fixado, para evitar truncamento silencioso de contexto;
- ordenação `warm → check → unload` no ciclo de carga do modelo.

Este protocolo foi construído *em resposta* a uma medida anterior: uma métrica
de controle, escolhida por não poder mudar, mudou 43%, revelando que o cliente
não fixava temperatura e que 26% das execuções divergiam entre rodadas
idênticas. O capítulo 6 trata do episódio como achado metodológico; aqui ele
registra apenas que o determinismo relatado é condicional ao protocolo, e não
uma propriedade do servidor.

---

## 5.4 Recuperação versionada

`recall@8` = **0,9524**.

Duas ressalvas, ambas no sentido de não superestimar o componente. Parte da
queda aparente de desempenho em corpus maior, observada antes, era
subestimação da própria medida e não degradação da recuperação. E as consultas
sintéticas de avaliação foram escritas por quem construiu o corpus, o que é
viés conhecido e está declarado no capítulo 7.

---

## 5.5 Geradores mais capazes

Para responder se o gargalo é a arquitetura ou o gerador, a mesma cascata foi
executada com dois geradores mais capazes sobre um subconjunto de 16 tarefas.

**O n é 16.** Diferenças de poucas tarefas neste subconjunto não sustentam
afirmação estatística, e nenhuma é apresentada como tal. O que o subconjunto
responde é qualitativo e suficiente: a arquitetura funciona quando o gerador
alcança o regime em que ela opera.

| | local 7B (n=120) | 30B R0 | 30B R2 ⚠ | 30B R3 | 30B R4 | fronteira |
|---|---|---|---|---|---|---|
| sucesso | 7/120 | 4/16 | 9/16 | 6/16 | 10/16 | 15–16/16 |
| `compila@1` | 20/120 | 11–12/16 | | | | 16/16 |
| loop engajado | 16/16¹ | 12/16 | | | | 0–2/16 |
| convergido | 1 | 1 | 6 | 3 | 7 | 0–1 |

¹ no subconjunto correspondente.

**⚠ R2 não é resultado válido.** Naquela configuração, informação derivada do
oráculo de referência alcançava o crítico. T118 fechou o vazamento e o número
caiu de 9 para 6. A diferença de três tarefas mede quanto valia o vazamento,
não quanto vale o sistema. A regra em vigor desde então: o crítico e o gerador
podem ver o enunciado da tarefa, propriedades do circuito gerado e qual
asserção declarada falhou; nunca nada derivado da referência. O critério é "o
que um usuário real teria é legítimo; o que só o benchmark tem não é".

**R3 → R4** é a única comparação com uma só variável: T090d, diagnóstico
estruturado mais ancorado. Resultado 6 → 10, acima da banda de 7–9 registrada
antes da execução. O custo também foi medido, e é real: alternâncias A→B→A
caíram de 11 para 1, mas falhas idênticas consecutivas subiram de 5 para 11, e
das cinco tarefas que falham nos dois braços, quatro repetem o mesmo erro mais
vezes que antes. Um diagnóstico mais firme reduz oscilação e aumenta fixação.
O valor líquido é de quatro tarefas em n=16.

**A relação inversa entre capacidade e engajamento do loop é o achado central
desta seção.** No gerador local o loop engaja em todas as execuções e resgata
seis de sete sucessos. No modelo de fronteira engaja em zero a duas de
dezesseis, porque quase nada precisa de resgate. O loop é instrumento de
recuperação: seu valor cresce à medida que o gerador piora, e a arquitetura não
é o gargalo em nenhum dos dois regimes.

**Custo.** Três braços de fronteira custaram cerca de US$ 0,09 no total. Os
braços de 30B em GPU alugada: R0 US$ 0,172, R1+R2 US$ 0,237, R4 cerca de
US$ 0,31 — este último incluindo aproximadamente 45 minutos de GPU ociosa por
defeito no laço de espera do runner, registrado como erro de execução e não
diluído na média.

---

## 5.6 Desempenho

Existem três medições de duração de suíte, sob configurações diferentes:

| rodada | configuração | tempo |
|---|---|---|
| A (`99960870…`) | 360 execuções, 3 sementes, reset único, Ollama 0.34.1 | 205,8 min |
| B (`9e19fa12…`) | 360 execuções, 3 sementes, `reset_per_run`, Ollama 0.34.4 | 260 min |
| C (`1bf505bf…`) | 120 execuções, 1 semente, `reset_per_run`, Ollama 0.35.1 | **72 min** |

**O número citável é 72 minutos, para a suíte como configurada hoje.** As três
medidas não são comparáveis entre si — diferem em número de execuções,
protocolo de reset e versão de servidor — e não constituem série temporal de
desempenho. Nenhuma tendência é afirmada a partir delas.

Os tempos observados na interface não entram aqui: são réplica de cache e não
medem geração.

---

## 5.7 Confundimentos e o que não foi medido

**Versão de servidor não fixada no momento da execução.** O servidor Ollama
local mudou de 0.34.4 para 0.35.1 entre as rodadas comparadas em §5.2.

A proteção parcial já existia: a versão era gravada em cada registro de
execução, e a ferramenta de comparação se recusava a comparar rodadas de
versões diferentes. A comparação foi feita em prosa, lado a lado, fora dessa
ferramenta. O capítulo 6 trata o padrão — uma verificação que só dispara dentro
de uma ferramenta de uso opcional não é verificação; aqui registra-se o
reparo: a versão esperada passou a ser fixada em `bench/environment.yaml`, o
runner aborta na inicialização em caso de divergência nomeando as duas versões,
servidor inacessível conta como divergência, e a execução com
`--allow-ollama-version-mismatch` é estampada no registro, de modo que rodada
sob exceção não possa ser confundida com rodada limpa.

Uma re-execução completa das 120 tarefas em 0.34.4, idêntica em todo o resto,
limita o efeito. A previsão foi registrada antes da execução: 5 a 9 sucessos de
120, sendo 3 ou menos — ou 12 ou mais — motivo para retirar qualquer atribuição
do delta ao loop. *[PREENCHER com o resultado. Ver §5.2: o resultado desta
rodada não altera as duas afirmações centrais da seção, que são
intra-rodada.]*

**Modelo de GPU declarado, não verificado.** O servidor local não expõe o
modelo de GPU por nenhum dos endpoints disponíveis. O campo passou a ser
registrado com status explícito de não verificado, em vez de omitido ou
assumido.

**`cx_ratio` não é citável.** O orçamento de recursos aplica o fator 2,0 sobre
a profundidade da referência transpilada, e essa camada funciona. A razão de
portas de dois qubits é reportada ao lado dela mas não condiciona veredito, e
não conta as portas `cp` em tarefas de QFT porque a transpilação é feita sem
`basis_gates`. Nenhum número de `cx_ratio` é usado neste capítulo, e nenhum
deve ser citado no relatório enquanto a métrica não for recomputada com base
declarada.

Registre-se também o que foi investigado e **não** se confirmou: suspeitou-se
que o orçamento de duas tarefas perturbadas fosse largo demais, por comparação
com a profundidade de suas gêmeas não perturbadas. A comparação é inválida — a
gêmea é outra tarefa, e sua profundidade não é linha de base para a versão
perturbada. Implementações naturais corretas das duas tarefas ficam em 20–26 e
23–27, contra referências de 25 e 27. As referências estão corretas, o
orçamento discrimina, e nenhuma tarefa foi excluída.

**Execução em hardware quântico real** não foi medida. A US5 permanece não
construída e consta no capítulo 8 como trabalho futuro.

**Reparo incremental** (hipótese H-inc) não foi medido. Está registrado com
condições de falsificação e consta no capítulo 8.

**Figuras do baseline de 19/09, reconciliadas.** Run `ce9614fa3a6f60a6`
(360 execuções, 3 seeds, 19 `harness_error`, **341 válidas**): sucesso
**6/341 = 1,8%**; **287/341 = 84%** terminam em falha estática (o enunciado
"param antes da verificação funcional" estava errado: 63 das 287 já tinham
chegado a ela); **331 de 335 falhas** esgotaram as cinco tentativas (335 =
341 − 6; 4 recusadas na entrada). Run pré-F28, corpus 2.x, seeds não
independentes: citar só como histórico, com run e denominador, nunca ao lado
dos números de 120 execuções sem esse rótulo. Ver `report-notes.md`,
"Reconciliação das figuras".

---

## Pendências deste capítulo

Não fazem parte do texto final; remover quando resolvidas.

1. ~~Confirmar os números de regressão.~~ Resolvido: 40/74 → 29/88, apurado do
   *trace*.
2. ~~Diagnóstico das duas tarefas com orçamento suspeito.~~ Resolvido: nada a
   alterar; a suspeita era baseada em linha de base inválida.
3. Preencher o resultado da re-execução em Ollama 0.34.4 em §5.7. **Não
   bloqueante** — nenhuma afirmação central depende dela.
4. ~~Reconciliar ou aposentar as figuras de 1,8% / 84% / 331-de-335.~~
   Resolvido: as três se re-derivam do run `ce9614fa…` (6/341, 287/341, 331 de
   335); o enunciado do 84% foi corrigido nos três documentos.
5. Decidir se `compila@1`, loop engajado e convergido entram na tabela de §5.5
   para R2–R4 ou ficam só em R0 e fronteira, conforme o que estiver apurado.
6. Recomputar `cx_ratio` com `basis_gates` declarada, ou removê-la do conjunto
   de métricas reportadas.
