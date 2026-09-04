# Research: Phase 0 — Decisões técnicas

**Feature**: `001-qcircuit-agent` | **Data**: 2026-08-11

Cada incógnita do `plan.md` resolvida no formato Decisão / Razão / Alternativas.
Itens marcados **[PENDENTE-PILOTO]** só fecham com dados de T055.

---

## D1 — Backend de simulação

**Decisão**: Qiskit Aer, método `statevector`, **`device="CPU"` por padrão**.
GPU acionada apenas por limiar (`n_qubits >= 18`). Pinado em `qiskit==1.2.4` /
`qiskit-aer==0.15.1`.

**Razão**: statevector é exato e habilita comparação de estado, que é o oráculo
mais forte disponível. A escolha de CPU como padrão é contraintuitiva e merece
justificativa explícita: **quase todo o dataset vive abaixo de 12 qubits**, faixa
em que a GPU perde para a CPU. O overhead de lançamento de kernel e a
transferência host↔device dominam o custo em circuitos pequenos.

A documentação de escolha de hardware do qsim mede exatamente isso e serve de
evidência externa: GPU só supera CPU de forma significativa acima de 20 qubits,
e nos benchmarks de 16 qubits uma A100 marca 0,007 s contra 0,009 s de uma CPU
de nuvem — diferença dentro do ruído. Não há razão para pagar complexidade de
CUDA por isso.

**Segundo motivo, específico deste projeto**: o Qwen2.5-Coder 7B em Q4_K_M ocupa
~4,5 GB dos 8 GB da RTX 3070. Rodar o simulador na mesma GPU durante a condição
C5 com gerador local disputa VRAM com o modelo que está gerando. Manter a
simulação fora da GPU elimina essa contenção sem custo.

**Alternativas rejeitadas**:
- `qiskit-aer-gpu` como padrão — mais lento na faixa dominante e disputa VRAM
  com o Ollama. Mantido como dependência opcional para os poucos itens T4.
- `matrix_product_state` — escala mais, mas só para estados pouco emaranhados;
  GHZ e QAOA violam isso por construção.
- **qsim / qsimcirq** — a própria documentação do Google desaconselha: abaixo de
  20 qubits o overhead da camada de tradução do qsimcirq domina o tempo, e o
  qsim não é otimizado para circuitos pequenos; abaixo de 17 qubits nem sequer
  usa mais de uma thread, por overhead de OpenMP. Somado a isso, exigiria
  conversão Qiskit↔Cirq, que introduziria erros de convenção — justamente a
  classe de erro que o projeto quer medir.
- **cuQuantum** — superior acima de 25 qubits, irrelevante aqui, e disputaria
  VRAM com o Ollama.
- Simulador em nuvem — latência e custo em 5.400 execuções, sem ganho.

---

## D1b — Onde está o gargalo real

**Decisão**: pool de workers pré-aquecidos em `sandbox.py`, reciclados a cada N
execuções, em vez de spawn de subprocesso por execução.

**Razão**: a intuição de que simulação quântica é cara não se aplica a este
projeto. Bell tem 2 qubits, GHZ ~5, QFT ~8 — simulam em milissegundos. O custo
dominante é o overhead por chamada: spawn do subprocesso mais `import qiskit`,
que sozinho leva ~1–2 s.

**Medido** (`scripts/bench_pool.py`, 20 submits sequenciais, um único worker,
dentro do container Linux — ver D15):

| | wall_time_s | exec_time_s | overhead_s |
|---|---|---|---|
| submit #1 | 1,5829 | 0,0011 | 1,5818 |
| submits #2–20 (média) | 0,0007 | 0,0005 | 0,0002 |

O custo do `import qiskit` é pago uma única vez, na primeira chamada ao
worker pré-aquecido — não a cada submit. Extrapolado para os ~27.000 chamadas
da matriz (5.400 execuções base × até ~5 tentativas), pagar 1,58 s por
chamada em vez de amortizá-lo uma vez custaria **~11,9 h** contra a meta de
72 h — exatamente o custo que o pool existe para evitar, e esta medição
confirma que ele evita.

**Este resultado depende de `fork`** (o método de início padrão do
`multiprocessing` no Linux: o processo filho herda o estado do pai por
copy-on-write). Não vale sob `spawn` nativo do Windows, onde cada processo
novo reexecuta o interpretador do zero — razão pela qual D15 exige que tanto
o desenvolvimento quanto a matriz experimental rodem no ambiente
containerizado Linux, nunca nativamente no Windows.

**Como preservar o isolamento** (Princípio constitucional, FR-025): o worker
continua sendo processo separado do orquestrador. O que muda é que ele é
reutilizado em vez de recriado. Reciclagem a cada N execuções evita acúmulo de
estado entre tarefas. O `timeout` e a denylist permanecem inalterados.

**Cuidado**: medir o tempo de simulação separado do tempo de overhead na
telemetria. Reportar latência sem essa separação torna a métrica dependente da
infraestrutura e não do sistema sob teste.

---

## D3b — Teto do oráculo de equivalência unitária

**Decisão**: `Operator.equiv()` como caminho exato **até 12 qubits**;
verificação por composição com a inversa acima disso.

**Razão**: `Operator(qc)` materializa a matriz densa 2ⁿ × 2ⁿ em complex128, ou
seja 4ⁿ elementos. E `equiv()` precisa de duas simultaneamente:

| qubits | uma matriz | viável em 32 GB? |
|---|---|---|
| 12 | 268 MB | sim |
| 13 | 1,07 GB | sim, apertado |
| 14 | 4,3 GB | não (duas + intermediários) |
| 15 | 17 GB | não |
| 20 | 17,6 TB | absurdo |

O teto real do oráculo unitário é ~13 qubits, **não 20**. Isso invalida a regra
de validação originalmente escrita em T052 e teria passado despercebido até
alguém tentar rodar um item T4 grande.

**Verificação por composição** (custo 2ⁿ em vez de 4ⁿ):

```python
composed = qc_gen.compose(qc_ref.inverse())
# Se composed ≡ I, todo estado retorna inalterado a menos de fase global
for seed in range(k):                     # k=5 basta
    psi = random_statevector(2**n, seed=seed)
    out = psi.evolve(composed)
    if not np.isclose(abs(out.inner(psi)), 1.0, atol=1e-9):
        return False
```

Com 5 estados Haar-aleatórios a probabilidade de falso positivo é desprezível.
A tolerância a fase global vem de graça no `abs()` do produto interno. O custo
cai para statevector, viável até 22 qubits.

**Trade-off aceito e documentado**: o teste passa de exato para probabilístico
acima de 12 qubits. Honesto, desde que declarado na dissertação e registrado no
`SemanticResult` (campo `verification_method`) para que a análise possa
segmentar por método.

**Alternativa rejeitada**: reduzir o dataset ao teto de 12 qubits — descartaria
a maior parte do tier T4, que é onde restrições de hardware ficam interessantes.

---

## D2 — Framework de orquestração

**Decisão**: LangGraph com `StateGraph` e reducers explícitos.

**Razão**: o fluxo tem ciclo real (`critic` volta para `retriever` ou
`generator`), o que descarta cadeias lineares. Persistência de estado e
`interrupt_before` cobrem o requisito de revisão humana opcional (FR-010) sem
código próprio.

**Alternativas rejeitadas**:
- Implementação do zero — mais controle, mas reimplementa checkpointing e
  telemetria sem ganho científico.
- Frameworks de agente conversacional — o fluxo aqui é determinístico e
  roteado por erro estruturado, não por negociação entre agentes.

---

## D3 — Verificação de equivalência

**Decisão**: `Operator(qc).equiv()` como primitiva primária **até 12 qubits**;
acima disso, verificação por composição (ver D3b). Fidelidade de Hilbert-Schmidt
normalizada como métrica contínua quando `equiv()` retorna falso.

**Razão**: `equiv()` já trata fase global, que é a armadilha número um. Duas
implementações corretas do mesmo circuito diferem rotineiramente por e^{iθ}, e
comparação direta de matrizes as marcaria como erradas.

**Cuidado registrado**: Qiskit é little-endian. Referências extraídas de artigos
ou portadas do PennyLane frequentemente usam a convenção oposta. O verificador
testa ambas as ordenações e reporta `EndiannessSwap` como categoria distinta —
tratar isso como erro comum inflaria artificialmente a taxa de falha.

---

## D4 — Modelo de embedding [PENDENTE-PILOTO]

**Decisão preliminar**: avaliar dois candidatos por `recall@8` nas 50 consultas
sintéticas de T040 — um modelo específico de código e um multilíngue geral.

**Razão**: o corpus é majoritariamente código e docstring em inglês, o que
favorece modelo de código; mas os enunciados podem vir em português, o que
favorece multilíngue. A decisão depende de qual lado domina empiricamente.

**Critério de desempate**: se ambos passarem de 0,85, escolher o menor —
inferência local é rodada 5.400 vezes.

---

## D5 — Estratégia de busca

**Decisão**: híbrido esparso + denso numa única coleção Qdrant, fundidos por RRF
via Query API nativa, top-8 final.

**Razão**: busca densa falha exatamente no caso crítico deste domínio.
`RZGate` e `RXGate` ficam a distância mínima no espaço de embedding, e recuperar
o errado produz o tipo de alucinação que o projeto existe para eliminar. O vetor
esparso (BM25 via `fastembed`) resolve correspondência literal de identificador;
o denso cobre intenção ("como aplicar rotação controlada parametrizada").

**Alternativas rejeitadas**:
- Só denso — falha no caso crítico.
- Só esparso — não recupera por intenção quando o usuário não sabe o nome da API.
- Fusão RRF em código próprio — desnecessária: a Query API do Qdrant faz
  `prefetch` das duas buscas e funde num round-trip. Menos código, menos latência.
- Reranker cross-encoder — custo adicional por consulta, deixado como trabalho
  futuro. (O Qdrant permite adicionar isso depois como estágio final da Query API
  sem reindexar.)

---

## D5b — Vector store

**Decisão**: Qdrant 1.12, self-hosted via Docker Compose, coleção única com
vetores nomeados (`dense` e `sparse`).

**Razão**: três fatores decidiram.

1. **Busca híbrida nativa.** Qdrant trata denso e esparso como vetores nomeados
   do mesmo ponto e funde por RRF na própria Query API. A alternativa exigiria
   manter índice lexical separado e escrever a fusão à mão — mais código para
   testar e mais um ponto de dessincronização entre índices.
2. **Filtragem por payload sem penalidade.** O filtro por `library_version` e
   `deprecated` (FR-011, FR-014) é usado em toda consulta. Qdrant aplica
   filtro **durante** a travessia do índice HNSW, não como pós-filtro — o que
   evita o modo de falha em que o top-k pré-filtro é engolido inteiro pelo
   filtro e a consulta volta vazia. Esse é o caso exato deste corpus, onde
   material obsoleto é abundante.
3. **Snapshot de coleção.** `POST /collections/{name}/snapshots` produz um
   artefato restaurável do índice inteiro. Isso serve ao Princípio II: o corpus
   recuperável na semana 4 pode ser reconstruído bit a bit na semana 11, mesmo
   que a documentação upstream tenha mudado. É um requisito de reprodutibilidade
   que uma extensão de banco relacional não atende com a mesma limpeza.

**Alternativas rejeitadas**:
- **PostgreSQL + pgvector** — atraente por já existir no stack e evitar um
  serviço, mas o híbrido exigiria combinar `tsvector` com vetor denso em SQL e
  implementar RRF manualmente; e o filtro por payload em HNSW é pós-filtro,
  o que degrada recall justamente nas consultas filtradas por versão.
- **FAISS em processo** — mais rápido e sem serviço, mas sem filtragem por
  metadado nem persistência gerenciada. O filtro por versão é central aqui, não
  acessório.
- **Serviço gerenciado em nuvem** — custo recorrente e latência de rede
  multiplicada por 5.400 execuções, sem ganho para um corpus de ~15k unidades.

**Consequência operacional**: mais um serviço no `docker-compose.yml`. Custo
aceito — o corpus cabe folgadamente em memória e o container é leve.

**Cuidado registrado**: fixar a versão da imagem (`qdrant/qdrant:v1.12.x`).
Mudança de versão do índice entre a construção do corpus e a rodada final
invalida a comparação tanto quanto mudança de versão do Qiskit.

---

## D6 — Chunking

**Decisão**: chunking por símbolo. Assinatura + docstring + exemplo permanecem
na mesma unidade. Se exceder o limite, dividir por exemplo replicando a
assinatura no cabeçalho de cada pedaço.

**Razão**: chunking por janela de tokens separa a assinatura do exemplo de uso —
e é precisamente a assinatura correta que impede a alucinação de API. Um chunk
com o exemplo mas sem a assinatura é pior que nenhum chunk.

---

## D7 — Tratamento de API obsoleta

**Decisão**: material obsoleto entra no contexto **rotulado como não
utilizável**, com a substituição indicada, em vez de ser filtrado fora.

**Razão**: o modelo já tem a construção obsoleta memorizada dos dados de treino.
Omitir o material não desfaz essa memória; declarar explicitamente "`execute()`
foi removido, use `backend.run()`" corrige ativamente. Contraste explícito é
mais eficaz que ausência.

---

## D8 — Teto de iterações [PENDENTE-PILOTO]

**Decisão preliminar**: `MAX_ITER = 5`, validar saturação em T056.

**Razão**: valor escolhido para não truncar o efeito que o experimento quer
medir. Se o piloto mostrar que a curva satura em 3, reduzir — cada iteração a
mais custa dinheiro em 5.400 execuções e não altera a conclusão.

---

## D9 — Idioma dos prompts [PENDENTE-PILOTO]

**Decisão preliminar**: prompts de sistema em inglês, enunciados de tarefa em
inglês, com braço de controle em português no piloto.

**Razão**: toda a documentação recuperada é em inglês; misturar idiomas entre
consulta e corpus tende a degradar a recuperação. Mas isso é hipótese, não fato,
e o resultado é interessante por si só num programa brasileiro. Medir e
documentar, seja qual for o resultado.

---

## D10 — Seleção de geradores

**Decisão**: dois de fronteira acessados por API, de famílias distintas, mais
**Qwen2.5-Coder 7B (Q4_K_M via Ollama)** como gerador local.

**Razão**: famílias distintas controlam o efeito de idiossincrasia de um único
provedor. O gerador local é o que dá peso prático ao trabalho — se o loop fizer
um 7B local se aproximar de um modelo de fronteira, o resultado tem implicação
de custo, privacidade e soberania de dados.

**A escolha do 7B não é inércia: é resultado medido.** Modelos Coder de geração
mais recente (Qwen3-Coder 30B-A3B, Qwen 4 Coder 32B-A3B, Qwen3-Coder-Next
80B-A3B) são todos MoE cujos pesos totais excedem os 8 GB da RTX 3070 — MoE
reduz o cômputo por token, não a memória residente. Não há tag oficial de
Qwen3-Coder abaixo de 10 GB.

### Benchmark executado (2026-08-12, RTX 3070 8 GB)

| | qwen2.5-coder:7b | qwen3-coder:30b |
|---|---|---|
| Tamanho | 4,7 GB | 19 GB |
| Processor (`ollama ps`) | **100% GPU** | 67%/33% CPU/GPU |
| Prefill | **492 tok/s** | 36 tok/s |
| Geração | **74,7 tok/s** | 14,1 tok/s |
| Por chamada C5 (~5k in / 400 out) | ~15,6 s | ~167 s |
| Braço local (1.800 exec. × 2,5 chamadas) | **~20 h** | **~209 h** |

O 30B fica 10× fora do orçamento contra a meta de 72 h da matriz completa.
Rejeitado por tempo de execução, não por qualidade — distinção que deve constar
na dissertação.

**Cuidado de medição registrado**: a primeira medição do 7B deu 8 tok/s de
prefill e sugeriu falsamente que rodava em CPU. Era `load_duration` de 23 s
contaminando o número. Toda medição de throughput exige aquecimento prévio do
modelo; sem isso a conclusão se inverte.

**Alternativa a reavaliar**: se houver upgrade para GPU de 16 GB+, refazer este
benchmark. Um MoE de geração atual rodando inteiro em VRAM mudaria a tese de
"7B de 2024 se aproxima de fronteira" para algo mais forte.

---

## D10b — Janela de contexto do gerador local

**Decisão**: `num_ctx` fixado explicitamente em cada chamada da API do Ollama
(16384 como ponto de partida), nunca herdado do default do servidor.

**Razão**: este é o achado mais perigoso do benchmark. O `ollama ps` mostrou
**CONTEXT 4096** — o default do Ollama — para ambos os modelos. Na condição C5
o prompt carrega 8 chunks de documentação, requisitos e histórico de erros,
o que ultrapassa 4096 com folga. **O Ollama trunca silenciosamente**: sem erro,
sem aviso, sem rastro no log.

O modo de falha é seletivo e por isso especialmente traiçoeiro: C1 (zero-shot,
prompt curto) passa intacta, C5 perde parte dos chunks recuperados. O
experimento mediria "RAG não ajuda" quando na verdade o RAG nunca chegou ao
modelo. **Isso invalidaria H1 e H3 sem deixar evidência nos resultados.**

Fixar via `num_ctx` no corpo da requisição, e não via `OLLAMA_CONTEXT_LENGTH`,
garante que o valor efetivo fique registrado no `RunRecord` em vez de depender
de variável de ambiente da máquina — requisito do Princípio II.

**A verificar no piloto**: custo de VRAM do KV cache a 16K. Estimativa grosseira
para este modelo é ~900 MB, o que somado aos 4,7 GB de pesos daria ~5,6 GB —
margem apertada nos 8 GB. Medir com `ollama ps` após uma chamada de contexto
real, não confiar na estimativa.

**Salvaguarda obrigatória**: contar os tokens do prompt antes de enviar e
levantar erro se exceder `num_ctx`. Truncagem silenciosa nunca deve ser possível
no caminho experimental.

---

## D10c — Contenção de VRAM com o ambiente desktop

**Decisão**: registrar estado da GPU em cada `RunRecord` e executar o braço
local com o desktop limpo.

**Razão**: durante o benchmark, o `nvidia-smi` reportou 6.030 MiB de 8.192 em
uso e 93% de utilização, com Chrome, Edge, Teams, WhatsApp, VS Code, Docker
Desktop e NVIDIA Broadcast todos ocupando a GPU — cerca de 1,3 GB fora do
Ollama.

Com pesos + KV cache em ~5,6 GB, a margem é pequena e, pior, **variável**. Uma
rodada com o Teams aberto tem menos VRAM disponível que outra sem. Se cruzar o
limite, o Ollama faz offload parcial e o throughput despenca no meio do
experimento, tornando a latência não reprodutível — violação direta do
Princípio II.

**Mitigações**:
1. Gravar `memory.used` (via `nvidia-smi`) e a string `PROCESSOR` do `ollama ps`
   em cada `RunRecord`. Permite detectar em análise se alguma execução sofreu
   offload, e excluí-la ou segmentá-la.
2. Executar o braço local com o desktop fechado, e documentar isso no protocolo.
3. Abortar a execução se `PROCESSOR` não for "100% GPU" — melhor falhar alto que
   contaminar a métrica de latência em silêncio.

---

## D11 — Isolamento de execução

**Decisão**: subprocesso separado com timeout, denylist de imports e
serialização QPY do circuito resultante.

**Razão**: contêiner efêmero por execução seria mais seguro, mas o overhead de
inicialização multiplicado por 5.400 execuções é proibitivo. Os enunciados são
autorais e não adversariais — a ameaça real é código gerado que trava ou escreve
onde não deve, não exploração deliberada. Essa premissa está registrada no
`spec.md` (Assumptions) e limita o uso do sistema a contexto de pesquisa.

---

## D12 — Estratégia de perturbação [PENDENTE-PILOTO]

**Decisão**: cinco famílias, com quantidade por família definida após teste piloto
de dificuldade.

| Família | Exemplo |
|---|---|
| Fase relativa | GHZ com fase φ=2π/5 no q2 |
| Restrição de gate set | apenas {RZ, SX, CX} |
| Convenção de ordenação | endianness explicitamente invertido |
| Composição | QFT seguida de difusor de Grover no mesmo registrador |
| Parametrização simbólica | `Parameter` em vez de valor fixo |

**Razão**: a perturbação precisa quebrar a memorização sem tornar o item
insolúvel. Se a taxa de acerto na variante perturbada cair a zero em todas as
condições, o item não mede nada — vira ruído.

**Critério**: descartar perturbações em que o gerador de fronteira, na condição
completa, não passe de 20% de acerto.

---

## D14 — Payload de diagnóstico semântico

**Decisão**: para falhas semânticas, `ErrorRecord.payload` carrega um diff
estrutural, não só o escalar de fidelidade já presente em `message`:
`expected_n_qubits`/`actual_n_qubits` e `expected_gate_counts`/
`actual_gate_counts` (contagem por tipo de gate em cada lado), mais se a
checagem de bits invertidos também bateu (`reversed_bit_order_matches`).
`nodes/generator.py` (`render_structural_diff`) formata isso como texto
legível no prompt — nunca um dump bruto do dict.

A sequência ordenada de `(gate, qubits)` de cada lado
(`expected_gate_sequence`/`actual_gate_sequence`) também é calculada e
anexada ao payload, mas **deliberadamente não é renderizada** — ver a
correção abaixo.

**Razão**: um escalar de fidelidade diz "está errado" sem dizer "errado
como". Numa rodada real, isso produziu exatamente o sintoma que motivou
este registro: iteração 1 reportou `fidelidade=0.5000`, iteração 3 reportou
`fidelidade=0.0000` — nenhuma pista sobre o quê mudar, e a iteração 3
reproduziu a iteração 1 palavra por palavra. Diagnóstico estruturado é a
tese central deste projeto (verificação determinística, Princípio I) — expor
só um escalar no laço de correção é a versão mais fraca possível dessa tese,
justamente no ponto em que ela deveria valer mais: o sinal que volta para o
gerador.

**Correção — o diff posicional foi tentado e revertido por ser ativamente
enganoso.** A primeira versão desta decisão também comparava
`expected_gate_sequence[i]` com `actual_gate_sequence[i]` posição a posição
e renderizava a divergência como prescrição ("esperado X aqui"), motivada
por um caso real onde contagem de gates sozinha não bastava:
`h(0),cx(0,1),cx(1,2)` vs. `h(1),cx(0,1),cx(1,2)` — contagens idênticas
(`cx: 2, h: 1`), circuito genuinamente diferente (H na qubit errada).

Isso presume uma ordenação canônica que não existe. Preparar um estado GHZ
por cadeia de CX (0→1→2) ou por estrela de CX (0→1 e 0→2) entrelaça
corretamente a partir de `|0..0⟩` nos dois casos — mesmo multiset de gates,
ordem de `.data` diferente, nenhum dos dois errado. Numa rodada real contra
a tarefa `ghz_3q` (`bench/tasks/t1_primitives/ghz_3q.json`), o diff
posicional acusou a topologia em estrela (`cx(0,2)`) como se fosse o erro —
dizendo "esperado `cx(1,2)`" — e não disse nada sobre o bug real da mesma
rodada (H aplicado às três qubits, não só à primeira). Um gerador de
fronteira, exposto ao mesmo diff, **ignorou o conselho da prescrição** e
corrigiu o circuito lendo o código por conta própria; o gerador local
**seguiu a prescrição** e ficou preso repetindo o mesmo `cx(0,2)` nas
iterações 1, 3 e 5.

A tabela de contagens por tipo, isolada, sempre relatou o sinal certo nesse
mesmo caso (`h: 1 vs 3`) — o problema nunca foi a contagem, foi a prescrição
posicional ao lado dela competindo por atenção com uma alegação falsa.
Removida a renderização posicional (mantendo os campos brutos no payload,
sem custo, para análise futura — ex.: um diff invariante a reordenação, ou
codificação qualitativa em T064), rodando a mesma tarefa de novo:

| | antes (diff posicional presente) | depois (removido) |
|---|---|---|
| iteração final | 5 (teto de `MAX_ITER`) | 5 |
| status | `failed_semantic` | `success` |

A contagem de iterações não mudou — 5 tentativas nos dois casos, incluindo
duas tentativas perdidas com símbolos alucinados (`cx_decompose`, `u3`) sem
relação com o diff. O que mudou foi o desfecho: antes, o gerador nunca
convergia dentro do orçamento; depois, converge exatamente na 5ª tentativa.
Uma única rodada não é evidência estatística — mas é evidência direta de
que a prescrição posicional ativamente atrapalhava, não só deixava de
ajudar.

**Alternativas rejeitadas**:
- Manter só a mensagem escalar (`fidelidade=X`) — sem sinal acionável, é o
  problema original que este registro documenta.
- Despejar o payload como `repr(dict)` no prompt — sintaxe de dict/JSON no
  meio de um prompt em linguagem natural é ruído, não diagnóstico; por isso
  `render_structural_diff` existe como formatador dedicado.
- Rodar uma nova passada de simulação para calcular o diff — desnecessário:
  tudo vem de propriedades estáticas já presentes no circuito desserializado
  do QPY (`.num_qubits`, `.count_ops()`, `.data`), sem custo adicional.
- Manter o diff posicional só quando multiset e comprimento batem — não
  resolve o caso que motivou a reversão: cadeia vs. estrela têm o mesmo
  multiset E o mesmo comprimento, e é exatamente aí que a prescrição está
  errada.
- Apagar `expected_gate_sequence`/`actual_gate_sequence` do payload por
  completo — rejeitada: o dado é gratuito (já vem do circuito desserializado)
  e pode servir a um diff melhor (invariante a reordenação) no futuro; o que
  precisava morrer era a renderização como prescrição, não o dado bruto.

**Restrição preservada**: todo o cálculo do diff vive em
`validators/semantic.py` — `validators/` continua sem importar de `llm/`
(Princípio I, `test_architecture.py`). Só a formatação em texto vive em
`nodes/generator.py`, reaproveitada tal qual por `bench/run_single.py`, para
que uma inspeção manual mostre exatamente o que o modelo recebeu.

**Restrição geral adicionada por D16**: comparação de contagem (por qubit,
por tipo de gate) é sólida — é aritmética sobre um multiset, não presume
ordem. Diff posicional de sequência **não é sólido** e não deve ser
reintroduzido fraseado como prescrição ("esperado X aqui") quando a
divergência pode ser uma decomposição alternativa igualmente válida — ver
D16 para o porquê e para a implicação metodológica mais ampla, além deste
componente específico.

---

## D16 — Fidelidade do diagnóstico como variável não controlada do experimento

**Decisão**: fidelidade do diagnóstico estrutural fornecido ao gerador
(D14) é tratada como uma variável que pode confundir a métrica de correção
do laço de repetição — não como um detalhe de implementação sem
consequência para a análise. Consequência concreta: a codificação
qualitativa de erros (T064) DEVE distinguir, para toda execução malsucedida
que passou pelo `critic`, falha causada pelo modelo (o gerador não produziu
o circuito correto apesar de receber diagnóstico correto) de falha causada
por feedback enganoso (o diagnóstico fornecido continha uma alegação
incorreta que direcionou a tentativa seguinte para o lugar errado). A
matriz experimental (C1–C5) não controla essa variável hoje: nenhuma
condição isola "laço com diagnóstico correto" de "laço com diagnóstico
potencialmente enganoso" — isso deve constar como limitação explícita na
análise (§ análise qualitativa), não ser silenciosamente absorvido na taxa
de acerto das condições C4/C5.

**Razão** — experimento de controle na tarefa `ghz_3q`
(`bench/tasks/t1_primitives/ghz_3q.json`): o diff estrutural posicional
(a versão de D14 antes da correção) relatou

```
[2] cx(1,2) vs cx(0,2)
```

Mas `cx(0,2)` está correto: topologia em estrela (0→1, 0→2) e em cadeia
(0→1, 1→2) produzem o mesmo estado GHZ a partir de `|000⟩`. O diff acusou
exatamente a parte que estava certa e nada disse sobre o erro real — três
portas H em vez de uma.

O mesmo código e o mesmo diff (idênticos, colados manualmente) foram
apresentados a um modelo de fronteira, em uma conversa nova, sem qualquer
outro contexto da rodada. O modelo de fronteira produziu um circuito
correto — **ignorando a prescrição do diff** e identificando as portas H
extras por conta própria. O modelo local, dentro do laço real do agente,
**seguiu a prescrição do diff** e reproduziu o erro idêntico nas iterações
1, 3 e 5.

**Isto não é uma limitação de capacidade do modelo local** — essa foi a
leitura inicial e estava errada. O modelo local fez exatamente o que um
diagnóstico estruturado deveria permitir: confiar no sinal fornecido em vez
de re-derivar tudo do zero a cada tentativa, o que é o comportamento
desejado quando o sinal está correto. O diagnóstico é que estava errado, e
segui-lo corretamente ainda assim produz um resultado errado quando ele
mesmo aponta para o lugar errado. Um laço de correção só é tão bom quanto a
fidelidade do seu diagnóstico — um diagnóstico incorreto é pior que
nenhum, porque ancora o gerador numa direção falsa em vez de deixá-lo
raciocinar livremente sobre o próprio código. Alinhamento posicional
presume uma ordenação canônica de gates que não existe para circuitos
equivalentes; por construção, ele produz falsos positivos sempre que a
referência e o código gerado usam decomposições diferentes, porém
igualmente válidas (D14).

**Implicação para o experimento**: C4 e C5 medem "o laço de correção
ajuda?", mas, sem essa distinção, não conseguem separar "o laço ajuda
quando o diagnóstico está correto" de "o laço pode ativamente atrapalhar
quando o diagnóstico está errado" — e qualquer componente do payload
estrutural (D14) é exatamente o tipo de peça que pode introduzir esse viés
silenciosamente, inclusive futuras adições que ninguém testou contra um
caso de decomposição alternativa. T064 deve registrar, para cada execução
malsucedida, se algum diagnóstico fornecido ao gerador ao longo da rodada
continha uma alegação identificavelmente incorreta — não só classificar o
`error_type` da tentativa final.

**Alternativas rejeitadas**:
- Atribuir o resultado à capacidade do modelo local e não registrar nada —
  rejeitada explicitamente: o modelo local seguiu corretamente um
  diagnóstico corretamente fornecido a ele; o defeito estava no
  diagnóstico, não na resposta a ele. Registrar isto como "modelo fraco"
  seria erro de atribuição, e contaminaria qualquer conclusão sobre H2/H3
  (valor do laço de correção) tirada da comparação entre geradores.
- Considerar o assunto encerrado com a correção de implementação em D14 —
  rejeitada: a correção remove a instância conhecida do problema, mas não
  elimina o risco estrutural de que outro componente do diagnóstico (a
  mensagem de erro em texto livre, um campo futuro de payload) carregue uma
  alegação incorreta sem que ninguém note até rodar a matriz inteira. A
  taxonomia qualitativa precisa de uma categoria para isso.
- Rodar mais itens antes de registrar a decisão, para ter significância
  estatística — rejeitada para o registro em si: a decisão metodológica
  (T064 distingue as duas causas de falha) deve ser tomada agora, antes da
  coleta de dados da matriz completa; validar a magnitude do efeito é
  trabalho de análise (Phase 5+), não motivo para adiar o desenho.

---

## D15 — Ambiente de execução canônico

**Decisão**: `app` (agente) e `qdrant` rodam em containers via
`docker-compose.yml`; **Ollama roda nativamente no host Windows**, nunca
como serviço containerizado, alcançado em `host.docker.internal:11434`.
Desenvolvimento **e** a matriz experimental completa DEVEM rodar nesta mesma
configuração — nunca uma mistura de execução nativa no Windows e execução
containerizada entre sessões de desenvolvimento e a rodada final.

**Razão**:

1. **`fork` é exigido pela amortização que D1b mede.** O `WorkerPool`
   (`sandbox.py`) depende de `multiprocessing` com o método de início padrão
   do Linux, `fork` — processo filho herda o estado do pai por
   copy-on-write, e por isso o `import qiskit` de cada worker paga seu custo
   uma única vez (ver a medição em D1b: ~1,58 s no submit #1, ~0,0002 s de
   overhead nos seguintes). No Windows nativo, `multiprocessing` usa
   `spawn`: cada processo novo reexecuta o interpretador Python do zero, sem
   o COW do `fork` — o mesmo pool não amortizaria nada. Rodar a matriz num
   container Linux e o desenvolvimento nativamente no Windows tornaria a
   métrica de latência **incomparável** entre as duas, e mudaria o
   comportamento de seed de subprocesso — o mesmo commit, a mesma seed,
   produziria perfis de custo estruturalmente diferentes. Princípio II
   (reprodutibilidade) exige que "mesmo commit, mesma seed" implique mesmo
   comportamento observável, não apenas mesmo resultado funcional.
2. **Ollama já está medido no host, não em container.** O benchmark de D10
   (492 tok/s de prefill, 74,7 tok/s de geração, 100% GPU) foi obtido com o
   Ollama rodando nativamente na RTX 3070. Containerizar o Ollama exigiria
   reconfigurar passthrough de GPU e um novo benchmark — sem ganho algum,
   já que o host já entrega 100% de offload sem essa camada extra. Um
   `ollama` em `docker-compose.yml` também disputaria a porta 11434 com a
   instância nativa e rebaixaria os pesos do modelo para um volume separado,
   obrigando a um novo download.
3. **Sem isso, `RunRecord.lib_versions` perderia a versão do Ollama.**
   Enquanto o Ollama era um serviço do compose, a tag da imagem fixava a
   versão. Com o Ollama fora do compose, nenhuma tag de imagem mais a fixa —
   por isso `config.collect_lib_versions()` agora consulta `GET
   /api/version` do Ollama do host em tempo de execução
   (`llm/ollama_client.py:ollama_version`) e grava o resultado em
   `RunRecord.lib_versions["ollama"]`, com fallback `"unknown"` se o host
   estiver inacessível — mesmo padrão de degradação suave de
   `config.git_sha()`.

**Mecânica**: `docker-compose.yml`'s `app` declara
`extra_hosts: ["host.docker.internal:host-gateway"]`; `OLLAMA_BASE_URL` em
`.env` aponta para `http://host.docker.internal:11434`. `./src`, `./bench` e
`./scripts` são montados por bind mount no serviço `app`, então uma
alteração de código tem efeito imediato — o install do `qcagent` dentro do
container é editável (`uv sync`), sem precisar de rebuild da imagem a cada
mudança.

**Verificação realizada** (sandbox Linux com Docker): `docker compose exec
app python -c "import qcagent; print(qcagent.__file__)"` resolveu para
`/app/src/qcagent/__init__.py` — confirma que o bind mount e o install
editável realmente servem o código do host, não uma cópia congelada na
imagem. `getent hosts host.docker.internal` dentro do container resolveu via
`extra_hosts: host-gateway`; uma tentativa de conexão real a
`http://host.docker.internal:11434/api/version` falhou com `ECONNREFUSED`,
não com falha de resolução de nome — confirma que o roteamento de rede está
correto (não há Ollama rodando no host deste sandbox de desenvolvimento; a
verificação de ponta a ponta com o Ollama respondendo de fato só ocorre na
máquina real com a RTX 3070). O benchmark do `WorkerPool` sob `fork` real
está registrado em D1b.

**Alternativa rejeitada**: desenvolver no Windows nativo e só containerizar
para a rodada final. Rejeitada por (1) acima — teria invalidado a
comparabilidade de latência entre o piloto (que mede saturação de
`MAX_ITER`, D8) e a matriz completa.

---

## D17 — recall@8 não é estável entre escalas de corpus; o ramo denso é onde degrada

**Decisão**: o portão M1 (recall@8 ≥ 0,85) DEVE ser reavaliado a cada
expansão significativa do corpus — um recall medido num piloto pequeno não
prediz o recall no corpus de produção, e não deve ser tratado como
validado de uma vez por todas. A análise de erro (T064 e a avaliação de
recall em si) DEVE segmentar por tipo de consulta (identificador exato vs.
frase de intenção) sempre que o recall agregado cair, para localizar qual
ramo do híbrido (denso ou esparso) é responsável antes de qualquer ajuste.

**Razão** — medido, não hipotético. O corpus foi expandido de 186 para
**1.020 chunks reais** (`qiskit.circuit.library` inteiro — 170 páginas —,
mais `qiskit.quantum_info` e `qiskit.primitives`, descobertos
dinamicamente a partir das páginas de índice de cada módulo, não uma lista
fixa). Reexecutando as mesmas 50 consultas de intenção sobre esse corpus:

| corpus | chunks | recall@8 | MRR |
|---|---|---|---|
| piloto (sessão anterior) | 186 | 0,9000 | 0,657 |
| expandido (esta sessão) | 1.020 | **0,7302** | **0,5300** |

**M1 agora FALHA** (0,7302 < 0,85) no mesmo conjunto de consultas que
passava com folga no corpus pequeno. Confirma exatamente a hipótese que
motivou a reavaliação: recall degrada com o número de distratores, e o
número medido em 186 chunks nunca foi uma previsão válida para a escala de
produção — era uma validação de que o mecanismo de busca funciona, não uma
medição do recall final.

**Segmentação por tipo de consulta** (13 consultas de identificador exato
adicionadas a este registro — `tests/retrieval/queries.jsonl`'s campo
`query_type` — especificamente para tornar este diagnóstico possível):

| query_type | n | recall@8 | MRR |
|---|---|---|---|
| exact_identifier (ex.: `"RZGate"`, `"QuantumCircuit.cx"`) | 13 | **1,0000** | **0,8974** |
| intent_phrasing (ex.: "How do I apply a Hadamard gate?") | 50 | 0,6600 | 0,4345 |

O ramo esparso (BM25 com IDF, D5) continua praticamente perfeito mesmo em
5,5× mais distratores — recall@8 e MRR de identificador exato não caíram
de forma proporcional ao ramo denso. A degradação está concentrada no ramo
denso: o padrão de erro mais comum nas consultas de intenção é o modelo de
embedding confundir o MÉTODO de `QuantumCircuit` com a CLASSE de gate
correspondente (ex.: "How do I add a CNOT gate...?" retorna `CXGate` no
topo, não `QuantumCircuit.cx` — ambos descrevem a mesma operação em
registros diferentes, e o corpus expandido agora tem as duas versões
competindo). Isso aponta diretamente para D4 (modelo de embedding,
PENDENTE-PILOTO): o piloto real de D4 precisa avaliar especificamente a
robustez a esse tipo de ambiguidade classe-vs-método sob carga de
distratores, não só recall@8 agregado num corpus pequeno.

**Verificação do gap de corpus u3 → u** (a segunda checagem pedida):
confirmado que o gap era real — `u3` não aparece em nenhum texto das notas
de lançamento 1.0 ingeridas (checado via busca de texto direta antes desta
expansão). A página da própria classe `U3Gate`, porém, existe e carrega um
aviso de depreciação explícito ("This gate is deprecated... `circuit.u
(theta, phi, lambda)`") — real, verificado ao vivo, não suposto.
`chunking.py`'s `chunk_gate_class_page` e `chunk_api_reference_page` agora
detectam esse padrão (`_GATE_DEPRECATED_RE`/`_GATE_REPLACEMENT_METHOD_RE`)
e marcam `deprecated=True, replacement="QuantumCircuit.u()"` — confirmado
no corpus reingerido: a consulta exata `"U3Gate"` retorna essa página em
`rank=1`. Isso era uma lacuna de CORPUS (a alucinação de `u3` sobreviveria
ao RAG porque o corpus simplesmente não continha a correção), não uma
lacuna de recuperação — exatamente a distinção que motivou a checagem.
`qiskit.extensions` já estava corretamente coberto desde a primeira
ingestão (confirmado de novo, sem regressão, no corpus expandido).

**Efeito colateral encontrado durante a expansão**: embutir os 1.020 chunks
de uma vez OOM-matou o processo (RSS ~15,5 GB num sistema de 15 GB) — um
pequeno número de chunks incomumente longos (12 de 1.020 acima de 4.000
caracteres) compartilhando um lote ONNX com padding customizado é
suficiente para isso, mesmo com `batch_size` pequeno. Corrigido com um teto
de 4.000 caracteres por chunk em `chunking.py` (trunca do fim, preservando
sempre o `doc_id`/assinatura que fica no início do texto — D6 já previa
"se exceder o limite, dividir"; truncar é a versão mínima disso, não a
divisão completa por exemplo).

**Alternativas rejeitadas**:
- Aceitar o recall@8 = 0,90 do piloto de 186 chunks como validação de M1 e
  seguir para conectar a recuperação ao grafo — rejeitada explicitamente
  pelo pedido que originou este registro: um corpus de 8 páginas não prediz
  desempenho num corpus de milhares. Conectar a recuperação com um
  retriever fraco tornaria qualquer resultado experimental posterior
  impossível de atribuir (viria do gerador ou do retriever ruim?).
- Aumentar `limit`/`prefetch_limit` para compensar o recall sem investigar
  a causa — mascararia o sintoma sem resolver que o RANKING denso está
  errado, não que o candidato correto nunca aparece na busca bruta.
- Trocar o modelo de embedding agora, sem esperar o piloto formal de D4 —
  rejeitada: esta medição é exatamente o tipo de evidência que o piloto de
  D4 deveria produzir, mas trocar de modelo com base numa única medição
  não documentada como piloto formal comprometeria a rastreabilidade da
  decisão.

### D17-1 — Correção: prefixo de registro no texto indexado, M1 agora passa

**Decisão**: cada chunk indexado carrega um prefixo de registro —
`[method]`, `[class]` ou `[migration]` — antes do texto (`chunking.py`'s
`_with_register`). Reingerido o corpus (1.020 chunks) e reexecutado
`analysis/eval_retrieval.py`:

| | recall@8 | MRR |
|---|---|---|
| antes do prefixo, 1.020 chunks | 0,7302 | 0,5300 |
| depois do prefixo, 1.020 chunks | 0,7619 | 0,5336 |

**Checagem 1 — o ramo esparso não regrediu**: `exact_identifier` ficou em
recall@8=1,0000 (inalterado) e MRR **subiu** de 0,8974 para 0,9487 — o
prefixo não custou nada ao BM25/IDF; os termos do identificador continuam
casando normalmente, e o token de registro não introduziu ruído
mensurável.

O prefixo sozinho moveu `intent_phrasing` de recall@8=0,66 para 0,70 — uma
melhora real, mas não suficiente para o portão (< 0,85) nem para explicar a
maior parte do problema original.

**Checagem 2 — os 50 alvos não eram mais únicos**: verificado
sistematicamente (não por amostragem) contra os 44 alvos `QuantumCircuit.
<método>` de tipo `intent_phrasing`: para cada um, buscou-se no corpus um
chunk `[class]` cujo texto afirma explicitamente "Can be applied to a
QuantumCircuit with the `<método>`() method" — a mesma frase que motivou a
checagem 1 de D17 (`CXGate`, `ZGate`, etc.). **26 dos 44 alvos** (59%)
tinham essa confirmação textual direta: `RXGate` para `rx`, `ZGate` para
`z`, `IGate` para `id` (este último só encontrado numa segunda passada — o
regex original exigia "the X()" contíguo e não capturava o segundo item de
"the i() and id() methods"; documentado como limitação conhecida, não
corrigido retroativamente no script de diagnóstico, que é descartável).

Essas 26 entradas de `tests/retrieval/queries.jsonl` ganharam um campo
`also_correct` com o(s) doc_id(s) irmão(s); `analysis/eval_retrieval.py`
conta acerto se `target_doc_id` OU qualquer item de `also_correct`
aparecer no top-k, usando o melhor rank entre eles para o MRR. Entradas
`exact_identifier` NUNCA recebem `also_correct` — uma consulta que É o
identificador literal ("QuantumCircuit.cx") pede exatamente aquele
símbolo, não um parente.

**Números finais** (`make eval-retrieval`, corpus de 1.020 chunks, prefixo
de registro, alvos corrigidos):

| | recall@8 | MRR |
|---|---|---|
| overall | **0,9524** | 0,7275 |
| exact_identifier (n=13) | 1,0000 | 0,9487 |
| intent_phrasing (n=50) | **0,9400** | 0,6700 |

**M1 PASSA** (0,9524 ≥ 0,85). A maior parte do "problema de recall" medido
em D17 nunca foi um problema de recuperação — foi um teto artificial do
próprio conjunto de avaliação, autorado contra um corpus de 186 chunks que
não continha as duas versões do mesmo conceito competindo. Dito isso, o
prefixo de registro também ajudou de verdade (0,66→0,70 antes de corrigir
o gabarito) — as duas causas são reais e independentes, e ambas precisavam
de correção.

**Sobre o piloto de D4**: com M1 passando sem trocar o modelo de embedding,
**o piloto formal de D4 não é bloqueante** para prosseguir. Ainda vale a
pena no futuro — restam 2 falsos negativos genuínos (abaixo) — mas não é
mais um pré-requisito para conectar a recuperação ao grafo.

**Falsos negativos remanescentes** (2 de 50 `intent_phrasing`, nenhum
explicado por ambiguidade de gabarito — nem `QuantumCircuit.rx`/`RXGate`
nem `QuantumCircuit.ry`/`RYGate` aparecem em nenhuma posição do top-8):

| consulta | esperado | topo retornado |
|---|---|---|
| "How do I rotate a qubit about the X axis by an angle?" | `QuantumCircuit.rx` (ou `RXGate`) | `Quaternion.from_axis_rotation` |
| "How do I rotate a qubit about the Y axis by an angle?" | `QuantumCircuit.ry` (ou `RYGate`) | `RZXGate` |

Ambos são defeitos genuínos do ramo denso — "rotate about X/Y axis"
confunde com uma utilidade não relacionada de `quantum_info` e com um gate
de duas qubits errado, respectivamente. Não bloqueiam M1, mas são exemplos
concretos para um eventual piloto de D4 ou para uma iteração futura do
prefixo de registro.

**Efeito colateral de engenharia**: reingerir com o texto prefixado (mais
longo em média, não só nos poucos outliers) reproduziu o risco de OOM de
D17 mesmo com o teto de 4.000 caracteres já aplicado — um processo chegou a
13 GB de RSS num sistema de 15 GB antes de ser interrompido preventivamente.
Causa: `fastembed`/ONNX Runtime usa paralelismo intra-op sem limite por
padrão (16 threads neste host), e mais threads significa mais buffers
concorrentes. Corrigido reduzindo `batch_size` de 16 para 8 e fixando
`threads=4` em `FastEmbedEmbedder` — a reingestão seguinte ficou estável
em ~1,5 GB de RSS.

**Alternativas rejeitadas**:
- Aceitar 0,7619 (prefixo, sem corrigir o gabarito) como número final —
  rejeitada: a checagem 2 pedida explicitamente mostrou que isso
  sub-mediria o recall real do sistema, não uma característica dele.
- Remover as 6 consultas `intent_phrasing` de estilo "matrix
  representation..." (já inequivocamente sobre a classe) da checagem de
  ambiguidade — desnecessário: seus alvos (`RZGate` etc.) nunca colidiram
  com `QuantumCircuit.*`, então nunca entraram no conjunto ambíguo.
- Corrigir retroativamente o regex do script de diagnóstico para pegar
  "the X() and Y() methods" em geral e buscar mais casos perdidos —
  adiada: o script é descartável (`/tmp`, não faz parte da suíte), e o
  único caso confirmado por essa lacuna (`id`→`IGate`) já foi corrigido à
  mão; uma nova varredura completa não muda o veredito do portão M1.

---

## Referências a levantar (Phase 0, continuação)

- Benchmarks existentes de geração de código quântico e suas limitações de oráculo
- Literatura sobre contaminação de dados de treino em benchmarks de código
- Trabalhos de reparo iterativo de código guiado por execução
- Estado da arte em RAG sobre documentação técnica versionada
