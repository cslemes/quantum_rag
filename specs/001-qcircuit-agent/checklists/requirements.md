# Requirements Quality Checklist

**Feature**: `001-qcircuit-agent` | **Gerado em**: 2026-08-11

"Testes unitários para o texto." Valida se `spec.md` está bem escrito **antes**
de implementar — não valida a implementação.

## Content Quality

- [x] CHK001 Nenhum detalhe de implementação (linguagem, framework, biblioteca) em `spec.md`
- [x] CHK002 Foco em valor para o usuário e resultado, não em mecanismo
- [x] CHK003 Escrito para leitor não-implementador (orientador, banca)
- [x] CHK004 Todas as seções obrigatórias preenchidas

## Requirement Completeness

- [x] CHK005 Nenhum marcador `[NEEDS CLARIFICATION]` remanescente
- [x] CHK006 Todo requisito é testável e não ambíguo
- [x] CHK007 Critérios de sucesso são mensuráveis
- [x] CHK008 Critérios de sucesso são agnósticos de tecnologia
- [x] CHK009 Cenários de aceitação estão definidos para todas as histórias
- [x] CHK010 Casos de borda identificados
- [x] CHK011 Escopo delimitado com seção *Out of Scope* explícita
- [x] CHK012 Dependências e premissas registradas

## Feature Readiness

- [x] CHK013 Toda história tem teste independente definido
- [x] CHK014 Histórias priorizadas (P1–P4) com justificativa
- [x] CHK015 P1 sozinha entrega valor demonstrável
- [x] CHK016 Todo FR mapeia para pelo menos uma história

## Domain-Specific — rigor experimental

- [x] CHK017 O oráculo de corretude é determinístico e reexecutável (FR-003)
- [x] CHK018 Condições de controle que isolam cada componente estão especificadas (FR-020)
- [x] CHK019 Controle de contaminação está no desenho, não na discussão (FR-017, FR-023)
- [x] CHK020 As próprias referências de avaliação são verificadas (FR-018)
- [x] CHK021 Métricas de corretude reportadas em camadas, nunca agregadas (FR-021)
- [x] CHK022 Falha é reportada explicitamente, nunca mascarada como sucesso (FR-008)
- [x] CHK023 O trabalho permanece defensável com resultado negativo (Princípio VI)
- [x] CHK024 Custo é tratado como restrição real, não como detalhe (FR-022)

## Notas de revisão

**CHK008** — verificado item a item. SC-002 a SC-007 falam de "taxa de artefatos
funcionalmente corretos" e "condição completa", sem nomear tecnologia. Os limiares
(20 p.p., 15 p.p., 70%) são estimativas de partida sem baseline publicado; se o
piloto mostrar que estão muito fora, ajustar **antes** da matriz completa e
registrar o ajuste — nunca depois de ver o resultado final.

**CHK015** — US1 entrega circuito verificado sem RAG e sem experimento. É
demonstrável ao orientador ao fim da Phase 3.

**CHK019** — o par canônico/perturbado é criado em T048, antes da primeira
execução experimental (T055). Ordem verificada no grafo de dependências.

**Risco aberto**: SC-005 ("gerador local alcança 80% do de fronteira") é o
critério mais especulativo do documento. Não há baseline público para calibrá-lo.
Tratado como hipótese a testar, não como requisito de aprovação — se falhar, o
achado é "o loop não fecha a lacuna entre 7B e fronteira neste domínio", que é
publicável.
