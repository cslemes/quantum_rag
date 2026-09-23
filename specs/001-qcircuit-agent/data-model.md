# Data Model: qcircuit-agent

**Feature**: `001-qcircuit-agent` | **Data**: 2026-08-11
**Fonte**: Key Entities de [spec.md](./spec.md)

---

## Estado do grafo

```python
# src/qcagent/state.py
from typing import Annotated, Literal, TypedDict
from operator import add
from pydantic import BaseModel, Field, StrictInt


class Requirement(BaseModel):
    """Requisito verificável extraído pelo planner. Vira o contrato do critic."""
    id: str
    kind: Literal["n_qubits", "gate_set", "property", "resource", "output_format"]
    description: str
    # StrictInt: fronteira de saída do LLM — fora-de-contrato é recusado, não
    # interpretado. Com `int` lax, `true` virava requisito de 1 qubit, `false`
    # de 0 e `3.0` virava 3 (enquanto `2.5` já era recusado). Ver F9.
    value: str | StrictInt | list[str] | None = None


# -- Linguagem de asserção (US3, T082) — ver §Linguagem de asserção abaixo
# para a sintaxe textual que `validators/assertions.py::parse_assertions`
# converte nestas entidades, e para a convenção de ket/Pauli compartilhada.
# Substitui os nomes de classe do rascunho de desenho original em plan.md
# (`AmplitudeEquality`/`MeasurementDeterminism`/`OperatorEigenstate`/
# `GateRestriction`) — os nomes abaixo são os que o código efetivamente usa,
# fixados só depois de duas rodadas de revisão (ver research.md D19).

class AmplitudeTerm(BaseModel):
    """Um operando de `AmplitudeAssertion`. `probability`/`amplitude` são
    cegos a fase global por construção (mesma lição de F1/D3c). `phase_diff`
    é a ÚNICA forma de expor fase nesta gramática — a diferença relativa
    entre duas amplitudes, nunca a fase de um único ket (não é um
    observável). Indefinido quando a amplitude referenciada é ~0 — nesse
    caso a avaliação produz `AssertionOutcome.passed=None`, nunca um
    veredito forçado."""
    kind: Literal["probability", "amplitude", "phase_diff"]
    basis_state: str
    basis_state_b: str | None = None   # obrigatório sse kind == "phase_diff"


class AmplitudeAssertion(BaseModel):
    """`PROBABILITY(...)`/`AMPLITUDE(...)`/`PHASE_DIFF(...)` de um lado de um
    comparador (`==`, `~=`, `>=`, `<=`); o outro lado é um número ou outro
    `AmplitudeTerm` do MESMO `kind` (comparação par-a-par, ex.:
    `AMPLITUDE(a) == AMPLITUDE(b)`) — o parser recusa comparar tipos
    diferentes ou um `PHASE_DIFF` do lado direito (FR-013)."""
    kind: Literal["amplitude"] = "amplitude"
    lhs: AmplitudeTerm
    comparator: Literal["==", "~=", ">=", "<="]
    rhs: AmplitudeTerm | float
    input_state: str | None = None     # prefixo INPUT(...); None = |0...0>


class MeasuresAssertion(BaseModel):
    """`MEASURES == "<bitstring>"` (forma NUA) ou `MEASURES([...]) ==
    "<bitstring>"` (forma COM LISTA) — nunca uma probabilidade parcial (use
    `AmplitudeAssertion`/`PROBABILITY` para isso).

    As duas formas usam convenções DIFERENTES de propósito — ver
    §Linguagem de asserção abaixo para o porquê (a alternativa, unificar as
    duas, produziria erro silencioso de usuário). `qubits=None` é a forma
    nua (registro inteiro, convenção compartilhada do módulo). `qubits=[...]`
    é a forma com lista (correspondência posicional `qubits[i]` <->
    `expected[i]`, obrigatória para qualquer subconjunto)."""
    kind: Literal["measures"] = "measures"
    qubits: list[int] | None = None
    expected: str
    input_state: str | None = None


class EigenstateAssertion(BaseModel):
    """`EIGENSTATE_OF("<pauli>", <+1|-1>)` — forma geral. `QUBIT(q) ==
    "|label>"` é açúcar sintático desabaçucarado em tempo de PARSE para esta
    classe (nunca um `kind` de runtime separado). Checado pela NORMA DO
    RESÍDUO `‖H|ψ⟩ − λ|ψ⟩‖`, nunca só `⟨ψ|H|ψ⟩ == λ` — ver achado F2
    (report-notes.md), aplicado aqui preventivamente."""
    kind: Literal["eigenstate"] = "eigenstate"
    pauli_string: str
    eigenvalue: Literal[1, -1]
    input_state: str | None = None


class GateRestrictionAssertion(BaseModel):
    """`GATES_SUBSET_OF({"h", "cx", ...})` — puramente estrutural sobre
    `circuit.data`, nunca simulada, por isso sem `input_state` (um prefixo
    `INPUT(...)` nesta forma é recusado no parse, não ignorado). Nomes de
    gate validados contra o vocabulário do próprio Qiskit — não porque um
    nome digitado errado tornasse a asserção vacuamente verdadeira (uma
    checagem de subconjunto é fail-closed por construção; ver F6,
    report-notes.md, para a correção dessa alegação original), mas porque
    valida-lo cedo troca uma falha de asserção confusa por um erro de parse
    preciso."""
    kind: Literal["gate_restriction"] = "gate_restriction"
    allowed_gates: frozenset[str]


Assertion = Annotated[
    AmplitudeAssertion | MeasuresAssertion | EigenstateAssertion | GateRestrictionAssertion,
    Field(discriminator="kind"),
]


class AssertionOutcome(BaseModel):
    """Resultado de avaliar uma `Assertion` (FR-011: reportada
    individualmente, nunca agregada). `passed` é TRI-ESTADO:
    `True`/`False` para o veredito normal, e `None` — "não avaliável" —
    em exatamente dois casos: um termo `phase_diff` cuja amplitude
    referenciada é ~0 (fase indefinida ali), e qualquer asserção sobre
    estado contra um circuito com medição NÃO final, reset ou outra
    instrução não unitária (não existe estado puro de saída). Medições
    finais são removidas antes e NÃO causam isso. `None` nunca conta como aprovação:
    `GuaranteeReport.functional_correctness_verified` (US4) exige
    `passed is True` em toda asserção, explicitamente (Princípio II)."""
    assertion: Assertion
    passed: bool | None
    detail: str


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
    max_depth_ratio: float           # herdado de TaskSpec — ver resource_check
    assertions: list[Assertion]      # US3 — parseada uma vez na entrada, nunca por iteração

    # trabalho — sobrescrito a cada iteração
    requirements: list[Requirement]
    chunks: list[Chunk]
    code: str
    iteration: int

    # resultados da tentativa corrente
    static: StaticResult | None
    semantic: SemanticResult | None
    resource: ResourceResult | None
    assertion_results: list[AssertionOutcome] | None   # US3 — uma entrada por asserção declarada
    requirement_results: list[RequirementOutcome] | None  # T091 — uma por requisito CHECÁVEL
    decision: CriticDecision | None

    # acumuladores
    error_history: Annotated[list[ErrorRecord], add]
    trace: Annotated[list[dict], add]

    # terminal
    status: Literal[
        "running",
        # "success" significa que ALGO REAL sobre corretude funcional foi
        # verificado E passou — comparação com referência (semantic_check,
        # caminho da suíte) OU toda asserção declarada pelo usuário
        # (assertion_check, caminho de produto). NÃO significa "o pipeline
        # terminou sem erro": isso é "completed_unverified".
        "success",
        # US4 — terminou limpo, mas nada verificou corretude funcional (sem
        # oracle_ref E sem asserções). Separado de "success" porque uma
        # invariante que depende de cada consumidor lembrar de ler também
        # `guarantee_report.functional_correctness_verified` será quebrada
        # pela primeira coisa que agregar `status` sozinho (uma tabela de
        # métricas, um resumo de CI, analysis/metrics.py quando T059
        # chegar). O tipo carrega a distinção em vez da convenção.
        "completed_unverified",
        "failed_semantic", "failed_static",
        "aborted", "infrastructure_error", "rejected_input",
        # US3 — a MESMA asserção (casada estruturalmente) voltou "não
        # avaliável" em duas tentativas CONSECUTIVAS. Distinto de "aborted"
        # (esgotamento de MAX_ITER) e de "failed_semantic" (uma checagem
        # bem posta que simplesmente não passou): regenerar não ajudou duas
        # vezes seguidas, evidência de que a PRÓPRIA ASSERÇÃO pode não
        # corresponder a nenhum circuito correto para a tarefa — um
        # problema de declaração do usuário, não necessariamente de
        # geração. Ver §Linguagem de asserção abaixo e `report.py` (US4).
        "assertion_not_evaluable",
    ]
```

**`guarantee_report` é tipado `Any`, e por quê**: `report.py` importa
`Assertion`/`AssertionOutcome`/`RequirementOutcome`/`ResourceResult` DESTE
módulo, então um import no sentido inverso seria circular; e um guardado por
`TYPE_CHECKING` quebra em runtime, porque `StateGraph(AgentState)` do
LangGraph chama `typing.get_type_hints()` sobre o `TypedDict` e falha com
`NameError` numa referência textual nunca importada de fato (confirmado ao
tentar exatamente essa rota). `Any` significa que o mypy deixa de proteger a
estrutura mais importante do produto, então a garantia é reestabelecida em
runtime no ÚNICO ponto onde o valor entra no estado —
`routing.py::finalize` levanta `TypeError` se o que for gravado nessa chave
não for um `GuaranteeReport`. Dívida nomeada e fechada na fronteira, não
herdada em silêncio (`test_routing.py::
test_finalize_puts_a_real_guarantee_report_in_state`).

**`RequirementOutcome` vs. `AssertionOutcome`** (T091): forma idêntica,
PROVENIÊNCIA diferente — uma asserção é o que o USUÁRIO declarou, um
requisito é o que um LLM extraiu da descrição. Por isso ficam em campos
separados no `GuaranteeReport`, e por isso um requisito reprovado pode VETAR
uma alegação de corretude mas nunca ESTABELECER uma (ver §GuaranteeReport).
`passed=None` aqui significa "não checável" (valor de `n_qubits` que não é
inteiro, `gate_set` nomeando instruções que o Qiskit não tem) — nunca um
veredito forçado. Requisitos de `kind` não tratado (`property`,
`output_format`, `resource`) não produzem entrada nenhuma: emitir "passou"
para uma checagem que não rodou seria exatamente o empréstimo de verbo de
verificação que o resto deste documento recusa.

**Nota de projeto**: só `error_history` e `trace` acumulam. O restante carrega
apenas a tentativa corrente, o que mantém o prompt do `generator` controlável —
ele recebe os 2 últimos erros, não todos. Sem isso, o contexto cresce
linearmente com as iterações e o custo explode ao longo de uma execução da
suíte de regressão (até 5 tentativas × 120 tarefas × 3 seeds — ver MIGRATION.md;
nota histórica: em v1 essa mesma preocupação motivava o desenho sob a condição
experimental C5, que não existe mais).

---

## Linguagem de asserção — sintaxe textual (US3)

**Fonte de verdade**: `src/qcagent/validators/assertions.py` (`parse_one`/
`parse_assertions`) — esta seção documenta o que o parser efetivamente aceita,
não um rascunho anterior a ele. Ver research.md D19 para o racional e o
histórico de duas rodadas de revisão que chegaram a esta forma.

**Convenção compartilhada** (declarada uma única vez, `state.py`): em todo
ket/Pauli-string desta gramática, o caractere mais à esquerda é o qubit de
maior índice, o mais à direita é o qubit 0 — idêntico à convenção de
`Statevector.probabilities_dict()`/`Pauli` do próprio Qiskit, verificado (não
assumido) como exatamente `int(ket_string, 2)` indexando `Statevector.data`.
Sem padding implícito: o comprimento de toda string sempre bate com
`n_qubits`. **Uma exceção deliberada** — a forma COM LISTA de `MEASURES`,
abaixo.

Uma asserção por linha; `#` inicia comentário; linha vazia mal formada
invalida o lote inteiro (FR-013 — nunca um subconjunto parseado em silêncio).

| Forma | Sintaxe | Exemplo |
|---|---|---|
| Probabilidade | `PROBABILITY(\|<ket>>) <cmp> <num>` | `PROBABILITY(\|11>) ~= 0.5` |
| Amplitude (magnitude) | `AMPLITUDE(\|<ket>>) <cmp> <num\|termo>` | `AMPLITUDE(\|00>) == AMPLITUDE(\|11>)` |
| Fase relativa | `PHASE_DIFF(\|<a>>,\|<b>>) <cmp> <num\|pi>` | `PHASE_DIFF(\|00>,\|11>) ~= 0` (Φ+) |
| Medição determinística (registro inteiro) | `MEASURES == "<bitstring>"` | `MEASURES == "101"` |
| Medição determinística (subconjunto) | `MEASURES([q,...]) == "<bitstring>"` | `MEASURES([2,0]) == "01"` |
| Autoestado (forma geral) | `EIGENSTATE_OF("<pauli>", <+1\|-1>)` | `EIGENSTATE_OF("ZII", -1)` |
| Autoestado (açúcar de 1 qubit) | `QUBIT(<q>) == "\|<label>>"` | `QUBIT(3) == "\|->"` |
| Restrição de gate set | `GATES_SUBSET_OF({"g1", ...})` | `GATES_SUBSET_OF({"h", "cx"})` |
| Prefixo de entrada (opcional, todas exceto `GATES_SUBSET_OF`) | `INPUT(\|<ket>>) THEN <asserção>` | `INPUT(\|0011>) THEN MEASURES == "1011"` |

`<cmp>` é um de `==`, `~=` (tolerância `DEFAULT_TOL=1e-9`), `>=`, `<=`.
`<label>` (açúcar `QUBIT`) é um de `0`, `1`, `+`, `-`, `i`, `-i` — os seis
estados cardeais da esfera de Bloch, cada um o autoestado de `X`/`Y`/`Z`
correspondente; `QUBIT(q) == "|label>"` desabaçucara para uma
`EigenstateAssertion` de N-1 `I`s e um `X`/`Y`/`Z` na posição `q`, NUNCA um
`kind` de runtime separado — `EIGENSTATE_OF` continua sendo o único caminho
de avaliação real.

**Por que `MEASURES` tem duas convenções, não uma**: a forma nua usa a
convenção compartilhada acima (registro inteiro, posição = índice do
qubit). A forma com lista usa correspondência POSICIONAL entre `qubits` e
`expected` (`qubits[i]` mede para `expected[i]`, ambos lidos da esquerda
para a direita) — deliberadamente diferente, porque uma vez que `qubits` é
um subconjunto/ordem arbitrária escolhida pelo usuário, "esquerda = maior
índice" deixa de fazer sentido. Unificar as duas produziria erro silencioso
de usuário (`MEASURES([0,1,2]) == "101"` e `EIGENSTATE_OF("XII", -1)` lidos
em direções opostas seriam indistinguíveis à primeira vista) — a mitigação
escolhida foi tornar as duas formas SINTATICAMENTE distintas (com/sem
parênteses) para que a colisão nunca aconteça dentro de uma única asserção
escrita, em vez de um aviso em tempo de execução.

**`INPUT(...) THEN <asserção>`**: prepara o registro num estado de base
computacional (um `X` por bit `'1'`, mesma convenção de ket) antes de
evoluir o circuito sob teste — sem isso, toda asserção só pode testar
comportamento a partir de `|0...0⟩`, o que é insuficiente para qualquer
tarefa cujo conteúdo seja uma TRANSFORMAÇÃO geral (ex.: QFT — ver research.md
D19 e report-notes.md F7 para o achado do exercício de validação a frio que
motivou este prefixo). Várias asserções `INPUT` sobre entradas não-triviais
distintas dão cobertura evidencial real de uma transformação — mesma lógica
de `_check_by_composition` (D3b), mas SEM a mesma garantia formal: lá, k
estados Haar-aleatórios testam uma proposição universal contra uma
referência CONHECIDA; aqui, não há referência — cada `INPUT` testa só a
propriedade que o usuário escolheu escrever, para aquela entrada específica.
Estruturalmente inaplicável a `GATES_SUBSET_OF` (propriedade do circuito,
não do estado) — um prefixo `INPUT(...)` nessa forma é recusado no parse,
não ignorado.

**Resultado tri-estado (`AssertionOutcome.passed: bool | None`)**: `None`
("não avaliável") ocorre em exatamente dois casos: um termo `PHASE_DIFF`
cujo ket referenciado tem amplitude ~0 (a fase não é definida ali), e
qualquer asserção sobre estado contra um circuito com medição NÃO final,
reset ou outra instrução não unitária (não há estado puro de saída sobre o
que afirmar). O segundo caso foi acrescentado depois do primeiro teste ponta
a ponta (T092): antes, `Statevector.from_instruction` levantava
`QiskitError` e derrubava o grafo inteiro. Medições FINAIS (o
`measure_all()` que código gerado faz o tempo todo) são removidas antes da
avaliação — não mudam o estado preparado, só o amostram — e não tornam nada
"não avaliável". `GATES_SUBSET_OF` sempre resolve para `True`/`False`, e
ignora as instruções que o próprio Qiskit nunca exige numa base
(`measure`, `reset`, `barrier`, `snapshot`, `delay`, `store` — a lista
`basic_instrs` do `BasisTranslator`, fixada contra o fonte instalado por
teste). Isto refina o Cenário de Aceitação 4 de
US3 (spec.md), que agrupa "mal formada" e "impossível de avaliar" sob a
mesma recusa explícita: essa recusa continua valendo, sem exceção, para
tudo que é conhecido como malformado NA ETAPA DE PARSE (comprimento
incompatível, índice fora de faixa, categoria desconhecida — `rejected_
input`, antes de qualquer geração). O tri-estado é um mecanismo DIFERENTE e
adicional, só possível em tempo de AVALIAÇÃO (depois que um circuito real
existe) para uma asserção bem formada que se revela não bem posta PARA
AQUELE CIRCUITO especificamente — nunca um `AssertionParseError`, nunca uma
recusa de todo o lote. Ver `AgentState.status="assertion_not_evaluable"`
acima para o que acontece quando isso se repete (T086).

**Largura do registro (T090)**: vem das próprias asserções do usuário
(`width_statements`), não do `n_qubits` extraído pelo LLM. Duas ou mais
asserções concordando contra o planner corrigem o requisito
(`QubitCountCorrection`, levado ao relatório); uma só é recusada como
ambígua. Ver
plan.md §Verificação sem referência. Um circuito de largura diferente da
asserção dá `passed=False` com "assertion is written for N qubits but the
circuit has M" — nunca é avaliado mesmo assim, o que antes gerava falso
positivo ou queda do grafo. `MEASURES([...])` e `GATES_SUBSET_OF` não fixam
largura; um índice listado além do circuito também é violação nomeada.

**Malformação (FR-013)** — detectada inteiramente na etapa de parse, antes
de qualquer geração: comprimento de ket/Pauli-string incompatível com
`n_qubits` (sem padding implícito), índice de qubit fora de faixa ou
duplicado numa lista de `MEASURES`, comparação entre `AmplitudeTerm`s de
`kind` diferente, `PHASE_DIFF` do lado direito de uma comparação, nome de
gate fora do vocabulário do próprio Qiskit, conjunto de gates vazio,
`INPUT(...)` sobre `GATES_SUBSET_OF`, categoria de asserção desconhecida.
Todos produzem `AssertionParseError` com mensagem específica ao que falhou
— nunca uma exceção não tratada, nunca uma asserção silenciosamente
ignorada. `tests/unit/test_assertions.py` cobre cada um destes casos
individualmente.

**Escopo explicitamente fora desta fase**: ver plan.md §Verificação sem
referência — `Requirement`s de `kind="property"`/`kind="output_format"`
não ganham tradução automática de linguagem natural para esta gramática.

---

## GuaranteeReport (US4)

**Fonte de verdade**: `src/qcagent/report.py` (T093–T096) —
`tests/unit/test_report.py` (23 casos) prova o texto abaixo, não é
ilustrativo. Montado por `nodes/routing.py::_build_guarantee_report`
inteiramente a partir de resultados já computados (`static`,
`assertion_results`, `resource`, `coupling_map_name`) — nenhuma checagem
nova roda aqui.

```python
class GuaranteeReport(BaseModel):
    model_config = ConfigDict(extra="forbid")   # é a garantia em si — ver abaixo

    executed: bool
    transpiled: bool
    # T091 — substitui o stub `requirements_checked: list[str]`, que só
    # sabia NOMEAR requisitos, nunca dizer se valiam. Uma entrada por
    # requisito CHECÁVEL; lista vazia significa "nada aqui era checável",
    # nunca "tudo passou" (o renderizador diz qual).
    requirements: list[RequirementOutcome]
    assertions: list[AssertionOutcome]  # vazia sse nenhuma foi declarada
    # T090: presente quando 2+ asserções concordantes corrigiram a contagem
    # de qubits lida pelo planner — renderizada, não só registrada no trace.
    n_qubits_correction: QubitCountCorrection | None
    # A comparação com referência (semantic_check), presente sse oracle_ref.
    # Ausente da primeira versão: um run da suíte que PASSAVA equivalência
    # unitária exata renderizava "nothing about its behavior was checked"
    # ao lado de status="success" (achado ponta a ponta, T098).
    reference: SemanticResult | None

    # Reference-free evidence (plan.md, round-2 item 2): as duas ficam None
    # juntas sse nenhum coupling_map foi declarado — nada a reportar, não
    # uma lacuna. Quando um coupling_map FOI declarado, topology_respected
    # vem de static.transpiled incondicionalmente; resource fica None a
    # menos que oracle_ref esteja presente (resource_check sempre exigiu
    # uma referência, nunca rodou só por coupling_map — ver §Contratos dos
    # nós, plan.md).
    coupling_map_name: str | None
    topology_respected: bool | None
    resource: ResourceResult | None

    hardware_note: str | None  # US5 — "comportamento sob ruído", nunca "verificação"

    @computed_field
    @property
    def functional_correctness_verified(self) -> bool:
        # Requisitos VETAM mas nunca ESTABELECEM (T091): um requisito que
        # PASSA significa só "o circuito concorda com o que o planner leu
        # da descrição" — não é evidência de corretude, porque a premissa
        # veio de um LLM. Um que REPROVA é assimetricamente mais forte:
        # circuito e descrição discordam sobre algo diretamente checável,
        # e nenhuma alegação de corretude sobrevive a isso. `passed=None`
        # ("não checável") não veta nada.
        # O ÚNICO lugar onde "verificado" é decidido, nos dois caminhos;
        # terminal_status() só lê este campo. Ordem:
        if not (self.executed and self.transpiled):   # 1. nada roda sobre código que não rodou
            return False
        if any(a.passed is not True for a in self.assertions):  # 2. asserção do usuário veta
            return False
        if self.reference is not None:                # 3/4. referência reprovada veta,
            return self.reference.passed              #      aprovada verifica (requisito não veta)
        if any(r.passed is False for r in self.requirements):   # 5. requisito veta...
            return False
        return bool(self.assertions)                  #    ...e sem asserção nada foi verificado

    @computed_field
    @property
    def only_trivial_input_tested(self) -> bool:
        input_capable = [o.assertion for o in self.assertions if hasattr(o.assertion, "input_state")]
        return bool(input_capable) and not any(a.input_state is not None for a in input_capable)
```

**`functional_correctness_verified` e `only_trivial_input_tested` são
`@computed_field`s, nunca argumentos de construtor** — com
`extra="forbid"`, `GuaranteeReport(functional_correctness_verified=True,
assertions=[])` levanta `ValidationError` em vez de aceitar um relatório
que mente. Esta é a invariante de SC-004 (Princípio II) tornada
estruturalmente impossível de violar, não apenas testada — ver
`test_report.py::test_cannot_construct_a_lying_report` (T095).

### Três casos canônicos (`render_guarantee_report`), colados da saída real

**O veredito vem PRIMEIRO, antes de qualquer linha afirmativa.** Uma versão
anterior o colocava por último, depois de `Executed: yes` / `Transpiled:
yes` / `Requirements checked: ...` — três linhas em formato de "sim" à
frente da única linha que não pode ser perdida, que é exatamente a forma que
produz leitura otimista por varredura. `test_report.py::
test_verdict_precedes_every_affirmative_fact` falha a build se alguma delas
voltar a preceder o veredito.

**Caso A — todas as asserções passam** (GHZ₃, sem `oracle_ref`, sem
`coupling_map`) — `status="success"`:

```
=== Guarantee Report ===

FUNCTIONAL CORRECTNESS: VERIFIED — all 4 declared assertions passed. This means the circuit satisfies every property you declared; it does NOT mean the circuit is correct in any sense beyond those properties.

--- What was and was not checked ---
Executed: yes
Transpiled: yes

Requirements (2/2 passed):
  [PASS] n_qubits — circuit has 3 qubits, requirement states 3
  [PASS] gate_set — all gates within the required set

Assertions (4/4 passed):
  [PASS] PROBABILITY(|000>) ~= 0.5
  [PASS] PROBABILITY(|111>) ~= 0.5
  [PASS] PHASE_DIFF(|000>,|111>) ~= 0
  [PASS] GATES_SUBSET_OF({"cx", "h"})

Input coverage: only the |0...0> input was exercised across all 4 assertions. If this circuit is meant to implement a general transformation, no assertion here confirms behavior on other inputs.
```

**Caso B — uma asserção violada** (Bell sem o CX emaranhador,
`coupling_map="linear_5"` declarado, sem `oracle_ref`):

```
=== Guarantee Report ===

FUNCTIONAL CORRECTNESS: NOT VERIFIED — 1 failed of 2 declared assertions. The circuit executing and respecting the declared constraints is NOT evidence of functional correctness.

--- What was and was not checked ---
Executed: yes
Transpiled: yes (coupling map: linear_5)

Requirements (1/1 passed):
  [PASS] n_qubits — circuit has 2 qubits, requirement states 2

Assertions (1/2 passed):
  [PASS] PROBABILITY(|00>) ~= 0.5
  [FAIL] PROBABILITY(|11>) ~= 0.5 — lhs=0 ~= rhs=0.5

Input coverage: only the |0...0> input was exercised across all 2 assertions. If this circuit is meant to implement a general transformation, no assertion here confirms behavior on other inputs.

Topology: respects the declared coupling map (linear_5) — verified by successful transpilation, independent of any assertion result above.
Resource/depth ratio: not evaluated — no reference circuit is available in this run, and depth_ratio has no meaning without one.
```

No grafo real este caso NÃO termina em `completed_unverified`: uma asserção
violada roteia para o `critic` (`AssertionViolated` → `retry_generation`) e,
esgotado `MAX_ITER`, termina em `failed_semantic`. O relatório acima é o
mesmo; o `status` que o acompanha depende de por onde o laço saiu.

**Caso C — nenhuma asserção declarada** (Princípio II vive aqui) —
`status="completed_unverified"`, nunca `"success"`:

```
=== Guarantee Report ===

FUNCTIONAL CORRECTNESS: NOT VERIFIED. No assertions were declared for this circuit, so nothing about its behavior was checked. The circuit executing successfully and satisfying the requirements below is NOT evidence that it does what you intended — only that it runs and respects the constraints you stated. If you want functional correctness verified, add assertions describing what the circuit should do.

--- What was and was not checked ---
Executed: yes
Transpiled: yes

Requirements (1/1 passed):
  [PASS] n_qubits — circuit has 3 qubits, requirement states 3

Assertions: none declared.
```

O Caso C nunca omite a não-verificação e nunca a deixa implícita na ausência
da seção `Assertions` — FR-016 exige a frase explícita, e
`test_no_correctness_claim_without_verified_assertion` (T095) falha a build
se ela sumir. Nenhum dos três casos usa "executa e respeita restrições" como
sinônimo de "está correto" (FR-017) — os Casos A e B dizem isso
explicitamente na direção oposta ("does NOT mean the circuit is correct...",
"is NOT evidence of functional correctness"). E o `status` ao lado do Caso C
diz o mesmo sem depender de ninguém ler o texto: `completed_unverified`.

**Quando a lista de requisitos está vazia**, o renderizador NÃO diz
"Requirements checked: none" — isso lê como "checamos e não achamos nenhum",
emprestando um verbo de verificação para uma checagem que não rodou. Diz:
`Requirements: none checked — no qubit-count or gate-set requirement was
extracted from the description (those are the only two checkable without a
reference circuit).` Coberto por `test_report.py::
test_empty_requirements_does_not_claim_a_check_happened`.

**Idioma**: texto renderizado em inglês, como o resto de `src/qcagent/`
(mensagens de erro de `validators/assertions.py` inclusive) — os documentos
de desenho ficam em português, o produto fala a língua do seu próprio código.

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
    """Uma linha do JSONL append-only. Unidade de análise. Sem campo de
    condição experimental (`condition: C1..C5`) — não existe mais em v2, a
    suíte roda uma configuração por vez (ver MIGRATION.md; `bench/schema.py`
    corrigido para bater com esta definição)."""
    run_id: str
    task_id: str
    model_id: str
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
| `HallucinatedSymbol` | static | `retry_retrieval` — símbolo que NÃO EXISTE em lugar nenhum (`ImportError`, `AttributeError`, ou `NameError` sobre nome desconhecido). Mais documentação pode corrigir |
| `MissingImport` | static | `retry_generation` — `NameError` sobre símbolo que EXISTE em Qiskit/numpy e só não foi importado. Subconjunto estrito do caso acima, separado porque a ação é oposta: **nenhuma quantidade de documentação recuperada acrescenta uma linha de `import`**. A dica é DETERMINÍSTICA (a linha exata, sem LLM no laço), já que o símbolo resolveu para um módulo real. No baseline `ce9614fa3a6f60a6`, 112 runs — 39% das falhas estáticas — gastaram 5 iterações em `retry_retrieval` por esta causa. Ver F14, F3 e `static.py::missing_import_for` |
| `SyntaxError` | static | `retry_generation` |
| `TranspilationFailure` | static | `retry_generation` |
| `CircuitSerializationFailure` | static | `retry_generation` — o sandbox construiu e serializou o circuito, mas o leitor QPY do próprio Qiskit o recusou (bug 21: `IndexError` em `read_circuit`, tarefa QAOA). Gatilho NÃO reproduzido; a entrada existe para conter o crash e registrar `final_code` + fingerprint (sha256/tamanho/versão do Qiskit) para diagnosticar a próxima ocorrência. Ver `static.py::check_static` |
| `QubitIndexError` | static | `retry_generation` |
| `MissingMeasurement` | static | `retry_generation` |
| `ParameterBindingError` | static | `retry_generation` |
| `EndiannessSwap` | semantic | `retry_generation` |
| `WrongGateDecomposition` | semantic | `retry_generation` |
| `ConceptualAlgorithmError` | semantic | `retry_generation` |
| `NonUnitaryCircuit` | semantic | `retry_generation` — o circuito gerado tem medição/reset NÃO-FINAL, logo não há estado puro de saída para comparar com a referência. A verificação NÃO RODOU: `SemanticResult.unitary_equiv`/`state_equiv` ficam `None` (não `False`) e nenhuma fidelidade é reportada, porque não houve medição alguma. Medições FINAIS são removidas antes e nunca chegam aqui — `measure_all()` ao fim de código gerado é o normal, não um erro. Ver `validators/circuits.py` |
| `AssertionViolated` | semantic | `retry_generation` (US3, T086 — `assertion_check` writes one `ErrorRecord` per violated outcome) |
| `AssertionNotEvaluable` | semantic | `retry_generation` na 1ª ocorrência; `abort` (`status="assertion_not_evaluable"`, não `"aborted"`) na 2ª ocorrência CONSECUTIVA da MESMA asserção — única entrada desta tabela cujo roteamento depende de histórico entre iterações, não só do `error_type` isolado. Ver `critic.py::_is_repeated_not_evaluable` e `routing.py::terminal_status` |
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
| Offload de GPU verificado e REGISTRADO antes de qualquer tarefa, senão abortar | `runner.py::verify_gpu_offload` | D10c — **a regra anterior dizia `gpu_processor == "100% GPU"` e NUNCA foi executada**: `assert_full_gpu_offload` existia mas ninguém a chamava, e não funcionaria de qualquer forma, porque chama `ollama ps`/`nvidia-smi` por subprocesso e esses binários estão no host Windows enquanto o agente só alcança o Ollama por HTTP. `gpu_processor` é `None` nos 360 registros de todas as execuções já feitas. Agora medido por `/api/ps` (`size_vram/size`), gravado como `lib_versions["gpu_offload"]`, e verificado ANTES do reset de estado para não alterar o protocolo sob o qual o 0/360 foi medido. Ver F21 |
| Erro de infraestrutura excluído do denominador das métricas | `analysis/metrics.py` | contrato de erros |
| `status="harness_error"` distinto de `"infrastructure_error"` | `bench/runner.py::_run_one` | uma exceção inesperada é DEFEITO NOSSO, não instabilidade do mundo. Ambos saem do denominador, mas `infrastructure_error` é rotina e `harness_error` invalida o baseline — `analysis/metrics.py` imprime um aviso ANTES de qualquer taxa quando há algum. Registrar bug próprio no balde que ninguém conta contra nós é como uma suíte aprende a parecer saudável enquanto está quebrada (F10) |
| Exceção em uma execução não derruba a suíte | `bench/runner.py::_run_one` | Princípio III — a primeira execução ao vivo perdeu 360 runs para um único defeito; uma suíte que custa horas por bug não é rodada com frequência suficiente para servir de regressão |
| `status="rejected_input"` distinto de `"aborted"` — recusa antes da geração, não esgotamento de `MAX_ITER` | `planner.py` | FR-030, FR-031 — preserva SC-001 sem conflatar "nunca tentado" com "tentou e falhou" |
| `status="success"` só quando algo real sobre corretude funcional foi verificado E passou; senão `"completed_unverified"` | `routing.py::terminal_status` | Princípio II — uma invariante que depende de cada consumidor também ler o relatório é uma invariante que será quebrada por qualquer coisa que agregue `status` sozinha. Métricas NÃO PODEM colapsar os dois valores |
| `AgentState["guarantee_report"]` validado em runtime como `GuaranteeReport` | `routing.py::finalize` | o campo é `Any` por um limite do `get_type_hints()` do LangGraph (ver §Estado do grafo); a checagem que o mypy não pode fazer é feita à mão na fronteira de construção |
| Requisito reprovado VETA `functional_correctness_verified`, requisito aprovado nunca o ESTABELECE | `report.py` | T091 — requisitos vêm de um LLM (planner); um que passa só diz que circuito e leitura concordam, um que reprova diz que circuito e descrição discordam sobre algo checável |
