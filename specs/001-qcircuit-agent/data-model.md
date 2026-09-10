# Data Model: qcircuit-agent

**Feature**: `001-qcircuit-agent` | **Data**: 2026-08-11
**Fonte**: Key Entities de [spec.md](./spec.md)

---

## Estado do grafo

```python
# src/qcagent/state.py
from typing import Annotated, Literal, TypedDict
from operator import add
from pydantic import BaseModel, Field


class Requirement(BaseModel):
    """Requisito verificável extraído pelo planner. Vira o contrato do critic."""
    id: str
    kind: Literal["n_qubits", "gate_set", "property", "resource", "output_format"]
    description: str
    value: str | int | list[str] | None = None


class Chunk(BaseModel):
    doc_id: str
    text: str
    source: Literal["qiskit_api", "pennylane_api", "arxiv", "migration_guide"]
    library_version: str | None = None
    deprecated: bool = False          # FR-014: rotulado, não omitido
    replacement: str | None = None    # o que usar no lugar
    score: float


class ErrorRecord(BaseModel):
    iteration: int
    stage: Literal["static", "semantic", "resource"]
    error_type: str                   # taxonomia fechada — ver abaixo
    message: str                      # traceback truncado ou diff formatado
    payload: dict = Field(default_factory=dict)


class StaticResult(BaseModel):
    parsed: bool
    executed: bool
    transpiled: bool
    circuit_qpy: bytes | None = None
    error: ErrorRecord | None = None


class SemanticResult(BaseModel):
    unitary_equiv: bool | None = None       # None a menos que oracle_kind="unitary"
    state_equiv: bool | None = None         # None a menos que oracle_kind="statevector" (D3c)
    verification_method: Literal["exact", "composition", "statevector"] | None = None
    endianness_swapped: bool = False        # FR-005: categoria própria
    hellinger_fidelity: float | None = None
    hellinger_std: float | None = None      # desvio entre seeds
    tvd: float | None = None
    energy_error: float | None = None
    passed: bool = False
    error: ErrorRecord | None = None


class ResourceResult(BaseModel):
    depth: int
    cx_count: int
    width: int
    depth_ratio: float                # gerado / referência, MESMO transpiler
    cx_ratio: float
    passed: bool


class CriticDecision(BaseModel):
    action: Literal["retry_retrieval", "retry_generation",
                    "optimize", "abort", "done"]
    rationale: str
    retrieval_hint: str | None = None
    generation_hint: str | None = None


class AgentState(TypedDict, total=False):
    # entrada
    task_id: str
    spec: str
    oracle_ref: str
    coupling_map_name: str | None

    # trabalho — sobrescrito a cada iteração
    requirements: list[Requirement]
    chunks: list[Chunk]
    code: str
    iteration: int

    # resultados da tentativa corrente
    static: StaticResult | None
    semantic: SemanticResult | None
    resource: ResourceResult | None
    decision: CriticDecision | None

    # acumuladores
    error_history: Annotated[list[ErrorRecord], add]
    trace: Annotated[list[dict], add]

    # terminal
    status: Literal["running", "success", "failed_semantic",
                    "failed_static", "aborted", "infrastructure_error",
                    "rejected_input"]
```

**Nota de projeto**: só `error_history` e `trace` acumulam. O restante carrega
apenas a tentativa corrente, o que mantém o prompt do `generator` controlável —
ele recebe os 2 últimos erros, não todos. Sem isso, o contexto cresce
linearmente com as iterações e o custo explode na condição C5.

---

## Entidades do benchmark

```python
# bench/schema.py
class TaskSpec(BaseModel):
    task_id: str                      # "t2_grover_3q_perturbed"
    tier: Literal["t1", "t2", "t3", "t4"]
    prompt: str
    n_qubits: int                     # <= 20 geral; <= 13 se oracle_kind="unitary"
    oracle_kind: Literal["unitary", "statevector", "distribution", "energy"]
    oracle_path: str
    gate_set: list[str] | None = None
    coupling_map: str | None = None
    perturbed: bool = False
    perturbation_family: str | None = None
    base_task_id: str | None = None   # FR-017: pareamento
    tolerance: float = 0.99
    max_depth_ratio: float = 2.0
```

**Correção (D3h, research.md)**: `oracle_kind` listava `"resource"` como um
quinto valor até T047. Não é um `oracle_kind` — nunca teve despacho em
`make_semantic_check_node` (`src/qcagent/graph.py`), e `resource_check` é
ORTOGONAL a `oracle_kind`: só precisa de um circuito de referência, que
`"statevector"`/`"unitary"` já fornecem, e roda automaticamente assim que
`semantic_check` popula `verification_method`. O que torna uma tarefa
"hardware-constrained" (tier T4) é `coupling_map` não-nulo, não um
`oracle_kind` diferente. Removido do `Literal` acima e de `bench/schema.py`
para que o valor não seja mais autorável — antes, uma tarefa escrita com
`oracle_kind="resource"` falharia de forma confusa em runtime
(`NotImplementedError` em `_load_oracle`) em vez de um erro de tipo no
momento de autoria.

```python
class RunRecord(BaseModel):
    """Uma linha do JSONL append-only. Unidade de análise."""
    run_id: str
    task_id: str
    model_id: str
    condition: Literal["C1", "C2", "C3", "C4", "C5"]
    seed: int
    status: Literal["success", "failed_semantic", "failed_static",
                    "aborted", "infrastructure_error", "rejected_input"]
    iterations: int
    final_code: str
    static: dict | None
    semantic: dict | None
    resource: dict | None
    error_history: list[dict]
    input_tokens: int
    output_tokens: int
    num_ctx: int | None = None            # D10b — valor efetivo, não o configurado
    cost_usd: float
    latency_s: float
    prefill_tok_s: float | None = None
    gen_tok_s: float | None = None
    gpu_memory_used_mib: int | None = None   # D10c
    gpu_processor: str | None = None         # ex.: "100% GPU" — detecta offload
    git_sha: str
    lib_versions: dict[str, str]
    timestamp: str
```

---

## Mapeamento `Chunk` → ponto Qdrant

Coleção `qdocs`, um ponto por chunk:

```python
PointStruct(
    id=uuid5(NAMESPACE_URL, doc_id),      # determinístico → upsert idempotente
    vector={
        "dense":  [...],                   # embedding do modelo escolhido em D4
        "sparse": SparseVector(...),       # BM25 via fastembed
    },
    payload={
        "text": ...,
        "source": "qiskit_api",            # keyword
        "library_version": "1.2.4",        # keyword — INDEXADO
        "deprecated": False,               # bool    — INDEXADO
        "replacement": None,
        "symbol": "SparsePauliOp",         # keyword — para depuração de recall
    },
)
```

**Índices de payload obrigatórios**: `library_version` e `deprecated`. Sem eles,
o Qdrant aplica o filtro depois da busca vetorial em vez de durante a travessia
do HNSW — e como material obsoleto é abundante neste corpus, um top-k pré-filtro
pode ser inteiramente descartado, devolvendo resultado vazio numa consulta que
deveria ter resposta. É o modo de falha que mais ameaça o portão M1.

**ID determinístico**: `uuid5` sobre `doc_id` garante que reingerir o corpus
sobrescreve em vez de duplicar (T035b).

---

## Relacionamentos

```
TaskSpec ──1:1──▶ Oracle
TaskSpec ──1:1──▶ TaskSpec (perturbada → base_task_id)
TaskSpec ──1:N──▶ RunRecord        (× modelo × condição × seed)
RunRecord ─1:N──▶ ErrorRecord      (histórico embutido)
Chunk    ──N:1──▶ DocSource
```

---

## Taxonomia fechada de erros

Usada tanto pelo roteamento do `critic` (T026) quanto pela análise qualitativa
(T064). Fechada por definição — categoria nova exige emenda ao spec.

| `error_type` | Camada | Ação do critic |
|---|---|---|
| `DeprecatedAPI` | static | `retry_retrieval` |
| `HallucinatedSymbol` | static | `retry_retrieval` |
| `SyntaxError` | static | `retry_generation` |
| `TranspilationFailure` | static | `retry_generation` |
| `QubitIndexError` | static | `retry_generation` |
| `MissingMeasurement` | static | `retry_generation` |
| `ParameterBindingError` | static | `retry_generation` |
| `EndiannessSwap` | semantic | `retry_generation` |
| `WrongGateDecomposition` | semantic | `retry_generation` |
| `ConceptualAlgorithmError` | semantic | `retry_generation` |
| `ResourceExcess` | resource | `optimize` |

---

## Regras de validação

| Regra | Onde | Requisito |
|---|---|---|
| `n_qubits <= 20` para qualquer tarefa | ingestão do dataset | T052 |
| `n_qubits <= 13` quando `oracle_kind="unitary"` | ingestão do dataset | D3b — acima disso a verificação é probabilística. **Não se aplica a `oracle_kind="statevector"`** (D3c): `Statevector` custa 2ⁿ, não 4ⁿ, então o teto de 13 é exclusivo do caminho unitário |
| `verification_method` preenchido sempre que uma verificação circuito-vs-circuito rodou (`oracle_kind` `unitary` ou `statevector`) | `semantic.py` | D3b/D3c — permite ao roteamento decidir se `resource_check` tem referência, e à análise segmentar por método |
| `oracle_kind="statevector"` para toda tarefa cujo enunciado especifica apenas o estado de saída a partir de `\|0...0>`, nunca `"unitary"` | autoria de tarefas (T044-T047) | D3c — `Operator.equiv()` rejeita decomposições unitariamente distintas do mesmo estado (ex.: GHZ via cadeia de CX vs. estrela de CX), o que rejeitaria respostas corretas |
| Toda canônica tem exatamente uma perturbada | `validate_oracles.py` | FR-017 |
| Oráculo unitário satisfaz `U @ U† ≈ I` | `validate_oracles.py` | FR-018 |
| `results/` nunca sofre UPDATE ou DELETE | `runner.py` | Princípio II |
| `validators/` não importa de `llm/` | `test_architecture.py` | Princípio I |
| Gerado e referência transpilados com parâmetros e seed idênticos | `resource.py` | FR-006 |
| `num_ctx` explícito em toda chamada; prompt que exceder levanta erro | `ollama_client.py` | D10b — truncagem silenciosa invalidaria H1/H3 |
| `gpu_processor == "100% GPU"` no braço local, senão abortar | `runner.py` | D10c |
| Erro de infraestrutura excluído do denominador das métricas | `analysis/metrics.py` | contrato de erros |
| `status="rejected_input"` distinto de `"aborted"` — recusa antes da geração, não esgotamento de `MAX_ITER` | `planner.py` | FR-030, FR-031 — preserva SC-001 sem conflatar "nunca tentado" com "tentou e falhou" |
