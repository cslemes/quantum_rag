# Tasks: Síntese verificada de circuitos quânticos assistida por IA

**Input**: Documentos de desenho em `/specs/001-qcircuit-agent/`
**Prerequisites**: `plan.md` (obrigatório), `spec.md` (obrigatório), `research.md`, `data-model.md`

**Tests**: incluídos — o Princípio V da constituição exige verificação dos
próprios oráculos, e o Princípio I exige teste de arquitetura que impeça LLM em
caminho de veredito. Testes de UI/integração amplos ficam fora.

**Organization**: tarefas agrupadas por user story. Cada grupo é
independentemente implementável e testável.

**Convenções**
- `[P]` — pode rodar em paralelo (arquivos distintos, sem dependência)
- `[USn]` — história de usuário a que pertence
- Caminhos de arquivo exatos nas descrições

---

## Phase 1: Setup

**Purpose**: ambiente reprodutível e esqueleto do projeto.

- [X] **T001** Criar estrutura de diretórios conforme `plan.md` (`src/qcagent/`, `bench/`, `analysis/`, `tests/`, `results/`)
- [X] **T002** Criar `pyproject.toml` com `uv`, Python 3.11, e **versões exatas** `qiskit==1.2.4`, `qiskit-aer==0.15.1` (CPU). Declarar `qiskit-aer-gpu` como extra opcional `[gpu]`, não como dependência padrão (D1)
- [X] **T003** [P] Criar `Dockerfile` com base CUDA 12.1 e `docker-compose.yml` (app + `qdrant/qdrant:v1.12.x` com tag fixa + ollama), volume persistente para o storage do Qdrant
- [X] **T004** [P] Configurar `ruff` + `mypy` + `pre-commit` em `.pre-commit-config.yaml`
- [X] **T005** [P] Criar `Makefile` com alvos `index`, `eval`, `report`, `test`
- [X] **T006** Implementar `src/qcagent/validators/simulator.py` com `make_simulator` (CPU por padrão, GPU acima de `GPU_THRESHOLD_QUBITS=18`) conforme [`contracts/validators.md`](./contracts/validators.md)
- [X] **T006b** [P] Escrever `tests/smoke/bench_backend.py` — cronometrar CPU vs GPU em 5, 10, 15, 18, 20 qubits e **confirmar empiricamente o limiar**; ajustar a constante com o resultado medido
- [X] **T007** [P] Criar `.env.example` e `src/qcagent/config.py` com `pydantic-settings`

**Checkpoint (M0)**: `make test` verde, versões pinadas registradas.

---

## Phase 2: Foundational (bloqueia todas as histórias)

**Purpose**: infraestrutura que qualquer história precisa. Nenhum trabalho de
história começa antes desta fase concluir.

- [X] **T008** Implementar entidades Pydantic em `src/qcagent/state.py` conforme `data-model.md` (`Requirement`, `Chunk`, `ErrorRecord`, `StaticResult`, `SemanticResult`, `ResourceResult`, `CriticDecision`, `AgentState`)
- [X] **T009** [P] Implementar `src/qcagent/llm/base.py` — interface comum de gerador com contagem de tokens e custo
- [X] **T010** [P] Implementar `src/qcagent/llm/anthropic_client.py`
- [X] **T011** [P] Implementar `src/qcagent/llm/ollama_client.py` com `num_ctx` **explícito em cada requisição** (16384 inicial), nunca herdado do default do servidor (D10b)
- [X] **T011b** [US1] Implementar guarda anti-truncagem em `ollama_client.py` — contar tokens do prompt antes de enviar e levantar `ContextOverflowError` se exceder `num_ctx`. Truncagem silenciosa atinge seletivamente C5 e invalidaria H1/H3 sem deixar rastro
- [X] **T011c** [P] Registrar `num_ctx` efetivo e contagem de tokens de entrada no `RunRecord` — o valor precisa estar no resultado, não só na configuração
- [X] **T012** Implementar cache de resposta por `hash(prompt + modelo + seed)` em `src/qcagent/llm/base.py` (FR-028)
- [X] **T012b** Implementar retry com backoff exponencial limitado em `src/qcagent/llm/base.py` para falhas transitórias do provedor (rate limit, 5xx, timeout). Esgotadas as tentativas, propagar como `status="infrastructure_error"` sem passar pelo `critic` — não é erro de código gerado (edge case de infraestrutura, spec). Mesmo arquivo de T012, sequencial
- [X] **T013** Implementar `WorkerPool` em `src/qcagent/validators/sandbox.py` — processos pré-aquecidos (qiskit já importado), reciclagem a cada N execuções, timeout que mata e substitui o worker, denylist, serialização QPY (FR-025, D1b)
- [X] **T013b** [P] Instrumentar `SandboxResult` com `wall_time_s` e `exec_time_s` separados — latência sem essa separação mede infraestrutura, não o sistema sob teste
- [X] **T014** [P] Escrever `tests/unit/test_sandbox.py` cobrindo timeout, denylist e código que não define `qc`
- [X] **T015** Implementar logging estruturado e `run_id = hash(config + git SHA + timestamp)` em `src/qcagent/config.py` (FR-026)
- [X] **T015b** [P] Implementar coleta de telemetria de GPU em `src/qcagent/llm/ollama_client.py` — `memory.used` via `nvidia-smi` e a string `PROCESSOR` do `ollama ps`, gravadas no `RunRecord` (D10c)
- [X] **T015c** [US3] Abortar a execução se `PROCESSOR` não for "100% GPU" no braço local — melhor falhar alto que contaminar a métrica de latência em silêncio
- [X] **T016** [P] Escrever `tests/contract/test_architecture.py` — falha se `src/qcagent/validators/` importar de `src/qcagent/llm/` (Princípio I)

**Checkpoint**: fundação pronta — histórias podem começar.

---

## Phase 3: User Story 1 — Circuito verificado a partir de descrição (P1) 🎯 MVP

**Goal**: entregar circuito com veredito verificável, corrigindo-se quando falha.

**Independent Test**: 20 descrições com referência conhecida → veredito correto
para todas, incluindo os vereditos de falha.

### Validadores (o coração determinístico)

- [X] **T017** [P] [US1] Implementar `src/qcagent/validators/static.py` — camadas 1-2: `ast.parse`, execução isolada, `transpile`; tabela `DEPRECATED_SYMBOLS` produzindo `error_type="DeprecatedAPI"` (FR-002)
- [X] **T018** [P] [US1] Implementar `_check_exact` em `src/qcagent/validators/semantic.py` com `Operator.equiv()` — tolerância a fase global, teto de 12 qubits (FR-004)
- [X] **T018b** [US1] Implementar `_check_by_composition` — `generated.compose(reference.inverse())` com 5 estados Haar-aleatórios, custo 2ⁿ (D3b)
- [X] **T018c** [US1] Implementar o despacho `check_unitary` por porte e registrar `verification_method` no `SemanticResult`
- [X] **T019** [US1] Adicionar detecção de inversão de ordenação em `semantic.py` — verificar contra referência com bits invertidos, reportar `EndiannessSwap` (FR-005)
- [X] **T020** [P] [US1] Implementar `check_distribution` (fidelidade de Hellinger + TVD, média sobre 3 seeds) em `semantic.py`
- [X] **T021** [P] [US1] Implementar `check_energy` para oráculos de VQE em `semantic.py`
- [X] **T022** [US1] Implementar `src/qcagent/validators/resource.py` — transpilar gerado **e** referência com `opt_level`, `coupling_map` e `seed_transpiler` idênticos; `depth_ratio`, `cx_ratio` (FR-006)
- [X] **T023** [P] [US1] Escrever `tests/unit/test_semantic.py` com casos-armadilha: fase global, ordenação invertida, dimensões incompatíveis
- [X] **T023b** [US1] **Teste-chave de D3b**: rodar os caminhos exato e por composição sobre o mesmo par de circuitos de 8 qubits e exigir concordância — garante que a troca de método acima de 12 qubits não introduz viés

### Nós e grafo

- [X] **T024** [P] [US1] Escrever prompt e implementar `src/qcagent/nodes/planner.py` — descrição → `list[Requirement]`
- [X] **T024b** [US1] Implementar checagem de não-satisfazibilidade em `planner.py` — sinalizar `status="rejected_input"` e encerrar o grafo antes de `retriever`/`generator` quando os requisitos extraídos indicam entidade faltante, restrição contraditória, ou `n_qubits` acima do teto de simulação configurado. Ambiguidade não detectável nesta etapa segue o fluxo normal (FR-030, FR-031). Mesmo arquivo de T024, sequencial
- [X] **T025** [P] [US1] Escrever prompt e implementar `src/qcagent/nodes/generator.py` — injeta apenas os 2 últimos erros no contexto
- [X] **T026** [US1] Implementar `src/qcagent/nodes/critic.py` — roteamento por `error_type` conforme tabela do `plan.md` (FR-007)
- [X] **T027** [US1] Implementar `src/qcagent/nodes/routing.py` — arestas condicionais e corte em `MAX_ITER` com status de falha explícito (FR-008)
- [X] **T028** [US1] Montar `src/qcagent/graph.py` com reducers `add` em `error_history` e `trace`; incluir a aresta condicional de `planner` direto para `[ rejected_input ]` quando T024b sinaliza a recusa, pulando `retriever`/`generator`/`critic` (FR-009, FR-030, FR-031)
- [X] **T029** [US1] Adicionar `interrupt_before` opcional entre `semantic_check` e `resource_check`, desligado por padrão (FR-010)
- [X] **T030** [US1] Escrever `tests/integration/test_us1_flow.py` cobrindo os 4 cenários de aceitação da US1

**Checkpoint**: US1 entregável isoladamente. Sistema já é útil sem RAG.

---

## Phase 4: User Story 2 — Evitar interfaces obsoletas (P2)

**Goal**: eliminar uso de API depreciada via recuperação versionada.

**Independent Test**: comparar taxa de construção obsoleta com e sem recuperação.

- [X] **T031** [P] [US2] Implementar `src/qcagent/retrieval/ingest.py` — coleta de docs Qiskit, guias de migração, docs PennyLane e abstracts do arXiv quant-ph
- [X] **T032** [US2] Implementar `src/qcagent/retrieval/chunking.py` — chunking por símbolo; assinatura + docstring + exemplo permanecem íntegros (FR-012)
- [X] **T033** [US2] Adicionar metadados `library_version` e `deprecated` na ingestão; marcar símbolos dos guias de migração (FR-011)
- [X] **T033b** [US2] Confirmar a API do `qdrant-client` na versão fixada em T003 contra `contracts/retrieval.md`; corrigir o contrato antes de implementar T034
- [X] **T034** [US2] Implementar `ensure_collection` e `point_id` em `src/qcagent/retrieval/index.py` conforme [`contracts/retrieval.md`](./contracts/retrieval.md) — vetores nomeados `dense` (cosine) e `sparse` (`Modifier.IDF`) (FR-013)
- [X] **T035** [US2] Implementar `_create_payload_indexes` — `library_version` (KEYWORD), `deprecated` (BOOL), `source` (KEYWORD). Sem isso o filtro vira pós-filtro e o recall despenca nas consultas filtradas por versão
- [X] **T035b** [P] [US2] Implementar `upsert_chunks` (lote, `wait=True`) e teste de idempotência em `tests/unit/test_index.py` — reingestão não altera `point_count`
- [X] **T036** [US2] Implementar `search` e `build_filter` em `src/qcagent/retrieval/hybrid.py` — Query API com `prefetch` denso + esparso, filtro em **cada ramo**, `FusionQuery(RRF)`, `limit=8`
- [X] **T036b** [P] [US2] Implementar snapshot da coleção em `src/qcagent/retrieval/index.py` (`create_snapshot`) e registrar o hash do snapshot no `run_id` — reprodutibilidade do corpus (Princípio II)
- [X] **T037** [US2] Implementar `RetrievalBundle.to_prompt_context` — chunk `deprecated=True` renderizado com marcação de proibição e o campo `replacement` visível, não omitido (FR-014)
- [X] **T038** [US2] Implementar `split_by_register` — separar `api_chunks` de `paper_chunks` e entregar em blocos distinguíveis ao gerador (FR-015)
- [X] **T038b** [P] [US2] Implementar o `Embedder` Protocol em `src/qcagent/retrieval/embedding.py` com métodos separados para documento e consulta (prefixos assimétricos)
- [X] **T039** [US2] Implementar `src/qcagent/nodes/retriever.py` e conectar ao grafo, incluindo `retry_retrieval` do critic
- [X] **T040** [US2] Criar 50 consultas sintéticas com chunk-alvo conhecido em `tests/retrieval/queries.jsonl`
- [X] **T040b** [US2] Escrever teste do caso crítico em `tests/unit/test_hybrid.py` — consulta contendo `RZGate` traz o chunk de `RZGate` acima do de `RXGate`. Se falhar, o ramo esparso não contribui: verificar o modifier IDF antes de trocar o modelo denso
- [X] **T041** [US2] Escrever `analysis/eval_retrieval.py` — `recall@8` e MRR; **portão M1: recall@8 ≥ 0.85**
- [X] **T042** [US2] Escrever `tests/integration/test_us2_flow.py` cobrindo os 3 cenários de aceitação da US2

**Checkpoint (M1)**: recuperação validada isoladamente antes de influenciar métricas de geração.

---

## Phase 5: Dataset de avaliação (habilita US3)

**Purpose**: sem oráculos verificados não existe experimento.

- [X] **T043** [P] Implementar `bench/schema.py` — `TaskSpec` conforme `data-model.md`, incluindo `oracle_kind="statevector"` (D3c)
- [X] **T044** [P] Criar 18 tarefas canônicas T1 em `bench/tasks/t1_primitives/` — Bell×3, GHZ×3, W-state×3, QFT×3, Deutsch-Jozsa×3 (todas `statevector` exceto QFT em `unitary`), Aritmética booleana reversível×3 (`unitary`, flat — ver D3d). **Teleporte descartado do conjunto canônico** (D3d): nem `unitary` nem `statevector` se encaixa sem admitir respostas incorretas ou exigir uma convenção oráculo↔gerador que não existe hoje; oráculo de fidelidade de canal registrado como trabalho futuro, não implementado
- [X] **T045** [P] Criar 18 tarefas canônicas T2 em `bench/tasks/t2_algorithms/` — Bernstein-Vazirani×3, Simon×3, Grover×3, QPE×3, QAOA MaxCut×3 (todas `statevector`, D3e — cada família embute um oráculo/parâmetro fixo por tarefa, nenhuma é transformação geral), VQE H₂×3 (`energy`, D3e-3 — Hamiltoniano de O'Malley et al. 2016 Table I, lido e citado, não recitado de memória). QAOA e VQE H₂ têm parâmetros (gamma/beta, theta) fixos no enunciado — mede fidelidade de construção do ansatz, não capacidade de otimização (D3e/D3e-3), registrado para a análise de erro (T064) não confundir os dois
- [X] **T046** [P] Criar 12 tarefas canônicas T3 em `bench/tasks/t3_formulation/` — Ising MaxCut ponderado×3, interação multi-corpo (3/4 qubits)×3, campo+acoplamento×3, QUBO→Ising×3 (todas `unitary`, D3f — Hamiltonianos diagonais, sem preocupação de flatness pois nenhum qubit é ancila). Terceira armadilha de convenção não declarada encontrada (D3f): a substituição QUBO→Ising `x_i=(1-z_i)/2` vs. `x_i=(1+z_i)/2` são ambas convenções padrão de sinal oposto — declarada explicitamente em cada enunciado `qubo_ising_*`
- [X] **T047** [P] Criar 12 tarefas canônicas T4 em `bench/tasks/t4_hardware/` — GHZ sobre subconjunto de qubits×4, Ising ponderado×4, Z-string multi-corpo×2, campo+acoplamento×2, todas com `coupling_map="linear_5"` (única topologia real implementada — `heavy_hex_27` continua não implementado, não fabricado). `oracle_kind="resource"` verificado e confirmado SEM despacho em `graph.py` — T4 usa `statevector`/`unitary` (mesmo que T1-T3) + `coupling_map` não-nulo, já suficiente porque `resource_check` já é ortogonal a `oracle_kind` (D3h). Referência de profundidade: construção "óbvia" não otimizada à mão, defensável porque o critério de aprovação (`depth_ratio <= max_depth_ratio`) é um limite superior — uma resposta melhor que a referência nunca reprova (D3h). Gap encontrado: `TaskSpec.max_depth_ratio` nunca é lido por `make_resource_check_node` (sempre usa o default 2.0 de `check_resources`) — registrado para corrigir antes de T053, não corrigido aqui
- [ ] **T048** Criar as 60 variantes perturbadas pareadas, uma por canônica, com `base_task_id` preenchido (FR-017)
- [X] **T049** Construir oráculos em `bench/oracles/` — **construção independente**, não derivada do enunciado. Para tarefas `oracle_kind="statevector"`, o enunciado deve pedir apenas o estado de saída — se ele restringe a transformação, é `"unitary"`, não `"statevector"` (D3c). Para tarefas de circuito reversível `oracle_kind="unitary"`, o enunciado deve declarar a restrição de flatness (D3d). Para qualquer tarefa cujo oráculo seja MAIS específico do que "qualquer implementação correta" (ex.: Simon exige uma função exata; QAOA/VQE exigem parâmetros exatos; QUBO→Ising exige a convenção de sinal da substituição), a restrição extra tem que estar no enunciado, não só no oráculo (D3e/D3f/D3g) — senão uma resposta correta pode ser rejeitada por um critério nunca comunicado; padrão registrado como resultado metodológico próprio (D3g), não só detalhe de processo. Para `oracle_kind="energy"` sem backend de química disponível, usar coeficientes de uma fonte publicada LIDA e citada (D3e-3) — nunca recitados de memória. Para tarefas com `coupling_map` não-nulo (T4), a referência é uma construção "óbvia" não otimizada à mão — defensável porque o critério de aprovação é um limite superior, não igualdade (D3h). **18/18 T1 + 18/18 T2 + 12/12 T3 + 12/12 T4 feitos** — dataset canônico completo (`build_t1_primitives.py`, `build_t2_algorithms.py`, `build_t2_vqe_h2.py`, `build_t3_formulation.py`, `build_t4_hardware.py`)
- [X] **T050** Implementar `bench/validate_oracles.py` — unitariedade, construção alternativa, cross-check com biblioteca, sanity em 3 seeds (FR-018). Passando para os 60 oráculos canônicos existentes. `SANITY_FIDELITY_MIN=0.98` calibrado por Monte Carlo contra ruído de amostragem, não contra corretude de construção (garantida exatamente pelas checagens 1-2). A checagem de sanidade usa design de round-trip sempre que a distribuição-alvo (derivada da alternativa) tem probabilidade máxima abaixo de `PEAKEDNESS_THRESHOLD=0.9` — generalização do achado do QFT (D3d) para qualquer oráculo com distribuição espalhada, não só `oracle_kind="unitary"` (D3e). Um bug real do Aer (`StatePreparation(...).inverse()` derruba o processo com segfault via `transpile()`+`sim.run()`) foi encontrado e corrigido nesse processo (D3e). `oracle_kind="energy"` ganhou seu próprio conjunto de 4 checagens (`validate_energy_oracle`) — Hamiltoniano não é um circuito (D3e-3). T3's `_alt_diagonal_ising` cobre as 4 famílias de formulação com um único alternativo fechado, reaproveitado em T4 (D3f/D3h). `resource.py` ganhou cobertura de teste própria (`tests/unit/test_resource.py`, zero antes desta sessão) para a disciplina de transpilação simétrica que T4 é o primeiro tier a exercitar de verdade (D3h)
- [ ] **T051** Adicionar `validate_oracles.py` como job **bloqueante** no CI (`.github/workflows/oracles.yml`) — dataset canônico completo (T1-T4), agora o ponto natural para fazer isso
- [ ] **T052** Validar tetos de porte na ingestão do dataset: `n_qubits <= 20` para toda tarefa **e** `n_qubits <= 13` quando `oracle_kind="unitary"` (D3b). Rejeitar na entrada, nunca durante a execução

**Checkpoint (M2)**: 100% dos oráculos verdes. **🔒 CONGELAMENTO DE ESCOPO** — dataset e conjunto de geradores imutáveis a partir daqui.

---

## Phase 6: User Story 3 — Medir se o sistema melhora o resultado (P3)

**Goal**: produzir as métricas que sustentam ou refutam as hipóteses.

**Independent Test**: relatório contém todas as métricas primárias por
combinação gerador × condição, com variação entre seeds.

- [ ] **T052b** [US3] Definir o schema de `config.yaml` e implementar seu carregamento em `bench/runner.py` — enumera geradores, condições, `task_id`s e seeds de uma rodada; é a fonte de verdade que T054b consulta para saber quais combinações uma rodada deveria conter (FR-027)
- [ ] **T053** [US3] Implementar as condições C1–C5 como flags de configuração em `bench/runner.py` (FR-020)
- [ ] **T054** [US3] Implementar persistência JSONL append-only em `results/{run_id}/` com entrada, saída, veredito, tentativas e custo (FR-019)
- [ ] **T054b** [US3] Implementar retomada em `bench/runner.py` — antes de disparar uma combinação (gerador, condição, tarefa, seed), checar se já existe `RunRecord` persistido para essa chave em `results/{run_id}/` e pular se existir (FR-029). Necessário porque a matriz leva até 72h e uma interrupção não pode forçar reexecução integral
- [ ] **T055** [US3] **Piloto de custo** — 10 tarefas × 5 condições × 3 geradores; extrapolar e aprovar orçamento antes de liberar a matriz
- [ ] **T055b** [US3] Medir VRAM real do KV cache a 16K com `ollama ps` após chamada de contexto realista; ajustar `num_ctx` se estourar os 8 GB (D10b)
- [ ] **T055c** [US3] Documentar o protocolo de execução do braço local: desktop fechado, `nvidia-smi` antes e depois, verificação de 100% GPU (D10c)
- [ ] **T056** [US3] Validar saturação de `MAX_ITER` com os dados do piloto; ajustar se 3 já saturar
- [ ] **T057** [US3] Decidir idioma dos prompts com base no piloto e registrar a decisão em `research.md`
- [ ] **T058** [US3] Executar a matriz completa: 3 × 5 × 120 × 3 = 5.400 execuções
- [ ] **T059** [P] [US3] Implementar `analysis/metrics.py` — `compila@1`, `unitaria_equiv@1`, `fidelidade@1` reportados **separadamente** (FR-021)
- [ ] **T059b** [US3] Excluir `status="infrastructure_error"` do denominador de todas as métricas — timeout de pool, Qdrant fora do ar ou oráculo quebrado não são falha do gerador
- [ ] **T059c** [P] [US3] Segmentar `unitaria_equiv@1` por `verification_method` — verificar que exato e composição não divergem sistematicamente (D3b)
- [ ] **T060** [P] [US3] Implementar métricas secundárias: `iteracoes_ate_sucesso`, `depth_ratio`, `cx_ratio`, `taxa_erro_api`
- [ ] **T061** [P] [US3] Implementar métricas de custo e latência por execução resolvida (FR-022)
- [ ] **T062** [US3] Implementar `analysis/ablation.py` — atribuição de ganho por componente com variação entre seeds (SC-008)
- [ ] **T063** [US3] Implementar `delta_perturbacao` por gerador e condição (FR-023)
- [ ] **T064** [US3] Amostrar 150 falhas estratificadas e classificar pela taxonomia fechada; dupla anotação em 20%, calcular Cohen's κ. Discordâncias entre os dois anotadores vão a um terceiro anotador independente, que decide por maioria (FR-024)
- [ ] **T065** [US3] Escrever `tests/integration/test_us3_report.py` cobrindo os 4 cenários de aceitação da US3

**Checkpoint (M4/M5)**: hipóteses respondidas com evidência.

---

## Phase 7: User Story 4 — Execução em dispositivo físico (P4, opcional)

**Goal**: fechar o ciclo até hardware real.

⚠️ **Iniciar na semana 9.** Fila do plano aberto é imprevisível.

- [ ] **T066** [US4] Implementar submissão a IBM Quantum em `bench/hardware_runner.py` com timeout configurável e degradação graciosa (cenário 2 da US4)
- [ ] **T067** [US4] Selecionar 12 artefatos T4 aprovados e submeter
- [ ] **T068** [US4] Registrar resultado medido ao lado do simulado em `results/{run_id}/hardware.jsonl`
- [ ] **T069** [US4] Gerar figura de degradação de fidelidade em função de `cx_count`

---

## Phase 8: Polish & Entrega

- [ ] **T070** [P] Escrever `quickstart.md` — validação end-to-end em 10 minutos
- [ ] **T071** [P] Reproduzir uma rodada arquivada a partir do `config.yaml` e verificar divergência < 2 p.p. (SC-010)
- [ ] **T072** [P] Gerar model card e datasheet do dataset
- [ ] **T073** Publicar dataset no Zenodo com DOI
- [ ] **T074** [P] Preparar release do código sob Apache 2.0, tag `v1.0`
- [ ] **T075** Escrever capítulo de análise qualitativa de erros a partir de T064

---

## Phase 9: User Story 6 — Demonstração interativa para a defesa (P6, opcional)

**Goal**: mostrar o sistema funcionando ao vivo — descrição entra, geração
acontece, os quatro vereditos aparecem, o laço de correção é visível quando
falha.

⚠️ **Iniciar somente após M5.** Condicional a tempo restante — se não
acontecer, nada na dissertação fica enfraquecido. Não deve consumir tempo
antes que a matriz experimental esteja completa.

- [ ] **T076** [P] [US6] Implementar `demo/run_demo.py` reaproveitando `qcagent.graph.build_graph` e os mesmos node factories já usados em `bench/run_single.py` — nenhuma lógica de orquestração própria. Usa `.stream()` do grafo compilado (em vez de `.invoke()`) para exibir cada nó conforme executa, não só o resultado final
- [ ] **T077** [US6] Exibir, a cada iteração, o código gerado e os quatro vereditos de camada (static/semantic/resource/critic) conforme produzidos pelo `.stream()` (cenário 1 da aceitação da US6)
- [ ] **T078** [US6] Exibir, quando uma tentativa falha e é corrigida, o diagnóstico (`CriticDecision.rationale` e o hint) que motivou a tentativa seguinte, ao lado de cada iteração (cenário 2 da aceitação da US6)
- [ ] **T079** [US6] Ao esgotar `MAX_ITER`, exibir o status de falha explícito do grafo (`failed_static`/`failed_semantic`/`aborted`) — nunca a última tentativa apresentada como se fosse um resultado aprovado (cenário 3 da aceitação da US6)
- [ ] **T080** [US6] Confirmar que `demo/run_demo.py` nunca grava em `results/` — a sessão de demonstração não persiste `RunRecord` algum; execução é read-only em relação aos artefatos experimentais

**Checkpoint**: demonstração ao vivo funcional, reaproveitando o grafo real sem duplicar orquestração; nenhuma escrita em `results/`.

---

## Dependencies

```
Setup (T001-T007)
  └─▶ Foundational (T008-T016)   ← BLOQUEIA TUDO
        ├─▶ US1 (T017-T030)      ← MVP, entregável sozinho
        │     └─▶ US2 (T031-T042)
        │           └─▶ Dataset (T043-T052) 🔒 congelamento
        │                 └─▶ US3 (T052b, T053-T065)
        │                       ├─▶ US4 (T066-T069)  [opcional]
        │                       └─▶ Polish (T070-T075)
        │                             └─▶ US6 (T076-T080)  [opcional, pós-M5]
```

Dentro da US1: validadores (T017-T023) antes dos nós (T024-T030) — o `critic`
roteia sobre `error_type`, que só existe depois dos validadores.

## Parallel Execution Examples

**Setup**: T003, T004, T005, T007 em paralelo.
**Foundational**: T009, T010, T011 em paralelo; T014 e T016 em paralelo.
**US1 validadores**: T017, T018, T020, T021, T023 em paralelo. Sequenciais: T018b→T018c (mesmo arquivo), T019 depende de T018c, T022 depende de T017, T023b depende de T018c.
**US2 índice**: T035b, T036b e T038b em paralelo após T034 (T035 e T036 tocam os mesmos arquivos e são sequenciais). T033b precede T034 — confirmar a API antes de escrever contra ela.
**Dataset**: T044, T045, T046, T047 em paralelo — quatro tiers, quatro diretórios.
**Métricas**: T059, T060, T061 em paralelo.

## Implementation Strategy

**MVP primeiro**: parar após a Phase 3. O sistema já gera circuitos verificados
e é demonstrável. Tudo depois é incremento mensurável.

**Ordem de entrega incremental**:
1. Phase 1-2 → fundação
2. Phase 3 → **US1: MVP demonstrável**
3. Phase 4 → **US2: qualidade de geração** (validar isoladamente antes de misturar)
4. Phase 5 → dataset (portão de congelamento)
5. Phase 6 → **US3: a contribuição científica**
6. Phase 7-8 → opcional e entrega

**Regra de parada**: se o orçamento do piloto (T055) estourar a projeção,
reduzir seeds de 3 para 2 antes de reduzir tarefas — perde-se precisão do
intervalo, não cobertura do dataset.
