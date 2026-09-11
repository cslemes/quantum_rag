# Estado do projeto e aprendizados

**Feature**: `001-qcircuit-agent` | **Período**: 11/08/2026 – 09/09/2026 (semanas 1–4 de 12)

**Este documento é um SNAPSHOT de estado** — o que está construído, o que
está pendente, riscos vivos no momento em que foi escrito. É reescrito
conforme o projeto avança; seções ficam obsoletas e são atualizadas, não
acumuladas. Para achados metodológicos, números a citar, limitações e
material de apêndice — conteúdo que continua válido independente da fase
do projeto — ver `specs/001-qcircuit-agent/report-notes.md`, que é
append-only e não é reescrito. Para o porquê de cada decisão de
implementação, ver `specs/001-qcircuit-agent/research.md`. Onde o conteúdo
deste documento se sobrepõe ao de `report-notes.md`, a versão
completa mora lá — aqui fica só um ponteiro, para as duas cópias não
divergirem.

---

## 1. Onde o projeto está

| Fase | Escopo | Status |
|---|---|---|
| 1–2 | Setup e fundação | Completa |
| 3 (US1) | Validadores, nós, grafo | Completa — MVP funcional |
| 4 (US2) | Recuperação híbrida | Completa — portão M1 aprovado |
| 5 (dataset) | 60 tarefas canônicas + oráculos | **Completa — 60/60 verificados** |
| 5 (T048) | 60 variantes perturbadas | **Completa — 60/60 verificados, 120/120 oráculos no total** |
| 6 (US3) | Matriz experimental | Não iniciada |

O item de maior risco do projeto — o dataset com oráculos verificados
independentemente — está concluído quatro semanas antes do previsto no
cronograma original (que o colocava nas semanas 5–6), e agora inclui tanto
o conjunto canônico quanto o perturbado.

### Cobertura do dataset canônico

| Tier | Famílias | Tarefas |
|---|---|---|
| T1 primitivas | Bell, GHZ, W-state, QFT, Deutsch-Jozsa, aritmética booleana reversível | 18 |
| T2 algoritmos | Bernstein-Vazirani, Simon, Grover, QPE, QAOA MaxCut, VQE H₂ | 18 |
| T3 formulação | Ising ponderado, strings-Z multicorpo, campo+acoplamento, QUBO→Ising | 12 |
| T4 hardware | Subconjuntos das famílias acima sob `coupling_map="linear_5"` | 12 |

Teleportação foi removida do conjunto canônico e substituída por aritmética
booleana reversível — razão completa em `report-notes.md`, seção
"Threats to validity" (item "teleportação está ausente do conjunto
canônico").

---

## 2. Achados metodológicos

Movido para `report-notes.md` § Findings (F1–F5) e § Threats to
validity — esse é o material de redação, e este documento não o duplica
mais. Resumo de uma linha de cada, para quem só quer saber o que existe:

- **F1** — oráculos mais estreitos que seus enunciados falham em silêncio
  (GHZ, aritmética reversível, QUBO→Ising).
- **F2** — checks por medição podem ser estruturalmente cegos (cegueira de
  fase da QFT).
- **F3** — um diagnóstico incorreto é pior que nenhum (diff posicional).
- **F4** — construção independente pegou cinco erros reais de método.
- **F5** — perturbações vazias teriam diluído `delta_perturbacao`.
- **Threats to validity** — teleportação ausente do conjunto canônico
  (nem `unitary` nem `statevector` cabem: precisa de fidelidade de canal
  sobre múltiplos estados de entrada, oráculo esboçado como trabalho
  futuro em D3d, não implementado).

---

## 3. Verificações que valeram o custo

Movido para `report-notes.md` § Findings, **F4**. A contagem mudou de
quatro para **cinco** erros reais de método depois que este parágrafo foi
escrito (um quinto apareceu construindo o conjunto PERTURBADO, T048/D3i) —
outro motivo para este documento não guardar mais o número em duplicata:
uma cópia aqui teria ficado desatualizada.

---

## 4. Decisões medidas, não estimadas

Índice rápido — números completos e as duas medições que quase enganaram
(aquecimento do 7B, subestimação do recall) estão em `report-notes.md`
§ Measured results, não duplicados aqui.

| Decisão | Medição | Resultado |
|---|---|---|
| D1 simulador | Aer CPU vs GPU | GPU perde abaixo de ~18 qubits; padrão é CPU |
| D1b pool | 20 submits em container Linux | 1,58 s no primeiro, 0,2 ms nos demais — ~12 h economizadas |
| D3b teto unitário | matriz densa 4ⁿ | teto real de 13 qubits, não 20 |
| D10 gerador local | qwen2.5-coder:7b vs qwen3-coder:30b | 30B em offload: 209 h vs meta de 72 h — rejeitado |
| D10b contexto | `ollama ps` | default 4096 truncava em silêncio; `num_ctx` agora explícito |
| M1 recuperação | 50 consultas, 1.020 chunks | recall@8 = 0,9524 após correção de ground truth |

---

## 5. Evidência empírica antecipada para H1

Movido para `report-notes.md` § Measured results ("Evidência
qualitativa antecipada para H1 — RAG antes/depois em `ghz_3q`"). Resumo:
duas execuções da mesma tarefa (GHZ-3), antes e depois de a recuperação
estar ativa — sem RAG, três de quatro falhas eram API inexistente
(`qiskit.extensions`, `cx_decompose`, `u3`); com RAG, zero erros de
`DeprecatedAPI` em cinco tentativas, com o caso do `u3` rastreado até uma
lacuna de corpus específica que foi corrigida.

---

## 6. Dívidas abertas

| Item | Impacto | Quando |
|---|---|---|
| ~~`TaskSpec.max_depth_ratio` definido mas nunca lido~~ | **Fechada** — `graph.py` agora lê o valor da tarefa em vez do default hardcoded | fechada antes de T048 |
| ~~`oracle_kind="resource"` listado no glossário e no `data-model.md`~~ | **Fechada** — `glossary.md` e `data-model.md` corrigidos (D3h) | fechada antes de T048 |
| Módulos sem cobertura de teste (auditoria feita, maioria dos gaps ainda sem teste) | `resource.py` ganhou `tests/unit/test_resource.py`; outros módulos identificados na auditoria seguem sem teste | escrever sob demanda, não em bloco |
| Truncamento em 4.000 chars no chunking | implementação parcial do D6; corta exemplos de uso | cresce com o corpus |
| `HallucinatedSymbol` para import faltando roteia para `retry_retrieval` | reconsultar não corrige esquecimento de import | cosmético |
| VQE/QAOA com parâmetros fixos | medem construção de ansatz, não otimização (ver `report-notes.md` § Threats to validity) | registrado; relevante para T064 |

---

## 7. Riscos vivos

As perguntas em si estão em `report-notes.md` § Open questions for
the advisor (título do projeto, reunião com o orientador, segundo anotador
para κ, calibração de descarte das perturbadas D12) — aqui só o prazo em
que cada uma vira bloqueio, que é informação de estado, não de redação:

| Pergunta em aberto | Vira bloqueio quando |
|---|---|
| Segunda anotação da T064 (κ) | semana 11, se não resolvido antes |
| Reunião com o orientador | no congelamento M2 — último ponto barato para mudar escopo |
| Calibração de descarte das perturbadas (D12) | no piloto, T055 (não antes — decisão não pode ser antecipada) |
| Nome do projeto | sem prazo rígido, mas quanto mais tarde, mais lugares para atualizar (repositório, dissertação, citações) |

---

## 8. Próximos passos

1. **M2 — congelamento de escopo.** Dataset e conjunto de geradores
   imutáveis — dataset (120/120 tarefas) já pronto para isso
2. Reunião com o orientador antes do congelamento
3. T053–T055 — condições C1–C5 e piloto de custo, que fecha D8, D9, D12
   (inclui a calibração de descarte das 60 perturbadas) e o orçamento de API
4. T058 — matriz completa

---

## 9. O que este projeto já produziu de citável

Independentemente do resultado do experimento principal — o dataset (120
tarefas, canônicas e perturbadas, com oráculos verificados
independentemente) e os achados F1–F5 de `report-notes.md` § Findings.
Nenhum depende do sinal do resultado principal, o que satisfaz o Princípio
VI: o trabalho permanece defensável mesmo se a hipótese central for
refutada.
