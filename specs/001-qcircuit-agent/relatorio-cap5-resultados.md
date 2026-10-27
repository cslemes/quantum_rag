# 5. Resultados medidos

Este capítulo apresenta o que foi medido, sob qual protocolo, e com quais
limites de interpretação. A taxa de sucesso do gerador local é baixa. Ela é
apresentada como diagnóstico do gargalo, não como resultado do sistema: o
objeto de avaliação aqui é a cascata de verificação e o loop de reparo, e um
gerador que falha muito é precisamente o regime em que esses componentes podem
ser observados funcionando.

Nenhum número neste capítulo vem de julgamento de modelo de linguagem. Todo
veredito de sucesso é produto da cascata determinística descrita no capítulo 3.

**Regra de redação.** Toda cifra em prosa nomeia a execução ou o estado do
sistema em que foi medida: a build do servidor *e* o estado do código (corpus,
correções que já tinham entrado). Nenhuma cifra de um estado anterior a uma
correção aparece no presente: ou é rotulada como histórica, com a execução e o
denominador, ou é re-derivada no estado vigente. A regra existe porque ela foi
violada: ver o capítulo 6, §6.5, "Uma cifra interna de antes da correção". Durações
têm dois nomes fixos, tempo de relógio e tempo de execução, e nunca aparecem sem
um deles (§5.6).

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

| | 2026-09-26 (run B, Ollama 0.34.4) | run C (Ollama 0.35.1) |
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
  baseline de 19/09, Ollama 0.34.1, anterior ao roteamento de `MissingImport` e ao
  *trace*) para 51% (61/120, run C, Ollama 0.35.1).

Ou seja: o contador de sucesso do braço local é integralmente atribuível ao
loop de reparo. Não há componente de "o gerador ficou melhor" nele.

Um segundo sinal aponta na mesma direção. Chamando de **regressão** a execução
que alcança verificação semântica e depois volta a falhar em estático, a taxa
caiu de 40 em 74 (54,1%; rodada B, fatia da semente 1 — 120 tarefas, 74 com checagem semântica; as três sementes dão o mesmo 74/40) para 29 em 88 (33,0%; rodada C): o loop não só avança mais,
destrói menos do que já havia conseguido. O baseline de 19/09 (anterior ao
*trace*; contagem por `error_history`, limite inferior) dá 63 em 113 (55,8%)
agregado, mas por semente dá 10/19 (52,6%), 35/55 (63,6%) e 18/39 (46,2%): três
sementes não independentes numa faixa de 46% a 64%, que o agregado esconde. A
leitura defensável é a mais fraca: os dois estados anteriores (baseline de
19/09, Ollama 0.34.1, e rodada B, 0.34.4, 54,1%) caem na mesma faixa de 46–64%,
e a rodada C (33,0%) fica abaixo dela. Não se afirma que a taxa estivesse
"estável". Os estados diferem em protocolo e corpus.

A métrica é apurada a partir do *trace* de execução, não da contagem de
`error_history`. A contagem anterior deixava escapar uma tarefa
(`vqe_h2_r055_perturbed`), cuja falha na primeira tentativa era classificada
como erro estático embora a verificação semântica tivesse rodado. Diferente das
duas afirmações acima, esta é comparação entre rodadas e está sujeita ao
confundimento de versão de servidor tratado em §5.7.

### Runs E e F: a mesma suíte em outra build, e em outra escala

Duas execuções posteriores, ambas na build **Ollama 0.40.8** e sob o mesmo
código do laço, os mesmos enunciados, uma semente e `reset_per_run`:
**E**, o mesmo `qwen2.5-coder:7b` (arquivo de modelo não baixado de novo desde
C), e **F**, `qwen2.5-coder:1.5b`. A comparação C × E isola a versão do servidor;
E × F isola a escala do modelo. As duas são lidas separadamente.

| run | modelo | Ollama | sucesso (IC 95%) | `compila@1` | falha estática / semântica / abortada | veredito semântico alcançado | checagem semântica em alguma tentativa | regressão |
|---|---|---|---|---|---|---|---|---|
| C `1bf505bf…` | 7B | 0.35.1 | 7/120 (2,9–11,6%) | 20 | 61 / 51 / 1 | 58 | 88 | 29/88 (33,0%) |
| **E** `7fd09e27…` | 7B | **0.40.8** | **5/120** (1,8–9,4%) | 19 | 56 / 58 / 1 | 63 | 87 | 23/87 (26,4%) |
| **F** `a6a6a63f…` | 1,5B | **0.40.8** | **1/120** (0,1–4,6%) | 10 | 107 / 11 / 0 (+1 `rejected_input`) | 12 | 16 | 4/16 (25,0%) |
| **F-prime** `cf4ba161…` | 1,5B + penalidade de repetição 1.1 | **0.40.8** | **0/120** (0–3,1%) | 19 | 99 / 20 / 0 (+1 `rejected_input`) | 20 | 22 | 2/22 (9,1%) |

As previsões foram registradas antes das execuções e se confirmaram: E, 3 a 11
de 120 (resultado 5); F, 0 a 3 sucessos e `compila@1` de no máximo 10/120
(resultado 1 e 10, este exatamente no teto da faixa). Nenhuma das duas execuções
usou o parâmetro de exceção do portão de versão. E foi executada com o cache de
respostas frio; uma primeira execução E foi, na verdade, um replay do cache de
C e foi descartada (capítulo 6, §6.5). O resultado entre builds está em §5.3;
o de escala é que o 1,5B alcança a checagem semântica em 16 de 120 tarefas
contra 87 do 7B: o gargalo de compilar piora com a escala, e a conclusão do
capítulo de que o gargalo está no gerador se sustenta.

**F-prime.** O Ollama 0.40.8 não envia penalidade de repetição por padrão (um parâmetro herdado e nunca fixado), e em F
51 das 77 falhas que repetiam o mesmo erro nas cinco tentativas eram uma geração que degenerava em repetição até o
teto de 4.096 tokens (capítulo 6, §6.3). F-prime repete a suíte com penalidade 1.1 (perfil `local-1.5b-rp`), no mesmo
código do laço mais o rótulo `GenerationTruncated`, com o cache frio. A previsão, registrada antes, era que a
degeneração sumisse, que a fração de falhas presas caísse para perto de 38,8% e que o sucesso subisse para 2 a 5 de
120. **A degeneração diminuiu (51 execuções para 18) mas a fração presa não caiu** (65,3% para 67,2%): as falhas presas
que não são truncagem passaram de 26 para 62, porque o programa agora executa e o 1,5B repete cinco vezes erros
comuns (símbolos inexistentes, decomposição errada). **O sucesso foi 0 de 120**, abaixo da faixa; o ramo "acima de 10",
que reescreveria a narrativa do 1,5B, não disparou. A decodificação explicava a executabilidade (`compila@1` de 8,3%
para 15,8%, tokens e latência pela metade), não o que a narrativa sustenta: o 1,5B quase nunca conclui uma tarefa e
não muda a resposta quando corrigido. A narrativa do 1,5B fica; F permanece a comparação de configuração idêntica
contra E, e F-prime é a linha de base da destilação.

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

O determinismo relatado depende do que se mediu e da build do servidor. Há três
medidas de estabilidade, em três escopos, e cada uma vale só nas condições dela;
uma quarta medida (entre builds) mostra que a estabilidade não se transfere. Nenhuma
das três substitui as outras:

| escopo | protocolo | build | n | resultado | o que NÃO mostra |
|---|---|---|---|---|---|
| (1) repetição sob sequência de chamadas fixa (A × A2) | um descarregamento por execução | 0.34.1 | 360 | 0 divergências nas 4 métricas | independência entre tarefas; outras builds; o protocolo vigente |
| (2) invariância de semente dentro da execução (B) | reset por execução | 0.34.4 | 120 tarefas × 3 sementes | 120/120 tarefas idênticas | repetição da suíte; outras builds |
| (3) repetição da suíte (G × E) | reset por execução | 0.40.8 | 120 | **0/120 divergências** nas 4 métricas | outras builds; o 1,5B; mais de uma repetição |

**(1) Repetição sob uma sequência de chamadas fixa: zero divergências em 360,
Ollama 0.34.1.** Execuções A (`99960870…`, 2026-09-22, 02:23–05:43 UTC) e A2
(`7de38e77…`, 05:49–09:09 UTC): mesmo commit, 120 tarefas × sementes 1, 2 e 3,
corpus de 1.019 pontos, mesmo host e ambiente, `temperature=0` e `num_ctx`
fixados, ordem de recuperação determinística, servidor **descarregado uma única
vez** antes de cada execução. Quatro métricas, re-derivadas dos registros:
status, classificação da tentativa 1, código final byte a byte e sequência de
erros (iteração, estágio, tipo e mensagem): 0/360 em cada uma (IC 95% 0–1,1%);
vetor de resultado por tarefa, 0/120. Iterações e contagens de tokens também
coincidem em 360/360. Uma exceção fora das métricas: o resumo (hash) do
circuito serializado (`qpy_sha256_16`) no *payload* de um erro de serialização difere em
3 registros (`ising_weighted_maxcut_4q`, sementes 1 a 3), com código final
idêntico. Investigado depois (ver (3)): o resumo é instável por construção para
circuitos de biblioteca (§6.4), não uma divergência do gerador.

O cache de respostas **não pode** ter servido as chamadas da segunda execução.
A razão por tarefa entre os tempos de parede de A2 e A tem mediana 1,00 (mínimo
0,98, nenhuma tarefa abaixo de 0,5), e as duas execuções levaram o mesmo tempo
de execução, 200 minutos; um replay servido por cache foi medido antes em 2 min
24 s contra 8 min 51 s (3,7 vezes mais rápido; tempo total de um piloto de 20
tarefas, sem separar execução de relógio). Os registros de projeto dizem
que o diretório do cache foi limpo antes das duas execuções (isso não é
re-verificável hoje). E um acerto dentro de uma execução não esconderia uma
divergência entre as duas, porque a primeira ocorrência de um prompt é uma
chamada real em ambas.

O que esse zero mede é **identidade de replay**: as duas execuções percorreram a
mesma ordem de tarefas, portanto o mesmo histórico de estado do servidor em cada
ponto. Ele **não** mede que o resultado de uma tarefa independe das que a
precederam, e depois se mostrou que não independe (estado interno de prompt e KV
do Ollama passa de uma tarefa à seguinte). Vale nas condições acima: uma build
(0.34.1), um único descarregamento, a mesma sequência de chamadas, cache frio, o
mesmo host. **Não é o protocolo vigente** (reset por execução, adotado em
2026-09-26, depois dessa descoberta), e versões anteriores deste capítulo o
atribuíam a ele: a atribuição estava errada.

**(2) Sob o protocolo vigente, dentro de uma execução.** Na rodada B (`9e19fa12…`,
2026-09-26, Ollama 0.34.4, `reset_before_each_run`, 360 registros, 236 minutos
de execução, geração real) as três sementes de cada tarefa são **byte-idênticas**
em status, código final e sequência de erros em **120 de 120 tarefas** (as
sementes têm chaves de cache distintas, portanto não servem umas às outras). O
verificador de protocolo (duas tarefas × três sementes byte-idênticas) passou
antes de C, E e F, nas builds 0.35.1 e 0.40.8. É determinismo dentro de uma
execução e de uma build, e não é uma repetição da suíte.

**(3) Repetição da suíte sob o protocolo vigente, na mesma build: 0 em 120.**
A execução G (`f64b9464…`, 2026-10-23, Ollama **0.40.8**, `reset_before_each_run`,
7B, 120 tarefas, uma semente, mesmo código do laço e mesmos enunciados) foi
comparada com a execução E (`7fd09e27…`, mesma build e configuração), que já
existia. As quatro métricas, **0/120** cada: status, classificação da
tentativa 1, código final byte a byte e sequência de erros (iteração, estágio,
tipo e mensagem). Também 0/120: iterações, tokens de entrada e de saída, e o
*trace* inteiro. A única diferença no registro de erros completo, incluindo o
*payload*, é 1 tarefa (`ising_weighted_maxcut_5q`), e é o resumo (hash) do
circuito serializado em erros de serialização, instável por construção para
circuitos de biblioteca (§6.4), não uma divergência do gerador. O tempo de
execução é compatível (68,1 min contra 67,2; razão por tarefa com mediana 1,02).

*Cache.* A taxa de acerto de G é **112 de 1.064 chamadas (10,5%)**, e o resumo a
rotula "parcialmente quente". Todos os acertos são de entradas que a própria G
gravou antes: 12 do verificador de protocolo, que roda as duas tarefas de
controle com a semente 1 antes da suíte (os 9 de `dj_constant_4q` e os 3 de
`qaoa_maxcut_4q_perturbed` na suíte), e 100 de prompts idênticos repetidos
dentro de uma mesma execução de tarefa. Nenhum pode vir de E: as chaves de E são
de um formato anterior e não casam com as atuais, e os 988 arquivos de cache que
existiam antes de G são os de E. Para as duas tarefas de controle, o registro
da suíte é a cópia da geração do verificador de protocolo, comparada com E do
mesmo modo. A taxa de acerto de E **não foi gravada** (o relato por execução veio
depois); o argumento de que E foi fria é o tempo de execução (67,2 min contra 66,1 de C
e contra 2,4 min da primeira E, que foi replay; razão por tarefa em relação a C
com mediana 1,04), a medida certa para "isto chamou o modelo" (§5.6). Uma repetição só, em uma build: não mostra que duas outras
repetições coincidiriam.

**(4) Entre builds do servidor, o determinismo não vale.** C e E diferem só na
versão do servidor (0.35.1 e 0.40.8): mesmo arquivo de modelo, mesmo código do
laço, mesmos enunciados, mesma semente, servidor reiniciado a cada execução. O
nó planejador recebe apenas o enunciado da tarefa e um *prompt* de sistema
fixo — sem recuperação, sem tentativa anterior, sem estado acumulado — e o
código dele não mudou. Mesmo assim os requisitos que ele devolveu diferem entre
as duas builds em **34 das 120 tarefas (28%)**, com entrada idêntica (em
`vqe_h2_r055`, o `output_format` saiu `"numeric"` em C e `"fixed_circuit"` em
E). No grafo inteiro, o código final difere em **102 das 120 tarefas** e o
status final em **36 das 120** (84 coincidem). O agregado quase não se move (7
para 5 sucessos, `compila@1` 20 para 19), mas os sucessos que as duas execuções
têm em comum são 3, e o conjunto de `compila@1` coincide em 14 tarefas (6 só em
C, 5 só em E). Nenhuma conclusão por tarefa passa de uma build para a outra, e
"zero em 360" significa zero em 360 para uma build.

---

---

## 5.4 Recuperação versionada

`recall@8` = **0,9365** (59 de 63 alvos; MRR 0,7152) no corpus **1.2.x de 875
chunks**, o índice fixado e usado nas execuções B, C, E, F e G. A cifra de
0,9524 (60/63; MRR 0,7196) que este parágrafo trazia foi medida sobre o corpus
anterior (documentação 2.x rotulada 1.2.4, 1.020 chunks), que o corpus atual
substituiu; ela vale como história do corpus, não como o recall do sistema
medido neste capítulo. As 63 consultas e os gabaritos são os mesmos nas duas
medidas.

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

| | local 7B (run C, n=120, Ollama 0.35.1) | 30B R0 (pod, Ollama 0.34.4) | 30B R2 ⚠ (pod, 0.34.4) | 30B R3 (pod, 0.34.4) | 30B R4 (pod, 0.34.4) | fronteira (API; sem build de servidor) |
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
desta seção.** No gerador local (7B, run C, Ollama 0.35.1) o loop engaja em todas as
execuções do subconjunto e resgata seis de sete sucessos. Nos braços de
fronteira (API, n = 16) engaja em zero a duas de dezesseis, porque quase nada precisa de resgate. O loop é instrumento de
recuperação: seu valor cresce à medida que o gerador piora, e a arquitetura não
é o gargalo em nenhum dos dois regimes.

**Custo.** Três braços de fronteira custaram cerca de US$ 0,09 no total. Os
braços de 30B em GPU alugada: R0 US$ 0,172, R1+R2 US$ 0,237, R4 cerca de
US$ 0,31 — este último incluindo aproximadamente 45 minutos de GPU ociosa por
defeito no laço de espera do runner, registrado como erro de execução e não
diluído na média.

---

## 5.6 Desempenho

**Duas medidas, dois nomes fixos, e uma só por afirmação.**

- **Tempo de relógio**: do lançamento do processo ao seu fim. Responde "quanto
  tempo a suíte leva", e é a base do critério SC-007 (3 h para 3 sementes).
- **Tempo de execução**: a soma de `latency_s` dos registros. Responde "quanto
  cômputo a suíte consome", e é a medida certa para comparar uma execução real
  com um replay de cache.

Uma terceira quantidade, o intervalo entre o início do primeiro registro e o fim
do último, não é uma medida citável: serve só de ponte, para dizer de onde vem a
diferença entre as duas.

| run | configuração | execução | intervalo 1º→último registro | relógio |
|---|---|---|---|---|
| A (`99960870…`) | 360 execuções, 3 sementes, reset único, Ollama 0.34.1 | 200,1 min | 200,1 min | 205,8 min |
| B (`9e19fa12…`) | 360 execuções, 3 sementes, `reset_per_run`, Ollama 0.34.4 | 236,4 min | 254,5 min | 260,4 min |
| C (`1bf505bf…`) | 120 execuções, 1 semente, `reset_per_run`, Ollama 0.35.1 | 66,1 min | 72,1 min | **não gravado** |
| E (`7fd09e27…`) | 120 execuções, 1 semente, `reset_per_run`, Ollama 0.40.8 | 67,2 min | 73,2 min | 81,7 min |
| F (`a6a6a63f…`, 1,5B) | 120 execuções, 1 semente, `reset_per_run`, Ollama 0.40.8 | 112,4 min | 118,4 min | 126,5 min |
| G (`f64b9464…`) | 120 execuções, 1 semente, `reset_per_run`, Ollama 0.40.8 | 68,1 min | 74,1 min | 83,9 min |

Sobre a diferença entre o relógio e a execução (cerca de 15 minutos em E e G):
**só uma parte é o reinício do servidor.** Os registros mostram que o intervalo
entre tarefas é exatamente 3,0 s por execução em todas as runs com
`reset_per_run` (18,1 min em B, 6,0 min em C, E, F e G) e zero em A (um
descarregamento único): esse é o reinício. O resto é a verificação de
referências e o verificador de protocolo, que rodam antes da primeira execução
(cerca de 5,7 a 9,8 min). O relógio de C não foi gravado: o "72 min" que este
capítulo citava era o intervalo 1º→último registro (72,1), e o "81,7" de E, o
relógio; a primeira correção deste parágrafo ainda misturou as duas.

**Qual medida sustenta qual afirmação.** "Quanto tempo a suíte leva": relógio,
citando só E ou G, **nunca C, cujo relógio não foi gravado**
(E 81,7 e G 83,9 min, uma semente; A 205,8 e B 260,4 min, três sementes, que
reprovam o SC-007). "Quanto cômputo consome": execução (66 a 68 min nas três
runs de 7B; 112,4 min no 1,5B, que falha mais e gasta as cinco iterações com
mais frequência). "A execução E foi real, não replay": execução (67,2 min contra
2,4 min do replay). As medidas não são comparáveis entre as linhas — diferem em
número de execuções, protocolo de reset e versão de servidor — e não constituem
série temporal de desempenho. O executor do sandbox foi trocado depois de todas
elas (workers como processos novos, §5.7); o efeito dessa troca no tempo não foi
medido.

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
reparo: a versão esperada passou a ser fixada no perfil do gerador
(`generator_profiles.yaml`), o runner aborta na inicialização em caso de divergência nomeando as duas versões,
servidor inacessível conta como divergência, e a execução com
`--allow-ollama-version-mismatch` é estampada no registro, de modo que rodada
sob exceção não possa ser confundida com rodada limpa.

A re-execução completa das 120 tarefas em 0.34.4 (run D), que limitaria o efeito,
foi **aposentada**: a comparação C × E (§5.3) a substitui. Ela testa a
sensibilidade à versão numa distância maior (0.35.1 para 0.40.8, contra 0.34.4
para 0.35.1) e dispensa baixar o Ollama. A previsão registrada para o run D (5 a
9 sucessos de 120) nunca foi testada. O que C × E mostra: o agregado quase não
se move, as tarefas individuais sim; a atribuição do delta de 1 para 7 ao loop
continua apoiada apenas nas duas afirmações intra-rodada de §5.2. A deriva não
parou ali: em 2026-10-22 o servidor do host passou de 0.35.1 a 0.40.7 e a
0.40.8 em cerca de 37 minutos; o portão de versão recusou o lançamento
antes de produzir um número, e as
execuções E e F foram feitas sob a nova fixação, 0.40.8.

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

**Timeouts do sandbox: o defeito era real, e o que preservou as medições foi
sorte, não robustez.** Um defeito do executor — um *worker* criado por `fork`
depois que o orquestrador usou o pool Rust do Qiskit trava em
`SparsePauliOp.to_matrix()` (capítulo 6, §6.4) — podia transformar código
correto em `timeout after 60s`, rotulado `SyntaxError` e contado como falha do
gerador. `verify_references` roda em `main()` antes de o pool existir, de modo
que **todos** os *workers* de todas as execuções estavam expostos, e não só os
substituídos; nada no desenho os protegia. O que protegeu os números foi que
nenhum código gerado em B, C, E, F e G chamou o gatilho. Os registros foram
varridos em busca de `timeout after`, na lista de erros e no resultado estático:
**0 em B, C, E, F e G**; **1 registro em A e o mesmo em A2**
(`ising_field_coupling_5q`, semente 2, iteração 5 de 5). Esse caso também não
mudou nada, mas por outra sorte: o código era inválido de qualquer modo (num
*worker* limpo levanta `CircuitError`, 3 qubits do gate contra 5 do circuito,
rotulado também `SyntaxError`) e era a última iteração, de modo que `status`,
tipo de erro e contagem de falhas são os mesmos; só a mensagem difere. Um código
válido que chamasse `to_matrix()` teria dado *timeout*, sido contado como falha
do modelo, e deixado como único sinal a mensagem. A comparação A × A2 (0/360)
não é afetada: os dois registros são idênticos entre si. Os 479 códigos finais
de C, E, F e G foram reexecutados no executor corrigido (*workers* novos) e o
veredito estático (`parsed`, `executed`, `transpiled`, tipo de erro) coincide em
todos. Nenhum número deste capítulo é reapresentado, e nenhum foi medido
sabendo-se isto.

---

## Pendências deste capítulo

Não fazem parte do texto final; remover quando resolvidas.

0. ~~F-prime (1,5B com penalidade de repetição 1.1), a medir.~~ Medido: 0 em 120, `compila@1` 19, a fração
   de falhas presas não caiu; a narrativa do 1,5B fica (ver a seção F-prime acima e `distill-pilot-families.md`).

1. ~~Confirmar os números de regressão.~~ Resolvido: 40/74 → 29/88, apurado do
   *trace*.
2. ~~Diagnóstico das duas tarefas com orçamento suspeito.~~ Resolvido: nada a
   alterar; a suspeita era baseada em linha de base inválida.
3. ~~Preencher o resultado da re-execução em Ollama 0.34.4 em §5.7.~~ Aposentado:
   o run D foi substituído pela comparação C × E (§5.3).
4. ~~Reconciliar ou aposentar as figuras de 1,8% / 84% / 331-de-335.~~
   Resolvido: as três se re-derivam do run `ce9614fa…` (6/341, 287/341, 331 de
   335); o enunciado do 84% foi corrigido nos três documentos.
5. Decidir se `compila@1`, loop engajado e convergido entram na tabela de §5.5
   para R2–R4 ou ficam só em R0 e fronteira, conforme o que estiver apurado.
6. Recomputar `cx_ratio` com `basis_gates` declarada, ou removê-la do conjunto
   de métricas reportadas.
