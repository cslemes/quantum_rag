# Estado do projeto e aprendizados

**Feature**: `001-qcircuit-agent` | **Período**: 11/08/2026 – presente

**Migração de escopo em 2026-09-11** (v1→v2, ver
`specs/001-qcircuit-agent/MIGRATION.md`): o entregável passou de
dissertação com experimento controlado para **produto com relatório**. O
sistema construído permanece; o aparato de medição (condições C1-C5,
ablação, hipóteses H1-H5, taxonomia de erros com κ) sai. Este documento
descreve o estado ATUAL (pós-migração) — para o histórico de como se
chegou aqui, ver `MIGRATION.md` e o git log de `research.md`/`spec.md`.

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

**Construído e preservado integralmente pela migração** (nenhum código
descartado — ver `MIGRATION.md` §1):

| Escopo | Status |
|---|---|
| US1 — gerar circuito que executa e transpila | Completa — MVP funcional |
| US2 — recuperação híbrida versionada, sem API obsoleta | Completa — portão M1 aprovado |
| Suíte de 120 tarefas com referências verificadas (60 canônicas + 60 perturbadas) | **Completa — 120/120 verificadas** |
| Ambiente containerizado, pool de workers | Completa |

**Novo em v2, ainda não iniciado** — ordem de prioridade de
`MIGRATION.md` §3 (US3 é o caminho crítico: sem ela, corretude funcional só
é verificável quando o usuário já tem a resposta):

| História | Escopo | Status |
|---|---|---|
| US3 — verificação sem referência | gramática de asserção, avaliador por simulação, integração ao loop | Não iniciada |
| US4 — relatório de garantia | estrutura verificado/como/não verificado, teste anti-overclaim | Não iniciada |
| US6 — interface | submissão, progresso, exibição código+relatório | Não iniciada (P2 por decisão — ver riscos) |
| US7 — regressão | runner com `run_id`/seeds/versões, comparação entre execuções | Não iniciada |

O item de maior risco do projeto v1 — o dataset com oráculos verificados
independentemente — segue concluído e agora sob escopo novo: era
instrumento experimental, é suíte de regressão (`MIGRATION.md` §2). As 60
variantes perturbadas, por sua vez, eram controle de contaminação de
treino e passam a ser teste de robustez.

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
| VQE/QAOA com parâmetros fixos | medem construção de ansatz, não otimização (ver `report-notes.md` § Threats to validity) — o caveat sobrevive à migração, a referência a T064 (removida) não | registrado; relevante para o relatório, não mais para uma taxonomia formal |

---

## 7. Riscos vivos

**Um risco inteiro foi eliminado pela migração**: a segunda anotação
independente para o cálculo de κ (T064) dependia de disponibilidade de
terceiro e travava na semana 11 se não resolvida — T064 não existe mais em
v2 (`MIGRATION.md`: "a remoção de T064 elimina o risco mais frágil do
projeto"). O mesmo vale para a calibração de descarte de perturbadas via
piloto (D12): sem condição C5 nem T055, não há mais essa decisão a tomar
antes de prosseguir — as 60 variantes já construídas valem como estão.

Riscos que permanecem, mais os quatro que a própria migração introduz
(`MIGRATION.md` §7):

| Risco | Nota |
|---|---|
| Reunião com o orientador ainda pendente | agora é sobre revisar o escopo v2, não o desenho experimental v1 — M2 (congelamento de dataset/geradores) já tem sua barra técnica satisfeita (120/120 verificado), falta só a validação de escopo |
| Nome do projeto | sem prazo rígido — três em circulação, ver `report-notes.md` § Open questions |
| **Escopo inflado por liberdade** (novo) | sair da matriz experimental abre ~8 semanas; a tentação é adicionar funcionalidade — as histórias novas (US3/US4/US6/US7) já são o suficiente, o produto precisa estar PRONTO, não completo |
| **A interface virar o projeto** (novo) | US6 é P2 por decisão deliberada — um produto bonito que verifica pouco é o oposto do que este trabalho defende |
| **Perder a disciplina de verificação** (novo) | sem banca esperando rigor experimental, a pressão por evidência cai — Princípios I e IV (v2) existem para isso: a verificação determinística É o produto, não um processo a mais |
| **A promessa exceder a garantia** (novo, o maior) | um produto de verificação que sugere garantia que não tem é pior que nenhum — Princípio II (v2) e US4 existem contra isso especificamente |

---

## 8. Próximos passos

Ordem de prioridade de `MIGRATION.md` §3 ("Novas, em ordem de prioridade"):

1. **US3 — verificação sem referência** (caminho crítico): gramática mínima
   de asserção (amplitude em estados de base, determinismo de medida,
   autoestado de operador, restrição de portas) → avaliador determinístico
   por simulação → conversão dos `Requirement` já extraídos pelo `planner`
   em checagens executáveis → integração ao loop (asserção violada vira
   `ErrorRecord` nomeado) → recusa explícita de asserção mal formada →
   testes com asserções conhecidamente verdadeiras/falsas
2. **US4 — relatório de garantia**: estrutura verificado/como/não
   verificado → declaração explícita quando não há asserção → teste que
   impede afirmar corretude sem asserção verificada
3. **US6 — interface** (P2): submissão de descrição+asserções → progresso
   das tentativas visível → exibição de código e relatório juntos
4. **US7 — regressão**: runner da suíte com `run_id`/seeds/versões →
   comparação entre duas execuções por tarefa

Tarefas v1 preservadas com escopo novo (não recomeçam do zero): T054 →
persistência de execuções de regressão; T059–T061 → métricas da suíte;
T066–T069 → execução em hardware como funcionalidade (não mais como
tentativa de US4 v1).

Reunião com o orientador para validar o escopo v2 continua sendo o passo
que deveria acontecer antes de ir longe nas histórias novas — o
congelamento M2 (dataset + geradores imutáveis) já está tecnicamente
satisfeito, falta a validação humana.

---

## 9. O que este projeto já produziu de citável

O dataset (120 tarefas, canônicas e perturbadas, com oráculos verificados
independentemente) e os achados F1–F5 de `report-notes.md` § Findings —
reenquadrados como lições de engenharia de produto, não resultados de
pesquisa (`MIGRATION.md` §6). Nenhum depende de rodar a matriz
experimental, que não existe mais: o valor do trabalho não estava
condicionado ao sinal de um experimento que a migração tornou
desnecessário — é o que `MIGRATION.md` chama de "um relatório de produto
que mostra por que o experimento controlado foi abandonado, e o que se
aprendeu no caminho, é mais honesto e mais interessante que um que finge
ter começado assim".
