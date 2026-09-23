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

## D3c — Oráculo de preparação de estado (correção a D3/D3b)

**Achado**: rodada ao vivo do task `ghz_3q` com retrieval ativo (US2, T039/T042
já concluídos). O enunciado é "Build a 3-qubit GHZ state circuit: (|000> +
|111>) / sqrt(2), up to global phase" — pede um ESTADO. O gerador produziu GHZ
via estrela de CX (`h(0); cx(0,1); cx(0,2)`); o oráculo de referência usa
cadeia de CX (`h(0); cx(0,1); cx(1,2)`). Ambos preparam exatamente o mesmo
estado a partir de `|000>` — verificado diretamente:

```python
Operator(star).equiv(Operator(chain))        # False
Statevector(star).equiv(Statevector(chain))  # True, fidelidade ≈ 1.0
```

O verificador (`oracle_kind="unitary"`) rejeitou uma resposta correta. Isto
**não é um bug de código do gerador** — é um descasamento entre o que o
enunciado da tarefa pede e o que o oráculo verifica: `Operator.equiv()`
compara o comportamento sobre TODA a base computacional (2ⁿ estados), mas o
enunciado só restringe a saída sobre `|0...0>` (1 estado). D3/D3b assumiram
implicitamente que equivalência unitária é o oráculo forte correto para toda
tarefa de síntese de circuito. Isso só vale quando o enunciado de fato
especifica uma transformação — não quando especifica um estado.

**Decisão**: adicionar `oracle_kind="statevector"` a `TaskSpec`.
`check_statevector_with_endianness` (paralelo a `check_with_endianness`,
mesma categoria `EndiannessSwap`, mesmo formato de `_structural_diff`) evolui
`|0...0>` por ambos os circuitos e compara via `Statevector.equiv()` — mesma
tolerância a fase global que `Operator.equiv()` dá ao caminho unitário (FR-004
continua valendo). `SemanticResult` ganha `state_equiv` (paralelo a
`unitary_equiv`, nunca os dois preenchidos na mesma verificação) e
`verification_method` passa a aceitar `"statevector"` além de `"exact"` /
`"composition"`.

**Efeito colateral no roteamento**: `route_after_semantic` decidia se
`resource_check` roda checando `unitary_equiv is not None` — sob a premissa
(agora falsa) de que só o oráculo unitário tem um circuito de referência para
comparar recursos. Um oráculo de estado também tem um circuito de referência
(veio do mesmo QPY). A condição foi trocada para `verification_method is not
None`, que já era populado exatamente nos dois casos onde uma comparação
circuito-vs-circuito de fato ocorre (unitário e, agora, estado) e nunca nos
oráculos sem circuito de referência (`distribution`, `energy`) — reaproveita
um campo existente em vez de introduzir um novo, e não muda o comportamento
de nenhuma tarefa `oracle_kind="unitary"` já existente.

**Benefício colateral**: o teto de 13 qubits de D3b (`Operator` materializa
4ⁿ elementos) não se aplica ao oráculo de estado — `Statevector` materializa
2ⁿ, do mesmo porte que o caminho de composição de D3b ou `check_distribution`.
Não há necessidade de despacho exato/composição nem fallback probabilístico
para `oracle_kind="statevector"` nos portes deste dataset (até 20 qubits).

**Auditoria de `bench/tasks/`**: no momento deste achado, só existia
`ghz_3q.json` (`t1_primitives`), usado como fixture de desenvolvimento por
`bench/run_single.py` antes de T043-T052 existirem; foi reclassificado para
`oracle_kind="statevector"` como correção direta. T044 (as 18 tarefas
canônicas T1) foi concluído logo em seguida — ver D3d para o que essa
construção revelou. A classificação abaixo — lida no enunciado de cada
tarefa citada em T044/T045, não adivinhada pelo nome — orienta quem
escrever T045-T047, para não reintroduzir este mesmo descasamento:

| Tarefa (T044/T045) | Classificação | Razão |
|---|---|---|
| Bell, GHZ, W-state | `statevector` | enunciado pede só o estado de saída a partir de `\|0...0>` |
| QFT | `unitary` — **manter** | QFT é especificada como transformação a ser aplicada sobre entrada arbitrária, não como preparação de um estado fixo. `QFT\|0...0>` é a superposição uniforme — o mesmo resultado que só aplicar H em cada qubit produz, sem exercitar nenhuma estrutura de fase relativa. Testar só a partir de `\|0>` aprovaria uma implementação errada; isto teria sido um falso positivo na direção oposta ao achado do GHZ |
| Deutsch-Jozsa, Simon, Bernstein-Vazirani | `statevector` — **correção** | as três são "oráculo linear/XOR fixo, um circuito, uma execução": com o oráculo embutido no circuito de referência (não variável por instância dentro de uma mesma tarefa), o estado de saída é um alvo único e determinístico, exatamente como Bell/GHZ. A entrada original desta tabela classificava DJ/Simon como `distribution`, confundindo duas coisas distintas: Simon exige VÁRIAS execuções + álgebra linear clássica para recuperar `s`, mas o ESTADO QUÂNTICO que uma única execução produz (superposição uniforme sobre `{y : y·s=0}`) é, ele mesmo, um alvo fixo e exato — "precisa de várias amostras para responder classicamente" não é o mesmo que "o estado é não-determinístico". **Esta linha da tabela foi escrita de memória, sem verificar** — só foi corrigida porque construir o oráculo de DJ para T044 forçou testar a afirmação em vez de mantê-la por suposição (ver `bench/oracles/build_t1_primitives.py`'s `deutsch_jozsa()`). Ver D3d para esta e outras duas correções que a mesma disciplina (Princípio V) rendeu ao construir T044. |
| Teleporte | **nenhum se encaixa limpo — não resolvido aqui** | o protocolo depende do estado arbitrário de entrada sendo teleportado; nem `unitary` nem `statevector` (que fixam um único alvo) capturam "funciona para qualquer estado de entrada". Provavelmente precisa de um oráculo próprio (fidelidade sobre múltiplos estados de entrada aleatórios) — deixado como item em aberto para quem escrever T044 |
| Grover, QPE, QAOA MaxCut | depende da instância | Grover e QAOA são amplificação/otimização aproximada — a distribuição de medição (probabilidade de sucesso) é o critério natural, não igualdade exata de estado, então `distribution` é o padrão recomendado. QPE só tem alvo `statevector` exato quando a fase escolhida é EXATAMENTE representável no registrador (`k/2^n` para `k` inteiro); caso contrário a saída é espalhada e `distribution` é mais honesto. Decidir por tarefa na autoria (T045), não por família de algoritmo |
| VQE H₂, QAOA (custo) | `energy` (já existente) | corretude é sobre valor esperado do Hamiltoniano no estado de saída, nunca sobre equivalência de circuito — já não usa oráculo unitário, não afetado por este achado |

**Alternativa rejeitada**: reduzir toda tarefa de preparação de estado ao
oráculo de distribuição (`check_distribution`) em vez de um oráculo de estado
dedicado — perderia a garantia exata (`Statevector.equiv()` é determinístico;
contagens de medição introduzem ruído estatístico e exigem `shots`/seeds/
tolerância só para reobter o que a amplitude exata já dá de graça) e não
generaliza para portes onde medir é caro mas materializar `2ⁿ` amplitudes não.

---

## D3d — T044 construído: teleporte descartado, flatness em aritmética
reversível, e o placar do Princípio V

**Contexto**: T044 (as 18 tarefas canônicas T1) foi completado nesta sessão —
Bell×3, GHZ×3, W-state×3, QFT×3, Deutsch-Jozsa×3 (D3c), mais a família abaixo.
Três achados genuínos surgiram no processo, não previstos ao planejar a
tarefa. Registrados aqui juntos porque o padrão é o ponto: **construir o
oráculo, não apenas escrevê-lo, encontrou os três** — nenhum teria sido pego
por revisão de código do circuito de referência sozinho.

### Achado 1 — teleporte descartado do conjunto canônico (não resolvido por "input fixo")

Nem `unitary` nem `statevector` se encaixam: o protocolo precisa funcionar
para um estado de entrada ARBITRÁRIO, e ambos os oráculos existentes fixam um
único alvo. Duas opções foram descartadas:

- **Fixar um estado de entrada específico** (ex.: sempre teleportar `\|+>`) —
  rejeitada: admitiria circuitos acidentalmente corretos só para aquele
  estado, o que é PIOR do que omitir a tarefa — recompensaria uma resposta
  errada em vez de simplesmente não testar a propriedade.
- **`unitary` sobre o circuito completo** — rejeitada: teleporte envolve
  medição no meio do circuito com correção condicionada classicamente: o
  circuito não é uma transformação unitária fixa nem produz um estado puro
  determinístico ao final (o resultado depende do outcome da medição e da
  correção aplicada). `statevector` também não se aplica de forma limpa
  mesmo com entrada fixa, pelo mesmo motivo.

**Trabalho futuro (não implementado)**: a solução conceitualmente correta é
um oráculo de fidelidade de canal — evoluir K estados de entrada aleatórios
através do circuito completo (medição real incluída) e comparar a fidelidade
do qubit de saída contra cada estado de entrada original, média e pior caso.
Isso exige uma convenção que não existe hoje: como o circuito GERADO expõe
"qual qubit é a entrada a ser substituída" para o verificador injetar cada um
dos K estados de teste. Definir essa convenção mal — por exemplo, se o
enunciado disser "use o qubit 0 como entrada" mas o gerador rotular os
qubits de forma diferente — criaria uma nova categoria de falso negativo:
"falhou a tarefa" ficaria indistinguível de "não seguiu a convenção de
qual-qubit-é-a-entrada", exatamente o tipo de erro que D3c e este documento
existem para evitar, só que relocado do oráculo para o protocolo de
comunicação oráculo↔gerador. Por isso fica como item em aberto, não como
implementação apressada: o custo de fazer errado (rejeitar respostas
corretas por violar uma convenção não comunicada) supera o custo de deixar
teleporte fora do conjunto T1 por ora.

**Substituição**: aritmética booleana reversível (meio-somador, somador
completo, um lote de 4 funções booleanas), `oracle_kind="unitary"` — sem
sobreposição com T045, e diversifica T1 (que sem isso teria só QFT como
representante de `unitary` contra 4 famílias `statevector`).

### Achado 2 — somador com "vai-um" encadeado: por que `unitary` só é sólido quando o circuito é FLAT

A primeira tentativa da terceira variante foi um somador de 2 bits com
"ripple carry" — a saída de vai-um do primeiro estágio (meio-somador)
alimentando o segundo estágio (somador completo) como `cin`. `check_
alternative_construction` (o próprio mecanismo do Princípio V) discordou da
construção fechada independente. Investigação: o circuito primário estava
CORRETO nos 16 casos "físicos" (ancillas começando em `\|0>`) — o
desacordo estava inteiramente na extensão "não física" (ancillas começando
em outro valor).

A razão é estrutural, não um bug de digitação: quando um gate usa uma
ancila (não uma entrada original) como CONTROLE — aqui, o vai-um do primeiro
estágio controlando gates do segundo — o valor final dessa ancila em pontos
do domínio onde ela não começa em `\|0>` passa a depender de QUAL sequência
de gates reversíveis a computa, não apenas da função booleana pretendida.
Duas implementações igualmente corretas nos 16 casos físicos podem
legitimamente divergir nos 240 casos "não físicos" restantes — exatamente o
mesmo tipo de ambiguidade que motivou D3c, só que aqui a equivalência unitária
COMPLETA (não a equivalência de estado) é over-constrained, porque o
enunciado da tarefa só define o comportamento no subespaço físico.

**Fix**: toda tarefa de aritmética reversível em T044 é **flat** — cada gate
usa como controle SOMENTE qubits de entrada originais, nunca uma saída/ancila
computada. Sob essa restrição, a extensão ao domínio completo (2ⁿ_qubits
entradas, incluindo as "não físicas") fica unicamente determinada pela
definição booleana sozinha, verificado nos três circuitos finais (meio-somador,
somador completo, lote de 4 funções) — todos concordam com a permutação de
verdade fechada independente sobre TODO o domínio, não só o subespaço físico.

**A restrição de flatness é declarada no ENUNCIADO da tarefa, não só no
projeto do oráculo.** Um modelo recebendo apenas a especificação booleana
("sum = a XOR b, carry = a AND b") poderia legitimamente produzir uma
implementação correta que encadeia por uma ancila — e `Operator.equiv()`
rejeitaria por violar uma restrição que ninguém comunicou. Isso é
estruturalmente o mesmo defeito do caso GHZ (D3c): rejeitar uma resposta
correta por um critério não declarado — só que relocado do oráculo para o
enunciado. Cada um dos três `bench/tasks/t1_primitives/reversible_*.json`
declara explicitamente: "compute each output using ONLY qubits N..M (the
original inputs) as controls. Do not use a computed output or ancilla as a
control for another output."

### Achado 3 — QFT: direção do loop errada na primeira tentativa

Registrado em D3c originalmente de forma breve; detalhado aqui porque é o
terceiro ponto de dados do mesmo padrão. A primeira implementação de `qft()`
processava qubits em ordem crescente com a fase controlada no qubit de índice
maior — compilava, rodava, produzia uma unitária ERRADA (confirmado:
`Operator.equiv()` contra `qiskit.circuit.library.QFTGate` retornou `False`
para n=2,3,5,8). A correção foi processar do índice mais alto para o mais
baixo, com o controle no qubit de índice MENOR — verificado contra `QFTGate`
antes de aceitar.

Um segundo problema, mais sutil, apareceu depois: a checagem de sanidade em 3
seeds (T050) comparava uma execução real medida contra um alvo derivado do
PRÓPRIO circuito primário — o que só testa "o simulador executa o que o
circuito especifica", nunca "o circuito especifica a coisa certa". Para QFT
especificamente isso era pior que inútil: QFT de qualquer estado de base
computacional produz magnitude UNIFORME sobre todas as saídas,
independentemente das fases estarem certas — confirmado experimentalmente,
um circuito computando a QFT INVERSA (todos os sinais de fase trocados) mede
fidelidade de Hellinger 1.0000 contra esse alvo, indistinguível de correto,
para QUALQUER tolerância. Corrigido compondo o circuito primário com o
inverso da construção alternativa independente antes de medir — um bug de
fase agora vaza probabilidade medida para fora de um alvo nítido (o mesmo bug
de sinal invertido agora mede 0.0000). Ver `bench/validate_oracles.py`'s
`check_sanity_seeds` e `tests/unit/test_validate_oracles.py` (testes de
regressão para os dois: exact `Operator.equiv()` continua pegando o bug
incondicionalmente; a checagem de sanidade agora também pega, o que a versão
original não fazia).

### O que isso diz sobre o desenho do benchmark

Três tarefas genuinamente diferentes (preparação de estado, transformação
unitária, aritmética reversível), três erros reais de método, todos
encontrados pela CONSTRUÇÃO independente exigida pelo Princípio I/FR-018, não
por revisão de código: a direção do loop do QFT, a classificação errada de
DJ/Simon/BV (linha da tabela escrita de memória, nunca verificada até
construir o oráculo forçar o teste), e o encadeamento por ancila no somador.
Nenhum desses seria pego só lendo o circuito de referência e concordando que
"parece certo" — cada um exigiu uma segunda construção, escrita sem
referência à primeira, discordando dela. Essa é exatamente a garantia que o
Princípio V afirma existir; a taxa de acerto observada aqui — 3 de 3 tarefas
onde a construção independente foi genuinamente testada contra uma primeira
tentativa — é evidência de que o mecanismo funciona como desenhado, não
apenas burocracia de processo. Vale registrar isso explicitamente porque é o
tipo de achado que justifica o custo de exigir construção independente em
TODA tarefa do dataset (T049), não só nas que "parecem arriscadas".

---

## D3e — T045 construído: classificação de oracle_kind, restrição não
declarada (de novo), blindness de fase generalizada, e um bug real do Aer

**Contexto**: T045 — 15 das 18 tarefas canônicas T2 (Bernstein-Vazirani×3,
Simon×3, Grover×3, QPE×3, QAOA MaxCut×3). VQE H₂×3 **não incluído** — ver
seção própria abaixo. Todas as 15 usam `oracle_kind="statevector"`.

### Classificação de oracle_kind — por que todas as 15 são `statevector`

Cada família embute UM oráculo/conjunto de parâmetros fixo por tarefa (nunca
variável por instância dentro da mesma tarefa), o que torna a saída do
circuito a partir de `\|0...0>` um alvo único e determinístico — exatamente
como Bell/GHZ (D3c) e a correção de DJ/Simon/BV (D3d). Nenhuma das cinco
famílias é `oracle_kind="unitary"` aqui: nenhuma é especificada como
transformação geral sobre entrada arbitrária (o critério que mantém QFT em
`unitary`, D3c). Detalhe por família:

- **Bernstein-Vazirani, Simon**: mesma estrutura de oráculo linear/XOR fixo
  já estabelecida para Deutsch-Jozsa em D3d — sem novidade de classificação.
- **Grover**: item(ns) marcado(s) e número de iterações são fixos pelo
  enunciado (nunca "o ótimo, calcule você mesmo"). Com ambos fixos, o estado
  após as iterações a partir de `\|0...0>` é um único alvo matematicamente
  determinado, independente de qual decomposição de gates do difusor o
  chegou — não há a ambiguidade "muitos estados finais válidos" do caso GHZ,
  porque o difusor tem UMA definição matemática (`2\|s><s\| - I`), só muitas
  decomposições EQUIVALENTES dela.
- **QPE**: fase escolhida exatamente representável no registrador de
  contagem (`k/2^n_count`, `k` inteiro) — o registrador de contagem colapsa
  EXATAMENTE em `\|k>` com certeza, não por aproximação. Uma fase não
  exatamente representável produziria uma distribuição espalhada
  (tipo sinc²), mais apropriada para `oracle_kind="distribution"` —
  deliberadamente fora deste lote; ver nota abaixo.
- **QAOA MaxCut**: grafo E os parâmetros (`gamma`, `beta`) totalmente fixos
  no enunciado. Ver a seção de restrição-não-declarada abaixo para por que
  isso é necessário, não apenas conveniente.

### Restrição não declarada — de novo, agora relocada para o enunciado

O usuário pediu explicitamente, para cada tarefa T2: "o oráculo aceita TODA
implementação correta do que o enunciado pede, ou só a que eu tinha em
mente?" Dois casos exigiram ação:

**QAOA**: o ansatz p=1 tem liberdade de parametrização real — normalmente
`gamma`/`beta` são otimizados classicamente para maximizar o valor esperado
do corte. Se o enunciado nomeasse só o grafo, dois modelos escolhendo ângulos
diferentes (ambos razoáveis, ou um genuinamente melhor) alcançariam estados
finais legitimamente diferentes; fixar UMA escolha arbitrária como gabarito
rejeitaria a outra. **Decisão**: enunciado fixa grafo E `gamma`/`beta`
numericamente exatos — a tarefa deixa de ser "otimize" e passa a ser
"construa este circuito parametrizado específico corretamente", o que
resolve a ambiguidade tornando os parâmetros parte do enunciado, não algo a
derivar. Isto é **estreitar o enunciado**, não alargar o oráculo — a
alternativa (aceitar qualquer `gamma`/`beta` "razoável") exigiria um oráculo
de otimização/qualidade-de-corte muito mais complexo, fora de escopo aqui.
**Consequência a registrar para a análise de erro (T064)** — *T064 (taxonomia
com dupla anotação e κ) foi removida na migração v1→v2 (2026-09-11,
`MIGRATION.md`); a referência abaixo é histórica. O CAVEAT em si (taxa de
sucesso alta não é evidência de capacidade de otimização) continua válido
para a suíte de regressão v2 — se o relatório mostrar essas tarefas
passando, ainda não deve ser lido como "o sistema otimiza QAOA/VQE", só que
"o sistema reproduz fielmente um ansatz já especificado"; só o MECANISMO de
registrar isso (uma taxonomia formal com anotação dupla entre condições
experimentais) é que não se aplica mais*: com `gamma`/
`beta` fixos, estas 3 tarefas medem fidelidade de CONSTRUÇÃO do ansatz, não
capacidade de otimização de QAOA — uma escolha de escopo legítima, mas que
muda o que a tarefa de fato testa. Uma taxa alta de sucesso aqui não deve ser
lida como evidência de que o gerador sabe otimizar QAOA. A mesma ressalva se
aplica a VQE H₂ (D3e-3, mesmo motivo: `theta` fixo em vez de livre).

**Aritmética booleana reversível já havia caído nesse defeito uma vez** (D3d,
flatness). Confirmado ao revisar T2 que a lição generaliza: sempre que o
oráculo especifica MAIS do que o enunciado pede — um circuito específico em
vez de "qualquer circuito correto" — a restrição extra precisa aparecer no
texto do enunciado, ou uma resposta correta é rejeitada por um critério nunca
comunicado. Para Simon especificamente, isso significou declarar não só o
segredo `s`, mas a construção EXATA do oráculo (qual qubit é o "controle
extra", quais CNOTs exatamente) — existem MUITAS funções `f` satisfazendo
`f(x)=f(x XOR s)` para o mesmo `s`; sem fixar qual delas, um modelo
poderia legitimamente implementar uma `f` diferente (também válida) e chegar
a um estado final genuinamente diferente do oráculo de referência. Cada
enunciado de Simon em `bench/tasks/t2_algorithms/simon_*.json` declara a
receita exata (qubit de controle extra, quais CNOTs), não apenas o segredo.

Grover foi verificado e **não** precisou dessa correção: qualquer difusor
correto implementa a MESMA unitária (`2\|s><s\|-I`), então não existe "muitos
estados finais válidos" ali — só a convenção oráculo-de-fase-sem-ancilla
precisou ser declarada explicitamente (ver enunciados), para não deixar em
aberto se o modelo deveria usar um qubit ancilla para o phase kickback.

### D3e-1 — blindness de fase generalizada além do QFT

O achado de D3d sobre QFT (a checagem de sanidade em 3 seeds media contra um
alvo derivado do PRÓPRIO circuito primário, cego a bugs de fase pura) não é
específico de QFT: **qualquer** oráculo cuja distribuição-alvo (derivada da
construção alternativa) seja espalhada tem a mesma lacuna estrutural.
Medido ao construir T2:

- Simon: estado conjunto completo é EXATAMENTE uniforme sobre `2^n`
  resultados (`max_prob = 1/2^n`) — o pior caso observado.
- Grover antes de amplificação ótima: comparável a uniforme (`k=0`:
  `PR=16=dim`; `k=1`, sub-ótimo: `max_prob≈0.47`).
- QAOA em p=1 com ângulos realistas: `max_prob` medido entre 0.11 e 0.37 nas
  três instâncias construídas — nenhuma sequer perto de um pico dominante.

**Decisão**: `check_sanity_seeds` agora aplica o design de round-trip (compor
o primário com o inverso da alternativa independente, medir contra um alvo
NÍTIDO) sempre que a probabilidade máxima da distribuição-alvo (derivada da
alternativa) cai abaixo de `PEAKEDNESS_THRESHOLD=0.9` — computado por tarefa,
não decidido por família. Isso significa que alguns casos de baixo risco
(Bernstein-Vazirani: `max_prob=0.5`, mas só 2 resultados possíveis, não
genuinamente espalhado) também passam a usar round-trip. Aceito como
conservador, não errado: o round-trip nunca é menos informativo que a
comparação direta, então aplicá-lo onde não era estritamente necessário não
custa nada além de compute. Ver `bench/validate_oracles.py`'s
`PEAKEDNESS_THRESHOLD` e `check_sanity_seeds` para a implementação e a
justificativa completa.

**Simplificação em relação a D3d**: para famílias `oracle_kind="statevector"`
que precisam de round-trip, o circuito de round-trip é derivado
GENERICAMENTE via `StatePreparation(alt.data)` — não é preciso registrar um
circuito alternativo próprio por família (diferente de `oracle_kind=
"unitary"`, que já exigia isso desde D3d). Isso não é o mesmo erro de
"compor o primário com o próprio inverso" (que seria tautológico, sempre
cancela não importa o que o primário compute): `alt` já é independente do
primário por construção, então compor o primário com o inverso de UMA
preparação diferente só cancela de volta à origem SE o primário de fato
chegar ao mesmo alvo que `alt` — continua sendo um teste genuíno.

### D3e-2 — bug real do Aer: `StatePreparation(...).inverse()` derruba o processo

Ao generalizar o round-trip para famílias `statevector`, `bench.
validate_oracles` **segfaultou** (`exit code 139`, não uma exceção Python)
na primeiríssima tarefa testada (`bell_phi_minus_2q`, já validada e passando
antes desta mudança). Isolado: `StatePreparation(...).inverse()` decompõe em
instruções `"multiplexer"` que o Aer aceita silenciosamente via
`transpile()` (nenhum erro na chamada de transpilação em si) mas derruba o
processo ao executar via `sim.run()`. Não é um bug de lógica deste projeto —
é uma incompatibilidade real entre a forma como `StatePreparation.inverse()`
se decompõe e o que o backend Aer desta versão realmente suporta.

**Fix**: `measured.decompose(reps=8)` antes de `transpile()`, desenrolando os
gates `"multiplexer"` em gates padrão (`u`, `cx`) antes que o Aer os veja.
Verificado a remover o crash e produzir resultados corretos (inclusive um
caso em que a otimização do `transpile()` simplificou o round-trip inteiro
de um oráculo correto até sobrar só `barrier`+`measure`, confirmando o
cancelamento perfeito esperado). Coberto por
`tests/unit/test_validate_oracles.py::
test_inverted_stateprepation_round_trip_survives_aer_without_predecompose`
— um alerta antecipado caso uma futura versão do Qiskit/Aer mude esse
comportamento, já que o teste não pode importar `bench.validate_oracles`
diretamente (`bench` não está no caminho de import do pytest) e por isso
reproduz o padrão em vez de cobrir a call site em si.

### D3e-3 — VQE H₂ construído a partir de uma fonte citável, não de memória

As 3 tarefas de VQE H₂ (o gap deixado em aberto na primeira passada de T045)
**foram construídas nesta sessão**, sem `qiskit-nature`/`pyscf` (continuam
ausentes deste ambiente) e sem recitar coeficientes de estrutura eletrônica
de memória — a alternativa que o Princípio V/FR-018 exige excluir.

**Fonte, lida e citada, não recordada**: O'Malley et al., "Scalable Quantum
Simulation of Molecular Energies", Phys. Rev. X 6, 031007 (2016),
arXiv:1512.06860v2, Tabela I. `pdftotext -layout` rodado diretamente sobre o
PDF do arXiv (baixado via WebFetch) extraiu a tabela real — os coeficientes
`(g0..g5)` usados nos 3 oráculos são linhas REAIS da tabela (R=0.55, 0.75,
1.30 Å), copiados do texto extraído, não digitados de memória nem
interpolados. Conferência interna: a tabela extraída tem `g4==g5` em toda
linha, batendo com a estrutura simétrica Y0Y1/X0X1 da Eq. (1) do próprio
artigo — um sinal de que a extração não introduziu erro de transcrição.

**A energia exata não é uma segunda citação** — é computada por diagonalização
exata (`numpy.linalg.eigvalsh`) do Hamiltoniano construído a partir dos
coeficientes citados, verificável independentemente por qualquer um a partir
da própria tabela, sem depender de uma segunda fonte não verificável.

**Ansatz** para cada instância: `X(qubit0); RY(theta, qubit1); CNOT(controle=
qubit1, alvo=qubit0)`, com `theta` resolvido por minimização escalar exata
(`scipy.optimize.minimize_scalar`, não adivinhado) até bater com a energia
exata (erro < 1e-8 antes de qualquer arquivo ser escrito). `check_energy`
proíbe `Parameter`s livres no circuito gerado (`ParameterBindingError` senão)
— não há como um circuito gerado rodar uma otimização clássica de verdade
dentro do sandbox, então o enunciado já entrega o ansatz e o `theta` exatos.

**Isso significa que estas tarefas medem fidelidade de CONSTRUÇÃO, não
capacidade de otimização de VQE** — exatamente a mesma ressalva de D3e para
QAOA, e pelo mesmo motivo estrutural: `gamma`/`beta` fixos em QAOA e `theta`
fixo aqui removem a liberdade de escolha de parâmetro que tornaria a tarefa
"encontre bons parâmetros" em vez de "construa este circuito específico
corretamente". Uma taxa alta de sucesso nestas tarefas (VQE H₂ e QAOA) NÃO
deve ser lida, na análise de erro (T064 — **superada na migração v1→v2**,
ver a nota acima nesta mesma seção) ou no relatório, como evidência de
que o gerador sabe otimizar VQE/QAOA — só que sabe reproduzir fielmente um
circuito parametrizado já especificado. Uma tarefa que testasse otimização de
verdade exigiria um loop de otimização clássica fora do sandbox (T3/T4? — não
resolvido aqui, registrado como possível trabalho futuro).

**Checagem própria em `validate_oracles.py`**: `oracle_kind="energy"` não é
um circuito, então ganhou seu próprio conjunto de 4 checagens
(`validate_energy_oracle`): hermiticidade do Hamiltoniano; construção
alternativa via produtos de Kronecker escritos à mão (nunca
`SparsePauliOp.to_matrix()`) diagonalizada por `scipy.sparse.linalg.eigsh`
(Lanczos iterativo — algoritmo genuinamente diferente de `numpy.linalg.
eigh`); N/A para cross-check de biblioteca (nenhum primitivo aplicável);
sanidade em 3 seeds medindo `<H>` de verdade via `AerSimulator`, com
mudança de base (Z direto; H em ambos os qubits para o termo XX; Sdg+H para
o termo YY) — o jeito padrão de estimar valor esperado de Pauli a partir de
contagens em base computacional. `ENERGY_SANITY_TOL=0.02` Hartree calibrado
por Monte Carlo (10 tentativas, 8192 shots, mesmo padrão de `SANITY_
FIDELITY_MIN`): desvio padrão observado ~0.0029, pior erro observado ~0.006
— folga de ~3x. Todas as 3 tarefas passam nas 4 checagens.

---

## D3f — T046 construído: formulação, o espaço de respostas corretas mais
largo do dataset, e uma segunda armadilha de convenção não declarada

**Contexto**: T046 — 12 tarefas canônicas T3. T3 = "formulação": traduzir
uma função de custo/Hamiltoniano/QUBO enunciado em prosa/números para o
circuito que o aplica como fase diagonal `exp(-i*gamma*H)|+>^n`. Quatro
famílias, três variantes de porte cada — todas `oracle_kind="unitary"`:

- **A — Ising MaxCut com pesos não uniformes**: estende o QAOA de T2 (pesos
  sempre uniformes) para arestas com pesos diferentes.
- **B — interação multi-corpo (3 e 4 qubits)**: um termo `Z0*Z1*Z2` ou
  `Z0*Z1*Z2*Z3` — um padrão de gate (escada de CNOT de comprimento
  arbitrário) que não apareceu em T1 nem T2.
- **C — campo + acoplamento combinados**: termos de campo de um qubit
  (`h_i*Z_i`) e termos de acoplamento de pares na MESMA tarefa.
- **D — QUBO → Ising**: matriz QUBO explícita, substituição declarada
  (`x_i = (1-z_i)/2`), o enunciado pede a DERIVAÇÃO dos coeficientes de
  Ising, não os entrega prontos — esta é a família que mais genuinamente
  testa "formulação" (tradução algébrica), não só construção de circuito.

`unitary`, não `statevector`: todo Hamiltoniano aqui é diagonal na base
computacional, então a unitária resultante é bem definida em qualquer um dos
2^n estados de entrada — a mesma razão que mantém QFT em `unitary` (D3c). E,
diferente de D3d (aritmética reversível), **não há preocupação de flatness
aqui**: nenhum qubit é ancila zerada, todos são variáveis reais do problema,
então não existe "subespaço não físico" para o domínio completo da checagem
unitária estar sobre-restringindo.

### Restrição não declarada — de novo, uma terceira vez, e desta vez é uma convenção de sinal

O usuário pediu para checar isso "mais do que em qualquer lugar" para T3,
dado o espaço de respostas corretas mais largo do dataset até aqui. Achado
real ao projetar a família D: a substituição QUBO → Ising `x_i = (1-z_i)/2`
E `x_i = (1+z_i)/2` são AMBAS convenções padrão na literatura — e produzem
Hamiltonianos de sinal OPOSTO (`h_i`, `J_ij` todos invertidos). Se o
enunciado não declarasse qual, um modelo usando a outra convenção
(igualmente válida) derivaria um Hamiltoniano genuinamente diferente do
oráculo de referência e seria rejeitado por uma resposta correta sob uma
convenção não comunicada — exatamente a mesma classe de defeito de D3c (GHZ)
e D3d (flatness), a terceira instância encontrada nesta sessão. Cada
enunciado `qubo_ising_*.json` declara a convenção exata
(`x_i = (1 - z_i) / 2`) explicitamente.

Famílias A, B, C foram checadas e **não** precisaram de nenhuma restrição
extra além dos números em si: cada termo (`Z_i*Z_j`, `Z_{q1}...Z_{qk}`,
`h_i*Z_i`) é diagonal com uma unitária única, então qualquer decomposição de
gates correta chega à MESMA unitária — os enunciados dizem isso
explicitamente ("any correct implementation... is accepted") em vez de
prescrever uma sequência de gates específica, o oposto do que foi necessário
para QAOA/Grover em T2 (lá a ambiguidade era de PARÂMETRO, não de
decomposição — aqui não há ambiguidade de parâmetro nenhuma, `gamma` e todos
os coeficientes são números fixos no enunciado).

### Construção independente

Um único alternativo fechado (`_alt_diagonal_ising` em `bench/
validate_oracles.py`) cobre as quatro famílias: a fase diagonal computada
DIRETAMENTE da definição da função de custo (soma de termos campo +
acoplamento + multi-corpo), via `Diagonal`, sem nenhuma escada de CNOT — uma
construção estruturalmente diferente da decomposição CNOT-ladder-mais-RZ do
primário. Para a família D especificamente, a substituição QUBO→Ising é
RE-DERIVADA de forma independente (`_alt_ising_from_qubo`, mesma fórmula,
zero código compartilhado com `build_t3_formulation.py`'s `ising_from_qubo`)
— as duas precisam concordar para a checagem 2 passar, o que torna isso um
cross-check genuíno sobre a substituição em si, não só sobre o circuito de
fase construído a partir dela. Verificado por força bruta sobre todos os
bitstrings antes de confiar na fórmula (ver sessão): a substituição bate
exatamente com a função de custo QUBO original para n=3.

Todas as 12 tarefas passam nas 4 checagens (unitariedade, construção
alternativa, sanity em 3 seeds — round-trip automático já que
`oracle_kind="unitary"`; cross-check de biblioteca N/A, nenhuma família tem
primitivo aplicável em `qiskit.circuit.library`).

---

## D3g — Padrão recorrente: oráculo mais estreito que o enunciado rejeita
resposta correta em silêncio (resultado metodológico, não só detalhe de
processo)

Três achados independentes, em três tiers diferentes, mesma estrutura:

- **D3c (GHZ, T044)**: GHZ via estrela de CX e via cadeia de CX preparam o
  MESMO estado a partir de `\|000>`, mas `Operator.equiv()` (equivalência
  unitária completa) os distingue — o oráculo testava mais do que o
  enunciado pedia (só o estado de saída).
- **D3d (aritmética reversível, T044)**: um somador de 2 bits com "vai-um"
  encadeado por uma ancila tem extensão não-física (ancila não começando em
  `\|0>`) dependente de qual decomposição de gates o computa — o oráculo
  (`Operator.equiv()` sobre o domínio completo) testava um comportamento que
  o enunciado nunca definiu, porque o enunciado só restringe o subespaço
  físico.
- **D3f (substituição QUBO→Ising, T046)**: `x_i=(1-z_i)/2` e
  `x_i=(1+z_i)/2` são ambas convenções padrão, sinal oposto — sem declarar
  qual, o oráculo aceitaria implicitamente só UMA das duas respostas
  igualmente corretas.

**A estrutura comum**: em cada caso, o oráculo era internamente
CONSISTENTE — nunca lançou uma exceção, nunca produziu um resultado
obviamente absurdo, sempre comparou exatamente o que foi programado para
comparar. A falha é silenciosa precisamente PORQUE o oráculo funciona
corretamente segundo sua própria definição — só que essa definição é mais
estreita do que o problema que o enunciado da tarefa realmente coloca. Não
existe sinal de alerta automático: sem a checagem de construção
independente (Princípio V/FR-018) discordando da referência, ou sem alguém
perguntando explicitamente "o oráculo aceita toda implementação correta, ou
só a que eu tinha em mente?", os três teriam permanecido invisíveis —
cada um rejeitaria silenciosamente uma fração de respostas corretas,
deprimindo artificialmente a taxa de sucesso medida de QUALQUER gerador
testado contra eles, por um motivo que nada tem a ver com a capacidade do
gerador.

**Isto generaliza além de circuitos quânticos.** É uma propriedade geral de
benchmarks de código gerado com oráculo automatizado, sempre que (a) o
espaço de implementações corretas é mais amplo do que uma única forma
canônica, e (b) o oráculo compara contra uma referência ou uma propriedade
que só cobre um subconjunto desse espaço sem que isso seja declarado. A
mesma estrutura apareceria em qualquer domínio com múltiplas implementações
válidas — geração de SQL contra um schema com índices alternativos,
otimização de código contra um "gabarito" que não é o único ótimo,
prova formal contra uma tática específica quando outras táticas válidas
existem. O padrão de mitigação encontrado aqui — perguntar explicitamente,
para cada tarefa, "o oráculo aceita toda implementação correta do que o
enunciado pede, ou só a que eu tinha em mente", e preferir ESTREITAR O
ENUNCIADO (tornar a resposta única e correta por definição) a ALARGAR O
ORÁCULO (construir um verificador mais permissivo e mais complexo) sempre
que estreitar o enunciado não sacrifica o que a tarefa pretende testar — é
reproduzível fora deste projeto.

**Candidato a seção própria na dissertação**, não apenas nota de processo:
o achado central não é "encontramos três bugs", é que os três compartilham
uma causa raiz estrutural e um teste diagnóstico repetível (constrói-se uma
segunda implementação, genuinamente independente, e pergunta-se explicitamente
se o oráculo aceitaria as duas) — isso é uma contribuição metodológica sobre
desenho de benchmark para código gerado, não um detalhe de implementação
deste dataset específico.

---

## D3h — T047 construído: `oracle_kind="resource"` não existe, o eixo
inverte (a unitária deixa de ser o alvo), e a referência como alvo móvel

**Contexto**: T047 — 12 tarefas canônicas T4 ("dependente de restrições do
alvo físico", FR-016). T4 inverte o risco de desenho de oráculo de todos os
tiers anteriores: em T1-T3 o que podia estar errado era a EQUIVALÊNCIA
funcional (estado ou unitária); em T4, a funcional já está resolvida
(reaproveita `statevector`/`unitary` de T1-T3) e o que pode estar errado é a
comparação de RECURSOS (profundidade, contagem de CX) sob um mapa de
acoplamento real.

### Achado prévio a qualquer construção: `oracle_kind="resource"` não tem implementação

Antes de escrever qualquer tarefa, `grep` em `src/qcagent/graph.py`
confirmou: `make_semantic_check_node` só despacha sobre `StatePreparationOracle
| QuantumCircuit | dict | tuple` — nenhum ramo trata `oracle_kind="resource"`,
apesar do valor existir no `Literal` de `data-model.md`/`bench/schema.py`
desde T043. Isto não bloqueia T4: `resource_check` já é ORTOGONAL a
`oracle_kind` no pipeline existente — só precisa de um circuito de
referência real (que `statevector`/`unitary` já fornecem) e já roda
automaticamente assim que `semantic_check` popula `verification_method`
(D3c/D3e). As 12 tarefas de T4 usam `oracle_kind="statevector"` (família
GHZ) ou `"unitary"` (famílias Ising/Z-string/campo+acoplamento) — o mesmo
valor que suas famílias já usariam em T1-T3. O que torna uma tarefa "T4" é
`coupling_map="linear_5"` no `TaskSpec`, não um `oracle_kind` diferente.
Registrado, não corrigido silenciosamente: se `oracle_kind="resource"` for
necessário no futuro (para uma tarefa cuja corretude é PURAMENTE sobre
recursos, sem alvo funcional — não é o caso de nenhuma tarefa aqui), precisa
de um despacho novo em `make_semantic_check_node`, que não existe hoje.

**Gap relacionado, também encontrado, não corrigido aqui**: `TaskSpec.
max_depth_ratio` (schema desde T043) nunca é lido por `make_resource_check_node`
— `check_resources` sempre usa seu próprio default (`2.0`), independente do
que o JSON da tarefa declara. Os 12 enunciados de T4 incluem `max_depth_ratio:
2.0` explicitamente (documentando a intenção mesmo que não tenha efeito
ainda), e o gap fica registrado aqui para ser corrigido antes de T053
(execução da matriz) — uma tarefa T4 genuinamente pesada em roteamento pode
legitimamente precisar de um teto mais frouxo que 2.0, e hoje não há como
declarar isso.

### Disciplina do usuário, item 1 — `seed_transpiler` e transpilação simétrica

Verificado, não assumido: `check_resources` (já implementado desde a Fase 3,
T017-T023) já transpila `generated` e `reference` com `coupling_map`,
`optimization_level` e `seed_transpiler` IDÊNTICOS — a armadilha 3 de
`contracts/validators.md` já estava corrigida antes de T047 existir. O que
FALTAVA era cobertura de teste: zero arquivos de teste para `resource.py`
existiam antes desta sessão, apesar de T017-T023 estarem marcados `[X]` e
todo teste de T1-T3 que chegasse a `resource_check` já exercitar esse
código (com `coupling_map=null`, nunca estressando o caminho de roteamento
de verdade — T4 é o primeiro tier a fazer isso). `tests/unit/test_resource.py`
(4 testes, novo) cobre: transpilação simétrica (mesmo circuito nos dois
lados dá ratio exatamente 1.0, quebraria sob parâmetros assimétricos);
reprodutibilidade do seed (duas chamadas com os mesmos circuitos dão o
mesmo `depth_ratio`); e a propriedade de segurança da desigualdade (próximo
item).

### Disciplina do usuário, item 2 — a referência como alvo móvel

**Decisão**: a referência de cada tarefa T4 é uma construção "óbvia", do
mesmo tipo já usado em T1-T3 (H+CX chain para GHZ, decomposição CNOT-ladder
para os termos Ising) — NUNCA uma topologia escolhida à mão para ser ótima
sob `linear_5`. Isso é defensável, não arbitrário, por uma razão estrutural
específica: o critério de aprovação de `check_resources` é `depth_ratio <=
max_depth_ratio` — um LIMITE SUPERIOR, não igualdade. Um circuito gerado que
roteia MELHOR que a referência (ex.: um modelo que reconhece que uma cadeia
é mais barata que uma estrela numa linha) produz `depth_ratio < 1.0`, que
SEMPRE satisfaz o limite superior. Isso neutraliza estruturalmente o risco
"minha referência não é ótima, uma resposta melhor pontua pior que 1.0" que
o usuário levantou: só um circuito genuinamente PIOR que a referência pode
falhar — uma referência subótima só torna a barra mais fácil de passar,
nunca mais difícil. Verificado com um teste dedicado
(`test_a_cheaper_valid_topology_passes_even_though_it_beats_the_reference`):
uma referência em estrela (pior para `linear_5`) comparada contra uma
resposta em cadeia (melhor) passa com `depth_ratio <= 1.0`.

`opt_level=2` usado sem alteração (default já existente de `check_resources`,
não escolhido agora para favorecer algum resultado específico de T4) —
mesma configuração em todos os tiers, mantendo a metodologia consistente em
vez de ajustar por tier.

### Achado de engenharia: `StatePreparation` como referência infla profundidade artificialmente

A primeira versão da família GHZ de T4 usava `StatePreparation` como
construção primária (a mesma escolha de T1, D3c — risco de derivação zero).
Medido antes de aceitar: a referência assim gerada tinha profundidade
transpilada de **57** (5 qubits, `linear_5`, `opt_level=2`) contra **5**
para a construção H+CX chain equivalente — a síntese genérica de
`StatePreparation` é muito mais profunda que qualquer circuito GHZ
razoável escrito à mão. Usar isso como referência de RECURSOS tornaria
`depth_ratio` quase sempre `<1.0` para qualquer resposta razoável, não
porque o modelo fez algo hardware-aware, mas porque a referência estava
desnecessariamente inflada — mascarando exatamente o eixo que T4 existe
para medir. **Corrigido**: papéis invertidos em relação a T1 — a família
GHZ de T4 usa a cadeia H+CX como PRIMÁRIA (mesmo risco baixo de derivação
que `StatePreparation` tinha em T1, é o circuito-textbook de GHZ) e
`StatePreparation` como ALTERNATIVA independente em `validate_oracles.py`.
Isto é específico de tiers focados em recursos: T1-T3 nunca precisaram
dessa cautela porque a profundidade da referência era irrelevante para o
que estavam testando.

### Nota honesta: distância de índice não força roteamento de verdade

Tentativa inicial: escolher índices de qubit "distantes" (ex.: qubits 0 e 4
numa linha de 5) assumindo que isso forçaria SWAPs. Verificado com
`transpile()` real: **falso em geral** — o passo de `layout` do
transpilador é livre para REMAPEAR índices lógicos para QUAISQUER qubits
físicos, então um circuito cuja estrutura de conectividade é um CAMINHO
(mesmo com índices "distantes" no rótulo lógico) sempre encontra um layout
físico adjacente e roteia de graça. O que genuinamente força SWAPs
independente de layout é um GRAU >= 3 (estrela) ou um CICLO na estrutura de
conectividade — nenhuma linha de 5 qubits suporta grau > 2. As 12 tarefas
de T4 ainda foram mantidas com a variação de localidade por índice (dá
diversidade real de profundidade pós-transpilação, confirmado
empiricamente — só não é "roteamento provadamente inevitável" no sentido
de teoria de grafos). A corretude do tier não depende dessa distinção:
transpilação simétrica + critério de desigualdade já garantem que a
comparação é válida independente de a referência forçar roteamento
"de verdade" ou não. Registrado para quem escrever T4 adicional ou revisar
este desenho no futuro.

### `heavy_hex_27` — não implementado, não fabricado

`COUPLING_MAPS` só define `linear_5` e `all_to_all`. O comentário já
existente em `resource.py` (anterior a esta sessão) já sinalizava:
"heavy_hex_27 intencionalmente omitido... adicionar a lista real de arestas
aqui quando as tarefas t4_hardware precisarem". Decisão desta sessão: não
perseguir isso agora — as 12 tarefas de T4 cabem em `linear_5` (5 qubits,
suficiente para a diversidade de localidade pretendida), e sourcing de uma
topologia real de 27 qubits de um backend IBM de verdade (mesmo rigor da
busca do Hamiltoniano do H₂ em D3e-3) fica como trabalho futuro explícito,
não fabricado por conveniência.

Todas as 12 tarefas passam nas 4 checagens de `validate_oracles.py`.

---

## D3i — T048 construído (parcial: T1, 18/18): quinto erro de construção
pego pela disciplina de verificação independente, desta vez no PRÓPRIO
conjunto de oráculos perturbados

Ao construir a variante de ordenação de qubits `dj_balanced_6q_perturbed`
(`bench/oracles/build_t1_perturbed.py`), a função `_deutsch_jozsa()` usava
`qc.cx(j, n_input)` com `j` FIXO (posição do bit menos significativo de
`secret`) para CADA bit setado de `secret`, em vez de `qc.cx(i, n_input)`
com `i` variando por bit — o padrão da construção canônica já validada em
`build_t1_primitives.py`. Como CX é autoinverso, repetir `CX(j, ancilla)`
um número ÍMPAR de vezes colapsa para um único `CX(j, ancilla)` (função
`f(x)=x_j`, não a função balanceada de múltiplos bits pretendida por
`secret`); um número PAR de vezes cancela por completo (constante, não
balanceada). Isso teria corrompido silenciosamente o oráculo de referência
de `dj_balanced_6q_perturbed` (e teria afetado `dj_balanced_4q_perturbed`
também, se não corrigido antes de construí-lo) — o oráculo errado
continuaria internamente consistente (unitário/norma válidos, autoconsistente
com a "construção alternativa" SE essa alternativa replicasse o mesmo erro,
o que não é o caso aqui pois a alternativa em `validate_oracles.py` é
derivada de `_alt_deutsch_jozsa`, independente).

Pego ANTES de qualquer dano: ao derivar a descrição direta (sem
`reverse_bits()`) para o texto do prompt de `dj_balanced_6q_perturbed`,
imprimir o diagrama do circuito revelou o padrão de controle fixo, que não
batia com a lembrança da construção canônica correta. Comparação direta
contra `build_t1_primitives.py::deutsch_jozsa()` confirmou a divergência.
Corrigido trocando `qc.cx(j, n_input)` por `qc.cx(i, n_input)`; os 3 `.qpy`
que dependiam da função (`dj_constant_4q_perturbed` — seguro, pois
`secret=None` não gera nenhum CX; `dj_balanced_6q_perturbed` e
`dj_balanced_4q_perturbed`) foram reconstruídos e re-verificados via
`Statevector.equiv()` contra a construção canônica antes de escrever
qualquer arquivo de tarefa.

Este é o QUINTO erro de construção genuíno pego pela disciplina de
verificação independente nesta dissertação (após D3d's QFT/ripple-carry,
D3e's DJ/Simon/BV, D3f's convenção de sinal QUBO→Ising) — e o primeiro a
ocorrer DENTRO do próprio processo de construção do conjunto perturbado, não
do conjunto canônico. Reforça [[D3g]]: a disciplina de "nunca confiar numa
construção sem verificá-la contra uma segunda, independente" continua a
pagar dividendos mesmo quando a segunda construção (aqui, uma variante da
primeira) parece trivialmente derivada da primeira já validada.

### As 18 tarefas de T1 perturbadas — tabela de validação

Todas as 18 passam nas 4 checagens de `bench/validate_oracles.py`
(unitariedade/normalização, construção alternativa, cross-check de
biblioteca onde aplicável — só QFT, N/A para as demais — e sanity em 3
seeds). Distribuição das 5 famílias (D12), 4/4/4/3/3 conforme planejado:

- **Fase relativa** (4): `bell_phi_plus_2q`, `ghz_3q`, `ghz_8q`,
  `w_state_3q`. Alternativa em `validate_oracles.py`: a construção canônica
  hand-gate mais um `RZ` final num único qubit — verificado que RZ(φ) numa
  superposição de exatamente dois ramos (Bell/GHZ) ou num único termo do
  suporte do estado W adiciona exatamente a fase relativa pretendida, antes
  de confiar nisso.
- **Restrição de gate set** (4): `bell_phi_minus_2q`, `ghz_5q`,
  `reversible_half_adder_4q`, `w_state_5q` — mesmo alvo do canônico (a
  restrição vive só no PROMPT: `{rz, sx, x, cx}`, padrão de hardware IBM);
  alternativa reaproveita a mesma função `_alt_*` já registrada para a
  tarefa canônica correspondente, já que o alvo não muda.
- **Ordenação de qubits / endianness explícita** (4): `dj_constant_4q`,
  `dj_balanced_6q`, `qft_8q`, `reversible_full_adder_5q` — `.reverse_bits()`
  do canônico (dj_*, full_adder) ou a convenção `do_swaps=False` do QFT.
  Alternativa: a construção canônica independente já registrada,
  bit-revertida via `.reverse_qargs()`/`.reverse_bits()` (uma operação
  genérica de relabeling, não uma reconstrução manual que pudesse
  compartilhar bug com o primário) — ou, para `qft_8q`, `QFTGate` com uma
  camada de SWAP adicional para desfazer seu SWAP interno, verificado contra
  o primário antes de confiar.
- **Composição** (3): `bell_psi_plus_2q`, `w_state_8q`,
  `reversible_boolean4_8q` — alvo canônico composto com QFT no mesmo
  registrador. Alternativa: a construção canônica independente + `QFTGate`
  (o mesmo primitivo de biblioteca já confiado como alternativa das próprias
  tarefas `qft_Nq` canônicas).
- **Parametrização simbólica** (3): `qft_3q`, `qft_5q`, `dj_balanced_4q` —
  mesmo oráculo do canônico; a perturbação é só no PROMPT (fórmula em vez de
  números já avaliados). Alternativa: reaproveita a alternativa canônica sem
  alteração.

### Pareamento (FR-017)

`bench/validate_oracles.py::check_perturbation_pairing()` (nova, T048)
verifica: (1) toda tarefa perturbada tem `base_task_id` apontando para uma
tarefa canônica existente; (2) nenhuma tarefa canônica tem mais de uma
variante perturbada. Essas duas invariantes são bloqueantes desde já,
independente de quanto do conjunto perturbado já foi construído. A
invariante de COMPLETUDE (toda tarefa canônica tem AO MENOS uma variante) é
reportada mas não bloqueante enquanto T048 está em construção incremental —
vira bloqueante automaticamente quando o número de pares bate com o número
de tarefas canônicas, sem exigir alterar o código depois. Estado atual:
18/60 pares.

Conjunto completo (60 canônicas + 18 T1 perturbadas = 78 oráculos) passa
`uv run python -m bench.validate_oracles` sem falhas. T2-T4 perturbadas
(42 tarefas restantes) ficam para continuação de T048, após revisão do
usuário deste primeiro lote.

---

## D3j — T048 construído (T2, 18/18): "mesma tarefa" não é automático por
família — três armadilhas de perturbação vazia/inválida encontradas e
evitadas ANTES de construir qualquer arquivo

T2 são algoritmos, não primitivas de preparação de estado — a pergunta "essa
perturbação ainda é reconhecivelmente a mesma tarefa, ou virou um problema
diferente com o mesmo nome?" (levantada explicitamente pelo usuário antes
desta rodada) exigiu checagem computacional por instância, não só por
família, e revelou três armadilhas genuínas:

1. **Ordenação de qubits pode ser um no-op silencioso.** `.reverse_bits()`
   só perturba algo se o alvo não for simétrico sob reversão completa.
   `grover_3q`/`grover_4q` têm strings marcadas palíndromas (101, 1001) —
   reversão mapeia o valor marcado nele mesmo, e o circuito inteiro (oráculo
   depende só do inteiro marcado, difusor é totalmente simétrico por
   permutação de qubits) fica invariante. Mais notável: as TRÊS instâncias
   de `qaoa_maxcut_*` (triângulo, ciclo-4, ciclo-5) são invariantes sob
   reversão completa, porque todo grafo-ciclo C_n tem a reflexão i -> n-1-i
   como automorfismo — um fato estrutural sobre ciclos, não coincidência das
   três instâncias. Ordenação de qubits foi EXCLUÍDA por completo da família
   QAOA aqui (0 de 3 instâncias), não só evitada em uma. `qpe_5q` também
   deu reversão-simétrica (verificado, não óbvio a priori) — excluído,
   movido para parametrização simbólica.
2. **Fase relativa é vazia num alvo totalmente determinístico.** Os alvos de
   Bernstein-Vazirani e QPE colapsam para um ÚNICO estado de base
   computacional (afora a ancilla fixa |-> do BV) — um RZ em qualquer qubit
   de um registro de base única é fase global pura, invisível a
   `Statevector.equiv()` (tolerante a fase global por definição). Fase
   relativa foi restrita às famílias com alvo genuinamente multi-termo:
   Simon (verificado), Grover, QAOA — checado computacionalmente para uma
   instância de cada antes de usar em todas.
3. **Restrição de gate set para {rz, sx, x, cx} parece quebrar silenciosamente
   em SWAP + esta combinação específica em `optimization_level >= 2`** — mas
   NÃO é um bug do transpilador (ver [[D3k]] para a investigação completa e a
   correção do que esta sessão registrou antes disso, em T1, como "quirk"): é
   `TranspileLayout.final_layout`, um comportamento documentado e
   propositalmente suportado — a partir de `optimization_level >= 2`, sem
   `coupling_map`, o transpilador pode implementar um SWAP lógico só
   permutando quais posições de saída correspondem a quais qubits de entrada
   (sem emitir gates físicos de SWAP), registrando essa permutação em
   `final_layout`. `Operator(circuito_transpilado)` ignora esse metadado — daí
   a fidelidade ~1e-32 — mas `Operator.from_circuit(circuito_transpilado)`
   (que LÊ `final_layout`) concorda exatamente com o circuito original. `qpe_
   5q` transpilou "errado" por essa razão; opt_level 0/1 não aciona esse
   comportamento porque não têm liberdade de layout a explorar. Toda
   construção canônica de QPE tem um SWAP interno (do estágio de QFT
   inversa), então restrição de gate set foi excluída das TRÊS instâncias de
   QPE aqui de qualquer forma — não porque o transpilador esteja errado, mas
   porque a metodologia de comparação de `validate_oracles.py` (`Operator.
   equiv()` direto, sem correção de layout) precisaria ser generalizada para
   lidar com isso, e isso ficou fora do escopo desta rodada. Registrado para
   que qualquer tarefa futura envolvendo SWAP + `transpile()` com
   `optimization_level >= 2` sem `coupling_map` saiba usar `Operator.
   from_circuit()`, não `Operator()`, se decidir enfrentar isso.

Consequência: a distribuição final de T2 (4 gate-set-restriction, 5
qubit-ordering, 4 symbolic-parameterization, 3 relative-phase, 2
composition) não é 4/4/4/3/3 como T1 — é o resultado honesto de quais
famílias preservam a natureza de CADA tarefa, não uma meta a forçar. T3/T4
devem compensar para que o balanceamento ENTRE tiers (não dentro de cada
tier) se aproxime do equilíbrio.

**VQE (3 instâncias) exigiu uma extensão real do validador.** `relative-
phase` e `composition` foram descartados para as 3 tarefas de VQE porque
mudam a energia alcançada — o ponto físico do VQE é atingir a energia do
estado fundamental, então "a mesma construção + uma fase extra" deixaria de
medir "construiu o ansatz certo" e passaria a medir "construiu ALGO que
atinge uma energia diferente, não especificada" — uma mudança de tarefa, não
uma perturbação, corretamente NÃO enviada. `gate-set-restriction` e
`symbolic-parameterization` (com uma fórmula fechada para theta, derivada à
mão de dE/dtheta=0 sobre o Hamiltoniano já citado — verificada contra os 3
valores canônicos de `ansatz_theta_rad`, e agora travada como asserção em
`build_t2_perturbed.py`, não só checada uma vez no sandbox) preservam a
física exatamente e foram usadas. `qubit-ordering` (trocar qual qubit físico
tem o papel X vs RY, com os coeficientes Z0/Z1 do Hamiltoniano trocados para
casar) é fisicamente válido (verificado: mesma `exact_ground_energy`,
mesmo theta) mas exigiu generalizar `check_energy_sanity_seeds` em
`validate_oracles.py`, que tinha os papéis do ansatz (X/RY/CX) HARDCODED —
agora lidos do payload com os valores canônicos como default, então nenhum
oráculo VQE existente muda de comportamento.

**Erro pego antes de embarcar**: o primeiro rascunho do prompt de
`vqe_h2_r055_perturbed` (gate-set-restriction) citava uma identidade
RY(theta) = RZ(-pi/2), SX, RZ(pi-theta), SX, RZ(-pi/2) de memória — verificada
como FALSA antes de escrever o arquivo (`Operator.equiv()` = False). A
identidade correta (RZ(-pi), SX, RZ(pi-theta), SX, fase global zero) foi
obtida do próprio `transpile()` do Qiskit, não de memória, e só então usada
no prompt — mais uma instância da disciplina "nunca confiar sem verificar",
desta vez pegando um erro na AUTORIA do prompt, não na construção do
oráculo.

**Composição não introduz um "talvez coincida por acaso"**: como QFT é uma
transformação unitária (bijetiva), qualquer diferença no estado PRÉ-QFT
mapeia para um estado PÓS-QFT igualmente distinguível — a checagem de
equivalência após compor com QFT é exatamente tão discriminante quanto
checar o alvo pré-QFT diretamente. Isso resolve, por argumento matemático e
não só por precedente de T1, a preocupação de que compor com QFT "dilua" o
que está sendo testado.

Todas as 18 tarefas passam nas 4 checagens de `validate_oracles.py`,
incluindo o ansatz trocado do VQE (erro de energia 0.0033 Ha, dentro de
`ENERGY_SANITY_TOL=0.02`). Conjunto completo agora: 60 canônicas + 36
perturbadas (T1+T2) = 96 oráculos, todos passando.

### T048 concluído (T3 12/12, T4 12/12): contabilidade final das 60
perturbadas — distribuição por tier, todas as exclusões agrupadas por
causa, e uma advertência sobre o que `delta_perturbacao` por família pode e
não pode sustentar

T3 e T4 seguiram a mesma disciplina computacional-antes-de-atribuir (D3i,
acima nesta seção) e não introduziram nenhuma família ou tipo de armadilha
nova além das já catalogadas em T1/T2 — só instâncias adicionais das MESMAS
duas causas estruturais (simetria sob reversão de registrador; blindness de
fase global num alvo de base única). A distribuição final por tier:

| Família \ Tier | T1 (18) | T2 (18) | T3 (12) | T4 (12) | Total (60) |
|---|---|---|---|---|---|
| relative_phase | 4 | 3 | 2 | 2 | 11 |
| gate_set_restriction | 4 | 4 | 3 | 3 | 14 |
| qubit_ordering | 4 | 5 | 3 | 3 | 15 |
| symbolic_parameterization | 3 | 4 | 2 | 2 | 11 |
| composition | 3 | 2 | 2 | 2 | 9 |

Nenhum tier usou 4/4/4/3/3 além de T1 (que definiu esse padrão inicial, antes
de qualquer exclusão estrutural ter sido descoberta) — cada tier posterior é
o resultado honesto de quais famílias preservam a NATUREZA de cada tarefa
individual, não uma meta a forçar (a instrução original do usuário, desde o
início de T048). O total por família, 9-15 numa base de 60, fica
razoavelmente equilibrado apesar disso — `qubit_ordering` puxa para cima
(15) por ser estruturalmente a família mais "segura" na maioria das tarefas
que não têm simetria interna; `composition` puxa para baixo (9) porque foi
inteiramente excluída das 3 tarefas de VQE (T2), a única exclusão de
"mudança de identidade de tarefa" encontrada em todo o conjunto.

**Todas as exclusões, agrupadas por causa:**

1. **Perturbação vazia (a família não muda o alvo/unitária, ou muda só a
   fase global de um alvo determinístico)** — a causa mais comum, sempre
   verificada computacionalmente (`Statevector`/`Operator` `.equiv(...
   reverse_qargs())` ou `.equiv()` pós-RZ), nunca assumida:
   - T1: GHZ e W-state excluídos de `qubit_ordering` (estado
     permutation-simétrico sob qualquer reversão de qubits).
   - T2: `qaoa_maxcut_*` (as 3 instâncias) excluídas de `qubit_ordering`
     (todo grafo-ciclo C_n tem a reflexão i -> n-1-i como automorfismo —
     um fato estrutural sobre ciclos); `grover_3q`/`grover_4q` excluídos de
     `qubit_ordering` (strings marcadas palíndromas); uma instância de
     `qpe` excluída de `qubit_ordering` (simetria verificada, não óbvia a
     priori); BV e QPE excluídos de `relative_phase` (alvo colapsa para um
     ÚNICO estado de base computacional — RZ ali é fase global pura,
     invisível a `Statevector.equiv()`).
   - T3: `ising_zzz_3q` e `ising_zzzz_4q` excluídos de `qubit_ordering`
     (ambos são um ÚNICO termo Z-string cobrindo TODOS os qubits do
     registro — um termo-produto sobre todo o registro é invariante sob
     qualquer permutação de seus próprios qubits, reversão inclusive).
   - T4: `ghz_linear5_full`, `ghz_linear5_scattered_even`,
     `ghz_linear5_endpoints`, `ising_linear5_endpoints`,
     `zstring_linear5_scattered`, `zstring_linear5_full_chain` — SEIS
     instâncias excluídas de `qubit_ordering`, todas pela mesma razão
     estrutural: o conjunto de qubits que cada termo/subconjunto toca é
     simétrico sob i -> 4-i (par de endpoints, subconjunto par-de-índices,
     ou registro inteiro).
   - Padrão único subjacente a TODAS essas instâncias (14 no total, de 6
     tarefas-tipo distintas): a relabeling é um no-op exatamente quando o
     conjunto de qubits que uma estrutura toca — ou o alvo que ela produz —
     já é simétrico sob essa relabeling especificamente. Isso não precisou
     ser redescoberto a cada tier; a partir de T2 já era um padrão
     ESPERADO a checar, não uma surpresa.
2. **Mudança de identidade de tarefa (a perturbação mudaria O QUE está
   sendo medido, não só o quão fácil é reconhecer)** — encontrada em UM
   lugar só, T2's VQE: `relative_phase` e `composition` excluídas das 3
   tarefas `vqe_h2_*` porque ambas mudariam a energia do estado fundamental
   alcançada — o ponto físico do VQE — transformando "construiu o ansatz
   certo" em "construiu algo que atinge uma energia diferente, não
   especificada". Esta é a única categoria onde a exclusão não é sobre a
   perturbação ser vazia, mas sobre ela ser ilegítima mesmo sendo
   NÃO-vazia — motivo pelo qual essa checagem (a pergunta do usuário: "essa
   perturbação ainda é a mesma tarefa?") importa independentemente da
   checagem de vacuidade.
3. **Armadilha de transpilador aparentemente real, mas NÃO um defeito
   (ver [[D3k]])** — `gate_set_restriction` excluída das 3 instâncias `qpe_*`
   (T2) por causa de `TranspileLayout.final_layout` (SWAP interno da QFT
   inversa + {rz,sx,x,cx} + `optimization_level>=2` sem `coupling_map`)
   fazer `Operator()` cru discordar do circuito, ainda que `Operator.
   from_circuit()` concorde exatamente. A mesma combinação já tinha
   aparecido, sem registro formal em research.md, ao evitar QFT+swap na
   família `gate_set_restriction` de T1 (por isso [[D3k]] descreve DUAS
   ocorrências independentes) — corretamente resolvida como comportamento
   documentado do Qiskit, não um bug a relatar, mas ainda assim uma
   exclusão real neste conjunto porque `validate_oracles.py` usa `Operator()`
   cru em todo o módulo e generalizar isso ficou fora do escopo desta
   rodada (D3k tem o reprodutor mínimo e a análise completa).

> **SUPERADA em 2026-09-11** (migração v1→v2, ver `MIGRATION.md`): o
> parágrafo abaixo é sobre `delta_perturbacao` como métrica INFERENCIAL —
> T063, FR-023, comparação por gerador e por condição experimental (C1-C5)
> — nenhum dos quais existe em v2. Preservado sem alteração porque o
> RACIOCÍNIO sobre tamanho de célula continua correto e reaproveitável: se
> o relatório v2 quiser reportar taxa de sucesso da suíte de robustez
> QUEBRADA POR FAMÍLIA de perturbação (em vez de agregada), a mesma
> advertência se aplica de forma descritiva — a família `composition` só
> tem 9 tarefas no total, então uma quebra por família dentro de um único
> tier ainda seria uma amostra pequena, mesmo sem C1-C5 nem T063 por trás
> dela. O que não sobrevive à migração é o vocabulário de INFERÊNCIA
> ESTATÍSTICA entre condições ("teste de hipótese sobre diferença real
> entre famílias") — a suíte de regressão v2 reporta taxa de sucesso, não
> testa hipóteses.

**Advertência explícita sobre análise (v1), registrada enquanto o raciocínio
das exclusões estava fresco**: a distribuição de família NÃO é balanceada por
desenho — é o resultado de quais famílias são estruturalmente válidas para
cada tarefa individual, checado caso a caso. Isso tem uma consequência real
para T063 (cálculo de `delta_perturbacao`, FR-023): os efeitos de FAMÍLIA e
de TIER estão parcialmente confundidos (um tier específico nunca teve
`qubit_ordering` aplicada a todas as suas tarefas GHZ/ciclo/termo-completo,
por exemplo), e uma quebra de `delta_perturbacao` POR FAMÍLIA terá células
desiguais e, nalguns casos, pequenas (a família `composition` tem só 9
tarefas no total; excluindo qualquer uma delas por não sobreviver ao piso de
20% de D12, uma quebra por família dentro de um único tier pode cair para
2-3 tarefas). `delta_perturbacao` por família, portanto, é DESCRITIVO, não
inferencial, nestes tamanhos de célula — útil para relatar "esta família
pareceu mais fácil/difícil nesta amostra", não para sustentar um teste de
hipótese sobre diferença real entre famílias. A métrica que carrega peso
inferencial é o `delta_perturbacao` AGREGADO (canônica vs. perturbada, por
gerador e por condição, T063/FR-023) — com 60 pares completos, essa
agregação tem tamanho de amostra suficiente; a quebra por família não tem, e
não deve ser lida como se tivesse. Registrar isso agora, antes do piloto
(T055) rodar e produzir números reais, evita a tentação retrospectiva de
tratar uma célula pequena como evidência mais forte do que ela é.

Conjunto completo de T048 agora: **60 canônicas + 60 perturbadas = 120
oráculos**, todos passando `uv run python -m bench.validate_oracles`.
`check_perturbation_pairing()`'s invariante de completude (antes apenas
informativa) agora reporta PASS automaticamente — as 60 tarefas canônicas
têm, cada uma, exatamente um par perturbado.

---

## D3k — Correção: a "quebra do transpilador" em SWAP + {rz,sx,x,cx} +
`optimization_level>=2` NÃO é um bug do Qiskit — é `TranspileLayout.
final_layout`, documentado e usado de propósito; investigado após dois
achados independentes (T1, T2) para decidir se valia um relato upstream

[[D3j]] (item 3) e uma nota anterior em T1 (não commitada em research.md,
só na conversa) caracterizaram esse comportamento como "um bug real,
reproduzível do transpilador do Qiskit". O usuário pediu explicitamente,
diante de DUAS ocorrências independentes, uma investigação própria: um
reprodutor mínimo, a versão do Qiskit, e uma checagem se já é um issue
conhecido upstream — para decidir se merece um relato de bug real e uma
linha na dissertação como achado lateral, ou não.

**Reprodutor mínimo** (não precisa de QFT, DJ, nem 8 qubits — um único
SWAP de 2 qubits já basta):

```python
from qiskit import QuantumCircuit, transpile
from qiskit.quantum_info import Operator

qc = QuantumCircuit(2)
qc.swap(0, 1)
t = transpile(qc, basis_gates=["rz", "sx", "x", "cx"],
              optimization_level=2, seed_transpiler=1)

Operator(qc).equiv(Operator(t))               # False
Operator(qc).equiv(Operator.from_circuit(t))  # True
```

`t` sai como um circuito VAZIO (0 gates) — o SWAP "desaparece". Ambiente:
Qiskit `1.2.4`, `qiskit-aer` `0.15.1`.

**Causa raiz, confirmada pela própria documentação do Qiskit** (docstring de
`qiskit.transpiler.layout.TranspileLayout`, lido nesta investigação, não
citado de memória): a partir de `optimization_level>=2`, SEM `coupling_map`
(circuito livre para rodar em qualquer topologia), o estágio de roteamento
pode implementar um SWAP lógico simplesmente reatribuindo qual posição de
saída corresponde a qual qubit de entrada — sem emitir nenhum gate físico —
e registra essa permutação em `TranspileLayout.final_layout`. Isso é
UNITARY-PRESERVING até essa permutação, não uma otimização incorreta: a
própria classe existe para que o chamador recupere a unitária real via
`Operator.from_circuit(t)` (que lê `final_layout`; citado no próprio
docstring: "used by Operator.from_circuit"), em vez de `Operator(t)` (que
ignora `TranspileLayout` inteiramente). Confirmado que essa é exatamente a
causa tanto do caso mínimo quanto do `qpe_5q` real de T2 (`Operator.
from_circuit()` concorda com o alvo original em ambos; `Operator()` cru
discorda em ambos).

**Não é um issue conhecido a relatar** — é comportamento documentado e
intencional, não um defeito. Não há bug a reportar upstream. A dissertação
não ganha um achado lateral de "bug do Qiskit"; ganha, em vez disso, uma
correção metodológica registrada aqui: `bench/validate_oracles.py`'s
`_build_alternatives`/checks de equivalência usam `Operator()` cru, não
`Operator.from_circuit()`, em TODO o módulo — o que é seguro hoje porque
nenhuma comparação atual passa por `transpile()` com `optimization_level>=2`
sem `coupling_map` sobre um circuito com SWAP interno (as tarefas de T4 que
usam `coupling_map` não-nulo já forçam roteamento físico real, sem essa
saída; T048's exclusão das 3 tarefas QPE de gate-set-restriction evita o
caso justamente onde apareceria). Continua correto enquanto essa condição
não for violada — registrado aqui para que quem adicionar uma futura
restrição de gate set sobre um circuito com SWAP saiba trocar para
`Operator.from_circuit()` em vez de reabrir esta investigação do zero.

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

## D8 — Teto de iterações [PENDENTE-PILOTO] — **SUPERADA (migração v1→v2)**

> **SUPERADA em 2026-09-11** (migração v1→v2, ver `MIGRATION.md`): a
> validação de saturação em T056 pressupunha o piloto de custo da matriz
> experimental, que não existe mais em v2 — não há mais "1.800 execuções ×
> 2,5 chamadas" para justificar minimizar iterações por custo agregado.
> `MAX_ITER` continua existindo como parâmetro do sistema; o que muda é
> COMO calibrá-lo: pela suíte de regressão (SC-007 — suíte completa em
> menos de 3h — e a taxa de sucesso por tier, FR-025), não por um piloto
> dedicado medindo onde a curva de correção satura sob custo de API. A
> razão original (não truncar o efeito que se quer medir) não se aplica
> mais — v2 não está medindo um efeito de pesquisa, está calibrando um
> parâmetro de produto. Preservada abaixo, sem alteração, como registro de
> por que `MAX_ITER=5` foi a escolha inicial em v1 — o raciocínio é
> material do relatório, não uma decisão ainda em vigor.

**Decisão preliminar (v1)**: `MAX_ITER = 5`, validar saturação em T056.

**Razão (v1)**: valor escolhido para não truncar o efeito que o experimento
quer medir. Se o piloto mostrar que a curva satura em 3, reduzir — cada
iteração a mais custa dinheiro em 5.400 execuções e não altera a conclusão.

---

## D9 — Idioma dos prompts [PENDENTE-PILOTO] — **SUPERADA (migração v1→v2)**

> **SUPERADA em 2026-09-11** (migração v1→v2, ver `MIGRATION.md`): o "braço
> de controle em português no piloto" era uma condição experimental —
> comparar recall/taxa de sucesso entre um braço inglês e um braço
> português é uma pergunta de PESQUISA (o idioma da consulta afeta o
> sistema? por quanto?), não uma decisão de produto. Em v2 não há braço de
> controle a rodar; a escolha de idioma dos prompts passa a ser decidida
> por teste direto na suíte de regressão (FR-025/SC-007) — se um idioma
> degrada recall@8 de forma mensurável contra a suíte, o produto usa o
> outro, sem precisar de um experimento dedicado para justificar a escolha.
> O achado em si (se best documentation recall favorece consultas em
> inglês) continua interessante e citável no relatório — só deixou de ser
> uma pergunta que o produto precisa responder via piloto formal.

**Decisão preliminar (v1)**: prompts de sistema em inglês, enunciados de
tarefa em inglês, com braço de controle em português no piloto.

**Razão (v1)**: toda a documentação recuperada é em inglês; misturar idiomas
entre consulta e corpus tende a degradar a recuperação. Mas isso é hipótese,
não fato, e o resultado é interessante por si só num programa brasileiro.
Medir e documentar, seja qual for o resultado.

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

## D12 — Estratégia de perturbação [PENDENTE-PILOTO] — **CRITÉRIO DE DESCARTE SUPERADO (migração v1→v2)**

> **Critério de descarte SUPERADO em 2026-09-11** (migração v1→v2, ver
> `MIGRATION.md`): o critério abaixo ("descartar perturbações em que o
> gerador de fronteira, na condição completa, não passe de 20% de acerto")
> dependia do piloto experimental (T055) e da condição C5, nenhum dos quais
> existe em v2 — não há mais "condição completa" no sentido de C1-C5, nem
> um piloto dedicado para calibrar dificuldade antes de decidir o que
> descartar. **As CINCO FAMÍLIAS abaixo continuam válidas e já construídas
> integralmente** — as 60 variantes perturbadas de T048 (D3i, D3j, D3k)
> instanciam exatamente estas cinco famílias, verificadas oráculo por
> oráculo com a mesma disciplina do conjunto canônico. O que muda de função
> é o PAPEL delas: eram controle de contaminação de treino (memorização) —
> um instrumento experimental — e passam a ser teste de robustez do
> produto (o sistema continua funcionando quando a tarefa não é
> textualmente idêntica a algo memorizável?), sem precisar de um piloto de
> dificuldade nem de um critério de descarte por taxa de acerto: uma
> variante perturbada que o produto não resolve é, em v2, um resultado de
> teste a reportar (falhou o teste de robustez X), não um item a remover do
> conjunto.

**Decisão (v1)**: cinco famílias, com quantidade por família definida após
teste piloto de dificuldade.

| Família | Exemplo |
|---|---|
| Fase relativa | GHZ com fase φ=2π/5 no q2 |
| Restrição de gate set | apenas {RZ, SX, CX} |
| Convenção de ordenação | endianness explicitamente invertido |
| Composição | QFT seguida de difusor de Grover no mesmo registrador |
| Parametrização simbólica | `Parameter` em vez de valor fixo |

**Razão (v1)**: a perturbação precisa quebrar a memorização sem tornar o
item insolúvel. Se a taxa de acerto na variante perturbada cair a zero em
todas as condições, o item não mede nada — vira ruído.

**Critério (v1, superado)**: descartar perturbações em que o gerador de
fronteira, na condição completa, não passe de 20% de acerto.

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

> **EMENDADO em 2026-09-23, para descrever o que de fato aconteceu.** A
> decisão original dizia que o agente rodava em container. **Ele nunca
> rodou.** A imagem `quantum-rag-app:latest` foi construída, validada uma vez
> (T103) e **nenhum container `app` jamais foi criado** — `docker compose ps
> -a`, que inclui containers parados, lista apenas `qdrant`. Todos os números
> registrados neste projeto — o baseline, as 3 h 26 min de SC-007, e o
> resultado de 0/360 em que a tese mais se apoia — foram produzidos pelo
> **venv do sandbox** (`/home/agent/.venvs/qcagent/bin/python3`), fora do
> ambiente que este documento declarava canônico.
>
> Pior: **os registros não permitiam descobrir isso.** `lib_versions` grava
> versões de pacote e nada que identifique o ambiente — sem hostname, sem
> digest de imagem, sem executável. A pergunta "onde isto rodou?" não era
> respondível a partir dos dados, só da memória de quem rodou. Corrigido em
> T106 (ver F21).
>
> **O que a emenda NÃO retrata como desastre, porque não é**: a RAZÃO
> substantiva de D15 continuou satisfeita o tempo todo. O motivo nº 1 abaixo
> é `fork` em Linux, e não "container" por si. Verificado nos dois:
>
> | | sandbox venv | imagem canônica |
> |---|---|---|
> | platform | Linux 7.0.12 | Linux 7.0.12 |
> | start method | `fork` | `fork` |
> | qiskit / aer / numpy / scipy | 1.2.4 / 0.15.1 / 1.26.4 / 1.17.1 | idênticos |
>
> Ou seja: a propriedade que D15 existia para garantir (Linux + `fork`, nunca
> `spawn` do Windows) valeu em todas as execuções. O que não valeu foi o
> MECANISMO descrito. Um documento que descreve um ambiente nunca usado é a
> mesma classe de falsa garantia que um campo gravado que ninguém verifica —
> e este projeto já encontrou quatro dessas (F21).
>
> **Risco residual, declarado**: a geração não é afetada (sandbox e container
> falam com o MESMO Ollama no host). A VERIFICAÇÃO roda localmente —
> `Statevector`, `Operator.equiv()`, comparações com tolerância — e BLAS ou
> despacho de CPU diferentes mudam os últimos bits, o que pode virar um
> `equiv()` na fronteira da tolerância. As versões coincidem; os builds e o
> caminho de CPU podem não. Isso é testável e ainda não foi testado: executar
> a suíte uma vez no container e comparar com `99960870239e97e7` com o
> `analysis/compare.py` que já existe. 0/360 entre DOIS ambientes genuinamente
> diferentes seria uma afirmação muito mais forte que 0/360 dentro de um só.

**Decisão (emendada)**: o ambiente canônico é **Linux com `multiprocessing`
usando `fork`**, `qdrant` em container, e **Ollama nativo no host Windows**,
alcançado em `host.docker.internal:11434`. O agente roda num venv Linux —
hoje o do sandbox; a imagem `app` é uma segunda encarnação VÁLIDA do mesmo
ambiente, ainda não exercitada de ponta a ponta. O que nunca é aceitável
continua sendo o que a decisão original proibia: misturar execução nativa no
Windows (`spawn`) com execução Linux entre sessões de desenvolvimento e a
rodada final.

**Decisão original, preservada para registro**: `app` (agente) e `qdrant`
rodam em containers via `docker-compose.yml`; **Ollama roda nativamente no
host Windows**, nunca como serviço containerizado, alcançado em
`host.docker.internal:11434`. Desenvolvimento **e** a matriz experimental
completa DEVEM rodar nesta mesma configuração — nunca uma mistura de execução
nativa no Windows e execução containerizada entre sessões de desenvolvimento
e a rodada final.

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

## D18 — Cache persistente dos modelos fastembed e CA corporativa para redes que interceptam TLS

**Achado**: `make index`/`ingest.py` falhou com um erro de verificação de
certificado TLS ao baixar o modelo esparso `Qdrant/bm25` do HuggingFace Hub —
a cadeia de certificados apresentada continha um certificado AUTOASSINADO.
Isso é a assinatura característica de interceptação de TLS (proxy
corporativo ou antivírus fazendo inspeção SSL man-in-the-middle), não um
problema de configuração do HuggingFace ou do fastembed em si.

**Duas coisas erradas, resolvidas separadamente**:

### 1. A dependência de rede deveria ser de primeira execução, não por execução

`FastEmbedEmbedder` (`src/qcagent/retrieval/embedding.py`) nunca passa
`cache_dir` ao construir `TextEmbedding`/`SparseTextEmbedding` — verificado
em `fastembed/common/utils.py::define_cache_dir`: sem `cache_dir` explícito
nem a variável de ambiente `FASTEMBED_CACHE_PATH`, o default é
`{tempfile.gettempdir()}/fastembed_cache`, ou seja `/tmp/fastembed_cache`
dentro do container. `/tmp` não sobrevive a `docker compose down`/recriação
do container — cada container novo é um download novo, e uma execução
experimental que precisa de acesso à internet só para começar é frágil,
exatamente o tipo de dependência que D15 (Ambiente de execução canônico)
existe para eliminar.

**Decisão**: volume nomeado `fastembed_cache` em `docker-compose.yml`,
montado em `/root/.cache/fastembed` no serviço `app`, com
`FASTEMBED_CACHE_PATH=/root/.cache/fastembed` setado via `environment:` no
mesmo serviço (não em `.env` — é uma escolha de infraestrutura fixa, não
algo que varie por máquina, então fica ao lado do volume que ela aponta, os
dois não podem divergir por engano). Efeito: o download do modelo acontece
uma vez, na primeira execução depois de um volume novo; toda execução
seguinte reaproveita os pesos ONNX já em disco, sem tocar a rede.

### 2. Como fornecer um bundle de CA corporativo — nunca `verify=False`

`fastembed` baixa via `huggingface_hub.snapshot_download`, que usa
`requests` por baixo (confirmado em
`fastembed/common/model_management.py`). `requests` e `huggingface_hub`
respeitam `REQUESTS_CA_BUNDLE` nativamente; a biblioteca padrão `ssl`/
`urllib` (usada por outras partes do stack em chamadas HTTPS diretas)
respeita `SSL_CERT_FILE`. Setar as duas para o caminho de um arquivo PEM
com a CA raiz corporativa resolve a verificação SEM desabilitá-la —
`verify=False`, `-k`, ou qualquer contexto SSL não verificado está
proibido neste projeto: isso desabilitaria a verificação para TODA
requisição, não só as interceptadas, e esconderia silenciosamente um
ataque man-in-the-middle real caso um dia aconteça um.

**Duas rotas documentadas, sem rebuild de imagem sempre que possível**:

1. **Variáveis de ambiente** (`.env`, ver `.env.example`):
   `REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE` apontando para o PEM da CA. Cobre
   `requests`/`httpx`/`huggingface_hub` — o caminho do download do
   fastembed especificamente — sem precisar reconstruir a imagem. Exige que
   o arquivo PEM esteja acessível DENTRO do container num caminho que essas
   variáveis referenciem (bind mount do arquivo, ou copiado no build — ver
   item 2).
2. **`Dockerfile`** (bloco comentado, inativo por padrão): `COPY` do
   arquivo `corporate-ca.crt` (gitignored — nunca um certificado real vai
   para o controle de versão) para
   `/usr/local/share/ca-certificates/corporate-ca.crt` seguido de `RUN
   update-ca-certificates`, instalando a CA no trust store DO SISTEMA
   (Ubuntu/OpenSSL) — necessário para qualquer ferramenta que ignore as
   variáveis de ambiente acima e confie só no trust store do SO. Rota mais
   pesada (exige rebuild), usada só se a rota 1 não cobrir alguma
   ferramenta específica.

**Por que a imagem já tinha o pré-requisito**: `ca-certificates` já está
instalado no `Dockerfile` (base `nvidia/cuda:12.1.0-runtime-ubuntu22.04`) —
`update-ca-certificates` já está disponível, não precisou de um pacote novo.

**Verificado ao vivo, não só derivado da leitura do código-fonte**: o
sandbox onde esta seção foi escrita tinha exatamente o mesmo sintoma —
proxy de saída com uma CA autoassinada própria (`O=Docker Sandboxes, CN=
Docker Sandboxes Proxy CA`), reproduzindo o erro relatado
(`SSLCertVerificationError: self-signed certificate in certificate chain`
ao baixar `Qdrant/bm25`). Testado: combinar o trust store do sistema com a
CA interceptadora num único arquivo PEM e apontar `REQUESTS_CA_BUNDLE`/
`SSL_CERT_FILE` para ele — sem tocar `verify=False` em lugar nenhum —
completou o download com sucesso. O layout de cache resultante confirmou
exatamente o descrito abaixo:
`models--Qdrant--bm25/snapshots/22b8d2af71a76161e18dd432d2cee0eefa66e412/`
— `<hash>` é o commit do repositório HF resolvido no momento do download,
validando também a seção seguinte sobre onde recuperar essa informação.

### Nome exato do modelo e versão — e um limite real do fastembed 0.3.6

Por Princípio II, uma versão que baixa em tempo de execução sem pinagem é
uma lacuna de reprodutibilidade. Registrado aqui com exatidão:

- **Biblioteca**: `fastembed==0.3.6`, resolvido e travado por hash em
  `uv.lock` (`pyproject.toml` declara `>=0.3,<0.4`; `uv sync --frozen` no
  `Dockerfile` é o que de fato fixa a versão instalada).
- **Modelo esparso (BM25, D5)**: `Qdrant/bm25` — único, sem alternativa
  pendente de piloto.
- **Modelo denso (D4, PENDENTE-PILOTO)**: `jinaai/jina-embeddings-v2-base-code`
  (768 dim, candidato ativo por default —
  `DEFAULT_DENSE_MODEL = DENSE_MODEL_CODE` em `embedding.py`) ou
  `intfloat/multilingual-e5-large` (1024 dim, candidato alternativo) — qual
  dos dois é usado na rodada final depende do piloto de recall@8 de D4,
  ainda não executado (M1 passou sem precisar dele — D17-1).

**Limite real, verificado no código-fonte, não contornado**: a versão
0.3.6 de `fastembed` não expõe nenhum parâmetro `revision` no caminho de
download — `download_files_from_huggingface` (`fastembed/common/
model_management.py`) chama `snapshot_download(repo_id=..., cache_dir=...,
local_files_only=...)` sem `revision`, e nem `TextEmbedding.__init__` nem
`SparseTextEmbedding.__init__` repassam um `revision` até lá (confirmado
lendo as assinaturas e o corpo da função, não assumido). Isso significa que
`fastembed==0.3.6` sozinho NÃO garante baixar exatamente os mesmos pesos
duas vezes em máquinas diferentes se o repositório upstream no HuggingFace
Hub mudar entre uma execução e outra — um gap real de reprodutibilidade que
pinar a biblioteca, por si só, não fecha.

**Mitigação prática, já garantida pela decisão da seção 1 acima**: o cache
persistente (`fastembed_cache`) congela os pesos ONNX EFETIVAMENTE baixados
na primeira execução — todo run subsequente contra o mesmo volume reusa
exatamente esse artefato, independente do que aconteça no HuggingFace Hub
depois. A garantia de reprodutibilidade passa a ser "mesmo volume Docker",
não "mesma revisão do repositório" — mais fraca do que uma pinagem de
revisão de verdade, mas suficiente para as 5.400 execuções da matriz
completa, que devem rodar contra o mesmo volume por construção (D15: mesmo
ambiente canônico do início ao fim). **Para provenance**, o commit
resolvido no momento do download fica gravado no próprio layout de cache
do `huggingface_hub` — o diretório `models--<org>--<nome>/snapshots/<hash>/`
dentro do volume tem `<hash>` como o commit SHA do repositório HF no
momento do download; registrar esse hash manualmente (ex.: `ls
/root/.cache/fastembed/models--Qdrant--bm25/snapshots/` dentro do
container) antes da rodada experimental final é o jeito de recuperar essa
informação hoje, já que a biblioteca não a expõe programaticamente.
Trabalho futuro genuíno, não implementado agora: gravar esse hash
automaticamente em `RunRecord.lib_versions` (mesmo padrão já usado para
`ollama`, D15 item 3) exigiria ler o layout de cache diretamente, já que
`fastembed` não expõe a revisão resolvida via sua própria API.

**Alternativas rejeitadas**:
- Desabilitar verificação de certificado (`verify=False`, variável
  `PYTHONHTTPSVERIFY=0`, ou similar) — rejeitada categoricamente pelo
  usuário e pela postura de segurança do projeto: esconde qualquer
  interceptação real, não só a corporativa esperada.
- Baixar o modelo manualmente e commitar os pesos ONNX no repositório —
  rejeitada: pesos de modelo são binários grandes (multiplica o tamanho do
  repositório Git por gigabytes) e uma cópia commitada ainda não resolve
  QUAL revisão foi usada, só esconde a pergunta.
- Fixar `HF_HUB_OFFLINE=1` como default do projeto — rejeitada: quebraria o
  primeiro uso de qualquer ambiente novo (nenhum modelo ainda em cache);
  correto como uma flag opcional que o usuário liga DEPOIS do primeiro
  download bem-sucedido, não como comportamento padrão do projeto.

---

## D18b — Modelos fixados em revisão, carregados só offline; suíte de testes sem rede

**Decisão**: (1) as revisões exatas (commit do HuggingFace) dos dois modelos
carregados ficam fixadas no código (`PINNED_MODEL_REVISIONS`,
`src/qcagent/retrieval/embedding.py`: jina `516f4baf…`, bm25 `22b8d2af…`);
(2) `scripts/fetch_models.py` (`make models`) é o ÚNICO código que baixa pesos,
e baixa exatamente essas revisões; (3) todo carregamento usa
`local_files_only=True` a partir do cache fixado, precedido de uma checagem
que falha na hora, nomeando o problema e a correção, se o cache não tiver a
revisão fixada ou se faltar qualquer arquivo; (4) a imagem traz os modelos
embutidos em `/opt/fastembed` (baixados no build), o que substitui o volume
nomeado de D18; (5) `tests/conftest.py` faz qualquer conexão não-loopback
durante os testes falhar na hora com `NetworkAccessInTests`, e grava ids das
falhas, revisão git e duração em `.pytest_cache/failures.log`.

**Razão**: uma execução da suíte levou 99 s e terminou com uma falha e cinco
erros que ninguém conseguiu nomear e que não se reproduziram em três
execuções seguintes. A causa, lida no fonte do fastembed 0.3.6 e não
presumida: `download_files_from_huggingface` chama
`snapshot_download(local_files_only=False)`, que CONSULTA o Hub a cada
construção, mesmo com o modelo inteiro em cache; se a chamada falha,
`download_model` dorme 3 s e depois 9 s entre tentativas. Os testes de
integração da US2 constroem modelos reais, então a suíte dependia da rede
em tempo de execução. O cache também ficava no padrão do fastembed,
`/tmp/fastembed_cache`, que não sobrevive. Uma suíte que falha às vezes por
motivos fora do código ensina a ignorar falhas; é o mesmo raciocínio do
ambiente canônico de D15.

**Fecha a lacuna que D18 deixou aberta**: D18 registrou que o fastembed 0.3.6
não aceita revisão, e que a reprodutibilidade dependia de "mesmo volume
Docker". Agora a revisão está no código e é conferida em todo carregamento;
um cache com outra revisão é recusado.

**Achados ao implementar, cada um com evidência**:
- **A primeira checagem do cache era insuficiente.** Verificava `refs/main` e
  o diretório do snapshot, e aprovou um cache cujos arquivos não existiam; o
  carregamento falhou dentro do onnxruntime com `NO_SUCHFILE`, exatamente o
  tipo de falha sem nome que se queria eliminar. Agora confere cada arquivo
  que o fastembed abre (`model_file` + `additional_files`). A exceção é o
  `mock.file` do `Qdrant/bm25`, placeholder do próprio fastembed ("bm25 does
  not require a model, so we just use a mock"), que não existe no upstream.
- **O repositório está num mount virtiofs sem suporte a symlink.** O cache do
  HuggingFace é feito de symlinks (`snapshots/<commit>/arquivo ->
  ../../blobs/<hash>`); uma cópia com `cp -a` produziu links que não
  resolvem. O `huggingface_hub` detecta a falta de suporte e grava arquivos
  reais, então `make models` funciona nesse mount; copiar um cache à mão
  exige desreferenciar (`cp -rL`).
- **A interceptação de TLS era intermitente, e o interceptador foi
  identificado.** `snapshot_download` falhava com "self-signed certificate in
  certificate chain" enquanto a MESMA URL respondia 200 via `requests` — não
  era flakiness de rede: repetindo o handshake através do proxy, cerca de uma
  conexão em cinco chega assinada por um **"Kaspersky Anti-Virus Personal
  Root Certificate"** (antivírus fazendo inspeção SSL na máquina host), e as
  demais chegam com a cadeia real da Amazon. O CA do proxy do sandbox já
  estava no trust store; o da Kaspersky não. Resolvido como D18 manda —
  fornecendo o CA, nunca `verify=False`: o certificado foi extraído da
  cadeia interceptada para `./corporate-ca.crt` (gitignored) e instalado no
  trust store do sistema; depois disso, 11 de 11 conexões interceptadas
  verificam OK.
- **Trust store do sistema e bundle do `certifi` são rotas COMPLEMENTARES,
  não alternativas.** O primeiro build da imagem instalou o CA no trust
  store do sistema e ainda assim falhou: `requests` (logo `huggingface_hub`,
  logo o download) verifica contra o bundle do `certifi`, não contra o do
  sistema. A imagem agora também define `REQUESTS_CA_BUNDLE`/`SSL_CERT_FILE`
  apontando para o bundle do sistema, no qual `update-ca-certificates` já
  fundiu qualquer CA corporativo. O `COPY corporate-ca.crt*` usa glob: nada
  a descomentar, no-op quando o arquivo não existe.
- **O cache fixado NÃO pode ficar dentro do repositório.** Primeiro
  `make models` limpo baixou os 641 MB de blobs e deixou todos os diretórios
  de snapshot VAZIOS: o layout do HuggingFace liga `snapshots/<commit>/
  arquivo` a `blobs/<hash>` por symlink, e no mount virtiofs do repositório
  `symlink()` retorna sucesso sem criar nada. O default passou a ser
  `$XDG_CACHE_HOME/qcircuit-agent/fastembed` (fora do mount), e
  `fetch_models.py` sonda suporte a symlink ANTES de baixar, recusando com
  a instrução de apontar `FASTEMBED_CACHE_PATH` para um sistema de arquivos
  local.

**Verificado de ponta a ponta (depois das correções acima)**: `make models`
a partir de cache limpo baixa as duas revisões fixadas e confirma o
carregamento offline; `docker compose build app` conclui, baixando os modelos
no build; `docker run --network none` carrega os modelos e produz embeddings
dentro do contêiner — prova de que nada em tempo de execução precisa de rede.
Além disso: suíte completa verde com o guarda ativo (nenhum teste precisava
de rede além deste); a construção antiga, sem `local_files_only`, é recusada
pelo guarda em 0,00 s, em vez de consultar o Hub e dormir; cache vazio falha
em menos de 2 s com a instrução `make models`; uma falha deliberada ficou
registrada em `failures.log` com nome, revisão git e duração.

**Alternativas rejeitadas**:
- **Só `HF_HUB_OFFLINE=1`** — insuficiente sozinho: com o modelo ausente o
  fastembed ainda cai no laço de tentativas com sleep, e a proteção dependeria
  de uma variável de ambiente estar setada em todo contexto. Mantido no
  conftest como camada extra, não como a garantia.
- **Pular (`skip`) os testes que precisam do modelo quando o cache falta** —
  esconderia a lacuna; um cache ausente é uma precondição de ambiente e deve
  falhar com nome e correção.
- **Manter o volume nomeado de D18** — torna o download um custo de primeira
  execução, mas um volume novo ainda precisa de rede em tempo de execução.

---

## D19 — Gramática da linguagem de asserção (US3): forma final e limites de escopo

**Decisão**: gramática textual mínima e fechada — quatro formas de
avaliação (`PROBABILITY`/`AMPLITUDE`/`PHASE_DIFF` sob um `AmplitudeAssertion`
comum, `MEASURES`, `EIGENSTATE_OF`, `GATES_SUBSET_OF`), mais um açúcar
sintático (`QUBIT(q) == "|label>"`, desabaçucarado para `EIGENSTATE_OF` em
tempo de parse) e um prefixo opcional (`INPUT(\|ket>) THEN <asserção>`),
parseada e avaliada por código Python determinístico
(`src/qcagent/validators/assertions.py`), nunca por um LLM. Resultado de
cada avaliação é TRI-ESTADO (`True`/`False`/`None`="não avaliável"), não
binário. Ver `data-model.md` §Linguagem de asserção para a sintaxe completa
e `plan.md` §Verificação sem referência para a decisão registrada junto do
código.

**Razão**: FR-010 exige que o usuário consiga declarar propriedades do
comportamento esperado sem fornecer um circuito de referência, e FR-013
exige que uma asserção mal formada seja recusada explicitamente — as duas
juntas só são satisfeitas por uma gramática pequena e fechada com parser
próprio, nunca por "deixar o LLM interpretar linguagem natural como
asserção" (isso reintroduziria exatamente a ambiguidade de julgamento que o
Princípio I existe para excluir do caminho de veredito). A forma final não
saiu da primeira proposta — chegou depois de duas rodadas de revisão do
usuário, cada uma resolvendo um problema concreto, não polimento:

1. **Açúcar `QUBIT`**: a forma geral (`EIGENSTATE_OF("XIII", -1)` para "a
   ancilla está em `|-⟩`") falha o próprio teste de usabilidade que US3
   define — exige saber que `|-⟩` é o autoestado `-1` de `X` e posicionar
   `N-1` caracteres `I` corretamente. Resolvido com açúcar de um qubit para
   os seis estados cardeais da esfera de Bloch, desabaçucarado em tempo de
   parse (nunca um segundo caminho de avaliação).
2. **`MEASURES` com duas formas sintaticamente distintas**: a proposta
   original tinha uma forma só, e `MEASURES([0,1,2]) == "101"` /
   `EIGENSTATE_OF("XII", -1)` liam a MESMA posição em direções OPOSTAS sem
   nenhum sinal visível — o mesmo erro silencioso de convenção que este
   projeto já pagou três vezes (D3c endianness, D3d somador, D3f sinal
   QUBO→Ising). As duas alternativas de mitigação eram: (a) avisar em tempo
   de execução quando a lista de `MEASURES` cobre o registro inteiro (onde
   as duas convenções divergem visivelmente), ou (b) dar a `MEASURES` uma
   forma nua (registro inteiro, convenção compartilhada) e uma forma com
   lista (subconjunto, convenção posicional), sintaticamente distintas.
   Escolhida (b) — resolve a colisão por CONSTRUÇÃO da gramática, não por
   um aviso que o usuário pode ignorar.
3. **Resultado tri-estado**: `PHASE_DIFF` entre duas amplitudes é
   estruturalmente indefinido quando uma delas é ~0. A terceira saída
   (`passed=None`, "não avaliável") foi decidida ANTES da implementação, não
   deixada para T084b — porque muda o contrato de `GuaranteeReport` (US4,
   `None` nunca conta como aprovação) e porque o loop de correção precisa de
   um comportamento definido quando a mesma asserção volta não-avaliável
   repetidamente. Decisão: duas ocorrências CONSECUTIVAS da mesma asserção
   (casada estruturalmente) não-avaliável encerram com
   `status="assertion_not_evaluable"`, distinto de `aborted` (esgotamento de
   `MAX_ITER`) e de `failed_semantic` (checagem bem posta que não passou) —
   regenerar não ajudou duas vezes seguidas, evidência de que o problema
   pode estar na declaração, não na geração.
4. **`INPUT(...) THEN <asserção>`, núcleo não extensão**: toda asserção sem
   este prefixo só testa comportamento a partir de `|0...0⟩`. Isso é
   suficiente para tarefas de preparação de estado, mas insuficiente — na
   verdade CEGO — para qualquer tarefa cujo conteúdo seja uma TRANSFORMAÇÃO
   geral (achado do exercício de validação a frio contra `qft_5q`, abaixo).
   `INPUT` prepara o registro num estado de base computacional (`X` por bit
   `'1'`, mesma convenção de ket já em uso) antes de evoluir o circuito sob
   teste. Várias asserções `INPUT` sobre entradas não-triviais distintas dão
   cobertura evidencial real de uma transformação — mesma lógica de
   `_check_by_composition` (D3b), com uma diferença que precisa ficar
   explícita: D3b testa uma proposição universal (equivalência unitária)
   contra uma referência CONHECIDA com k estados Haar-aleatórios, o que dá
   uma cota de probabilidade de falso positivo genuína; `INPUT` não tem
   referência nenhuma — cada asserção só testa a propriedade específica que
   o usuário escreveu, para aquela entrada específica. É cobertura maior,
   não uma garantia formal equivalente.

**Achados empíricos verificados antes de confiar na gramática** (não
assumidos a partir da documentação do Qiskit):

- **Convenção de ket = índice direto**: `int(ket_string, 2)` indexando
  `Statevector.data` bate exatamente com as chaves de
  `Statevector.probabilities_dict()` — confirmado construindo
  `qc.x(0);qc.x(2)` em 3 qubits e comparando `sv.data[5]` contra
  `probabilities_dict()["101"]`.
- **`probabilities_dict(qargs=...)` usa a convenção OPOSTA à prometida pela
  forma com lista de `MEASURES`**: o primeiro qarg listado aparece na
  posição MAIS À DIREITA da chave renderizada, não na mais à esquerda. Uma
  primeira implementação usando essa forma passou no primeiro teste
  (`bv_4q`, cujo segredo é coincidentemente palindrômico) e só falhou num
  segundo teste deliberadamente assimétrico — a diferença entre "parece
  certo" e "está certo" foi exatamente não confiar no primeiro caso de
  teste. Corrigido usando o array bruto `probabilities(qargs=...)` com um
  índice `j = sum(int(bit) << i for i, bit in enumerate(expected))`
  derivado e verificado à mão, nunca as chaves de `probabilities_dict`.
- **Nomes de gate de aridade variável fora de `get_standard_gate_name_mapping()`**:
  `mcx`, `barrier`, `mcphase`, `mcrx`, `mcry`, `mcrz` são nomes de instrução
  reais e usados neste projeto (`mcx` confirmado por `grep` no código de
  construção de oráculos) mas ausentes do mapeamento "padrão" de 54 gates do
  próprio Qiskit — teria produzido um `unknown gate name` falso-positivo em
  `GATES_SUBSET_OF` contra um circuito legítimo. Estendido explicitamente,
  não coberto por acidente.

**Correção registrada durante a implementação, não silenciosamente**: a
razão original para validar nomes de gate em `GATES_SUBSET_OF` ("nome
digitado errado torna a asserção vacuamente verdadeira, mesma direção de
falha de D3c/D3d/D3f") foi endossada pelo usuário e estava ERRADA — uma
checagem de subconjunto é fail-closed por construção, nunca passa
vacuamente num nome digitado errado. Corrigida para a razão real, mais
modesta (erro de parse preciso em vez de falha de asserção confusa). Ver F6
(report-notes.md) para a análise completa de por que a alegação errada foi
convincente antes de ser derivada com cuidado.

**Escopo real da gramática — achado do exercício de validação a frio, não
de revisão de desenho**: antes de implementar, três tarefas de tiers
diferentes (`qft_5q`/T2, `qubo_ising_3var`/T3, `ghz_linear5_full`/T4) foram
escritas à mão, sem consultar a especificação da gramática, para revelar
onde um usuário real tropeçaria. Um quarto exercício, depois da decisão de
dividir `MEASURES` em duas formas, usou `reversible_half_adder_4q`
especificamente para testar essa divisão contra um oráculo real antes de
implementar. Achados, todos verificados computacionalmente contra oráculos
reais, não hipotéticos:

- **Forte** para preparação de estado e propriedades qualitativas —
  `ghz_linear5_full`: nenhuma derivação numérica, só conhecimento
  conceitual do que a tarefa pede (autoestado coletivo, restrição de gate
  set).
- **Fraca** para tarefas cujo conteúdo inteiro é uma derivação numérica —
  `qubo_ising_3var`: a única asserção não-vazia possível (`PHASE_DIFF` entre
  dois estados de base) exigiu expandir a substituição QUBO→Ising à mão
  antes de saber o que escrever (`PHASE_DIFF(|000>, |111>) ~= -0.5`,
  verificado obtendo H(+++)=-0.25, H(---)=0.75, γ=0.5) — a mesma conta que
  CONSTRUIR o circuito exige, contradizendo a premissa central de US3. Ver
  "Threats to validity" em report-notes.md. **Registrado como limitação de
  cobertura, não alargada**: aceitar uma derivação pronta na gramática
  equivaleria a aceitar uma referência disfarçada.
- **Cega** (sem `INPUT`) para tarefas de transformação geral —
  `qft_5q`: uma QFT mal implementada pode passar em toda asserção ancorada
  só em `|0...0⟩`, porque a saída da QFT nesse caso específico é
  indistinguível de uma simples superposição uniforme (`H` em cada qubit,
  sem a estrutura de fase que distingue QFT de qualquer outra preparação de
  superposição uniforme). Este achado especificamente motivou o item 4
  acima (`INPUT`) — mitigado, não eliminado: o relatório de garantia (US4,
  ainda não implementado) precisa nomear esse ponto cego explicitamente
  quando uma tarefa de transformação geral só tem asserções ancoradas em
  `|0...0⟩`, em vez de passar em silêncio.
- Fora da gramática por desenho, não por omissão: recursos e topologia
  (`depth_ratio`, respeito ao `coupling_map`) são propriedades do
  CIRCUITO, não do estado — não pertencem a uma linguagem de asserção sobre
  estados. Uma transpilação bem-sucedida contra o `coupling_map` (já
  computada por `static_check`) É evidência sem referência de que a
  topologia foi respeitada; a decisão é surfar isso no relatório de
  garantia como verificado, não adicionar uma quinta forma de asserção
  sobre topologia.

Ver F7 (report-notes.md) para o relato completo do exercício como achado
metodológico por si só — ele definiu o escopo real do produto mais do que
qualquer quantidade de revisão de desenho teria.

**Alternativas rejeitadas**:
- **Unificar as convenções de `MEASURES` e `EIGENSTATE_OF`/`QUBIT`** — não
  há uma convenção única que sirva às duas (uma lista arbitrária de qubits
  não tem uma noção natural de "esquerda = maior índice"); rejeitada em
  favor de duas formas sintaticamente distintas (item 2 acima).
- **Alargar a gramática para aceitar um estado-alvo arbitrário** (ex.: "o
  estado final é aproximadamente X") — rejeitada categoricamente: isso É
  fornecer uma referência, só que disfarçada de asserção, o que anularia o
  ponto inteiro de US3 (verificação SEM referência).
- **Tradução automática de `Requirement`s `kind="property"`/
  `kind="output_format"` (já extraídos pelo `planner`, FR-009) para esta
  gramática via LLM** — permitida pelo Princípio I como "gerador de
  hipótese", mas rejeitada nesta fase: escopo genuinamente novo, não
  pedido por nenhuma FR de v2 explicitamente, e arriscaria reintroduzir a
  mesma ambiguidade que a gramática formal existe para evitar. Só
  `kind="n_qubits"`/`kind="gate_set"` (checáveis sem tradução nenhuma)
  ganham verificação automática nesta fase (T091).
- **Checar `EIGENSTATE_OF` por valor esperado (`⟨ψ|H|ψ⟩ == λ`) em vez de
  norma do resíduo** — rejeitada por F2 (report-notes.md): um valor
  esperado correto não implica autoestado. Verificado numericamente que a
  norma do resíduo detecta um caso em que um cheque de valor esperado, à
  mesma tolerância numérica usada em outra parte deste código
  (`DEFAULT_TOL=1e-9`), teria deixado passar — ver `plan.md`
  §Verificação sem referência para os números exatos.

---

## D20 — Critério de reprodutibilidade em duas camadas (emenda a SC-008)

**Decisão**: SC-008 deixa de ser um limiar único de 5% e passa a ter duas
camadas com critérios de naturezas diferentes: **igualdade exata (0%)** para o
que controlamos, e **piso de ruído medido e reportado** para o que não
controlamos. A medição exige cache de respostas frio entre as execuções.

**Razão**: o limiar de 5% foi escrito supondo ruído irredutível, sem que
ninguém soubesse se ele existia nem de onde vinha — SC-008 nunca havia sido
medido, porque até T102 nunca houve duas execuções completas para comparar.
Medido, o resultado foi 50,0% e depois 36,7% de divergência por tarefa, e a
investigação separou as causas em duas naturezas incompatíveis com um limiar
único:

1. **Defeitos nossos, corrigíveis, com divergência que DEVE ser zero**:
   `temperature` herdada do Modelfile (F15) e empates da fusão RRF resolvidos
   pela ordem dos segmentos do Qdrant (F17). Ambos corrigidos. Para esta
   camada, 5% é um critério errado em espécie, não em número: um sistema com
   4% de divergência aqui PASSA no limiar enquanto carrega um defeito, e é
   exatamente esse defeito que um critério de reprodutibilidade existe para
   pegar. Tolerar ruído residual não testa reprodutibilidade; testa que o
   ruído é pequeno, que é uma afirmação muito mais fraca.

2. **Estado interno do servidor de inferência, não corrigível por
   configuração** (F19): um prompt idêntico, mesmo seed, `temperature=0`,
   devolve uma resposta calculada do zero e outra servida do cache de
   prefixo/KV do próprio Ollama. Aparece em dois pontos de chamada (planner e
   gerador) com assinatura idêntica — é UMA fonte vista duas vezes, não duas.
   Para esta camada, exigir 0% seria um critério que o sistema não pode
   satisfazer por razões fora do código: uma luz vermelha permanente, que é
   o mesmo defeito social de um gate que sempre falha (ensina a ignorá-lo).

**Por que não escolher um número menor em vez de medir**: qualquer número
escolhido a priori herda o problema do 5% — é arbitrário e não distingue
"ruído do serving stack" de "defeito nosso ainda não achado". O piso MEDIDO
faz as duas coisas que um número escolhido não faz: dá a barra que um efeito
alegado precisa exceder para ser efeito, e muda quando o ambiente muda, em vez
de continuar afirmando um limite que deixou de valer.

**Alternativas consideradas**:

- *Manter 5% e seguir*: rejeitado. Não é falsificável na prática (qualquer
  resultado entre 0 e 5% "passa") e já mascarou três defeitos reais.
- *Exigir 0% em tudo*: foi minha recomendação inicial, revertida ao medir. A
  premissa era que toda fonte encontrada fosse defeito nosso; a terceira não
  é. Um SC inatingível por razões externas não é um gate.
- *Eliminar a fonte trocando o serving stack* (vLLM, llama.cpp direto, ou
  execução determinística forçada): não descartado, mas fora de escopo agora
  — mudaria D10 (o gerador local canônico) e exigiria reconstruir todo o
  baseline. Registrado como caminho, não como decisão.
- *Usar o cache de respostas deliberadamente como mecanismo de
  reprodutibilidade*: legítimo para REPLAY (reanálise de uma execução
  registrada), inútil para medir estabilidade do harness — um teste contra o
  cache devolve 0% por construção (F18).

**Consequência imediata**: `analysis/compare.py` não pode continuar tratando
qualquer mudança por tarefa como regressão (exit 1). Com um piso na camada do
gerador, o gate dispararia por azar em toda comparação. O redesenho está em
tasks.md T101b.

---

## Referências a levantar (Phase 0, continuação)

- Benchmarks existentes de geração de código quântico e suas limitações de oráculo
- Literatura sobre contaminação de dados de treino em benchmarks de código
- Trabalhos de reparo iterativo de código guiado por execução
- Estado da arte em RAG sobre documentação técnica versionada
