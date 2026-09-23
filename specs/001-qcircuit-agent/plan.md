# Implementation Plan: LLM Quantum Copilot

**Branch**: `001-qcircuit-agent` | **Data**: 2026-08-11 | **Reescrito**: 2026-09-15 (v2 — produto)
**Spec**: [spec.md](./spec.md) | **Ver também**: [MIGRATION.md](./MIGRATION.md)

> **Mudança de escopo (v2)**. Este plano substitui a versão v1 (instrumento de
> pesquisa: experimento controlado, matriz C1–C5, ablação). O sistema
> construído em v1 permanece integralmente; o aparato de medição sai. Ver
> `MIGRATION.md` para o racional completo e `research.md` (D8, D9, D12,
> partes de D3e/D3j marcadas **SUPERADA**) para o que isso invalida.

## Summary

Agente em grafo de estados que gera circuitos quânticos a partir de linguagem
natural, valida cada artefato por uma cascata determinística de camadas
(execução → transpilação → asserções declaradas pelo usuário → equivalência
com referência quando uma existe → recursos) e realimenta o gerador com o
diagnóstico estruturado da falha. Recuperação híbrida sobre documentação
versionada elimina a principal causa de erro do domínio — uso de API
obsoleta. Toda saída vem acompanhada de um **relatório de garantia** que
declara exatamente o que foi verificado e como, e o que permanece não
verificado — nunca apresentando "executa e respeita restrições" como
equivalente a "está correto". Uma suíte de 120 tarefas com referências
verificadas independentemente (60 canônicas + 60 perturbadas, construídas em
v1 e preservadas integralmente) funciona como regressão contínua de
qualidade — não mais como instrumento de um experimento controlado.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: Qiskit 1.2.4 (pinado), qiskit-aer 0.15.1 (**CPU**; variante `-gpu` opcional, ver D1), LangGraph, PennyLane (corpus secundário), Pydantic v2, qdrant-client, fastembed (BM25 esparso + cache persistente, ver D18)
**Storage**: Qdrant 1.12 (vetores densos + esparsos na mesma coleção, com payload de versão); JSONL append-only para resultados de regressão; QPY para serialização de circuitos
**Testing**: pytest; `bench/validate_oracles.py` como portão bloqueante em CI **e** como precondição em tempo de execução do runner da suíte (Princípio IV — ver §Constitution Check)
**Target Platform**: Linux (container Docker, ver D15) — Ryzen 7 5700X, 32 GB RAM, RTX 3070 8 GB; IBM Quantum open plan (US5)
**Project Type**: Single project — biblioteca Python + CLI mínima (US6) + suíte de regressão
**Performance Goals**: latência p95 < 180 s por execução; **suíte de regressão completa (120 tarefas) em menos de 3 h de wall-clock (SC-007)** — substitui a meta de 72h/5.400 execuções da matriz experimental v1, que não existe mais
**Constraints**: statevector em CPU viável até ~25 qubits; **`Operator.equiv()` tem teto real em ~12–13 qubits** (matriz densa 4ⁿ — ver D3b), por isso oráculos unitários acima disso usam verificação por composição; nenhum item da suíte excede 20 qubits; o gargalo por execução é overhead de processo, não a simulação (ver D1b); gerador local medido em 492 tok/s de prefill e 74,7 de geração, 100% em GPU (D10); `num_ctx` deve ser fixado explicitamente, o default de 4096 do Ollama trunca em silêncio (D10b); cache de modelo fastembed persistente via volume nomeado, sem dependência de rede a cada execução (D18)
**Scale/Scope**: suíte de regressão de 120 tarefas (60 canônicas + 60 perturbadas) com referências verificadas independentemente; corpus de ~15k unidades de documentação; geradores suportados são **configuráveis por execução** (local via Ollama, API via provedor configurável) — não mais um conjunto fixo de braços experimentais a comparar

## Constitution Check

*GATE: reavaliado contra a Constituição v2.0.0 (4 princípios — ver
`.specify/memory/constitution.md`). Reverificar após qualquer mudança
estrutural nas Phases 0/1 abaixo.*

| Princípio | Status | Evidência no desenho |
|---|---|---|
| I. Verificação determinística | ✅ PASS | `validators/` (incluindo o novo `assertions.py`, §Verificação sem referência) não contém chamada a LLM — `test_architecture.py` cobre o módulo novo. O `critic` roteia sobre erro já classificado por código determinístico; nunca emite veredito de corretude. Asserções são PARSEADAS por gramática determinística, nunca "interpretadas" por um modelo — a única função possível de um LLM no caminho de asserções é opcionalmente PROPOR uma asserção como hipótese a partir de linguagem natural (papel de "gerador de hipótese", explicitamente permitido pelo Princípio I), nunca decidir se ela vale. |
| II. Honestidade sobre garantia | ✅ PASS | `GuaranteeReport.functional_correctness_verified` (§Relatório de garantia) é um campo COMPUTADO — nunca aceito como argumento do construtor (`model_config = ConfigDict(extra="forbid")` torna a construção de um relatório mentiroso um erro de validação, não um bug possível de escrever por acidente). Um teste dedicado e obrigatório (`test_report.py`, tarefa T095) falha a build se a invariante SC-004 for violada. |
| III. Regressão verificável | ✅ PASS | `bench/runner.py` registra `run_id`, seeds, `lib_versions` em todo `RunRecord`; `results/` permanece append-only; mudança em prompt/corpus/modelo/pipeline é avaliada contra a suíte antes de adotada (FR-025–FR-027). |
| IV. Referências são código testado | ✅ PASS | `bench/validate_oracles.py` já bloqueia 120/120 referências (construção independente + checagem de propriedades, D3–D3k). **Novo em v2**: o próprio `bench/runner.py` recusa executar qualquer tarefa da suíte cuja referência não tenha passado nessa validação (T099) — o bloqueio deixa de ser só um portão de CI (T051, ainda pendente) e passa a ser também uma precondição em tempo de execução, testada (T100). |

**Resultado**: PASS — sem violações a registrar.

## Project Structure

### Documentation

```
specs/001-qcircuit-agent/
├── spec.md                # v2 — o quê e por quê (produto com relatório)
├── plan.md                # este arquivo
├── MIGRATION.md            # racional da mudança v1 → v2
├── research.md             # Phase 0 — decisões técnicas (D1–D18; D8/D9/D12/
│                            #   partes de D3e/D3j marcadas SUPERADA, não apagadas)
├── report-notes.md         # achados, números, limitações — material do
│                            #   relatório final (append-only, ver MIGRATION §6)
├── data-model.md           # Phase 1 — entidades e estado (§Assertion,
│                            #   §GuaranteeReport novos em v2 — T081)
├── quickstart.md           # Phase 1 — validação em 10 minutos
├── contracts/               # Phase 1 — contratos dos nós e validadores
├── checklists/
│   └── requirements.md
└── tasks.md                # Phase 2

estado-e-aprendizados.md    # snapshot de estado do projeto (raiz do repo)
```

### Source Code

```
src/qcagent/
├── state.py                 # AgentState + entidades Pydantic
│                             #   + Assertion (união discriminada), AssertionOutcome — US3
├── graph.py                 # montagem do StateGraph + make_assertion_check_node — US3
├── report.py                 # NOVO — GuaranteeReport e render_guarantee_report — US4
├── config.py                 # pydantic-settings
├── nodes/
│   ├── planner.py           # descrição → requisitos verificáveis  [LLM]
│   ├── retriever.py         # consulta híbrida versionada
│   ├── generator.py         # requisitos + trechos → código        [LLM]
│   ├── critic.py            # erro classificado → ação corretiva   [LLM]
│   └── routing.py           # arestas condicionais (+ route_after_assertion_check — US3)
├── validators/               # 100% determinístico — sem LLM
│   ├── sandbox.py           # subprocesso isolado + denylist + timeout
│   ├── static.py            # camada 1–2: execução e transpilação
│   ├── assertions.py        # NOVO — camada 3: gramática + avaliação de asserções (US3)
│   ├── semantic.py          # camada 4 (com referência): unitária / distribuição / energia
│   └── resource.py          # camada 5: profundidade, CX, largura
├── retrieval/
│   ├── ingest.py             # crawler docs + arXiv
│   ├── chunking.py           # code-aware: símbolo íntegro
│   ├── index.py              # coleção Qdrant: denso + esparso
│   └── hybrid.py             # Query API com fusão RRF nativa
├── llm/
│   ├── base.py                # interface comum
│   ├── anthropic_client.py
│   └── ollama_client.py
├── interface/
│   └── cli.py                 # NOVO — US6, interface mínima (P2)
└── prompts/

bench/
├── schema.py                 # TaskSpec
├── tasks/{t1,t2,t3,t4}/       # 120 tarefas (60 canônicas + 60 perturbadas) — completo
├── oracles/
├── validate_oracles.py        # portão bloqueante (Princípio IV) — 120/120 verde
└── runner.py                  # runner da SUÍTE DE REGRESSÃO — bloqueia sobre
                                #   referência não verificada (T099); NÃO é mais
                                #   um driver de matriz experimental

analysis/{metrics.py,notebooks/}   # ablation.py REMOVIDO — não há mais braços a comparar
results/{run_id}/
tests/{unit,integration,contract}/
```

**Structure Decision**: single project. `validators/` (agora incluindo
`assertions.py`) é mantido fisicamente separado de `nodes/` para tornar o
Princípio I verificável por inspeção de imports — `tests/contract/
test_architecture.py` falha se `validators/` importar de `llm/`. `report.py`
fica no nível de `state.py`/`graph.py` (não dentro de `nodes/`) porque
renderiza para o USUÁRIO final, não para o modelo — distinção já estabelecida
em v1 para `render_structural_diff` (D14, research.md), aqui aplicada ao
lado inverso da mesma linha.

## Phase 0 — Research

**Status**: completa (v1) — ver `research.md`. As seis incógnitas originais
(D4 embedding, D8 teto de iterações, D9 idioma, D10 gerador Fronteira B, D6
chunking, D12 estratégia de perturbação) foram todas resolvidas ou
substituídas por decisão de produto: D8/D9/D12 estão marcadas **SUPERADA**
em `research.md` (a decisão específica não se aplica mais — ver as notas
inline em cada uma), mas o raciocínio original permanece registrado, não
apagado. Nenhuma incógnita nova de Phase 0 foi aberta pela migração v1→v2 em
si — as incógnitas novas da v2 (como fica a linguagem de asserção, como fica
o relatório de garantia) são de **desenho**, não de pesquisa externa, e
estão resolvidas abaixo em Phase 1.

## Phase 1 — Design

**Status**: `data-model.md` e `contracts/` datam de v1 e permanecem corretos
para US1/US2 (já implementadas); precisam de uma extensão pontual para US3/
US4 (T081, abaixo) — não de reescrita.

### Grafo (v2 — cinco camadas, não mais quatro)

```
[spec] → planner → retriever → generator → static_check
             │          ▲                         │
             │          │                         ▼
             │          │                 assertion_check
             │          │                         │
             │          │           (violação? → critic; senão:)
             │          │           (oracle_ref presente?)
             │          │                /                \
             │          │              sim                 não
             │          │               │                   │
             │          │               ▼                   ▼
             │          │        semantic_check      resource_check*
             │          │               │                   │
             │       critic ◀───────────┴───────────────────┘
             │          │
             └──────────┘
      (retry_retrieval | retry_generation |     [ done ] → finalize
       optimize | abort)                          → GuaranteeReport (US4)
             │
             ▼ (entidade faltante | restrição contraditória |
                n_qubits > teto | asserção mal formada)
      [ rejected_input ]
```

\* `resource_check` só roda se `coupling_map` foi declarado — comportamento
já existente em v1, inalterado.

A diferença estrutural central em relação a v1: **`semantic_check` (a
comparação com referência) deixa de ser obrigatória**. Ela só roda quando
`oracle_ref` está presente no estado — o caminho da suíte de regressão (US7,
que executa `TaskSpec`s com oráculo). O caminho de produto geral (um usuário
real, sem `TaskSpec`, US3/US4) não tem referência nenhuma; `assertion_check`
é o que substitui a verificação de corretude nesse caminho. Isso é o desenho
inteiro de v2 em uma frase: **v1 verificava contra referência; v2 verifica
contra o que o usuário consegue declarar, e é honesto quando ele não declara
nada.**

### Contratos dos nós

| Nó | Entrada | Saída | LLM |
|---|---|---|---|
| `planner` | `spec`, `assertions` (texto bruto) | `requirements` \| `status="rejected_input"` | sim |
| `retriever` | `spec`, `requirements`, `retrieval_hint` | `chunks` | não |
| `generator` | `requirements`, `chunks`, últimos 2 erros | `code` | sim |
| `static_check` | `code` | `StaticResult` | não |
| `assertion_check` **novo, implementado (T087/T091)** | `code`, `assertions` (parseadas), `requirements` | `list[AssertionOutcome]`, `list[RequirementOutcome]` | não |
| `semantic_check` (condicional — só se `oracle_ref`) | `code`, `oracle` | `SemanticResult` | não |
| `resource_check` (condicional — só se `oracle_ref`, não `coupling_map` — ver nota abaixo) | `code`, `coupling_map` | `ResourceResult` | não |
| `critic` | estado | `CriticDecision` | sim |
| `finalize` | estado terminal | `GuaranteeReport` **novo, implementado (T096)** | não |

**Correção ao rascunho original desta tabela**: `resource_check` sempre exigiu
`oracle_ref` (carrega o circuito de referência via `oracle_loader`,
`graph.py`) — nunca rodou apenas por `coupling_map` estar presente, mesmo
antes de US3. A condição "só se `coupling_map`" nunca esteve correta; T088
(`route_after_assertion_check`) foi escrito contra o comportamento real, não
contra este rascunho — ver §Verificação sem referência e
`nodes/routing.py::route_after_assertion_check`'s docstring para o porquê
disso importa especificamente no caminho sem `oracle_ref` (US3/US4): nesse
caminho, respeito à topologia é reportado a partir de `static.transpiled`
diretamente, não por rodar `resource_check`.

### Roteamento do critic (adiciona uma linha a v1)

| Sinal | Ação | Justificativa |
|---|---|---|
| Símbolo obsoleto, `ImportError`, `AttributeError` | `retry_retrieval` | falta de contexto de API → reconsultar com hint de versão |
| Falha de sintaxe, transpilação, qubit fora de faixa | `retry_generation` | erro local → regerar com traceback |
| Unitária diverge, fidelidade < tolerância | `retry_generation` | erro conceitual → regerar com diff |
| **Asserção violada** | `retry_generation` | erro conceitual nomeado — mesma classe de `WrongGateDecomposition`, mas contra o que o USUÁRIO declarou, não contra uma referência interna |
| **Asserção não avaliável (1ª ocorrência)** | `retry_generation` | regenerar pode produzir um circuito onde a amplitude referenciada deixa de ser ~0 |
| **Asserção não avaliável (2ª ocorrência CONSECUTIVA, mesma asserção)** | `abort` | regenerar não convergiu — encerra antes de `MAX_ITER`, `status="assertion_not_evaluable"` (não `"aborted"` genérico). Implementado em `critic.py::_is_repeated_not_evaluable`, checado antes do corte por `MAX_ITER` |
| Correto, `depth_ratio > max_depth_ratio` | `optimize` | regerar pedindo redução de CX |
| `iteration >= MAX_ITER` | `abort` | registrar falha; não mascarar com força bruta |

Falha transitória do provedor externo continua fora do `critic` — tratada em
`llm/base.py` (inalterado de v1).

### Verificação sem referência — linguagem de asserção (US3)

**Status**: entidades (T082), parser e avaliador (T083–T084b) implementados
e testados (`tests/unit/test_assertions.py`, 46 casos) — ver
`data-model.md` §Linguagem de asserção para a sintaxe textual completa e o
código exato das entidades, e research.md D19 para o racional completo e o
histórico de revisão. Esta seção registra só a DECISÃO e o PORQUÊ; a forma
foi fixada em duas rodadas de revisão do usuário antes da implementação, não
na primeira proposta.

**Decisão de desenho**: gramática mínima — quatro categorias de avaliação
(mais um açúcar sintático e um prefixo opcional, nenhum dos dois um `kind`
de runtime novo), não uma linguagem geral de propriedades. Parseada por um
parser determinístico próprio (não por um LLM) — é o que torna FR-013
("asserção mal formada recusada explicitamente") uma checagem de gramática,
não uma interpretação sujeita a ambiguidade de modelo.

**A gramática mudou em quatro pontos entre a primeira proposta e a versão
implementada**, cada um resolvendo um problema de usabilidade ou de
corretude encontrado em revisão — não polimento cosmético:

1. **Açúcar `QUBIT(q) == "|label>"`** para os seis estados cardeais de um
   único qubit (`0`, `1`, `+`, `-`, `i`, `-i`). `EIGENSTATE_OF("XIII", -1)`
   para expressar "a ancilla está em `|-⟩`" falhou o teste de usabilidade
   que a própria US3 exige (escrevível por quem sabe o que quer, não como
   implementar) — exige saber que `|-⟩` é o autoestado `-1` de `X`, e
   escrever `N-1` caracteres `I` corretamente posicionados. `QUBIT`
   desabaçucara para `EigenstateAssertion` em tempo de PARSE; `EIGENSTATE_OF`
   continua sendo o único caminho de avaliação real, para o caso geral
   multi-qubit.
2. **`MEASURES` com duas formas sintaticamente distintas** (nua = registro
   inteiro, convenção compartilhada; com lista = subconjunto, convenção
   posicional) em vez de uma forma só. A gramática original tinha
   `MEASURES([0,1,2]) == "101"` e `EIGENSTATE_OF("XII", -1)` lidas em
   direções OPOSTAS sem nenhum sinal visível disso — um erro silencioso de
   usuário exatamente da forma que este projeto já pagou o custo de três
   vezes antes (D3c/D3d/D3f). Unificar as duas convenções não era possível
   sem perder uma delas; a mitigação escolhida foi tornar as duas formas de
   `MEASURES` sintaticamente distintas, de modo que a colisão nunca ocorre
   dentro de uma asserção escrita.
3. **Resultado tri-estado** (`AssertionOutcome.passed: bool | None`) para
   `PHASE_DIFF` contra uma amplitude ~0 — e, desde o primeiro teste ponta a
   ponta (T092), também para qualquer asserção sobre estado contra um
   circuito com medição NÃO final ou reset (não há estado puro de saída;
   medições finais são removidas antes e não contam). São os dois únicos
   casos em que "não avaliável" é uma resposta genuína, não um erro de
   sintaxe. Isto
   refina o Cenário de Aceitação 4 (spec.md), que agrupa "mal formada" e
   "impossível de avaliar" sob a mesma recusa — a refusal continua exata
   para tudo malformado em tempo de parse (`rejected_input`); o tri-estado é
   um mecanismo adicional, só em tempo de avaliação, para uma asserção BEM
   formada que se revela mal posta para o circuito específico gerado. Ver
   `AgentState.status="assertion_not_evaluable"` (data-model.md) para o que
   acontece quando isso se repete em duas tentativas seguidas — pendente de
   fiação no `critic` (T086).
4. **Prefixo `INPUT(|ket>) THEN <asserção>`**, tratado como núcleo da
   gramática, não extensão. Sem ele, toda asserção só testa comportamento a
   partir de `|0...0⟩` — insuficiente para qualquer tarefa cujo conteúdo
   seja uma TRANSFORMAÇÃO geral (o exercício de validação a frio contra
   `qft_5q`, abaixo, mostrou que uma QFT mal implementada pode passar em
   toda asserção anexada só a `|0...0⟩`, porque a saída nesse caso é
   indistinguível de uma simples superposição uniforme). Várias asserções
   `INPUT` sobre entradas não-triviais distintas dão cobertura evidencial
   real — mesma lógica de `_check_by_composition` (D3b) — mas SEM a mesma
   garantia formal: lá, k estados Haar-aleatórios testam uma proposição
   universal contra uma referência CONHECIDA; aqui não há referência
   nenhuma, cada `INPUT` só testa o que o usuário escreveu, para aquela
   entrada.

**Avaliação — `src/qcagent/validators/assertions.py` (T083–T084b)**: pura
`qiskit.quantum_info`, sem amostragem/shots (é simulação exata, não o
regime de ruído estatístico de `check_sanity_seeds` em `bench/
validate_oracles.py` — as duas tolerâncias não devem ser confundidas, a
mesma distinção que `PEAKEDNESS_THRESHOLD` já fazia em v1).

- `AmplitudeAssertion` (`PROBABILITY`/`AMPLITUDE`/`PHASE_DIFF`):
  `abs(psi[ket])**2`/`abs(psi[ket])`/diferença de fase relativa.
- `MeasuresAssertion`: massa de probabilidade ≈1 no valor esperado —
  **não** via `Statevector.probabilities_dict(qargs=...)` para a forma com
  lista, cujas chaves renderizadas colocam o PRIMEIRO qarg listado na
  posição MAIS À DIREITA (verificado empiricamente, o oposto do que esta
  gramática promete) — implementado contra o array bruto
  `probabilities(qargs=...)` com um índice derivado à mão, verificado
  contra um circuito deliberadamente assimétrico (não só um caso
  coincidentemente palindrômico).
- `GateRestrictionAssertion`: puramente estrutural sobre `circuit.data` —
  não precisa de simulação. Nome de gate validado contra o vocabulário do
  próprio Qiskit (`get_standard_gate_name_mapping()` + o punhado de nomes
  de aridade variável que este projeto usa, ex. `mcx`) — **correção**: a
  razão original para validar (nome digitado errado tornaria a asserção
  vacuamente verdadeira, mesma direção de falha de D3c/D3d/D3f) estava
  ERRADA — uma checagem de subconjunto é fail-closed por construção, nunca
  passa vacuamente num nome digitado errado. A razão real, mais modesta: dá
  um erro de parse preciso em vez de uma falha de asserção confusa que
  parece defeito do CIRCUITO. Ver F6 (report-notes.md) para como essa
  alegação incorreta foi endossada antes de ser corrigida.
- `EigenstateAssertion`: **o único ponto de risco de desenho desta seção**.
  Checar `‖H\|ψ⟩ − λ\|ψ⟩‖ ≈ 0` (norma do resíduo), **nunca** só `⟨ψ\|H\|ψ⟩ ≈ λ`
  (valor esperado). Um valor esperado correto NÃO implica que o estado seja
  um autoestado — uma superposição de autoestados cujos autovalores
  cancelam para a média certa passaria um checador que olhasse só o valor
  esperado. Esta é exatamente a estrutura do achado F2 (`report-notes.md`:
  "checks por medição podem ser estruturalmente cegos, não só frouxos") —
  aplicada aqui ao próprio verificador novo, antes de ele existir em
  produção, não depois de um bug real forçar a correção. `test_assertions.py`
  inclui um teste de regressão com um estado deliberadamente NÃO-autoestado
  mas de valor esperado correto (população `p=1e-10` na autoclasse errada,
  ⟨Z⟩ a `2e-10` de +1 — dentro do `DEFAULT_TOL` do próprio código — mas
  norma do resíduo ~2e-5, muito acima do limiar 1e-6), que REPROVA
  corretamente.

**Malformação** (FR-013): comprimento de bitstring/Pauli-string incompatível
com `n_qubits`, índice de qubit fora de faixa, categoria desconhecida —
todos detectados na etapa de parsing, ANTES de qualquer geração (T090
estende o mecanismo de `status="rejected_input"` que T024b já implementa em
v1, em vez de criar um segundo caminho de recusa). Lista completa em
`data-model.md` §Linguagem de asserção.

**Largura do registro — a asserção do usuário é a fonte de verdade**: o
número de qubits vem das próprias asserções (kets, `MEASURES ==`, Pauli,
`INPUT`), não do `n_qubits` extraído pelo planner. Asserções que discordam
entre si são recusadas (erro do usuário). Uma divergência com a contagem
extraída é resolvida pela força da evidência: duas ou mais asserções
concordando corrigem o requisito (e a correção aparece no relatório de
garantia); uma única asserção contra a leitura do planner é recusada como
ambígua e pergunta, porque nada desempata entre extração errada e erro de
digitação. Nunca é tratada como asserção malformada (F3, F9). Na avaliação, circuito de
largura diferente da asserção é violação nomeada, nunca avaliado mesmo
assim. As asserções também chegam ao gerador desde a primeira tentativa
(T090b); sem asserções, o prompt é idêntico ao anterior.

**Escopo real da gramática — achado do exercício de validação a frio, não
de desenho**: forte para preparação de estado e propriedades qualitativas
(autoestado coletivo, restrição de gate set); fraca para tarefas cujo
conteúdo inteiro é uma derivação numérica (QUBO→Ising — a asserção não-vazia
exige a mesma álgebra que construir o circuito); cega para tarefas de
transformação geral sem `INPUT` (mitigado, não eliminado, pelo item 4
acima — `INPUT` dá cobertura evidencial, não uma garantia formal). Ver F7
(report-notes.md) e o achado equivalente em "Threats to validity". A
gramática NÃO foi alargada para cobrir o caso QUBO — alargá-la para aceitar
uma derivação pronta equivaleria a aceitar uma referência disfarçada, que
anularia o ponto de US3.

**Escopo explicitamente fora desta fase**: os `Requirement`s de
`kind="property"`/`kind="output_format"` que o `planner` já extrai (FR-009)
NÃO ganham conversão automática para a gramática acima nesta fase — isso
exigiria uma camada de tradução de linguagem natural para a gramática
formal, que só pode ser feita hoje por um LLM. Isso é permitido pelo
Princípio I (papel de "gerador de hipótese"), mas é escopo genuinamente
novo, não pedido por nenhuma FR de v2 explicitamente, e arriscaria
reintroduzir a mesma ambiguidade que a gramática formal existe para evitar.
Só `kind="n_qubits"` e `kind="gate_set"` (checáveis sem tradução nenhuma)
ganham verificação automática nesta fase — implementado em
`validators/requirements.py` (T091), rodando dentro de `assertion_check`
porque é a mesma camada sem-referência sobre o mesmo circuito gerado, e
rodando MESMO quando o usuário não declarou asserção nenhuma, que é
precisamente o ponto da FR-009. Um `kind` não tratado não produz saída
nenhuma — nunca uma saída "passou", que alegaria uma checagem que não
rodou. Registrado como decisão de escopo, não como lacuna esquecida — mesmo
padrão de honestidade que D3d (v1) usou para deixar teleporte fora do
conjunto canônico.

**Requisitos são checados deterministicamente, mas sua PREMISSA vem de um
LLM** — e isso muda o que um resultado significa em cada direção. Um
requisito que PASSA diz apenas "o circuito concorda com o que o planner leu
da descrição"; não é evidência de corretude, e por isso não pode
estabelecer `functional_correctness_verified`. Um que REPROVA é
assimetricamente mais forte — circuito e descrição discordam sobre algo
diretamente checável — e por isso VETA a alegação. Um valor que o checador
não consegue avaliar (um `n_qubits` não inteiro, um `gate_set` nomeando
instruções que o Qiskit não tem) vira `passed=None`, "não checável", nunca
uma reprovação: culpar o circuito gerado por um problema de extração acima
dele seria a mesma classe de erro de F3 (diagnóstico incorreto é pior que
nenhum). **Decisão de escopo deixada em aberto de propósito**: uma violação
de requisito NÃO entra hoje na taxonomia fechada de `error_type` nem dispara
`retry_generation` — fazer isso colocaria uma premissa extraída por LLM
dentro do laço de reparo, o que é uma emenda à taxonomia fechada e uma
tensão real com o Princípio I, não uma consequência óbvia de T091. Hoje a
violação é reportada e bloqueia `success`; se deve também retroalimentar o
gerador é decisão a tomar explicitamente.

### Relatório de garantia (US4)

**Status**: implementado e testado (`src/qcagent/report.py`, T093–T096;
`tests/unit/test_report.py`, 23 casos incluindo T095's teste obrigatório).
A forma abaixo é a final — ver data-model.md §GuaranteeReport para os campos
exatos e o texto renderizado das três formas canônicas de relatório (todas
as asserções passando, uma violada, nenhuma declarada), revisadas com o
usuário antes de implementar.

```python
# src/qcagent/report.py — T093

class GuaranteeReport(BaseModel):
    model_config = ConfigDict(extra="forbid")   # ver abaixo — é a garantia em si

    executed: bool
    transpiled: bool
    requirements: list[RequirementOutcome]    # T091 — um por requisito CHECÁVEL
    reference: SemanticResult | None          # semantic_check, sse oracle_ref (T098)
    assertions: list[AssertionOutcome]        # vazia se nenhuma foi declarada
    coupling_map_name: str | None
    topology_respected: bool | None           # None sse coupling_map_name é None
    resource: ResourceResult | None           # None a menos que oracle_ref esteja presente
    hardware_note: str | None                 # US5 — "comportamento sob ruído", nunca "verificação"

    @computed_field
    @property
    def functional_correctness_verified(self) -> bool:
        if not (self.executed and self.transpiled):
            return False
        if any(a.passed is not True for a in self.assertions):
            return False
        if self.reference is not None:            # referência: reprovada veta, aprovada verifica
            return self.reference.passed
        if any(r.passed is False for r in self.requirements):   # requisitos VETAM (T091)
            return False
        return bool(self.assertions)

    @computed_field
    @property
    def only_trivial_input_tested(self) -> bool:
        input_capable = [o.assertion for o in self.assertions if hasattr(o.assertion, "input_state")]
        return bool(input_capable) and not any(a.input_state is not None for a in input_capable)
```

**O status terminal carrega a distinção, não a convenção**: `status=
"success"` significa "ALGO REAL sobre corretude funcional foi verificado e
passou" — comparação com referência (caminho da suíte) OU toda asserção
declarada (caminho de produto). Um run limpo que não verificou nada termina
como `"completed_unverified"`. A alternativa descartada era uma regra de
consumo ("nenhum consumidor lê `status` sem ler também o relatório"), e uma
invariante que depende de cooperação de consumidores é quebrada pela
primeira coisa que agregue `status` sozinha (T059, um resumo de CI).

**Onde "verificado" é decidido — uma vez, e só uma**: em
`GuaranteeReport.functional_correctness_verified`, na ordem acima (não
rodou → não verificado; asserção do usuário que não passou veta; referência
reprovada veta, aprovada verifica e não é vetada por requisito; senão
requisito reprovado veta e é preciso ao menos uma asserção).
`terminal_status()` apenas LÊ esse campo. **Correção a uma versão anterior
deste parágrafo**: ela dizia que status e texto "nunca podem discordar"
porque `terminal_status()` recebia o objeto de relatório — mas a função
ainda checava `semantic.passed` por conta própria enquanto o relatório
ignorava `semantic` inteiramente. Todo run da suíte que passava sua
comparação com referência saía com `status="success"` e um texto dizendo
"nothing about its behavior was checked". A alegação só passou a ser
verdadeira quando a referência entrou no relatório e a decisão foi
centralizada, e só foi descoberta pelos testes ponta a ponta (T098), não
pelos unitários. **A métrica da suíte não muda** — as sete asserções
`status == "success"` de `tests/integration/test_us1_flow.py` continuam
passando, e um requisito reprovado não veta uma referência aprovada
(oráculo é verdade-terreno, Princípio IV; quando discordam, errou o planner).

**O relatório diz o que cada tipo de referência de fato provou**: exato
("unitariamente equivalente, até fase global"), composição ("probabilístico,
não exato", D3b), statevector ("a partir de |0...0> somente", D3c),
distribuição ("fidelidade de Hellinger", não equivalência de estado) e
energia. Um "bate com a referência" único superestimaria em todos menos o
exato.

**`topology_respected`/`resource` — a decisão "recursos para o relatório,
não para a gramática" (round 2, item 2), implementada**: `topology_respected`
vem direto de `static.transpiled` (`nodes/routing.py::
_build_guarantee_report`) — evidência sem referência, disponível
independentemente de `oracle_ref`. `resource` permanece `None` a menos que
`oracle_ref` esteja presente, porque `resource_check` (graph.py) sempre
carregou um circuito de referência incondicionalmente — nunca rodou só por
`coupling_map` estar declarado (ver correção à tabela de contratos dos nós,
acima). Quando `coupling_map_name` foi declarado mas não há referência,
`render_guarantee_report()` diz explicitamente que `depth_ratio` não tem
significado sem uma, em vez de omitir o campo em silêncio.

**`only_trivial_input_tested` — a decisão "sempre mostrar, nunca tentar
adivinhar a forma da tarefa" (aprovada por pergunta direta ao usuário antes
de implementar)**: um fato puramente estrutural (nenhuma asserção usou
`INPUT`), renderizado sempre que verdadeiro, mesmo em relatórios de tarefas
de preparação de estado onde `|0...0⟩` é o único input relevante por
desenho — a alternativa (tentar detectar se a tarefa "é" uma transformação
geral) exigiria julgamento sobre a intenção da tarefa, que o Princípio I
proíbe neste caminho.

**A decisão de desenho que carrega o Princípio II inteiro**:
`functional_correctness_verified` é um `@computed_field`, não um campo
comum — não pode ser passado ao construtor. Com
`model_config = ConfigDict(extra="forbid")`, tentar
`GuaranteeReport(functional_correctness_verified=True, assertions=[])`
levanta `ValidationError` em vez de silenciosamente aceitar um relatório que
mente. **A invariante de SC-004 é estruturalmente impossível de violar por
construção**, não apenas coberta por um teste que alguém poderia esquecer
de rodar. T095 (`tests/unit/test_report.py::
test_no_correctness_claim_without_verified_assertion` +
`test_cannot_construct_a_lying_report`) é o teste obrigatório que confirma
isso — tanto o caso direto (relatório vazio não afirma corretude) quanto o
caso adversário (tentar construir o relatório mentiroso é rejeitado pela
própria classe).

`render_guarantee_report()` (T094) enumera cada asserção com veredito
individual (FR-011, FR-015), inclui a frase de não-verificação explícita
quando `functional_correctness_verified=False` (FR-016), e nunca usa
linguagem que equipare "executa e respeita restrições" a "está correto"
(FR-017) — essa é uma checagem de VOCABULÁRIO no renderizador, testada
diretamente (T095), não uma convenção de estilo.

**Nota de implementação (`AgentState.guarantee_report`)**: tipado `Any` em
`state.py`, não `GuaranteeReport | None` — `report.py` importa `Assertion`/
`AssertionOutcome`/`ResourceResult` de `state.py`, então um import no
sentido contrário seria circular, e um import guardado por `TYPE_CHECKING`
quebra em runtime: `StateGraph(AgentState)` do LangGraph chama
`typing.get_type_hints()` sobre o `TypedDict`, que tenta resolver toda
referência textual contra o namespace do próprio módulo e falha
(`NameError`) num nome nunca importado de fato em runtime — confirmado ao
tentar essa rota antes de revertê-la para `Any`. O valor real em tempo de
execução continua sendo sempre um `GuaranteeReport` de verdade; a perda de
precisão de tipo fica confinada a esta única anotação.

### Armadilhas endereçadas no desenho

Preservadas de v1 (continuam verdadeiras, nenhuma invalidada pela migração):

- **Fase global**: usar `Operator.equiv()`/comparação de magnitude, nunca
  comparação direta de amplitudes complexas. Aplica-se também a
  `AmplitudeAssertion`'s `PROBABILITY`/`AMPLITUDE` (acima) — mesma lição,
  novo lugar; `PHASE_DIFF` é a única exceção deliberada, por ser uma
  diferença relativa, não uma fase absoluta.
- **Teto de `Operator()`**: matriz densa 4ⁿ — acima de ~12–13 qubits, usar
  verificação por composição. Ver D3b.
- **Endianness**: Qiskit é little-endian; verificar também contra bits
  invertidos, reportar `EndiannessSwap` como categoria própria.
- **Transpilação assimétrica**: gerado e referência passam pelos mesmos
  parâmetros — erro metodológico comparar transpilado contra não-transpilado.
- **Truncagem silenciosa de contexto**: fixar `num_ctx` por requisição,
  contar tokens antes de enviar (D10b) — continua valendo mesmo sem C1–C5
  para "invalidar": um prompt truncado silenciosamente ainda produz um
  resultado errado atribuído à capacidade do gerador, não à infraestrutura.
- **Overhead por execução domina**: pool de workers pré-aquecidos (D1b) —
  ainda relevante para SC-007 (suíte < 3h), mesmo em escala muito menor que
  a matriz de 27.000 chamadas de v1.

**Nova em v2**:

- **Checador estruturalmente cego ao próprio erro que existe para pegar**:
  um valor esperado correto não implica ausência de erro (F2, acima,
  `EigenstateAssertion`). Testar o verificador contra um caso adversário
  ANTES de confiar nele — não depois de um bug real forçar a correção,
  diferente de como F2 foi descoberto originalmente em v1 (um bug real de
  QFT). A lição de v1 se paga aplicada preventivamente em v2 — entregue:
  `test_eigenstate_residual_norm_rejects_near_miss_that_expectation_alone_
  would_pass` (`tests/unit/test_assertions.py`).
- **Reconhecer um padrão de falha conhecido não confirma que ele se
  aplica**: a justificativa original para validar nomes de gate em
  `GATES_SUBSET_OF` ("mesma direção de falha de D3c/D3d/D3f") foi endossada
  antes de ser derivada com cuidado, e estava errada — ver F6
  (report-notes.md) e `research.md` D19. Registrada aqui como uma classe de
  erro distinta de F1-F5: não um defeito no artefato verificado, mas no
  raciocínio de desenho que justificou uma decisão de implementação.

### Suíte de regressão (substitui "Matriz experimental")

Não há mais condições C1–C5 nem braços a comparar. A suíte roda **uma
configuração por vez** (um gerador, um conjunto de tarefas, seeds
declaradas em `config.yaml`) e produz taxa de sucesso por tier — FR-025.

**Bloqueio do Princípio IV, em tempo de execução, não só em CI** (T099): o
runner recusa iniciar qualquer execução se alguma tarefa da configuração
tiver referência não verificada por `validate_oracles.py`. Isso é mais
forte que o portão de CI de v1 (T051, ainda pendente) porque bloqueia no
PONTO DE USO — um desenvolvedor rodando a suíte localmente, sem CI, ainda
está protegido.

**Comparação entre execuções** (FR-027, SC-008): por tarefa, não só
agregado — permite distinguir "esta mudança quebrou a tarefa X" de "a taxa
agregada caiu 2%", que sozinha não diz qual tarefa regrediu.

**Post-Design Constitution Check**: ✅ PASS — nenhum LLM em caminho de
veredito (incluindo o novo `assertion_check`); `results/` permanece
append-only; o bloqueio de referência não verificada agora é ativo em dois
pontos (CI + runtime), não um.

## Complexity Tracking

Nenhuma violação constitucional a justificar.

Complexidades deliberadas, aceitas com razão:

| Decisão | Custo | Por que a alternativa mais simples é insuficiente |
|---|---|---|
| Índice híbrido esparso + denso | serviço dedicado a mais no compose | busca densa confunde identificadores próximos (`RZGate` vs `RXGate`), que é exatamente o caso crítico. Com Qdrant o custo cai a um serviço e uma coleção — os dois vetores são nomeados no mesmo ponto |
| Chunking code-aware | parser dedicado por fonte | chunking por janela separa assinatura do exemplo e destrói o valor da recuperação |
| Pares canônico/perturbado (agora teste de robustez, não controle de contaminação) | dobra o custo de curadoria — já pago em v1, preservado | sem variantes perturbadas, uma taxa de sucesso alta na suíte pode refletir memorização de treino em vez de generalização — a suíte perderia a capacidade de distinguir as duas |
| Execução em subprocesso | overhead por execução | Princípio constitucional de isolamento; contêiner efêmero seria mais seguro mas inviável mesmo na escala menor da suíte de regressão |
| `functional_correctness_verified` como campo computado, não settable | uma indireção a mais em todo lugar que constrói `GuaranteeReport` | é a única forma de tornar SC-004 estruturalmente impossível de violar por acidente, em vez de apenas testado — ver §Relatório de garantia |

## Milestones

| Marco | Portão de saída |
|---|---|
| M0 — Ambiente | `make test` verde, versões pinadas — **concluído** |
| M1 — Recuperação | `recall@8 ≥ 0.85` — **concluído** (0,9524, D17-1) |
| M2 — Suíte de regressão, dados | `validate_oracles.py` 120/120 verde — **concluído**. Conjunto de referências estável a partir daqui: mudar uma referência depois é decisão registrada em `research.md`, não edição solta — SC-008 só significa algo contra uma suíte estável |
| M3 — Verificação sem referência (US3) | gramática de asserção com as 4 categorias implementada e testada; SC-003 (100%) passando |
| M4 — Relatório de garantia (US4) | SC-004 garantido por teste que falha a build se violado (T095), não por convenção |
| M5 — Interface (US6, P2) | SC-005 validado manualmente pela interface mínima |
| M6 — Suíte de regressão operacional (US7, P2) | SC-007/008/009 confirmados; bloqueio do Princípio IV testado em runtime (T100) |
| M7 — Entrega | relatório final consolidado (`report-notes.md` + `estado-e-aprendizados.md`), release do código, dataset com DOI, US5 (hardware) se houver tempo |
