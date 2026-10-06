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
corrente do braço local é 7/120.

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

`recall@8` = 0,9524, com a ressalva de que parte da queda aparente em corpus
maior era subestimação da medida.

### 5.4 Desempenho

Suíte completa a frio: 3h26m. *Este é o número citável de desempenho* — os
tempos da interface são réplica de cache.

### 5.5 O que não foi medido

**[PREENCHER se a rodada com modelo de fronteira acontecer]** — responde a
pergunta óbvia: o gargalo é a arquitetura ou o gerador?

---

## 6. Achados de engenharia — ESSENCIAL, e é o capítulo diferencial

*Vinte e dois achados documentados com evidência medida. Poucos trabalhos deste
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

### 6.6 Diagnóstico e reparo

Um diagnóstico incorreto é pior que nenhum — ancora o modelo numa direção falsa.

---

## 7. Limitações e ameaças à validade — ESSENCIAL

*Uma seção honesta aqui vale mais que uma seção de resultados inflada.*

- Verificação sem referência cobre executabilidade e restrições declaradas; não
  cobre corretude na ausência de asserção
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

- Execução em hardware real *(ou seção de resultados, se a US5 entrar)*
- Reparo incremental — a hipótese H-inc, registrada com condições de falsificação
- Verificar circuito escrito pelo próprio usuário (`/api/check` já é 80% disso)
- Oráculo de fidelidade de canal para teleportação
- Ajuste fino destilando o loop nos pesos

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
