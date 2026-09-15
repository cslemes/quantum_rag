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
| `assertion_check` **novo** | `code`, `assertions` (parseadas) | `list[AssertionOutcome]` | não |
| `semantic_check` (condicional — só se `oracle_ref`) | `code`, `oracle` | `SemanticResult` | não |
| `resource_check` (condicional — só se `coupling_map`) | `code`, `coupling_map` | `ResourceResult` | não |
| `critic` | estado | `CriticDecision` | sim |
| `finalize` | estado terminal | `GuaranteeReport` **novo** | não |

### Roteamento do critic (adiciona uma linha a v1)

| Sinal | Ação | Justificativa |
|---|---|---|
| Símbolo obsoleto, `ImportError`, `AttributeError` | `retry_retrieval` | falta de contexto de API → reconsultar com hint de versão |
| Falha de sintaxe, transpilação, qubit fora de faixa | `retry_generation` | erro local → regerar com traceback |
| Unitária diverge, fidelidade < tolerância | `retry_generation` | erro conceitual → regerar com diff |
| **Asserção violada** | `retry_generation` | erro conceitual nomeado — mesma classe de `WrongGateDecomposition`, mas contra o que o USUÁRIO declarou, não contra uma referência interna |
| Correto, `depth_ratio > max_depth_ratio` | `optimize` | regerar pedindo redução de CX |
| `iteration >= MAX_ITER` | `abort` | registrar falha; não mascarar com força bruta |

Falha transitória do provedor externo continua fora do `critic` — tratada em
`llm/base.py` (inalterado de v1).

### Verificação sem referência — linguagem de asserção (US3)

**Decisão de desenho**: gramática mínima, quatro categorias (não uma
linguagem geral de propriedades) — cobre exatamente os quatro exemplos do
`spec.md`, nada além disso nesta fase. Parseada por um parser determinístico
próprio (não por um LLM) — é o que torna FR-013 ("asserção mal formada
recusada explicitamente") uma checagem de gramática, não uma interpretação
sujeita a ambiguidade de modelo.

```python
# src/qcagent/state.py — T082

class AmplitudeEquality(BaseModel):
    kind: Literal["amplitude_equality"] = "amplitude_equality"
    basis_state_a: str            # ex.: "000" — comprimento deve bater com n_qubits
    basis_state_b: str
    # Magnitude apenas, por padrão — mesma lição de D3c/F1 (report-notes.md):
    # fase global não é comparável entre implementações corretas distintas.
    # Comparar fase RELATIVA é opt-in, nunca o default.
    relative_phase_rad: float | None = None

class MeasurementDeterminism(BaseModel):
    kind: Literal["measurement_determinism"] = "measurement_determinism"
    qubits: list[int]
    expected_value: str            # bitstring, mesmo comprimento de `qubits`

class OperatorEigenstate(BaseModel):
    kind: Literal["operator_eigenstate"] = "operator_eigenstate"
    pauli_string: str              # um caractere I/X/Y/Z por qubit
    eigenvalue: Literal[1, -1]

class GateRestriction(BaseModel):
    kind: Literal["gate_restriction"] = "gate_restriction"
    allowed_gates: list[str]

Assertion = Annotated[
    AmplitudeEquality | MeasurementDeterminism | OperatorEigenstate | GateRestriction,
    Field(discriminator="kind"),
]

class AssertionOutcome(BaseModel):
    assertion: Assertion
    passed: bool
    detail: str
```

**Avaliação — `src/qcagent/validators/assertions.py` (T083–T084b)**: pura
`qiskit.quantum_info`, sem amostragem/shots (é simulação exata, não o
regime de ruído estatístico de `check_sanity_seeds` em `bench/
validate_oracles.py` — as duas tolerâncias não devem ser confundidas, a
mesma distinção que `PEAKEDNESS_THRESHOLD` já fazia em v1).

- `AmplitudeEquality`: `abs(psi[a]) ≈ abs(psi[b])`.
- `MeasurementDeterminism`: `Statevector.probabilities(qargs=qubits)` tem
  massa ≈1 no `expected_value`.
- `GateRestriction`: puramente estrutural sobre `circuit.data` — não precisa
  de simulação.
- `OperatorEigenstate`: **o único ponto de risco de desenho desta seção**.
  Checar `‖H\|ψ⟩ − λ\|ψ⟩‖ ≈ 0` (norma do resíduo), **nunca** só `⟨ψ\|H\|ψ⟩ ≈ λ`
  (valor esperado). Um valor esperado correto NÃO implica que o estado seja
  um autoestado — uma superposição de autoestados cujos autovalores
  cancelam para a média certa passaria um checador que olhasse só o valor
  esperado. Esta é exatamente a estrutura do achado F2 (`report-notes.md`:
  "checks por medição podem ser estruturalmente cegos, não só frouxos") —
  aplicada aqui ao próprio verificador novo, antes de ele existir em
  produção, não depois de um bug real forçar a correção. T084b exige um
  teste de regressão com um estado deliberadamente NÃO-autoestado mas de
  valor esperado correto, que deve REPROVAR, escrito antes de aceitar a
  implementação.

**Malformação** (FR-013): comprimento de bitstring/Pauli-string incompatível
com `n_qubits`, índice de qubit fora de faixa, categoria desconhecida —
todos detectados na etapa de parsing, ANTES de qualquer geração (T090
estende o mecanismo de `status="rejected_input"` que T024b já implementa em
v1, em vez de criar um segundo caminho de recusa).

**Escopo explicitamente fora desta fase**: os `Requirement`s de
`kind="property"`/`kind="output_format"` que o `planner` já extrai (FR-009)
NÃO ganham conversão automática para a gramática acima nesta fase — isso
exigiria uma camada de tradução de linguagem natural para a gramática
formal, que só pode ser feita hoje por um LLM. Isso é permitido pelo
Princípio I (papel de "gerador de hipótese"), mas é escopo genuinamente
novo, não pedido por nenhuma FR de v2 explicitamente, e arriscaria
reintroduzir a mesma ambiguidade que a gramática formal existe para evitar.
Só `kind="n_qubits"` e `kind="gate_set"` (checáveis sem tradução nenhuma,
T091) ganham verificação automática nesta fase. Registrado como decisão de
escopo, não como lacuna esquecida — mesmo padrão de honestidade que D3d
(v1) usou para deixar teleporte fora do conjunto canônico.

### Relatório de garantia (US4)

```python
# src/qcagent/report.py — T093

class GuaranteeReport(BaseModel):
    model_config = ConfigDict(extra="forbid")   # ver abaixo — é a garantia em si

    executed: bool
    transpiled: bool
    requirements_checked: list[str]          # n_qubits/gate_set — T091
    assertions: list[AssertionOutcome]        # vazia se nenhuma foi declarada
    resource: ResourceResult | None
    hardware_note: str | None                 # US5 — "comportamento sob ruído", nunca "verificação"

    @computed_field
    @property
    def functional_correctness_verified(self) -> bool:
        return bool(self.assertions) and all(a.passed for a in self.assertions)
```

**A decisão de desenho que carrega o Princípio II inteiro**:
`functional_correctness_verified` é um `@computed_field`, não um campo
comum — não pode ser passado ao construtor. Com
`model_config = ConfigDict(extra="forbid")`, tentar
`GuaranteeReport(functional_correctness_verified=True, assertions=[])`
levanta `ValidationError` em vez de silenciosamente aceitar um relatório que
mente. **A invariante de SC-004 é estruturalmente impossível de violar por
construção**, não apenas coberta por um teste que alguém poderia esquecer
de rodar. T095 (abaixo, em tasks.md) é o teste obrigatório que confirma isso
— tanto o caso direto (relatório vazio não afirma corretude) quanto o caso
adversário (tentar construir o relatório mentiroso é rejeitado pela própria
classe).

`render_guarantee_report()` (T094) enumera cada asserção com veredito
individual (FR-011, FR-015), inclui a frase de não-verificação explícita
quando `functional_correctness_verified=False` (FR-016), e nunca usa
linguagem que equipare "executa e respeita restrições" a "está correto"
(FR-017) — essa é uma checagem de VOCABULÁRIO no renderizador, testada
diretamente (T095), não uma convenção de estilo.

### Armadilhas endereçadas no desenho

Preservadas de v1 (continuam verdadeiras, nenhuma invalidada pela migração):

- **Fase global**: usar `Operator.equiv()`/comparação de magnitude, nunca
  comparação direta de amplitudes complexas. Aplica-se também a
  `AmplitudeEquality` (acima) — mesma lição, novo lugar.
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
  `OperatorEigenstate`). Testar o verificador contra um caso adversário
  ANTES de confiar nele — não depois de um bug real forçar a correção,
  diferente de como F2 foi descoberto originalmente em v1 (um bug real de
  QFT). A lição de v1 se paga aplicada preventivamente em v2.

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
