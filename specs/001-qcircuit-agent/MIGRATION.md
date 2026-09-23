# Migração v1 → v2: de instrumento de pesquisa a produto

**Data**: 2026-09-11 | **Motivo**: o entregável da pós-graduação é produto com
relatório, não dissertação com experimento controlado.

Guia de aplicação das mudanças. Substitui `spec.md` e `constitution.md`; exige
reescrita de `tasks.md` e ajustes em `plan.md` e `research.md`.

---

## Como aplicar

1. Substituir `.specify/memory/constitution.md` pela v2.0.0
2. Substituir `specs/001-qcircuit-agent/spec.md` pela v2
3. Reescrever `tasks.md` — ver §3
4. Ajustar `plan.md` — ver §4
5. Marcar decisões obsoletas no `research.md` como superadas, **sem apagar**
6. Renomear `dissertation-notes.md` → `report-notes.md`

Commitar cada passo separadamente. A v1 permanece no histórico do git e é
material do relatório — o registro de uma mudança de escopo fundamentada vale
mais que a aparência de um projeto que sempre soube o que era.

---

## 1. O que permanece construído

Nada do código é descartado:

- cascata de validação em quatro camadas
- loop de correção com diagnóstico estruturado
- recuperação híbrida versionada (`recall@8` = 0,9524)
- 120 tarefas com referências verificadas independentemente
- ambiente containerizado e pool de workers

## 2. O que muda de função

| Ativo | Era (v1) | É (v2) |
|---|---|---|
| 120 tarefas com referências | instrumento experimental | suíte de regressão |
| 60 variantes perturbadas | controle de memorização | teste de robustez |
| `results/` append-only | dados do experimento | histórico de regressão |
| Achados metodológicos | resultados de pesquisa | lições de engenharia no relatório |
| `dissertation-notes.md` | material da dissertação | material do relatório |

## 3. Tarefas

### Removidas

Tudo que existia para sustentar inferência experimental:

- T053, T055–T058 — condições C1–C5, piloto e matriz completa
- T059c, T062, T063 — segmentação por método, ablação, `delta_perturbacao`
- T064 — taxonomia de erros com dupla anotação e cálculo de κ
- D12 como critério de descarte de perturbações

**A remoção de T064 elimina o risco mais frágil do projeto**: o segundo
anotador dependia de disponibilidade de terceiro.

### Preservadas com escopo novo

- T054 → persistência de execuções de regressão
- T059–T061 → métricas da suíte, não do experimento
- T066–T069 (US4 v1) → execução em hardware como funcionalidade

### Novas, em ordem de prioridade

**US3 — verificação sem referência** (o caminho crítico)

1. Linguagem de asserção: gramática mínima cobrindo amplitude em estados de
   base, determinismo de medida, autoestado de operador, e restrição de portas
2. Avaliador de asserção por simulação, determinístico, sem LLM
3. Conversão dos `Requirement` que o `planner` já extrai em checagens
   executáveis
4. Integração ao loop: asserção violada vira `ErrorRecord` nomeando a asserção
5. Recusa explícita de asserção mal formada
6. Testes com asserções conhecidamente verdadeiras e falsas

**US4 — relatório de garantia**

7. Estrutura do relatório: verificado, como, não verificado
8. Declaração explícita quando não há asserção
9. Teste que impede o relatório de afirmar corretude sem asserção verificada

**US6 — interface**

10. Submissão de descrição e asserções
11. Progresso das tentativas visível
12. Exibição de código e relatório juntos

**US7 — regressão**

13. Runner da suíte com `run_id`, seeds e versões
14. Comparação entre duas execuções, por tarefa

## 4. Ajustes no `plan.md`

- Remover a matriz experimental (C1–C5, 5.400 execuções)
- Substituir o orçamento de 72 h pelo SC-007 (suíte em menos de 3 h)
- Manter Technical Context, decisões medidas e a tabela de armadilhas
- Refazer o Constitution Check contra os quatro princípios da v2.0.0
- Substituir os marcos M3–M6 pelos das histórias novas

## 5. Ajustes no `research.md`

Marcar como superadas, sem apagar:

- D8 (`MAX_ITER` via piloto) — não há piloto; calibrar pela suíte
- D9 (idioma dos prompts) — decidir por teste na suíte
- D12 (descarte de perturbações) — sem critério experimental
- D3e/D3j nas partes sobre `delta_perturbacao` inferencial

Permanecem integralmente válidas: D1, D1b, D3–D3d, D3f–D3i, D5–D7, D10, D10b,
D10c, D14–D17.

## 6. O que o relatório ganha

A mudança de escopo é ela própria material. Um relatório de produto que mostra
por que o experimento controlado foi abandonado — e o que se aprendeu no
caminho — é mais honesto e mais interessante que um que finge ter começado
assim.

Os cinco achados permanecem, reenquadrados:

| Achado | Como lição de engenharia |
|---|---|
| Oráculos mais estreitos que os enunciados | por que o produto verifica propriedades, não semelhança com referência |
| Cegueira de fase em checks por medição | por que testar o verificador contra bug injetado |
| Diagnóstico incorreto pior que nenhum | por que o loop reporta contagens, não diffs posicionais |
| Cinco erros pegos por construção independente | por que a suíte de regressão exige referência verificada |
| Perturbações vazias | por que teste de robustez precisa ser verificado, não presumido |

## 7. Riscos da própria migração

**Escopo inflado por liberdade.** Sair a matriz abre oito semanas. A tentação é
adicionar funcionalidade. As histórias novas já são o suficiente; o produto
precisa estar pronto, não completo.

**A interface virar o projeto.** US6 é P2 por decisão. Um produto bonito que
verifica pouco é o oposto do que este trabalho defende.

**Perder a disciplina de verificação.** Sem banca esperando rigor experimental,
a pressão por evidência cai. Os princípios I e IV existem para isso — a
verificação determinística é o produto, não o processo.

**A promessa exceder a garantia.** O risco maior. Um produto de verificação que
sugere garantia que não tem é pior que nenhum. O princípio II e a US4 existem
contra isso.
