# Tasks: LLM Quantum Copilot

**Input**: Documentos de desenho em `/specs/001-qcircuit-agent/`
**Prerequisites**: `plan.md` (obrigatório), `spec.md` v2 (obrigatório), `research.md`, `data-model.md`, `MIGRATION.md`

> **Reescrita completa para v2 (2026-09-15)** — ver `MIGRATION.md`. Phases 1–5
> (T001–T052) documentam trabalho **já concluído em v1 e preservado
> integralmente** — US1 e US2 continuam implementadas e marcadas `[X]`, sem
> reescrita de conteúdo. A partir da Phase 6, todo o conteúdo é novo,
> organizado pelas histórias de usuário de `spec.md` v2 (US3 → US4 → US6 →
> US7 → US5 → Polish). Tarefas removidas pela migração (T053, T055–T058,
> T059c, T062–T064, T075) não aparecem mais — ver `MIGRATION.md` §3 para o
> porquê de cada uma.

**Tests**: incluídos — o Princípio IV exige verificação dos próprios
oráculos (bloqueante), e o Princípio I exige teste de arquitetura que impeça
LLM em caminho de veredito. O Princípio II (honestidade sobre garantia)
ganha, pela primeira vez, um teste obrigatório e nomeado (T095) em vez de
ficar implícito em convenção de código. Testes de UI/integração amplos
ficam fora.

**Organization**: tarefas agrupadas por user story. Cada grupo é
independentemente implementável e testável.

**Convenções**
- `[P]` — pode rodar em paralelo (arquivos distintos, sem dependência)
- `[USn]` — história de usuário a que pertence (numeração de `spec.md` v2 —
  **não** a de v1: o que era `[US4]` hardware em v1 é `[US5]` em v2)
- Caminhos de arquivo exatos nas descrições

---

## Phase 1: Setup

**Purpose**: ambiente reprodutível e esqueleto do projeto. **Concluída.**

- [X] **T001** Criar estrutura de diretórios conforme `plan.md` (`src/qcagent/`, `bench/`, `analysis/`, `tests/`, `results/`)
- [X] **T002** Criar `pyproject.toml` com `uv`, Python 3.11, e **versões exatas** `qiskit==1.2.4`, `qiskit-aer==0.15.1` (CPU). Declarar `qiskit-aer-gpu` como extra opcional `[gpu]`, não como dependência padrão (D1)
- [X] **T003** [P] Criar `Dockerfile` com base CUDA 12.1 e `docker-compose.yml` (app + `qdrant/qdrant:v1.12.x` com tag fixa), volume persistente para o storage do Qdrant e para o cache de modelos fastembed (D18)
- [X] **T004** [P] Configurar `ruff` + `mypy` + `pre-commit` em `.pre-commit-config.yaml`
- [X] **T005** [P] Criar `Makefile` com alvos `index`, `eval`, `report`, `test`
- [X] **T006** Implementar `src/qcagent/validators/simulator.py` com `make_simulator` (CPU por padrão, GPU acima de `GPU_THRESHOLD_QUBITS=18`) conforme [`contracts/validators.md`](./contracts/validators.md)
- [X] **T006b** [P] Escrever `tests/smoke/bench_backend.py` — cronometrar CPU vs GPU em 5, 10, 15, 18, 20 qubits e **confirmar empiricamente o limiar**; ajustar a constante com o resultado medido
- [X] **T007** [P] Criar `.env.example` e `src/qcagent/config.py` com `pydantic-settings`

**Checkpoint (M0)**: `make test` verde, versões pinadas registradas. ✅

---

## Phase 2: Foundational (bloqueia todas as histórias)

**Purpose**: infraestrutura que qualquer história precisa. **Concluída.**

- [X] **T008** Implementar entidades Pydantic em `src/qcagent/state.py` conforme `data-model.md` (`Requirement`, `Chunk`, `ErrorRecord`, `StaticResult`, `SemanticResult`, `ResourceResult`, `CriticDecision`, `AgentState`)
- [X] **T009** [P] Implementar `src/qcagent/llm/base.py` — interface comum de gerador com contagem de tokens e custo
- [X] **T010** [P] Implementar `src/qcagent/llm/anthropic_client.py`
- [X] **T011** [P] Implementar `src/qcagent/llm/ollama_client.py` com `num_ctx` **explícito em cada requisição** (16384 inicial), nunca herdado do default do servidor (D10b)
- [X] **T011b** [US1] Implementar guarda anti-truncagem em `ollama_client.py` — contar tokens do prompt antes de enviar e levantar `ContextOverflowError` se exceder `num_ctx`. Truncagem silenciosa é um modo de falha que se atribuiria à capacidade do gerador, não à infraestrutura, sem essa guarda
- [X] **T011c** [P] Registrar `num_ctx` efetivo e contagem de tokens de entrada no `RunRecord` — o valor precisa estar no resultado, não só na configuração
- [X] **T012** Implementar cache de resposta por `hash(prompt + modelo + seed)` em `src/qcagent/llm/base.py` (FR-005, registro de toda tentativa)
- [X] **T012b** Implementar retry com backoff exponencial limitado em `src/qcagent/llm/base.py` para falhas transitórias do provedor (rate limit, 5xx, timeout). Esgotadas as tentativas, propagar como `status="infrastructure_error"` sem passar pelo `critic` — não é erro de código gerado. Mesmo arquivo de T012, sequencial
- [X] **T013** Implementar `WorkerPool` em `src/qcagent/validators/sandbox.py` — processos pré-aquecidos (qiskit já importado), reciclagem a cada N execuções, timeout que mata e substitui o worker, denylist, serialização QPY (FR-021, D1b)
- [X] **T013b** [P] Instrumentar `SandboxResult` com `wall_time_s` e `exec_time_s` separados — latência sem essa separação mede infraestrutura, não o sistema sob teste
- [X] **T014** [P] Escrever `tests/unit/test_sandbox.py` cobrindo timeout, denylist e código que não define `qc`
- [X] **T015** Implementar logging estruturado e `run_id = hash(config + git SHA + timestamp)` em `src/qcagent/config.py`
- [X] **T015b** [P] Implementar coleta de telemetria de GPU em `src/qcagent/llm/ollama_client.py` — `memory.used` via `nvidia-smi` e a string `PROCESSOR` do `ollama ps`, gravadas no `RunRecord` (D10c)
- [X] **T015c** [US1] Abortar a execução se `PROCESSOR` não for "100% GPU" no braço local — melhor falhar alto que contaminar a métrica de latência em silêncio
- [X] **T016** [P] Escrever `tests/contract/test_architecture.py` — falha se `src/qcagent/validators/` importar de `src/qcagent/llm/` (Princípio I)

**Checkpoint**: fundação pronta — histórias podem começar. ✅

---

## Phase 3: User Story 1 — Circuito verificado a partir de descrição (P1) 🎯 MVP

**Status**: ✅ **IMPLEMENTADA** (spec.md v2). Conteúdo preservado de v1 sem
alteração — o comportamento continua correto sob a constituição v2.0.0.

**Goal**: entregar circuito com veredito verificável, corrigindo-se quando falha.

**Independent Test**: 20 descrições com referência conhecida → veredito correto
para todas, incluindo os vereditos de falha.

### Validadores (o coração determinístico)

- [X] **T017** [P] [US1] Implementar `src/qcagent/validators/static.py` — camadas 1-2: `ast.parse`, execução isolada, `transpile`; tabela `DEPRECATED_SYMBOLS` produzindo `error_type="DeprecatedAPI"` (FR-002)
- [X] **T018** [P] [US1] Implementar `_check_exact` em `src/qcagent/validators/semantic.py` com `Operator.equiv()` — tolerância a fase global, teto de 12 qubits (FR-014)
- [X] **T018b** [US1] Implementar `_check_by_composition` — `generated.compose(reference.inverse())` com 5 estados Haar-aleatórios, custo 2ⁿ (D3b)
- [X] **T018c** [US1] Implementar o despacho `check_unitary` por porte e registrar `verification_method` no `SemanticResult`
- [X] **T019** [US1] Adicionar detecção de inversão de ordenação em `semantic.py` — verificar contra referência com bits invertidos, reportar `EndiannessSwap`
- [X] **T020** [P] [US1] Implementar `check_distribution` (fidelidade de Hellinger + TVD, média sobre 3 seeds) em `semantic.py`
- [X] **T021** [P] [US1] Implementar `check_energy` para oráculos de VQE em `semantic.py`
- [X] **T022** [US1] Implementar `src/qcagent/validators/resource.py` — transpilar gerado **e** referência com `opt_level`, `coupling_map` e `seed_transpiler` idênticos; `depth_ratio`, `cx_ratio` (FR-002)
- [X] **T023** [P] [US1] Escrever `tests/unit/test_semantic.py` com casos-armadilha: fase global, ordenação invertida, dimensões incompatíveis
- [X] **T023b** [US1] **Teste-chave de D3b**: rodar os caminhos exato e por composição sobre o mesmo par de circuitos de 8 qubits e exigir concordância — garante que a troca de método acima de 12 qubits não introduz viés

### Nós e grafo

- [X] **T024** [P] [US1] Escrever prompt e implementar `src/qcagent/nodes/planner.py` — descrição → `list[Requirement]`
- [X] **T024b** [US1] Implementar checagem de não-satisfazibilidade em `planner.py` — sinalizar `status="rejected_input"` e encerrar o grafo antes de `retriever`/`generator` quando os requisitos extraídos indicam entidade faltante, restrição contraditória, ou `n_qubits` acima do teto de simulação configurado (spec.md v2 — Edge Cases: "descrição ambígua ou impossível → recusa explícita"; FR-004). Ambiguidade não detectável nesta etapa segue o fluxo normal. Mesmo arquivo de T024, sequencial
- [X] **T025** [P] [US1] Escrever prompt e implementar `src/qcagent/nodes/generator.py` — injeta apenas os 2 últimos erros no contexto
- [X] **T026** [US1] Implementar `src/qcagent/nodes/critic.py` — roteamento por `error_type` conforme tabela do `plan.md` (FR-003)
- [X] **T027** [US1] Implementar `src/qcagent/nodes/routing.py` — arestas condicionais e corte em `MAX_ITER` com status de falha explícito (FR-004)
- [X] **T028** [US1] Montar `src/qcagent/graph.py` com reducers `add` em `error_history` e `trace`; incluir a aresta condicional de `planner` direto para `[ rejected_input ]` quando T024b sinaliza a recusa
- [X] **T029** [US1] Adicionar `interrupt_before` opcional entre `semantic_check` e `resource_check`, desligado por padrão
- [X] **T030** [US1] Escrever `tests/integration/test_us1_flow.py` cobrindo os 4 cenários de aceitação da US1

**Checkpoint**: US1 entregável isoladamente. Sistema já é útil sem RAG. ✅

---

## Phase 4: User Story 2 — Evitar interfaces obsoletas (P1)

**Status**: ✅ **IMPLEMENTADA**. Preservada sem alteração.

**Goal**: eliminar uso de API depreciada via recuperação versionada.

**Independent Test**: comparar taxa de construção obsoleta com e sem recuperação.

- [X] **T031** [P] [US2] Implementar `src/qcagent/retrieval/ingest.py` — coleta de docs Qiskit, guias de migração, docs PennyLane e abstracts do arXiv quant-ph
- [X] **T032** [US2] Implementar `src/qcagent/retrieval/chunking.py` — chunking por símbolo; assinatura + docstring + exemplo permanecem íntegros (FR-006)
- [X] **T033** [US2] Adicionar metadados `library_version` e `deprecated` na ingestão; marcar símbolos dos guias de migração (FR-006, FR-007)
- [X] **T033b** [US2] Confirmar a API do `qdrant-client` na versão fixada em T003 contra `contracts/retrieval.md`; corrigir o contrato antes de implementar T034
- [X] **T034** [US2] Implementar `ensure_collection` e `point_id` em `src/qcagent/retrieval/index.py` conforme [`contracts/retrieval.md`](./contracts/retrieval.md) — vetores nomeados `dense` (cosine) e `sparse` (`Modifier.IDF`)
- [X] **T035** [US2] Implementar `_create_payload_indexes` — `library_version` (KEYWORD), `deprecated` (BOOL), `source` (KEYWORD). Sem isso o filtro vira pós-filtro e o recall despenca nas consultas filtradas por versão
- [X] **T035b** [P] [US2] Implementar `upsert_chunks` (lote, `wait=True`) e teste de idempotência em `tests/unit/test_index.py` — reingestão não altera `point_count`
- [X] **T036** [US2] Implementar `search` e `build_filter` em `src/qcagent/retrieval/hybrid.py` — Query API com `prefetch` denso + esparso, filtro em **cada ramo**, `FusionQuery(RRF)`, `limit=8` (FR-008)
- [X] **T036b** [P] [US2] Implementar snapshot da coleção em `src/qcagent/retrieval/index.py` (`create_snapshot`) e registrar o hash do snapshot no `run_id` — reprodutibilidade do corpus (Princípio III)
- [X] **T037** [US2] Implementar `RetrievalBundle.to_prompt_context` — chunk `deprecated=True` renderizado com marcação de proibição e o campo `replacement` visível, não omitido (FR-007)
- [X] **T038** [US2] Implementar `split_by_register` — separar `api_chunks` de `paper_chunks` e entregar em blocos distinguíveis ao gerador
- [X] **T038b** [P] [US2] Implementar o `Embedder` Protocol em `src/qcagent/retrieval/embedding.py` com métodos separados para documento e consulta (prefixos assimétricos)
- [X] **T039** [US2] Implementar `src/qcagent/nodes/retriever.py` e conectar ao grafo, incluindo `retry_retrieval` do critic
- [X] **T040** [US2] Criar 50 consultas sintéticas com chunk-alvo conhecido em `tests/retrieval/queries.jsonl`
- [X] **T040b** [US2] Escrever teste do caso crítico em `tests/unit/test_hybrid.py` — consulta contendo `RZGate` traz o chunk de `RZGate` acima do de `RXGate`. Se falhar, o ramo esparso não contribui: verificar o modifier IDF antes de trocar o modelo denso
- [X] **T041** [US2] Escrever `analysis/eval_retrieval.py` — `recall@8` e MRR; **portão M1: recall@8 ≥ 0.85**
- [X] **T042** [US2] Escrever `tests/integration/test_us2_flow.py` cobrindo os 3 cenários de aceitação da US2

**Checkpoint (M1)**: recuperação validada isoladamente. `recall@8` = 0,9524 (D17-1). ✅

---

## Phase 5: Suíte de regressão — dados (habilita US7)

**Purpose**: sem referências verificadas não existe suíte de regressão nem
Princípio IV. **Nota de estrutura v2**: esta fase deixou de ser um portão
prévio a US3 (verificação sem referência, por desenho, não depende disto) —
ela habilita exclusivamente **US7**. US3/US4 podem prosseguir em paralelo,
sem esperar T051/T052.

**Status**: 120/120 referências construídas e verificadas. T051/T052 são o
que resta.

- [X] **T043** [P] Implementar `bench/schema.py` — `TaskSpec` conforme `data-model.md`, incluindo `oracle_kind="statevector"` (D3c)
- [X] **T044** [P] Criar 18 tarefas canônicas T1 em `bench/tasks/t1_primitives/` — Bell×3, GHZ×3, W-state×3, QFT×3, Deutsch-Jozsa×3, Aritmética booleana reversível×3. Teleporte descartado do conjunto canônico (D3d) — nem `unitary` nem `statevector` se encaixa sem admitir respostas incorretas; oráculo de fidelidade de canal registrado como trabalho futuro
- [X] **T045** [P] Criar 18 tarefas canônicas T2 em `bench/tasks/t2_algorithms/` — Bernstein-Vazirani×3, Simon×3, Grover×3, QPE×3, QAOA MaxCut×3, VQE H₂×3. QAOA e VQE H₂ têm parâmetros fixos no enunciado — medem fidelidade de construção do ansatz, não capacidade de otimização (D3e/D3e-3), ressalva que se aplica a qualquer leitura futura dos resultados da suíte sobre essas 6 tarefas
- [X] **T046** [P] Criar 12 tarefas canônicas T3 em `bench/tasks/t3_formulation/` — Ising MaxCut ponderado×3, interação multi-corpo×3, campo+acoplamento×3, QUBO→Ising×3. Convenção de sinal QUBO→Ising declarada explicitamente em cada enunciado (D3f)
- [X] **T047** [P] Criar 12 tarefas canônicas T4 em `bench/tasks/t4_hardware/` — GHZ sobre subconjunto×4, Ising ponderado×4, Z-string×2, campo+acoplamento×2, todas com `coupling_map="linear_5"`. `oracle_kind="resource"` confirmado SEM despacho — T4 usa `statevector`/`unitary` + `coupling_map` não-nulo (D3h)
- [X] **T048** Criar as 60 variantes perturbadas pareadas, uma por canônica (`base_task_id`). 60/60 feito — distribuição final por família em D3j (research.md), toda exclusão catalogada por causa (vazia / mudança de identidade de tarefa / armadilha de transpilador não-defeito, D3k)
- [X] **T049** Construir oráculos em `bench/oracles/` — construção independente, não derivada do enunciado (Princípio IV). 60/60 canônicas + 60/60 perturbadas
- [X] **T050** Implementar `bench/validate_oracles.py` — unitariedade, construção alternativa, cross-check com biblioteca, sanity em 3 seeds. Passando para os 120 oráculos completos, incluindo `check_perturbation_pairing()` (pareamento `base_task_id`, completude 60/60)
- [ ] **T051** Adicionar `validate_oracles.py` como job **bloqueante** no CI (`.github/workflows/oracles.yml`) — metade do bloqueio do Princípio IV (a outra metade, em runtime, é T099)
- [ ] **T052** Validar tetos de porte na ingestão da suíte: `n_qubits <= 20` para toda tarefa **e** `n_qubits <= 13` quando `oracle_kind="unitary"` (D3b). Rejeitar na entrada, nunca durante a execução
- [ ] **T052c** [P] Atualizar `specs/001-qcircuit-agent/data-model.md` — remover `RunRecord.condition` (C1–C5 não existem mais em v2); adicionar `Assertion` (união discriminada: `AmplitudeEquality`, `MeasurementDeterminism`, `OperatorEigenstate`, `GateRestriction`), `AssertionOutcome`, `GuaranteeReport`, conforme o desenho em `plan.md` §Verificação sem referência / §Relatório de garantia. **Bloqueia T082 e T093** — a forma exata dos modelos deve ser fixada no documento de desenho antes do código

**Checkpoint (M2)**: 120/120 oráculos verdes. Conjunto de referências
estável a partir daqui — mudar uma referência depois é decisão registrada em
`research.md`, não edição solta (SC-008 só significa algo contra uma suíte
estável). ✅ (T051/T052/T052c pendentes, não bloqueiam US3/US4)

---

## Phase 6: User Story 3 — Verificação sem referência (P1) 🎯 CAMINHO CRÍTICO

**Goal**: usuário declara propriedades que o circuito deve satisfazer; o
sistema as verifica por simulação, sem exigir um circuito de referência.

**Independent Test**: submeter descrições com asserções conhecidamente
verdadeiras e conhecidamente falsas; confirmar que o sistema aprova as
primeiras e reprova as segundas (SC-003, 100% dos casos).

**Por que é o caminho crítico**: "é a história que torna o produto um
produto" (spec.md) — sem ela, corretude funcional só é verificável quando o
usuário já tem a resposta. Não depende da Phase 5 (dataset) nem de
`oracle_ref` algum — verificação sem referência é literalmente o ponto.

- [ ] **T081** [P] [US3] Ver T052c — pré-requisito de desenho (`data-model.md`) para esta fase
- [ ] **T082** [US3] Implementar `AmplitudeEquality`, `MeasurementDeterminism`, `OperatorEigenstate`, `GateRestriction` em `src/qcagent/state.py` como união discriminada por `kind` (`Assertion`), mais `AssertionOutcome`; adicionar `assertions: list[Assertion]` e `assertion_results: list[AssertionOutcome] | None` a `AgentState`. Depende de T052c fixar a forma exata
- [ ] **T083** [US3] Implementar `parse_assertions(text: str, n_qubits: int)` em `src/qcagent/validators/assertions.py` — parser determinístico (SEM LLM) da forma textual mínima (`AMPLITUDE_EQUAL(a, b)`, `MEASURES(qubits) == bitstring`, `EIGENSTATE_OF(pauli, eigenvalue)`, `GATES_SUBSET_OF({...})`). Entrada fora da gramática, qubit fora de faixa, ou comprimento de bitstring/Pauli-string incompatível com `n_qubits` produz um erro estruturado — nunca uma exceção não tratada, nunca uma asserção silenciosamente ignorada (FR-013)
- [ ] **T084** [US3] Implementar `evaluate_assertions(assertions, circuit)` em `validators/assertions.py` para `AmplitudeEquality` (`abs(psi[a]) ≈ abs(psi[b])` — magnitude apenas por padrão, fase relativa é opt-in via `relative_phase_rad`), `MeasurementDeterminism` (`Statevector.probabilities(qargs=...)`, massa ≈1 no valor esperado) e `GateRestriction` (estrutural sobre `circuit.data`, sem simulação). Mesmo arquivo de T083, sequencial
- [ ] **T084b** [US3] Implementar o checador de `OperatorEigenstate` no mesmo arquivo verificando a **norma do resíduo** `‖H\|ψ⟩ − λ\|ψ⟩‖ ≈ 0`, não `⟨ψ\|H\|ψ⟩ ≈ λ` sozinho (ver plan.md §Verificação sem referência — é o achado F2 aplicado preventivamente). **Escrever o teste adversário ANTES de aceitar a implementação**: um estado deliberadamente não-autoestado mas de valor esperado correto deve reprovar
- [ ] **T085** [P] [US3] Escrever `tests/unit/test_assertions.py` — casos verdadeiros e falsos para as quatro categorias, o caso armadilha de T084b, e os casos de asserção malformada de T083
- [ ] **T086** [US3] Adicionar `AssertionViolated` à taxonomia fechada de `error_type` em `data-model.md` (stage=`semantic`) e ao roteamento do `critic` em `src/qcagent/nodes/critic.py` — `retry_generation`, mesma classe de `WrongGateDecomposition`
- [ ] **T087** [US3] Implementar `make_assertion_check_node` em `src/qcagent/graph.py` — roda após `static_check` aprovar; produz lista vazia (não erro) quando `assertions` está vazia; cada violação vira `ErrorRecord(error_type="AssertionViolated")` nomeando a asserção (FR-012)
- [ ] **T088** [US3] Implementar `route_after_assertion_check` em `src/qcagent/nodes/routing.py`: violação → `critic`; aprovado (ou vazio) e `oracle_ref` presente no estado → `semantic_check`; aprovado e sem `oracle_ref` → `resource_check` se `coupling_map` presente, senão `critic` diretamente. Atualizar `route_after_static` para apontar a `assertion_check` em vez de `semantic_check`
- [ ] **T089** [US3] Atualizar `build_graph` em `graph.py` com o nó e as arestas condicionais de T087/T088; confirmar que o diagrama ASCII e a tabela de contratos de nós em `plan.md` continuam batendo com o código
- [ ] **T090** [US3] Estender a checagem de não-satisfazibilidade de `planner.py`/T024b — asserção malformada (T083) é detectada e recusada ANTES da geração, reaproveitando `status="rejected_input"`, não gasta uma tentativa de geração
- [ ] **T091** [P] [US3] Implementar checagem executável dos `Requirement`s de `kind="n_qubits"` (compara contra `circuit.num_qubits`) e `kind="gate_set"` (reaproveita `GateRestriction` de T084) já extraídos pelo `planner` (FR-009). **Fora de escopo nesta fase, registrado explicitamente**: `kind="property"` e `kind="output_format"` continuam sem checagem automática — ver plan.md §Verificação sem referência para o porquê
- [ ] **T092** [US3] Escrever `tests/integration/test_us3_flow.py` cobrindo os 4 cenários de aceitação da US3 (spec.md)

**Checkpoint (M3) — PARAR E REVISAR ANTES DE PROSSEGUIR PARA US4**: SC-003
(100% de classificação correta em asserções verdadeiras/falsas) precisa
estar verde. A interface de `AssertionOutcome` que US4 consome é definida
aqui — mudá-la depois de US4 começar é retrabalho em dois lugares.

---

## Phase 7: User Story 4 — Relatório de garantia (P1)

**Goal**: toda saída vem com um relatório que declara exatamente o que foi
verificado, como, e o que permanece não verificado.

**Independent Test**: para cada combinação de verificações executadas,
conferir que o relatório enumera corretamente o verificado e o não
verificado.

**Depende de**: US3 completa (consome `AssertionOutcome`).

- [ ] **T093** [P] [US4] Implementar `GuaranteeReport` em `src/qcagent/report.py` (novo módulo) conforme plan.md §Relatório de garantia — `functional_correctness_verified` é um `@computed_field` (nunca um argumento do construtor), `model_config = ConfigDict(extra="forbid")` faz uma tentativa de setá-lo diretamente levantar `ValidationError`. Depende de T052c
- [ ] **T094** [US4] Implementar `render_guarantee_report(report: GuaranteeReport) -> str` em `report.py` — enumera cada asserção com veredito individual (FR-011, FR-015); quando `functional_correctness_verified=False`, inclui literalmente a frase de não-verificação (FR-016); nunca renderiza "executa e respeita restrições" como sinônimo de "está correto" (FR-017)
- [ ] **T095** [US4] **TESTE OBRIGATÓRIO (Princípio II)** — escrever `tests/unit/test_report.py::test_no_correctness_claim_without_verified_assertion`. Para `assertions=[]` e para `assertions` só com `passed=False`: (a) confirmar `functional_correctness_verified is False`; (b) confirmar que o texto renderizado CONTÉM a declaração explícita de não-verificação; (c) confirmar que o texto renderizado NÃO CONTÉM nenhuma alegação de corretude sem qualificação. Teste adversário complementar, no mesmo arquivo: tentar construir `GuaranteeReport(functional_correctness_verified=True, assertions=[])` diretamente e confirmar que `extra="forbid"` rejeita com `ValidationError` — a violação da invariante deve ser estruturalmente impossível, não apenas não-testada
- [ ] **T096** [US4] Integrar `GuaranteeReport` ao nó `finalize` já existente em `graph.py` — monta o relatório a partir de `static`, `assertion_results`, `semantic` (quando presente) e `resource`; adicionar `guarantee_report: GuaranteeReport | None` a `AgentState`
- [ ] **T097** [US4] Rotular resultado de execução em dispositivo físico como "comportamento sob ruído", nunca como verificação, dentro de `render_guarantee_report` (FR-020) — implementado aqui, exercitado de fato só quando US5 rodar
- [ ] **T098** [US4] Escrever `tests/integration/test_us4_flow.py` cobrindo os 3 cenários de aceitação da US4

**Checkpoint (M4) — PARAR E REVISAR**: SC-004 garantido por T095, não por
convenção de código. Revisar antes de prosseguir para US6/US7.

---

## Phase 8: User Story 7 — Suíte de regressão operacional (P2)

**Goal**: o mantenedor executa a suíte de regressão sobre as 120 tarefas
antes de adotar qualquer mudança em prompt, corpus, modelo ou pipeline.

**Independent Test**: a suíte produz taxa de sucesso por tier com `run_id`,
seeds e versões registradas; duas execuções são comparáveis por tarefa.

**Nota de dependência**: tecnicamente independente de US3/US4 (depende só
da Phase 5, já concluída, e de US1/US2, já implementadas) — poderia rodar
em paralelo a elas. Ordenada depois na prioridade de entrega porque P1 > P2
em `spec.md`, não por dependência técnica.

- [ ] **T054** [US7] Implementar persistência JSONL append-only em `results/{run_id}/` — uma linha por (tarefa, gerador, seed); sem eixo de condição (`RunRecord.condition` removido, ver T052c); inclui veredito de cada camada e o `GuaranteeReport` (FR-025, FR-026)
- [ ] **T098b** [P] [US7] Implementar `config.yaml` e seu carregamento em `bench/runner.py` — enumera gerador(es), `task_id`s e seeds de uma rodada de regressão; fonte de verdade que T099 consulta
- [ ] **T099** [US7] **BLOQUEIO OBRIGATÓRIO (Princípio IV)** — implementar precondição em `bench/runner.py`: antes de executar qualquer tarefa da rodada, confirmar que TODAS as tarefas da configuração passaram em `bench/validate_oracles.py` (rodar a validação ou consultar seu resultado mais recente persistido). Abortar com erro explícito, **sem executar nenhuma tarefa**, se qualquer referência da rodada não estiver verificada (FR-028, SC-009)
- [ ] **T100** [P] [US7] **TESTE OBRIGATÓRIO (Princípio IV)** — escrever `tests/integration/test_runner_blocks_unverified.py`: injetar uma tarefa com oráculo deliberadamente quebrado (referência corrompida) na configuração de uma rodada; confirmar que o runner recusa executar QUALQUER tarefa da rodada — não só a quebrada — antes de tocar o sandbox
- [ ] **T059** [P] [US7] Implementar `analysis/metrics.py` — `compila@1`, `unitaria_equiv@1`, `fidelidade@1`, taxa de sucesso por tier, reportados separadamente (FR-025)
- [ ] **T059b** [US7] Excluir `status="infrastructure_error"` do denominador de todas as métricas — timeout de pool, Qdrant fora do ar ou oráculo quebrado não são falha do gerador
- [ ] **T060** [P] [US7] Implementar métricas secundárias: `iteracoes_ate_sucesso`, `depth_ratio`, `cx_ratio`, `taxa_erro_api`
- [ ] **T061** [P] [US7] Implementar métricas de custo e latência por execução resolvida — métrica operacional, não ligada a uma FR específica de v2
- [ ] **T101** [US7] Implementar comparação entre duas execuções da suíte por tarefa (não só agregado) em `analysis/metrics.py` ou novo `analysis/compare.py` (FR-027, SC-008: divergência < 5% das tarefas entre duas rodadas com mesmo código/versões)
- [ ] **T102** [US7] Executar a suíte completa uma vez e confirmar SC-007 (< 3h). Se estourar, decidir entre paralelizar por tarefa (WorkerPool já suporta isso, D1b) ou reduzir seeds, e registrar a decisão em `research.md`
- [ ] **T103** [US7] Escrever `tests/integration/test_us7_flow.py` cobrindo os 3 cenários de aceitação da US7

**Checkpoint (M6)**: suíte operacional, bloqueio do Princípio IV testado em
runtime (T100), SC-007/008/009 confirmados.

---

## Phase 9: User Story 6 — Interface (P2)

**Goal**: o usuário opera o sistema por uma interface — descreve, declara
asserções, acompanha tentativas, vê relatório de garantia e código juntos.

**Independent Test**: SC-005 — usuário sem familiaridade gera um circuito
com asserção verificada em menos de 5 minutos pela interface.

**Depende de**: US3 + US4 (a interface expõe o que as duas produzem, não
implementa lógica própria).

**Risco explícito** (`estado-e-aprendizados.md` §7): "a interface virar o
projeto". A decisão abaixo é deliberadamente mínima por causa disso.

- [ ] **T104** [US6] CLI mínima em `src/qcagent/interface/cli.py`, reaproveitando `qcagent.graph.build_graph` e os mesmos node factories de `bench/run_single.py` — **sem lógica de orquestração própria**. Uma interface web fica fora do escopo desta fase por decisão, não por esquecimento
- [ ] **T105** [US6] Usar `.stream()` do grafo compilado (não `.invoke()`) para exibir cada nó conforme executa — submissão de descrição e asserções na entrada, progresso de tentativas visível (FR-022, FR-023)
- [ ] **T106** [US6] Exibir, ao falhar e corrigir, o diagnóstico que motivou a tentativa seguinte (`CriticDecision.rationale`) ao lado de cada iteração
- [ ] **T107** [US6] Exibir código gerado e `GuaranteeReport` renderizado (T094) juntos ao final (FR-024); usuário consegue copiar os dois
- [ ] **T108** [US6] Confirmar que a CLI nunca persiste em `results/` por conta própria — toda escrita em `results/` continua vindo exclusivamente de `bench/runner.py` (US7); a interface é read-only em relação aos artefatos de regressão
- [ ] **T109** [US6] Validar manualmente SC-005 — não é testável por unidade. Registrar o resultado da validação manual em `report-notes.md`

**Checkpoint (M5)**: interface mínima funcional, SC-005 validado.

---

## Phase 10: User Story 5 — Execução em dispositivo físico (P2)

> Numerada **US5** em v2 (era `[US4]` em v1 — spec.md v2 renumerou: v2's
> US4 agora é o relatório de garantia). Conteúdo técnico preservado de v1,
> só a tag de história muda.

**Goal**: executar o circuito em simulador (sempre) e, opcionalmente, em
dispositivo físico real.

**Nota de prioridade**: P2, mas tecnicamente simples relativo a US6/US7
(reaproveita infraestrutura do simulador já existente) — pode ser
adiantada se houver folga, sem violar a ordem de prioridade de
`MIGRATION.md` (que ordena P1 antes de P2, não entre P2s).

- [ ] **T110** [US5] Expor execução em simulador com distribuição de medidas como parte da saída padrão, não só verificação interna — `finalize` roda uma execução de medição real (shots configuráveis) sobre o código final aprovado e anexa o resultado ao `GuaranteeReport`/saída (FR-018)
- [ ] **T066** [US5] Implementar submissão a IBM Quantum em `bench/hardware_runner.py` com timeout configurável e degradação graciosa (FR-019)
- [ ] **T067** [US5] Selecionar 12 artefatos T4 aprovados e submeter
- [ ] **T068** [US5] Registrar resultado medido ao lado do simulado em `results/{run_id}/hardware.jsonl`; rotular como "comportamento sob ruído", nunca "verificação" (FR-020, reaproveita T097)
- [ ] **T069** [US5] Gerar figura de degradação de fidelidade em função de `cx_count`

---

## Phase 11: Polish & Entrega

- [ ] **T070** [P] Escrever `quickstart.md` — validação end-to-end em 10 minutos
- [ ] **T071** [P] Reproduzir uma rodada arquivada a partir do `config.yaml` e verificar divergência < 5% (SC-008)
- [ ] **T072** [P] Gerar model card e datasheet do dataset
- [ ] **T073** Publicar dataset no Zenodo com DOI
- [ ] **T074** [P] Preparar release do código sob Apache 2.0, tag `v1.0`
- [ ] **T125** Consolidar o relatório final a partir de `report-notes.md` (achados F1–F5, threats to validity, measured results) e `estado-e-aprendizados.md` — a seção sobre a própria migração de escopo (por que o experimento controlado foi abandonado, e o que se aprendeu no caminho) é material do relatório, não nota de rodapé (`MIGRATION.md` §6). Substitui a antiga T075 (capítulo de análise de erros a partir de T064), removida na migração

---

## Dependencies

```
Setup (T001-T007) [DONE]
  └─▶ Foundational (T008-T016) [DONE]        ← BLOQUEIA TUDO
        ├─▶ US1 (T017-T030) [DONE]           ← MVP
        │     └─▶ US2 (T031-T042) [DONE]
        │
        ├─▶ Suíte — dados (T043-T052, T052c) [98% DONE — T051/T052/T052c pendentes]
        │     └─▶ US7 (T054, T098b-T103, T059-T061, T101-T103)  [P2]
        │
        └─▶ US3 (T081-T092)  🎯 CAMINHO CRÍTICO — SEM dependência de
              │                 Suíte-dados nem de US1/US2 além da fundação
              └─▶ US4 (T093-T098)
                    ├─▶ US6 (T104-T109)  [P2]
                    └─▶ US5 (T110, T066-T069)  [P2, depende só de US1]
                          └─▶ Polish (T070-T074, T125)
```

**Mudança estrutural em relação a v1** (registrar explicitamente, porque é
fácil de ler errado a partir do formato da árvore): em v1, "Dataset"
bloqueava a então-US3 (a matriz experimental precisava do dataset completo
antes de rodar qualquer coisa). Em v2, **US3 não depende do dataset de
forma alguma** — verificação sem referência é, por desenho, sem referência.
A Suíte-dados (Phase 5) e US7 formam um ramo paralelo, independente, que só
por causa da prioridade P1 > P2 aparece depois de US3/US4 na ordem de
entrega abaixo — não porque exista uma dependência técnica bloqueando.

Dentro de US1 (v1, inalterado): validadores (T017-T023) antes dos nós
(T024-T030). Dentro de US3: entidades (T081-T082) antes do parser
(T083-T084b) antes da integração ao grafo (T087-T089).

## Parallel Execution Examples

**Setup**: T003, T004, T005, T007 em paralelo.
**Foundational**: T009, T010, T011 em paralelo; T014 e T016 em paralelo.
**US1 validadores**: T017, T018, T020, T021, T023 em paralelo. Sequenciais: T018b→T018c, T019 depende de T018c, T022 depende de T017, T023b depende de T018c.
**US2 índice**: T035b, T036b e T038b em paralelo após T034. T033b precede T034.
**Dataset**: T044, T045, T046, T047 em paralelo — quatro tiers, quatro diretórios.
**US3**: T085 (testes) pode começar assim que T083/T084/T084b tiverem uma forma estável, mesmo que a implementação final ainda mude — escrever os casos primeiro é o ponto de T084b. T091 é paralelo ao resto de US3 (arquivo e escopo distintos).
**US7 métricas**: T059, T060, T061 em paralelo (como em v1); T098b e T100 em paralelo entre si, ambos antes de T099 depender deles.

## Implementation Strategy

**MVP já entregue**: US1+US2 (Phases 1-4) continuam válidas sob a
constituição v2.0.0 sem nenhuma mudança de código — só a moldura em torno
delas mudou.

**Novo caminho crítico**: US3, porque é reference-free por desenho e porque
"é a história que torna o produto um produto" (spec.md). Nenhum portão de
dataset ou suíte bloqueia o início do trabalho nela.

**Ordem de entrega incremental** (`MIGRATION.md` §3):
1. Phase 6 → **US3: verificação sem referência** (caminho crítico)
2. Phase 7 → **US4: relatório de garantia** (consome a saída de US3)
3. Phase 9 → US6: interface mínima [P2] (consome US3+US4)
4. Phase 8 → US7: suíte de regressão operacional [P2] (tecnicamente
   independente de US3/US4 — pode ser adiantada se a capacidade permitir)
5. Phase 10 → US5: hardware [P2] (depende só de US1, pode adiantar)
6. Phase 11 → Polish & Entrega

**Regra de parada** (nova — a de v1 dependia do piloto de custo, removido
na migração): se o escopo ameaçar crescer além das quatro histórias novas
(US3/US4/US6/US7), cortar profundidade da interface (US6) antes de cortar
rigor de verificação (US3/US4) — ver risco "escopo inflado por liberdade"
em `estado-e-aprendizados.md` §7. O produto precisa estar **pronto**, não
completo.
