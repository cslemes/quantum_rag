# Estado do projeto e aprendizados

**Feature**: `001-qcircuit-agent` | **Período**: 11/08/2026 – 09/09/2026 (semanas 1–4 de 12)

Registro consolidado do que foi construído, do que foi medido e do que foi
aprendido. Complementa o `research.md` — este documento narra; aquele é o
registro normativo das decisões.

---

## 1. Onde o projeto está

| Fase | Escopo | Status |
|---|---|---|
| 1–2 | Setup e fundação | Completa |
| 3 (US1) | Validadores, nós, grafo | Completa — MVP funcional |
| 4 (US2) | Recuperação híbrida | Completa — portão M1 aprovado |
| 5 (dataset) | 60 tarefas canônicas + oráculos | **Completa — 60/60 verificados** |
| 5 (T048) | 60 variantes perturbadas | Próxima |
| 6 (US3) | Matriz experimental | Não iniciada |

O item de maior risco do projeto — o dataset com oráculos verificados
independentemente — está concluído quatro semanas antes do previsto no
cronograma original (que o colocava nas semanas 5–6).

### Cobertura do dataset canônico

| Tier | Famílias | Tarefas |
|---|---|---|
| T1 primitivas | Bell, GHZ, W-state, QFT, Deutsch-Jozsa, aritmética booleana reversível | 18 |
| T2 algoritmos | Bernstein-Vazirani, Simon, Grover, QPE, QAOA MaxCut, VQE H₂ | 18 |
| T3 formulação | Ising ponderado, strings-Z multicorpo, campo+acoplamento, QUBO→Ising | 12 |
| T4 hardware | Subconjuntos das famílias acima sob `coupling_map="linear_5"` | 12 |

Teleportação foi removida do conjunto canônico e substituída por aritmética
booleana reversível — ver §2.4.

---

## 2. Achados metodológicos

Esta é a parte com valor além do projeto. Quatro descobertas, todas obtidas
por medição e nenhuma prevista no desenho inicial.

### 2.1 Oráculos mais estreitos que seus enunciados falham em silêncio

**O achado central.** Três instâncias independentes da mesma classe de defeito:

| Caso | O enunciado permitia | O oráculo aceitava |
|---|---|---|
| GHZ (D3c) | qualquer circuito que prepare o estado | apenas a topologia em cadeia |
| Aritmética reversível (D3d) | qualquer implementação da função | apenas as sem encadeamento de ancilla |
| QUBO→Ising (D3f) | ambas as convenções de substituição | apenas uma delas |

Em todos os três, o oráculo é **internamente consistente** — passa em
verificação de propriedade, em construção independente, em tudo. O erro só
aparece quando um gerador produz uma resposta legitimamente correta e é
reprovado.

Consequência se não detectado: **todos os geradores são penalizados igualmente**,
o resultado parece plausível, e a corretude medida fica sistematicamente abaixo
da real por razão sem relação com capacidade do modelo.

Generaliza para muito além de circuitos quânticos: vale para qualquer benchmark
de código gerado em que o problema admita mais de uma implementação correta.
Candidato a seção própria na dissertação (registrado em D3g).

**A contramedida que funcionou**: para cada tarefa, perguntar explicitamente se
o oráculo aceita *todas* as implementações corretas do que o enunciado pede.
Onde não aceita, ou o oráculo se alarga ou o enunciado se estreita — e a
escolha é registrada. O inverso também importa: quando qualquer decomposição
serve, o enunciado declara isso ("any correct implementation is accepted").

### 2.2 Checks por medição podem ser estruturalmente cegos, não só frouxos

A verificação por medição da QFT reportava fidelidade 1,0000 para um circuito
que computava a QFT **inversa**. Motivo: a QFT de qualquer estado da base
computacional tem magnitude uniforme, independentemente de as fases estarem
corretas.

Nenhuma calibração de tolerância corrigiria isso. O check estava cego, não
permissivo.

O mecanismo de nota nunca esteve em risco — `Operator.equiv()` rejeitava o bug
incondicionalmente. Mas o check 4 não cumpria a função declarada.

**Correção**: compor o circuito primário com a inversa da construção
alternativa antes de medir, transformando divergência de fase em vazamento
visível. O bug passou a ler 0,0000.

**Generalização**: aplicada automaticamente sempre que a distribuição-alvo tem
pico abaixo de `PEAKEDNESS_THRESHOLD=0.9`, calculado por tarefa. Varreu Simon,
Grover, QAOA e Bernstein-Vazirani.

**Lição transferível**: testar o verificador contra um bug injetado revela o que
ajustar tolerância não revela.

### 2.3 Um diagnóstico incorreto é pior que nenhum

O loop de reparo recebeu um diff estrutural posicional que apontava
`[2] cx(1,2) vs cx(0,2)` — sinalizando como erro a única parte que estava
**certa** (topologia estrela é GHZ válido) e omitindo o erro real (três portas H
em vez de uma).

O modelo local seguiu o diff e reproduziu o mesmo erro nas iterações 1, 3 e 5.
Um modelo de fronteira, dado o mesmo código e o mesmo diff, corrigiu — mas
ignorando a prescrição do diff e identificando o problema real por conta
própria.

**Conclusão**: alinhamento posicional pressupõe uma ordenação canônica de portas
que não existe para circuitos equivalentes, gerando falsos positivos por
construção. Comparações de contagem (portas, qubits) são sólidas; diffs
posicionais não são, e não devem ser formulados prescritivamente quando a
divergência pode ser decomposição alternativa legítima.

**Implicação para a análise de erros (T064)**: é preciso distinguir falhas
causadas pelo modelo de falhas causadas por feedback enganoso. A literatura de
reparo iterativo raramente separa as duas.

### 2.4 Nem toda tarefa cabe nos oráculos disponíveis

Teleportação não se encaixa em `unitary` nem em `statevector`: o protocolo deve
funcionar para estado de entrada arbitrário, e ambos os tipos fixam um alvo
único. Testar com um estado fixo aprovaria um circuito acidentalmente correto
só para aquele estado.

Além disso, envolve medição intermediária e correção condicional — não é
unitário nem produz estado puro determinístico ao final.

**Decisão**: removida do conjunto canônico, substituída por família inequívoca.
O oráculo correto (fidelidade de canal sobre K estados aleatórios) está
esboçado em D3d como trabalho futuro, com a razão de não adotá-lo agora:
exigiria uma convenção para o circuito expor um "qubit de entrada", e falhas em
seguir a convenção se confundiriam com falhas na tarefa.

---

## 3. Verificações que valeram o custo

A construção independente dos oráculos (Princípio V) pegou **quatro** erros
reais de método:

1. QFT implementada à mão com direção de laço invertida (índice ascendente em
   vez de descendente) — pego por cross-check contra `QFTGate`
2. Deutsch-Jozsa classificado como `distribution` quando é `statevector` — a
   classificação anterior tinha sido escrita de memória; construir o oráculo a
   corrigiu. Simon e Bernstein-Vazirani foram reclassificados junto
3. Somador ripple-carry com ancilla encadeada, cujo comportamento em entradas
   não-físicas é dependente de implementação
4. Convenção de sinal do QUBO→Ising

Nenhum deles seria detectado por revisão de código. Todos apareceram ao
construir a segunda implementação.

**Taxa de acerto suficiente para ser argumento**, não só detalhe de processo:
verificação independente de ground truth é barata em relação ao custo de
descobrir o erro depois da escrita.

---

## 4. Decisões medidas, não estimadas

| Decisão | Medição | Resultado |
|---|---|---|
| D1 simulador | Aer CPU vs GPU | GPU perde abaixo de ~18 qubits; padrão é CPU |
| D1b pool | 20 submits em container Linux | 1,58 s no primeiro, 0,2 ms nos demais — ~12 h economizadas |
| D3b teto unitário | matriz densa 4ⁿ | teto real de 13 qubits, não 20 |
| D10 gerador local | qwen2.5-coder:7b vs qwen3-coder:30b | 30B em offload: 209 h vs meta de 72 h — rejeitado |
| D10b contexto | `ollama ps` | default 4096 truncava em silêncio; `num_ctx` agora explícito |
| M1 recuperação | 50 consultas, 1.020 chunks | recall@8 = 0,9524 após correção de ground truth |

### Duas medições que quase enganaram

**O 7B parecia rodar em CPU** (8 tok/s de prefill). Era `load_duration` de 23 s
contaminando o número. Com o modelo quente: 492 tok/s, 100% GPU. Toda medição
de throughput exige aquecimento prévio.

**O recall parecia ter despencado** de 0,90 para 0,73 ao expandir o corpus. A
maior parte era subestimação: 26 de 44 alvos tinham irmão legitimamente
correto que o ground truth não reconhecia. Consultas sintéticas escritas contra
corpus pequeno subestimam sistemas em corpus grande.

O ganho real do prefixo de registro foi de 0,7302 para 0,7619 — modesto. O
resto foi correção de medição, e os dois efeitos precisam ser reportados
separados.

---

## 5. Evidência empírica antecipada para H1

Duas execuções da mesma tarefa (GHZ-3), antes e depois de a recuperação estar
ativa:

**Sem RAG** — três de quatro falhas foram API inexistente: `qiskit.extensions`
(removido no Qiskit 1.0), `cx_decompose` e `u3` (nunca existiram em
`QuantumCircuit`).

**Com RAG** — zero erros de `DeprecatedAPI` em cinco tentativas. Nenhum dos três
símbolos reapareceu.

O caso do `u3` é o mais forte: foi confirmado como **lacuna de corpus** (a
correção não estava no índice), corrigida na ingestão, e não voltou. Causa
identificada e rastreável, não correlação.

Isso não substitui o experimento formal, mas é evidência qualitativa com
mecanismo explicado — vale mais na dissertação que uma linha de tabela.

---

## 6. Dívidas abertas

| Item | Impacto | Quando |
|---|---|---|
| `TaskSpec.max_depth_ratio` definido mas nunca lido | tarefas com tolerância própria avaliadas com critério errado | antes de T048 |
| Módulos sem cobertura de teste (auditoria pendente) | `resource.py` rodou desde a Phase 3 sem testes | auditar agora |
| `oracle_kind="resource"` listado no glossário e talvez no `data-model.md` | não existe; `resource_check` é ortogonal (D3h) | correção documental |
| Truncamento em 4.000 chars no chunking | implementação parcial do D6; corta exemplos de uso | cresce com o corpus |
| `HallucinatedSymbol` para import faltando roteia para `retry_retrieval` | reconsultar não corrige esquecimento de import | cosmético |
| VQE/QAOA com parâmetros fixos | medem construção de ansatz, não otimização | registrado; relevante para T064 |

---

## 7. Riscos vivos

**Segunda anotação da T064.** O cálculo de κ exige anotador independente em 20%
da amostra. Depende de disponibilidade de terceiro — trava na semana 11 se não
for resolvido antes.

**Reunião com o orientador.** Pendente desde o início. O congelamento M2 é o
último ponto barato para mudar escopo.

**Calibração das perturbadas.** O critério do D12 (descartar onde o gerador de
fronteira não passe de 20%) exige rodar geradores. A decisão de descarte
acontece no piloto (T055), não antes.

**Nome do projeto.** Três em circulação: `qcircuit-agent`, Quantum-RAG,
LLM Quantum Copilot. "Quantum RAG" colide com termo estabelecido para
recuperação acelerada por algoritmos quânticos. Pendente fixar o título formal.

---

## 8. Próximos passos

1. Fechar as dívidas de §6 marcadas "antes de T048"
2. T048 — 60 variantes perturbadas (construir; calibrar depois)
3. **M2 — congelamento de escopo.** Dataset e conjunto de geradores imutáveis
4. Reunião com o orientador antes do congelamento
5. T053–T055 — condições C1–C5 e piloto de custo, que fecha D8, D9, D12 e o
   orçamento de API
6. T058 — matriz completa

---

## 9. O que este projeto já produziu de citável

Independentemente do resultado do experimento principal:

- **O dataset** — 60 tarefas canônicas com oráculos verificados
  independentemente, em domínio sem benchmark público equivalente
- **O padrão de oráculos estreitos** (§2.1) — resultado metodológico sobre
  desenho de benchmarks para código gerado
- **A cegueira de fase em checks por medição** (§2.2) — e a contramedida por
  composição com a inversa
- **Diagnóstico incorreto sendo pior que nenhum** (§2.3) — resultado sobre
  desenho de loops de reparo

Nenhum deles depende do sinal do resultado principal, o que satisfaz o
Princípio VI: o trabalho permanece defensável mesmo se a hipótese central for
refutada.
