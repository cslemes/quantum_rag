# Implementation Plan: Síntese verificada de circuitos quânticos assistida por IA

**Branch**: `001-qcircuit-agent` | **Data**: 2026-08-11 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification de `/specs/001-qcircuit-agent/spec.md`

## Summary

Agente em grafo de estados que gera circuitos quânticos a partir de linguagem
natural, valida cada artefato por uma cascata determinística de quatro camadas
(execução → transpilação → equivalência unitária/distribucional → recursos) e
realimenta o gerador com o diagnóstico estruturado da falha. Recuperação híbrida
sobre documentação versionada elimina a principal causa de erro do domínio —
uso de API obsoleta. A contribuição científica é a matriz de ablação que isola
a contribuição de cada componente, medida sobre um conjunto de avaliação
construído com pares canônico/perturbado para controlar contaminação de treino.

## Technical Context

**Language/Version**: Python 3.11
**Primary Dependencies**: Qiskit 1.2.4 (pinado), qiskit-aer 0.15.1 (**CPU**; variante `-gpu` opcional, ver D1), LangGraph, PennyLane (corpus secundário), Pydantic v2, qdrant-client, fastembed (BM25 esparso)
**Storage**: Qdrant 1.12 (vetores densos + esparsos na mesma coleção, com payload de versão); JSONL append-only para resultados; QPY para serialização de circuitos
**Testing**: pytest; `bench/validate_oracles.py` como portão bloqueante em CI
**Target Platform**: Linux (WSL2) — Ryzen 7 5700X, 32 GB RAM, RTX 3070 8 GB; IBM Quantum open plan (US4)
**Project Type**: Single project — biblioteca Python + harness de experimento
**Performance Goals**: latência p95 < 180 s por execução na condição completa; matriz completa (5.400 execuções) concluída em ≤ 72 h de wall-clock
**Constraints**: statevector em CPU viável até ~25 qubits; **`Operator.equiv()` tem teto real em ~12 qubits** (matriz densa 4ⁿ — ver D3b), por isso oráculos unitários acima disso usam verificação por composição; nenhum item de avaliação excede 20 qubits; o gargalo real é overhead por execução, não a simulação (ver D1b); gerador local medido em 492 tok/s de prefill e 74,7 de geração, 100% em GPU — ~20 h para o braço local (D10); `num_ctx` deve ser fixado explicitamente, o default de 4096 do Ollama trunca em silêncio (D10b); orçamento de API definido por piloto extrapolado
**Scale/Scope**: 3 geradores × 5 condições × 120 tarefas × 3 seeds = 5.400 execuções; corpus de ~15k unidades de documentação

## Constitution Check

*GATE: deve passar antes da Phase 0. Reverificar após a Phase 1.*

| Princípio | Status | Evidência no desenho |
|---|---|---|
| I. Verificação determinística | ✅ PASS | `validators/` não contém chamada a LLM. O `critic` roteia sobre erro já classificado por código determinístico; nunca emite veredito de corretude. |
| II. Reprodutibilidade | ✅ PASS | `run_id = hash(config + git SHA)`; JSONL append-only; `make eval` a partir de `config.yaml`; versões pinadas. |
| III. Ablação obrigatória | ✅ PASS | C1–C5 cobrem as quatro combinações de {RAG, loop} mais few-shot. |
| IV. Contaminação no desenho | ✅ PASS | 60 pares canônico/perturbado criados na Phase 1, antes de qualquer execução. `delta_perturbacao` é métrica de primeira classe. |
| V. Oráculos testados | ✅ PASS | `validate_oracles.py` com construção alternativa + checagem de unitariedade, bloqueante em CI. |
| VI. Resultado negativo entregável | ✅ PASS | Dataset e taxonomia de erros (§ análise qualitativa) publicáveis independentemente do sinal. |

**Resultado**: PASS — sem violações a registrar.

## Project Structure

### Documentation

```
specs/001-qcircuit-agent/
├── spec.md              # o quê e por quê
├── plan.md              # este arquivo
├── research.md           # Phase 0 — decisões técnicas
├── data-model.md         # Phase 1 — entidades e estado
├── quickstart.md         # Phase 1 — validação em 10 minutos
├── contracts/            # Phase 1 — contratos dos nós e validadores
├── checklists/
│   └── requirements.md
└── tasks.md              # Phase 2 (gerado por /speckit.tasks)
```

### Source Code

```
src/qcagent/
├── state.py                 # AgentState + entidades Pydantic
├── graph.py                 # montagem do StateGraph
├── config.py                # pydantic-settings
├── nodes/
│   ├── planner.py           # descrição → requisitos verificáveis  [LLM]
│   ├── retriever.py         # consulta híbrida versionada
│   ├── generator.py         # requisitos + trechos → código        [LLM]
│   ├── critic.py            # erro classificado → ação corretiva   [LLM]
│   └── routing.py           # arestas condicionais
├── validators/              # 100% determinístico — sem LLM
│   ├── sandbox.py           # subprocesso isolado + denylist + timeout
│   ├── static.py            # camada 1-2: execução e transpilação
│   ├── semantic.py          # camada 3: unitária / distribuição / energia
│   └── resource.py          # camada 4: profundidade, CX, largura
├── retrieval/
│   ├── ingest.py            # crawler docs + arXiv
│   ├── chunking.py          # code-aware: símbolo íntegro
│   ├── index.py             # coleção Qdrant: denso + esparso
│   └── hybrid.py            # Query API com fusão RRF nativa
├── llm/
│   ├── base.py              # interface comum
│   ├── anthropic_client.py
│   └── ollama_client.py
└── prompts/

bench/
├── schema.py                # TaskSpec
├── tasks/{t1,t2,t3,t4}/
├── oracles/
├── validate_oracles.py      # portão bloqueante
└── runner.py                # matriz experimental

analysis/{metrics.py,ablation.py,notebooks/}
results/{run_id}/
tests/{unit,integration,contract}/
```

**Structure Decision**: single project. Não há frontend nem serviço; o
entregável é uma biblioteca mais um harness reprodutível. `validators/` é
mantido fisicamente separado de `nodes/` para tornar o Princípio I verificável
por inspeção de imports — um teste de arquitetura falha se `validators/`
importar de `llm/`.

## Phase 0 — Research

Saída: `research.md`. Incógnitas a resolver:

1. **Modelo de embedding** — específico de código vs. multilíngue geral, medido
   por `recall@8` em 50 consultas sintéticas.
2. **Teto de iterações** — `MAX_ITER=5` é hipótese; validar saturação no piloto.
3. **Idioma dos prompts** — documentação é em inglês; prompt em português pode
   degradar. Testar no piloto e documentar.
4. **Gerador Fronteira B** — escolher família distinta da Fronteira A para
   controlar efeito de família.
5. **Granularidade de chunking** — símbolo inteiro vs. divisão por exemplo com
   assinatura replicada no cabeçalho.
6. **Estratégia de perturbação** — quais das cinco famílias de perturbação
   produzem queda mensurável sem tornar o item impossível.

## Phase 1 — Design

Saídas: `data-model.md`, `contracts/`, `quickstart.md`.

### Grafo

```
[spec] → planner → retriever → generator → static_check
             │          ▲                         │
             │          │                         ▼
             │          │                  semantic_check
             │          │                         │
             │       critic ◀───────────── resource_check
             │          │                         │
             └──────────┘                         ▼
      (retry_retrieval | retry_generation |    [ done ]
       optimize | abort)
             │
             ▼ (entidade faltante | restrição contraditória | n_qubits > teto)
      [ rejected_input ]
```

`planner` pode encerrar o grafo diretamente em `rejected_input`, sem passar
por `retriever`/`generator`/`critic` — ver FR-030, FR-031 e T024b.

### Contratos dos nós

| Nó | Entrada | Saída | LLM |
|---|---|---|---|
| `planner` | `spec` | `requirements` \| `status="rejected_input"` | sim |
| `retriever` | `spec`, `requirements`, `retrieval_hint` | `chunks` | não |
| `generator` | `requirements`, `chunks`, últimos 2 erros | `code` | sim |
| `static_check` | `code` | `StaticResult` | não |
| `semantic_check` | `code`, `oracle` | `SemanticResult` | não |
| `resource_check` | `code`, `coupling_map` | `ResourceResult` | não |
| `critic` | estado | `CriticDecision` | sim |

### Roteamento do critic

| Sinal | Ação | Justificativa |
|---|---|---|
| Símbolo obsoleto, `ImportError`, `AttributeError` | `retry_retrieval` | falta de contexto de API → reconsultar com hint de versão |
| Falha de sintaxe, transpilação, qubit fora de faixa | `retry_generation` | erro local → regerar com traceback |
| Unitária diverge, fidelidade < tolerância | `retry_generation` | erro conceitual → regerar com diff |
| Correto, `depth_ratio > 2.0` | `optimize` | regerar pedindo redução de CX |
| `iteration >= MAX_ITER` | `abort` | registrar falha; não mascarar com força bruta |

Falha transitória do provedor externo (rate limit, 5xx, timeout) **não passa
pelo `critic`** — não é `error_type` de código gerado. É tratada na camada do
cliente LLM (`llm/base.py`): retry com backoff exponencial limitado e, se
persistir, a execução é marcada `status="infrastructure_error"` e excluída do
denominador das métricas de corretude, sem abortar a matriz (spec, edge case
de infraestrutura — ver `## Clarifications`).

### Armadilhas endereçadas no desenho

- **Fase global**: usar `Operator.equiv()`; comparação direta de matrizes falha.
- **Teto de `Operator()`**: a matriz densa é 4ⁿ e `equiv()` precisa de duas
  simultaneamente — 14 qubits já estouram 32 GB. Acima de 12 qubits, usar
  verificação por composição com a inversa (custo 2ⁿ). Ver D3b e
  `contracts/validators.md`.
- **Endianness**: Qiskit é little-endian. Verificar também contra referência com
  bits invertidos e reportar `EndiannessSwap` como categoria própria (FR-005).
- **Transpilação assimétrica**: gerado e referência passam pelos mesmos
  parâmetros. Comparar transpilado contra não-transpilado é erro metodológico.
- **Truncagem silenciosa de contexto**: o default de 4096 do Ollama corta o
  prompt sem erro nem log. Atinge seletivamente C5 (a condição com RAG) e
  deixaria H1 e H3 sem evidência. Fixar `num_ctx` por requisição e contar
  tokens antes de enviar. Ver D10b.
- **Overhead por execução domina**: circuitos de 2–10 qubits simulam em
  milissegundos; o custo real é spawn de subprocesso + `import qiskit` (1–2 s).
  Com até 27.000 execuções, isso são 8–15 h só em imports. Usar pool de workers
  pré-aquecidos, reciclados a cada N execuções. Ver D1b.

### Matriz experimental

| # | Condição | RAG | Loop | Hipótese |
|---|---|---|---|---|
| C1 | Zero-shot | ✗ | ✗ | baseline |
| C2 | Few-shot | ✗ | ✗ | valor de exemplos |
| C3 | RAG puro | ✓ | ✗ | H1 |
| C4 | Loop puro | ✗ | ✓ | H2 |
| C5 | Completo | ✓ | ✓ | H3, H4 |

Geradores: Fronteira A (API), Fronteira B (API), Local (Qwen2.5-Coder 7B Q4_K_M
via Ollama no RTX 3070).

**Retomada**: `bench/runner.py` DEVE ser resumível (FR-029) — antes de
disparar uma combinação (gerador, condição, tarefa, seed), verifica se já
existe `RunRecord` persistido para essa chave em `results/{run_id}/` e pula se
sim. Necessário porque a rodada completa leva até 72h de wall-clock e uma
interrupção não pode forçar reexecução integral, sob risco real de orçamento
(ver Assumptions do spec).

**Post-Design Constitution Check**: ✅ PASS — o desenho não introduz LLM em
caminho de veredito; `results/` permanece append-only; C3 e C4 continuam
obrigatórias.

## Complexity Tracking

Nenhuma violação constitucional a justificar.

Complexidades deliberadas, aceitas com razão:

| Decisão | Custo | Por que a alternativa mais simples é insuficiente |
|---|---|---|
| Índice híbrido esparso + denso | serviço dedicado a mais no compose | busca densa confunde identificadores próximos (`RZGate` vs `RXGate`), que é exatamente o caso crítico. Com Qdrant o custo cai a um serviço e uma coleção — os dois vetores são nomeados no mesmo ponto |
| Chunking code-aware | parser dedicado por fonte | chunking por janela separa assinatura do exemplo e destrói o valor da recuperação |
| Pares canônico/perturbado | dobra o custo de curadoria | sem isso, memorização é hipótese alternativa não descartada e o resultado é indefensável |
| Execução em subprocesso | overhead por execução | Princípio constitucional de isolamento; contêiner efêmero seria mais seguro mas inviável em 5.400 execuções |

## Milestones

| Marco | Portão de saída |
|---|---|
| M0 — Ambiente | `make test` verde, versões pinadas |
| M1 — Recuperação | `recall@8 ≥ 0.85` em consultas sintéticas |
| M2 — Dataset | `validate_oracles.py` 100% verde · **congelamento de escopo** |
| M3 — Agente | US1 + US2 end-to-end; piloto de custo aprovado |
| M4 — Experimento | matriz completa em `results/`; US4 tentada |
| M5 — Análise | ablação, taxonomia com κ ≥ 0,70, figuras |
| M6 — Entrega | dissertação, release do código, dataset com DOI |
