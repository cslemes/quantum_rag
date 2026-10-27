# [TÍTULO] — Relatório

**Autor**: Cristiano da Silva Lemes
**Programa**: Especialização em Inteligência Artificial — PUC-Rio
**Orientador**: [PREENCHER]
**Data**: [PREENCHER]

> **[DECISÃO PENDENTE — título]** Três nomes em circulação: `qcircuit-agent`,
> Quantum-RAG, LLM Quantum Copilot. "Quantum RAG" colide com termo estabelecido
> na literatura (recuperação acelerada por algoritmos quânticos), o que é risco
> de confusão. Sugestão: nome do repositório e título formal não precisam
> coincidir — o título deveria nomear a verificação, que é a contribuição.
>
> **[DECISÃO PENDENTE — formato]** Extensão, estrutura e template dependem do
> que o orientador espera. Este esqueleto escala: as seções marcadas ESSENCIAL
> formam um relatório curto; as marcadas EXPANSÍVEL crescem se houver espaço.

---

## Resumo

*[PREENCHER por último]* Um parágrafo: o problema, o que foi construído, o que
foi medido, e a contribuição. Deve funcionar lido isoladamente.

---

## 1. Introdução — ESSENCIAL

### 1.1 O problema

*A abertura precisa estabelecer que o problema é real e não hipotético.*

- LLMs geram código Qiskit que não executa — alucinam APIs removidas
- Quem pede o circuito frequentemente não sabe verificar se está correto
- Código plausível e errado é o pior resultado possível

**Evidência disponível**: três de quatro falhas observadas eram símbolos
inexistentes (`qiskit.extensions`, `cx_decompose`, `u3`).
[FONTE: `report-notes.md`, exemplo trabalhado do `u3` — usar como ilustração com
mecanismo rastreado, **não** como efeito medido; n=1 sob não-determinismo]

### 1.2 Por que este domínio é tratável

*Esta subseção sustenta o trabalho inteiro. Não a encurte.*

O *oracle problem* da engenharia de software: obter critério de correção
automático é difícil, e em geral exige que alguém escreva asserções à mão.
Circuitos quânticos resolvem isso parcialmente de graça — equivalência unitária,
comparação de estado, composição com a inversa.

[FONTE: `glossary.md` §1, enquadramento do *oracle problem*]

### 1.3 Objetivo e escopo

O que o produto faz, o que não faz. Referenciar explicitamente o *Out of Scope*
do `spec.md` v2.

### 1.4 Mudança de escopo — ESSENCIAL

*Dizer isto cedo e sem rodeios é mais forte que omitir.*

O projeto foi inicialmente especificado como experimento controlado — cinco
condições comparativas, ablação, teste de hipóteses. Ao confirmar que o
entregável é produto, o escopo foi reduzido: saiu o aparato de inferência
estatística, ficou o sistema mais a suíte de regressão. As 120 tarefas mudaram
de função — eram instrumento de medida, viraram garantia contra degradação.

[FONTE: `MIGRATION.md`]

### 1.5 Contribuições

1. O sistema
2. A suíte de 120 tarefas com referências verificadas independentemente
3. Os achados de engenharia (capítulo 6)

### 1.6 Estrutura do documento

---

## 2. Contexto — EXPANSÍVEL

*Se o orientador quiser algo publicável, esta seção cresce. Para um relatório de
produto, pode ser curta.*

- Geração de código por LLM e seus modos de falha
- *Test oracles* e o *oracle problem*
- Deriva de API como causa de falha em código gerado
- Ausência de benchmark público para geração de circuitos quânticos

**[PREENCHER]** Levantamento bibliográfico — é o que menos existe pronto hoje.

---

## 3. O sistema — ESSENCIAL

### 3.1 Visão geral

Diagrama do grafo. [FONTE: `plan.md`, seção do grafo]

### 3.2 A cascata de validação

Quatro camadas ordenadas: executabilidade → transpilação → corretude funcional →
recursos. Cada uma com veredito próprio.

O princípio que governa: nenhum veredito vem de julgamento de LLM.
[FONTE: `contracts/validators.md`, constituição v2 Princípio I]

### 3.3 Loop de reparo com diagnóstico estruturado

Classificação da causa → ação corretiva correspondente. A taxonomia fechada.
[FONTE: `data-model.md`, tabela de `error_type`]

**Fato de projeto a registrar aqui (e só aqui; o capítulo 6, §6.6, o cita):** o
laço tem um teto de iterações (`MAX_ITER` = 5) e **nenhuma detecção de
convergência**. Não para antes do teto e não percebe que se repete, de modo que
**cada falha custa cinco gerações**. A única parada antecipada no código é
estreita: duas ocorrências consecutivas da mesma asserção "não avaliável"
(`critic.py::_is_repeated_not_evaluable`, US3), e a suíte não usa asserções. Nem a
falha idêntica repetida nem o código idêntico são detectados. Medido: toda
execução que gerou código e não terminou em sucesso chegou à iteração 5, **113 de
113 em C** (7B, Ollama 0.35.1), **115 de 115 em E** e **em G** (7B, 0.40.8) e
**118 de 118 em F** (1,5B, 0.40.8).

### 3.4 Recuperação versionada

Híbrido esparso + denso, filtro por versão, material obsoleto rotulado em vez de
omitido. [FONTE: `contracts/retrieval.md`, `research.md` D5–D7]

### 3.5 Linguagem de asserção

*O componente que torna o produto um produto.* Sem ela, corretude funcional só é
verificável por quem já tem a resposta.

Gramática, convenções, o caso não avaliável.
[FONTE: `research.md` D19]

### 3.6 Relatório de garantia

O que foi verificado, como, e o que não foi. O caso sem asserção.
[FONTE: `spec.md` v2 FR-015 a FR-017]

### 3.7 Interface

Diagrama, distribuição, streaming das tentativas, a afordância de rascunho e o
`circular=True`.

### 3.8 Requisitos extraídos por LLM: vetam, nunca estabelecem

*Decisão de desenho.* O planner lê a descrição e extrai requisitos verificáveis
(`n_qubits`, `gate_set`). A comparação com o circuito gerado é determinística
(um inteiro, uma diferença de conjuntos); a **premissa** não é, é a leitura de um
modelo de linguagem. O peso do resultado depende da direção, e por isso o
desenho é assimétrico:

- requisito que **passa** diz apenas "o circuito concorda com o que o planner
  leu"; não estabelece `functional_correctness_verified`;
- requisito que **reprova** é uma discordância diretamente checável entre o
  circuito e a descrição; **veta** a alegação de corretude no caminho de produto;
- valor que não dá para avaliar (`"three"`, `"hadamard"` como nome de porta) é
  "não checável": não veta nada e nunca é reportado como reprovação do circuito;
- no caminho da suíte, um requisito reprovado **não** veta `semantic.passed`: um
  oráculo verificado é verdade-terreno (Princípio IV) e, quando os dois
  discordam, quem errou foi o planner.

Uma violação de requisito é reportada e bloqueia `success`, mas não entra na
taxonomia fechada de `error_type` e não dispara `retry_generation`: fica fora do
laço de reparo. A decisão é justificada por argumento, não por medida de que
produza vereditos melhores; é o desenho, e é registrada como tal. Um defeito que
ela exigiu corrigir está em §6.3: a coerção silenciosa de tipos antes da
checagem. [FONTE: `report-notes.md`, F9]

---

## 4. A suíte de referência — ESSENCIAL

### 4.1 Construção

120 tarefas: 60 canônicas + 60 perturbadas, em quatro níveis.
[FONTE: `research.md` D3c–D3j]

### 4.2 Verificação independente das referências

O processo, e por que é bloqueante.

**Resultado**: cinco erros reais de método pegos — direção de laço na QFT,
classificação do Deutsch-Jozsa, encadeamento de ancilla no somador, convenção de
sinal do QUBO, controle fixo no Deutsch-Jozsa perturbado.

*Isto sustenta o capítulo 6 e deve ser apresentado com os cinco casos.*

### 4.3 Variantes perturbadas

As cinco famílias, e as 14 exclusões por vacuidade.

---

## 5. Resultados medidos — ESSENCIAL

*Apresentar os números com o contexto que os torna interpretáveis. O baseline
baixo é diagnóstico, não resultado.*

### 5.1 Baseline

Baseline de 19/09 (run `ce9614fa…`, 360 execuções, **341 válidas** após excluir
19 erros de harness): **6/341 = 1,8%** de sucesso; **287/341 = 84%** terminam em
falha estática (não é o mesmo que "param antes da verificação funcional": 63
das 287 chegaram a ela); **331 de 335 falhas** esgotam as cinco tentativas
(335 = 341 − 6; as outras 4 foram recusadas na entrada). Histórico: o número
corrente do braço local é 7/120 no Ollama 0.35.1 (5/120 no 0.40.8, mesmo modelo; uma cifra de sucesso sempre leva a build do servidor).

**Precisão**: toda taxa com intervalo POR TAREFA (119 tarefas), não por run —
as ~3 runs por tarefa não são sorteios independentes (F29). Ex.: sucesso 1,8%,
IC 95% [0,3%, 3,8%] por tarefa, contra [0,8%, 3,8%] tratando 341 como
independentes.

**A leitura**: o gargalo não é o modelo errar a física — é que ele raramente
chega lá. E o loop, quando engaja, praticamente nunca converge.

### 5.2 Determinismo

**0/360 replay-idênticos sob uma sequência de chamadas fixa**, em quatro
medidas, com o protocolo que o viabiliza. É um resultado forte — poucos
sistemas com LLM no laço podem afirmá-lo — e é exatamente isso: a mesma
execução, repetida com a mesma ordem de tarefas, se reproduz byte a byte.

**Não** foi mostrado, e no protocolo original é falso, que o resultado de uma
(tarefa, seed) independe das outras: o cache de prompt/KV do servidor de
inferência carrega estado de uma tarefa para a seguinte e muda a saída a
`temperature=0` (F28). Apresentar aqui o protocolo corrigido
(`reset_per_run`), a medição de independência que o valida, e o custo
aceito por ele (segunda emenda a SC-007). Redação anterior desta seção
("0/360 em quatro medidas") implicava uma independência nunca medida.

### 5.3 Recuperação

`recall@8` = 0,9365 (59/63) no corpus 1.2 de 875 chunks usado nas execuções B a G
(0,9524 era do corpus anterior, 2.x de 1.020 chunks, já substituído), com a
ressalva de que parte da queda aparente em corpus maior era subestimação da medida.

### 5.4 Desempenho

Suíte completa a frio: 3h26m. *Este é o número citável de desempenho* — os
tempos da interface são réplica de cache.

### 5.5 O que não foi medido

**[PREENCHER se a rodada com modelo de fronteira acontecer]** — responde a
pergunta óbvia: o gargalo é a arquitetura ou o gerador?

---

## 6. Achados de engenharia — ESSENCIAL, e é o capítulo diferencial

*Trinta e dois achados documentados (F1–F32 em `report-notes.md`), agrupados em seis temas; cada um com o grau de evidência marcado (medido, mecanismo traçado num caso, ou fino). Poucos trabalhos deste
porte têm isso. Cada subseção: a afirmação, as instâncias, a evidência, a
generalização.*

### 6.1 Critérios de correção que falham em silêncio

- Oráculos mais estreitos que seus enunciados (3 instâncias independentes)
- Perturbações vazias
- **Validação circular** — um sistema que sugere o próprio critério de aceitação
  produz verificação que não pode falhar, e a ajuda é o mecanismo da falha

*A generalização da validação circular alcança muito além deste domínio:
snapshot testing, e testes escritos por LLM para código escrito por LLM.*

### 6.2 Verificadores cegos

- Cegueira de fase em verificação por medição
- O que a construção independente pegou

### 6.3 Vereditos que não correspondem ao verificado

- Honestidade em prosa não sobrevive a um campo estruturado que diz outra coisa
- Divergência nas duas direções — superestimar e subestimar
- Campo registrado sem consumidor que falhe é decoração

### 6.4 Regras que não se propagam

Uma regra correta escrita num lugar não alcança o código ao lado. Quatro
instâncias, todas de **estado ambiente herdado**.

### 6.5 Medir o que se pensa estar medindo

- Um controle que dispara vale mais que uma hipótese que confirma — e uma
  refutação é tão compatível com um instrumento quebrado quanto uma confirmação
  (F16 + F29: o par)
- Reconhecer o padrão esperado não é evidência (cometido duas vezes)
- N fontes de não-determinismo em série
- Teste fora do regime de produção passa, por melhor que seja — e o regime
  tem de corresponder à pergunta, não só ao ambiente: o piso zero foi medido
  em produção, mas por replay, e a pergunta era independência (F19, F28)
- **Um número que parece medição e é replay, sem nada na saída que o mostre.** A
  primeira execução E (7B no Ollama 0.40.8) deu 7/120, `compila@1` 20/120, em 9
  minutos; era o cache de respostas da execução C, chaveado pelo NOME do modelo,
  e a build do servidor sob esse nome tinha mudado. Foi pega por acaso (o tempo:
  9 min contra 72), não por qualquer saída do instrumento. O gate de versão
  checou o servidor e passou, porque ele não vê o cache. Correção: o cache passa
  a ser chaveado por tudo de que a resposta depende (digest resolvido do modelo,
  build do servidor, parâmetros de amostragem, `max_tokens`), de modo que uma
  mudança é um miss frio e não um acerto errado; e toda execução termina
  declarando quantas chamadas vieram do cache (COLD / PARTLY WARM / REPLAY), no
  registro e no stderr. Segunda instância do mesmo mecanismo (F18 foi a
  primeira): o perigo não era o cache, era ele ser invisível

### 6.6 Diagnóstico e reparo

Um diagnóstico incorreto é pior que nenhum — ancora o modelo numa direção falsa.

---

## 7. Limitações e ameaças à validade — ESSENCIAL

*Uma seção honesta aqui vale mais que uma seção de resultados inflada.*

- Verificação sem referência cobre executabilidade e restrições declaradas; não
  cobre corretude na ausência de asserção
- **A afirmação final é limitada ao nível do enunciado e da resposta.** A fatia de
  famílias retidas (`heldout-v1`) foi retirada (decisão de 2026-10-27, com a razão no
  capítulo 6, §6.5): não há resultado de generalização fora da família. O que se afirma é
  que dados sintéticos verificados por oráculo, da mesma distribuição, melhoram um modelo
  pequeno em enunciados que ele nunca viu (nenhum enunciado e nenhuma resposta compartilhados
  com as 120 tarefas, por quase-duplicata lexical e equivalência estrita de circuito). O
  resultado é limitado a "treinado para a distribuição deste benchmark", não a melhoria geral
  de Qiskit.
- **Limite de medição (mais forte que o de capacidade acima):** a suíte sempre tem
  referência. As 120 tarefas são verificadas contra um oráculo construído
  independentemente e nenhuma declara asserções (`assertions: []` nos relatórios de
  garantia das runs C, E, F e G). O caminho **distintivo do produto** — um usuário
  sem referência, declarando asserções — é, portanto, a coisa **menos medida** do
  trabalho: a gramática de asserção, a parada por asserção não avaliável repetida, o
  relatório sem referência e o mecanismo de rascunho foram validados por testes
  (inclusive ponta a ponta) e por demonstrações, nunca por uma execução de suíte. A
  suíte exercita um subconjunto dos caminhos do produto, e o que só dispara nos
  caminhos não exercitados não está medido, por mais bem que funcione.
- A gramática de asserção é fraca onde o conteúdo da tarefa é derivação numérica,
  e cega para transformação geral sem `INPUT`
- Caminho de verificação por composição é probabilístico acima de 12 qubits
- QAOA e VQE com parâmetros fixos medem construção de ansatz, não otimização
- Consultas sintéticas de recuperação foram escritas por quem construiu o corpus
- O ambiente canônico declarado só passou a corresponder à realidade após emenda
- Qualquer demonstração apoiada num check `circular=True` não sustenta nada sobre
  corretude
- O braço de API é um retrato, não uma medição reprodutível: sem análogo de
  reset, sem controle do estado do servidor, e o modelo pode mudar sob o mesmo
  identificador; o braço local é o reprodutível
- Replay-identidade não é independência: toda execução anterior a F28 rodou com
  estado de servidor atravessando tarefas, então comparações por tarefa entre
  execuções com prompts diferentes (incluindo T090c) e a diferença entre seeds
  dentro de uma execução estão confundidas

[FONTE: `report-notes.md`, Threats to Validity — já escrito]

---

## 8. Conclusão e trabalhos futuros — ESSENCIAL

### 8.1 O que foi entregue

### 8.2 Trabalhos futuros

- **Parar quando a falha se repete (proposta; muda o instrumento; não construída).**
  *O resultado que importa vem antes da proposta:* a heurística óbvia, parar na
  **segunda** falha idêntica consecutiva, está **refutada por medição**. Nos
  registros vigentes (falha idêntica = mesmo estágio, tipo e mensagem em tentativas
  consecutivas) ela teria perdido **3 dos 7 sucessos da run C**: uma repetição
  única não é evidência de estar preso, e 43% dos sucessos dessa run vieram
  depois de exatamente uma. As três tarefas resgatadas são GHZ (`ghz_5q`,
  `ghz_linear5_endpoints`, `ghz_linear5_scattered_even`); com n = 3 pode ser
  coincidência, mas o limiar interage com a família (em E os dois sucessos GHZ não
  tiveram repetição), e a proposta tem de dizê-lo. O limiar seguro nas três runs
  medidas é a **terceira** falha idêntica: nenhum sucesso perdido em C (7), E/G (5)
  ou F (1); o maior bloco de falhas idênticas antes de um sucesso foi 2. A
  segurança do 3 é empírica, nessas runs, não geral.
  *A proposta:* o capítulo 3 (§3.3) registra que o laço não detecta convergência e
  o §6.6 e o cap. 5 (§5.5) que o diagnóstico ancorado (T090d) *aumentou* as falhas
  idênticas consecutivas, de 5 para 11 (R3 → R4, 30B no pod, Ollama 0.34.4,
  n = 16). Nenhum dos dois achados diz isto sozinho: o diagnóstico mais firme
  produz repetição, e o laço não tem mecanismo para percebê-la. A regra existe, para
  um único tipo de erro, em `critic.py::_is_repeated_not_evaluable` (§6.4), e
  generalizá-la para a **terceira** falha idêntica economiza, nas runs medidas, 8,8%
  das tentativas em C, 8,0% em E/G e 30,5% em F (a 2ª economizaria 20,4%, 19,7% e
  51,0%, ao custo acima). "Três de cinco tentativas" só vale para as execuções
  travadas desde o início (falhas idênticas nas cinco tentativas: 14 em C, 17 em E,
  77 em F); no conjunto das falhas do 7B a economia é de 8% a 20%. **Com o hash do
  código na traça (a partir de F-prime), a regra pode ser dita sobre o código e não sobre o erro:** parar quando o gerador
  devolve o mesmo código (mesmo hash) três vezes seguidas. Em F-prime, depois de três códigos iguais o quarto é igual em
  167 de 172 casos (97,1%), e parar aí encerraria 109 execuções e pouparia 175 das 595 tentativas (29%); F-prime não tem
  sucessos que a regra pudesse custar. **Evidência convergente:** duas medidas diferentes apontam no mesmo sentido, parar na terceira falha idêntica de *erro*
  não perdeu nenhum sucesso em C, E e F, e parar no terceiro *código* idêntico não perderia nenhum em F-prime. A regra
  não é exata (5 dos 172 casos mudam), de modo que não é uma prova e a perda de um resgate raro continua possível e não
  medida. **Não será construída para a execução ajustada:** a linha de base F-prime foi medida sem a regra, então
  aplicá-la só ao modelo ajustado seria um confundimento, e aplicá-la aos dois exigiria refazer F-prime; o ganho é de
  tempo de relógio, não de informação. **Muda o instrumento** (execuções mais curtas, e a invariância de C a G deixa
  de valer), por isso não foi construída.
- Execução em hardware real *(ou seção de resultados, se a US5 entrar)*
- Reparo incremental — a hipótese H-inc, registrada com condições de falsificação
- Verificar circuito escrito pelo próprio usuário (`/api/check` já é 80% disso)
- Oráculo de fidelidade de canal para teleportação
- Ajuste fino destilando o loop nos pesos — **precondição: o 1.5B base é refeito DUAS vezes, na MESMA build do servidor, imediatamente antes da execução destilada (a segunda dá a identidade de repetição)** (ver report-notes.md, "Destilação: precondição de build")

---

## Apêndices

**A. Reprodutibilidade** — ambiente canônico, versões fixadas, como reproduzir
uma rodada. [FONTE: `report-notes.md`, apêndice já escrito]

**B. A suíte de referência** — tabela das 120 tarefas.

**C. Glossário** — [FONTE: `glossary.md`, já escrito]

---

## Notas de preenchimento

**O que já existe escrito**: capítulos 3, 4, 5, 6, 7 e os apêndices estão
essencialmente prontos nos artefatos. É organização e redação de ligação, não
redação nova.

**O que precisa ser escrito do zero**: capítulo 2 (contexto e bibliografia) e as
seções de abertura e fechamento.

**O que depende de decisão**: título, formato, se a US5 entra, se a rodada com
modelo de fronteira acontece.

**Ordem sugerida de preenchimento**: 6 → 5 → 4 → 3 → 7 → 1 → 8 → 2 → resumo.
Comece pelo capítulo que já está pronto e é o diferencial; deixe a bibliografia
por último porque é a que mais depende de tempo e menos de você.

**Regra de vocabulário**: `glossary.md` §6 lista os termos a evitar. O mais
importante: nunca escrever que o modelo "validou" algo — validação é sempre
determinística, e a frase contradiz a tese do trabalho.
