# Contract: Validators

**Feature**: `001-qcircuit-agent` | **Data**: 2026-08-11
**Módulos**: `src/qcagent/validators/{sandbox,static,semantic,resource}.py`
**Tarefas**: T013, T017–T023
**Requisitos cobertos**: FR-002, FR-003, FR-004, FR-005, FR-006, FR-025

> **Princípio I — inegociável.** Nenhum módulo sob `validators/` importa de
> `llm/`. `tests/contract/test_architecture.py` falha se isso ocorrer. Todo
> veredito aqui é determinístico e reexecutável.

---

## Configuração do simulador

```python
# src/qcagent/validators/simulator.py
GPU_THRESHOLD_QUBITS = 18

def make_simulator(n_qubits: int, seed: int) -> AerSimulator:
    """
    CPU por padrão. GPU só acima do limiar — ver D1.

    Abaixo de ~18 qubits a GPU perde para a CPU (overhead de kernel e
    transferência host↔device dominam), e disputaria VRAM com o Ollama durante
    a condição C5 com gerador local.

    max_parallel_experiments=1 é DELIBERADO: o paralelismo vive no
    bench/runner.py. Deixar Aer paralelizar internamente E o runner paralelizar
    produz contenção de threads e torna a latência não reprodutível — o que
    contamina a métrica de custo por execução.
    """
    return AerSimulator(
        method="statevector",
        device="GPU" if n_qubits >= GPU_THRESHOLD_QUBITS else "CPU",
        max_parallel_threads=8,          # 5700X: 8 núcleos físicos
        max_parallel_experiments=1,
        seed_simulator=seed,             # obrigatório — Princípio II
    )
```

---

## `sandbox.py`

### `WorkerPool`

```python
class WorkerPool:
    """
    Pool de processos pré-aquecidos (qiskit já importado). Substitui o spawn
    por execução — ver D1b.

    Justificativa: circuitos de 2–10 qubits simulam em milissegundos; o custo
    dominante é spawn + `import qiskit` (1–2 s). Com ~27.000 chamadas isso são
    8–15 h só em imports, contra a meta de 72 h da matriz inteira.

    O isolamento de FR-025 é preservado: o worker continua sendo processo
    separado do orquestrador. Muda apenas que é reutilizado em vez de recriado.
    """

    def __init__(self, size: int = 6, recycle_after: int = 50) -> None: ...

    def submit(self, code: str, timeout: int = 60) -> SandboxResult:
        """
        Executa `code` num worker. Recicla o worker após `recycle_after`
        execuções, para evitar acúmulo de estado entre tarefas.

        Um worker que estoure o timeout é MORTO e substituído, nunca reusado —
        pode ter deixado thread pendurada.
        """
```

```python
class SandboxResult(BaseModel):
    ok: bool
    circuit_qpy: bytes | None
    stdout: str
    stderr: str
    wall_time_s: float          # tempo total
    exec_time_s: float          # tempo do código, sem overhead do pool
```

**Contrato de telemetria**: `wall_time_s` e `exec_time_s` são reportados
separadamente. Sem essa separação, a métrica de latência mede a infraestrutura
em vez do sistema sob teste.

### Contrato do código gerado

```python
FORBIDDEN = ("import os", "import subprocess", "import socket", "import sys",
             "__import__", "eval(", "exec(", "open(", "Path(")

WRAPPER = """
{user_code}

from qiskit import qpy
if "qc" not in dir():
    raise RuntimeError("codigo nao definiu variavel `qc`")
with open("{artifact}", "wb") as f:
    qpy.dump(qc, f)
"""
```

O código gerado **deve** definir `qc` no escopo global. A denylist roda antes da
execução e produz `ok=False` sem invocar o worker.

---

## `static.py` — camadas 1 e 2

```python
DEPRECATED_SYMBOLS = {
    "execute":              "Use backend.run() ou Sampler/Estimator (Qiskit 1.x)",
    "QuantumInstance":      "Removido — use primitives",
    "qiskit.providers.aer": "Renomeado para qiskit_aer",
    "qiskit.opflow":        "Removido — use quantum_info.SparsePauliOp",
    "qiskit.algorithms":    "Movido para qiskit_algorithms",
    "assemble":             "Removido no Qiskit 1.0",
}


def check_static(code: str, coupling_map: CouplingMap | None,
                 pool: WorkerPool) -> StaticResult:
    """
    Portões sequenciais:
      1. scan de DEPRECATED_SYMBOLS  → error_type="DeprecatedAPI"
      2. ast.parse                   → error_type="SyntaxError"
      3. pool.submit                 → produz QPY
      4. transpile(coupling_map)     → error_type="TranspilationFailure"

    O scan roda ANTES da execução e é o que distingue H1 de H2: `DeprecatedAPI`
    é a única categoria que o critic roteia para `retry_retrieval`. Sem essa
    separação, a hipótese sobre valor da recuperação não é testável.
    """
```

---

## `semantic.py` — camada 3

### Seleção de método

```python
EXACT_UNITARY_MAX_QUBITS = 12


def check_unitary(generated: QuantumCircuit,
                  reference: QuantumCircuit,
                  n_qubits: int,
                  k_samples: int = 5) -> UnitaryVerdict:
    """
    Despacha por porte — ver D3b:

      n_qubits <= 12  → _check_exact()        (Operator.equiv, 4^n)
      n_qubits >  12  → _check_by_composition() (statevector, 2^n)

    O método usado É REGISTRADO em SemanticResult.verification_method, para que
    a análise possa segmentar resultados por método de verificação.
    """
```

### Caminho exato

```python
def _check_exact(generated, reference) -> UnitaryVerdict:
    """
    ARMADILHA 1 — fase global. Duas implementações corretas do mesmo circuito
    diferem rotineiramente por e^{iθ}. `Operator.equiv()` já trata isso;
    comparação direta de matrizes as marcaria como erradas. NUNCA usar
    np.allclose sobre as matrizes (FR-004).

    Quando equiv() é falso, calcular fidelidade contínua:
        |Tr(U_ref† @ U_gen)| / dim
    """
    op_gen, op_ref = Operator(generated), Operator(reference)
    if op_gen.dim != op_ref.dim:
        return UnitaryVerdict(equivalent=False, fidelity=0.0,
                              method="exact", reason="dim_mismatch")
    if op_gen.equiv(op_ref):
        return UnitaryVerdict(equivalent=True, fidelity=1.0, method="exact")
    fid = abs(np.trace(op_ref.adjoint().data @ op_gen.data)) / op_gen.dim[0]
    return UnitaryVerdict(equivalent=False, fidelity=float(fid), method="exact")
```

### Caminho por composição

```python
def _check_by_composition(generated, reference, n_qubits,
                          k_samples=5, atol=1e-9) -> UnitaryVerdict:
    """
    Custo 2^n em vez de 4^n. Se generated ∘ reference⁻¹ ≡ I, todo estado
    retorna inalterado a menos de fase global.

    O abs() do produto interno dá tolerância a fase global de graça — mesma
    garantia de FR-004, sem materializar matriz.

    Probabilístico: com 5 estados Haar-aleatórios a chance de falso positivo é
    desprezível, mas NÃO é zero. Declarar isso na dissertação.
    """
    composed = generated.compose(reference.inverse())
    worst = 1.0
    for seed in range(k_samples):
        psi = random_statevector(2 ** n_qubits, seed=seed)
        overlap = abs(psi.evolve(composed).inner(psi))
        worst = min(worst, overlap)
        if not np.isclose(overlap, 1.0, atol=atol):
            return UnitaryVerdict(equivalent=False, fidelity=float(worst),
                                  method="composition")
    return UnitaryVerdict(equivalent=True, fidelity=1.0, method="composition")
```

### Endianness

```python
def check_with_endianness(generated, reference, n_qubits) -> SemanticResult:
    """
    ARMADILHA 2 — convenção de ordenação (FR-005).

    Qiskit é little-endian. Referências portadas de artigos ou do PennyLane
    usam com frequência a convenção oposta. Verificar contra a referência
    original E contra `reference.reverse_bits()`.

    Se apenas a invertida casar → endianness_swapped=True, passed=False,
    error_type="EndiannessSwap". É categoria PRÓPRIA, não erro comum: tratá-la
    como falha genérica inflaria artificialmente a taxa de erro e apagaria um
    achado interessante da taxonomia.
    """
```

### Oráculo de preparação de estado (D3c — correção a D3/D3b)

```python
def check_statevector(generated: QuantumCircuit,
                      reference: QuantumCircuit) -> StateVerdict:
    """
    Para `oracle_kind="statevector"`: o enunciado especifica apenas o ESTADO
    DE SAÍDA do circuito a partir de |0...0>, não sua ação sobre toda base
    computacional. `check_unitary` rejeita incorretamente uma decomposição
    unitariamente distinta que ainda assim prepara o mesmo estado (ex.: GHZ
    via cadeia de CX 0->1->2 vs. estrela de CX 0->1,0->2 — mesmo estado a
    partir de |000>, unitárias diferentes).

    Sem despacho por porte: Statevector(qc) materializa 2^n amplitudes, não
    os 4^n de Operator(qc) — barato até n_qubits=20 (teto geral do dataset),
    então não há caminho "composição" nem fallback probabilístico aqui,
    diferente do oráculo unitário (D3b).

    ARMADILHA 1 (fase global) continua valendo: Statevector.equiv() já trata,
    mesma garantia que Operator.equiv() dá a check_unitary.
    """


def check_statevector_with_endianness(generated, reference) -> SemanticResult:
    """
    Contraparte de check_with_endianness para oráculo de estado. ARMADILHA 2
    (convenção de ordenação) se aplica igualmente — testar contra a
    referência original E `reference.reverse_bits()`. Mesma categoria
    EndiannessSwap, mesmo formato de payload (_structural_diff) do caminho
    unitário.

    Preenche `state_equiv` (nunca `unitary_equiv`) e
    `verification_method="statevector"`.
    """
```

**Achado que motivou esta seção**: rodada ao vivo do task `ghz_3q` (GHZ-3,
`oracle_kind="unitary"` original) — o modelo produziu GHZ via estrela de CX
(0->1, 0->2), o oráculo de referência usa cadeia de CX (0->1, 1->2). Ambos
preparam exatamente `(|000> + |111>)/sqrt(2)` a partir de `|000>`, mas
`Operator.equiv()` os considera unitárias diferentes e rejeitou uma resposta
correta. O enunciado do task só restringe o estado, nunca a transformação —
`oracle_kind="unitary"` era o oráculo errado para essa tarefa desde o início.
Ver D3c em research.md para a classificação de quais tarefas canônicas
(T044-T047) precisam de qual oráculo.

---

### Oráculos alternativos

```python
def check_distribution(generated, reference_counts, shots=8192,
                       seeds=(1, 2, 3)) -> DistributionVerdict:
    """Fidelidade de Hellinger (primária) e TVD (secundária), média e desvio
    sobre as seeds. O desvio entra no relatório — média sozinha esconde
    instabilidade."""


def check_energy(generated, hamiltonian, exact_value,
                 tol=1e-2) -> EnergyVerdict:
    """Para VQE: erro absoluto contra diagonalização exata."""
```

---

## `resource.py` — camada 4

```python
COUPLING_MAPS = {"linear_5": ..., "heavy_hex_27": ..., "all_to_all": None}


def check_resources(generated, reference, coupling_map_name,
                    opt_level=2, seed=42) -> ResourceResult:
    """
    ARMADILHA 3 — transpilação assimétrica. Transpilar AMBOS com parâmetros
    IDÊNTICOS (mesmo opt_level, mesmo coupling_map, mesmo seed_transpiler).
    Comparar circuito transpilado contra referência não-transpilada é erro
    metodológico e produziria depth_ratio sem significado (FR-006).

    seed_transpiler é obrigatório: os passes de roteamento são estocásticos, e
    sem seed o depth_ratio varia entre execuções da mesma entrada.

    depth_ratio > task.max_depth_ratio → passed=False,
    error_type="ResourceExcess" → critic emite action="optimize".
    """
```

---

## Contrato de erros

| Condição | Comportamento |
|---|---|
| Código não define `qc` | `StaticResult(executed=False)`, `error_type="SyntaxError"` |
| Timeout no worker | Worker morto e substituído; `error_type="TranspilationFailure"` se ocorreu no transpile, senão erro de execução |
| `n_qubits` da tarefa > 20 | Levantar na ingestão do dataset, nunca aqui (T052) |
| Referência inválida | Levantar `OracleError` — é bug do dataset, não falha do gerador. NUNCA contabilizar como erro do modelo |
| Dimensões incompatíveis | `equivalent=False`, `reason="dim_mismatch"` — não é exceção |

**Regra crítica**: falha de infraestrutura (timeout do pool, Qdrant fora do ar,
oráculo quebrado) NUNCA entra nas métricas como falha do gerador. Registrar
como `status="infrastructure_error"` e excluir do denominador.

---

## Testes exigidos

| Teste | Arquivo | Verifica |
|---|---|---|
| `validators/` não importa de `llm/` | `tests/contract/test_architecture.py` | Princípio I |
| Circuitos idênticos a menos de fase global → equivalente | `tests/unit/test_semantic.py` | FR-004 |
| Caminhos exato e por composição concordam em 8 qubits | `tests/unit/test_semantic.py` | D3b |
| Referência com bits invertidos → `EndiannessSwap`, não falha genérica | `tests/unit/test_semantic.py` | FR-005 |
| Dimensões incompatíveis não levantam exceção | `tests/unit/test_semantic.py` | contrato de erros |
| Mesmo circuito transpilado duas vezes com a mesma seed → mesmo depth | `tests/unit/test_resource.py` | reprodutibilidade |
| Denylist bloqueia antes de invocar o worker | `tests/unit/test_sandbox.py` | FR-025 |
| Worker reciclado após N execuções não vaza estado | `tests/unit/test_sandbox.py` | D1b |
| Timeout mata e substitui o worker | `tests/unit/test_sandbox.py` | D1b |

**Teste-chave de D3b**: rodar os dois caminhos de verificação sobre o mesmo par
de circuitos de 8 qubits e exigir concordância. É o que garante que a troca de
método acima de 12 qubits não introduz viés na métrica.
