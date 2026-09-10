# Glossário — terminologia do projeto

**Feature**: `001-qcircuit-agent` | **Criado em**: 2026-09-08

Registro das convenções de nomenclatura. Serve a dois propósitos: manter o
vocabulário estável entre os artefatos e o código, e sinalizar os termos
ambíguos que precisam de tratamento explícito na dissertação.

Termos marcados **⚠ COLISÃO** têm mais de um sentido em uso no projeto ou na
literatura, e exigem desambiguação no texto final.

---

## 1. Verificação e avaliação

### ⚠ COLISÃO — Oráculo

Dois sentidos incompatíveis, ambos legítimos, ambos presentes no projeto.

**Sentido A — oráculo de verificação** (o uso deste projeto). O mecanismo que
decide se a saída está correta. Vem da engenharia de software, onde *test
oracle* é termo estabelecido desde os anos 1980. No código: `oracle_kind`,
`bench/oracles/`, `validate_oracles.py`.

**Sentido B — oráculo do algoritmo quântico**. A função caixa-preta consultada
*dentro* do circuito: o oráculo de Grover marca o estado buscado; Deutsch-Jozsa
consulta um oráculo para decidir se a função é constante ou balanceada. É parte
do circuito, não do critério de avaliação.

**Convenção**: na dissertação, usar **"oráculo de verificação"** na primeira
menção do sentido A e definir o termo; depois "oráculo" sozinho é aceitável
onde o contexto for inequívoco. Para o sentido B, sempre qualificar: "o oráculo
de Grover", "a função-oráculo do algoritmo". Frases como "o oráculo do
Deutsch-Jozsa" são ambíguas por construção — evitar.

O código mantém `oracle_kind` como está; o custo de renomear não compensa, e o
texto pode usar terminologia diferente do código.

**Enquadramento a explorar na escrita**: *the oracle problem* é a dificuldade
clássica de obter critério de correção automático — em geral alguém escreve
asserções à mão, o que limita a cobertura. O argumento do projeto é que
circuitos quânticos escapam disso: a equivalência unitária e a comparação de
estado fornecem oráculo automático e exato, derivado da matemática do domínio.
Não é um oráculo que alguém escreveu, é um que a estrutura do problema fornece.
Isso conecta o trabalho à literatura de teste e explica por que o método não
transfere trivialmente para geração de código comum — pergunta provável da
banca.

### Tipos de oráculo (`oracle_kind`)

| Valor | Verifica | Usar quando |
|---|---|---|
| `unitary` | matriz unitária completa | a tarefa especifica uma *transformação* (QFT) |
| `statevector` | estado a partir de \|0…0⟩ | a tarefa especifica um *estado* (Bell, GHZ, W, e — correção de D3e — Deutsch-Jozsa/Simon/Bernstein-Vazirani: oráculo linear fixo por tarefa, uma execução, estado de saída determinístico) |
| `distribution` | distribuição de medidas | implementado (`check_distribution`), mas nenhuma tarefa canônica construída até T047 usa este valor — candidato para Grover/QAOA quando avaliados por probabilidade de sucesso em vez de estado exato (D3e), não decidido ainda |
| `energy` | energia por diagonalização | VQE |

**`resource` NÃO é um `oracle_kind`** — foi erroneamente listado como um
nesta tabela e em `data-model.md` antes de D3h corrigir o registro.
`resource_check` (profundidade, contagem de CX sob um `coupling_map`) é
ORTOGONAL a `oracle_kind`: só precisa de um circuito de referência, que
`statevector`/`unitary` já fornecem, e roda automaticamente assim que
`semantic_check` popula `verification_method`. O que torna uma tarefa T4 é
`coupling_map` não-nulo no `TaskSpec`, não um `oracle_kind` diferente — ver
D3h, research.md, para o achado completo (incluindo que `oracle_kind=
"resource"` nunca teve despacho implementado em `graph.py`).

Ver D3c para a tabela de classificação por tarefa e o caso da QFT, que não pode
usar `statevector` porque QFT\|0⟩ degenera em superposição uniforme.

### Método de verificação (`verification_method`)

Como o veredito foi obtido, não o que foi verificado. Registrado no
`SemanticResult` para permitir segmentação na análise.

- `exact` — `Operator.equiv()`, custo 4ⁿ, teto de 12 qubits
- `composition` — composição com a inversa, custo 2ⁿ, probabilístico
- `statevector` — evolução de \|0…0⟩, custo 2ⁿ

### ⚠ COLISÃO — Fidelidade

Três métricas distintas com o mesmo nome curto. Sempre qualificar.

- **fidelidade de Hellinger** — entre distribuições de medida (`oracle_kind="distribution"`)
- **fidelidade unitária** — \|Tr(U_ref† U_gen)\|/dim, métrica contínua quando `equiv()` falha
- **fidelidade de estado** — \|⟨ψ_ref\|ψ_gen⟩\|, no caminho `statevector`

### Camada de verificação

Os quatro estágios da cascata determinística, nesta ordem: executabilidade →
transpilação → corretude funcional → recursos. **Não confundir com fase**
(organização das tarefas) nem com **condição** (braço experimental).

---

## 2. Experimento

### ⚠ COLISÃO — Tarefa

**Tarefa de avaliação** (`TaskSpec`) — um item do dataset: enunciado, oráculo,
tier. Identificada por `task_id` (`t2_grover_3q_perturbed`).

**Tarefa de implementação** — uma linha do `tasks.md`. Identificada por `Txxx`
(T017, T044).

Na dissertação, preferir **"item de avaliação"** para o primeiro sentido. O
segundo não aparece no texto final.

### Condição

Um dos cinco braços experimentais. **Não** é "condição" no sentido de
pré-requisito.

| | RAG | Loop |
|---|---|---|
| C1 zero-shot | ✗ | ✗ |
| C2 few-shot | ✗ | ✗ |
| C3 RAG puro | ✓ | ✗ |
| C4 loop puro | ✗ | ✓ |
| C5 completo | ✓ | ✓ |

### Tier

Nível de dificuldade do item (T1 primitivas, T2 algoritmos, T3 formulação, T4
hardware-aware). Colide visualmente com os IDs `Txxx` das tarefas de
implementação — no texto, escrever "tier 2", não "T2".

### Canônica / perturbada

**Canônica** — a formulação padrão de um item (estado de Bell, GHZ de 3
qubits). Presente em todo corpus de treino, logo suscetível a memorização.

**Perturbada** — variante pareada que quebra a memorização sem mudar a
natureza da tarefa. Cinco famílias: fase relativa, restrição de conjunto de
portas, convenção de ordenação, composição, parametrização simbólica.

**`delta_perturbacao`** — diferença de desempenho entre as duas. Métrica de
primeira classe, não ressalva.

### Ablação

Comparação entre condições que diferem em um único componente, para atribuir o
ganho. C3 vs C1 isola o RAG; C4 vs C1 isola o loop; C5 vs ambas testa
complementaridade.

### Execução

Uma combinação (item, gerador, condição, seed). Persistida como `RunRecord`.
5.400 no total. **Não confundir com iteração**, que é uma tentativa dentro de
uma execução.

---

## 3. Recuperação

### ⚠ COLISÃO — Registro

**Registro (sentido A)** — categoria de material recuperado: `api_chunks`
(documentação de interface) vs `paper_chunks` (descrição de algoritmo). Do
inglês *register*, no sentido linguístico. Usado em `split_by_register` e no
prefixo de chunk (`[method]`, `[class]`, `[migration]`).

**Registro (sentido B)** — uma linha de resultado (`RunRecord`), ou o ato de
registrar uma decisão. Do inglês *record*.

Ambos aparecem no projeto. Na dissertação, usar **"registro"** apenas para o
sentido A e **"linha de resultado"** ou "`RunRecord`" para o sentido B.

### Chunk / unidade de recuperação

Fragmento indexado do corpus. Chunking é **code-aware**: assinatura, docstring
e exemplo de um mesmo símbolo permanecem íntegros na mesma unidade.

### Denso / esparso

**Denso** — vetor de embedding, captura intenção. **Esparso** — BM25 com
modifier IDF, captura correspondência literal de identificador.

Os dois vivem como vetores nomeados no mesmo ponto do Qdrant e são fundidos por
RRF. A distinção importa porque a busca densa confunde `RZGate` com `RXGate`,
que é o caso crítico do domínio.

### Obsoleto (`deprecated`)

Marcação de payload. Material obsoleto **não é filtrado** — chega ao gerador
rotulado como não utilizável, com o campo `replacement` visível. O contraste
explícito corrige a memória do modelo; a omissão não (D7).

---

## 4. Identificadores

| Prefixo | O quê | Origem |
|---|---|---|
| `FR-xxx` | requisito funcional | spec-kit |
| `SC-xxx` | critério de sucesso | spec-kit |
| `US1`–`US6` | história de usuário | spec-kit |
| `P1`–`P6` | prioridade | spec-kit |
| `Txxx` | tarefa de implementação | spec-kit |
| `CHKxxx` | item de checklist | spec-kit |
| `H1`–`H5` | hipótese de pesquisa | **local** |
| `Dx`, `Dxb` | decisão técnica no `research.md` | **local** |
| `M0`–`M6` | marco | **local** |
| `C1`–`C5` | condição experimental | **local** |

Os identificadores locais não são do spec-kit e não sobrevivem a
`/speckit.plan`, que regenera o `research.md` a partir do template. E não
significam nada para leitor externo: na dissertação, as decisões precisam ser
narradas, não referenciadas por código.

---

## 5. Nome do projeto

Três nomes em circulação, com histórico:

- **`qcircuit-agent`** — slug nos artefatos de especificação e no branch
- **Quantum-RAG** — diretório do repositório
- **LLM Quantum Copilot** — nome em consideração

**Ponto de atenção**: "Quantum RAG" já designa outra coisa na literatura —
recuperação acelerada por algoritmos quânticos. Este projeto é o inverso: RAG
clássico sobre documentação quântica. Risco de confusão na indexação e na
banca.

"Copilot" carrega expectativa de autocomplete interativo, e o sistema é um
pipeline de síntese verificada em lote. Também não menciona a verificação, que
é a contribuição.

**Pendente**: fixar o título formal da dissertação, que não precisa coincidir
com o nome do repositório. Algo que nomeie a verificação — "síntese verificada
de circuitos quânticos com agentes LLM" — comunica melhor a contribuição.

---

## 6. Termos a evitar

| Evitar | Usar | Por quê |
|---|---|---|
| "o oráculo do Grover" | "a função-oráculo do Grover" | ambíguo com oráculo de verificação |
| "fidelidade" sem qualificar | nomear a métrica | três métricas distintas |
| "T2" para tier | "tier 2" | colide com IDs de tarefa |
| "o RAG melhorou X%" | nomear a condição (C3 vs C1) | RAG não é braço isolado |
| "o sistema acertou" | nomear a camada aprovada | corretude é hierárquica |
| "validou" para o LLM | "gerou" / "propôs" | validação é sempre determinística (Princípio I) |

A última linha importa mais do que parece: dizer que o modelo "validou" algo
contradiz a tese central do trabalho.
