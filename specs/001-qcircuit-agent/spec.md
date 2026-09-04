# Feature Specification: Síntese verificada de circuitos quânticos assistida por IA

**Feature Branch**: `001-qcircuit-agent`
**Criada em**: 2026-08-11
**Status**: Draft
**Input**: "Sistema que gera circuitos quânticos a partir de descrição em linguagem natural, verifica automaticamente se estão corretos e se corrige quando não estão — e mede se isso funciona melhor que geração direta."

---

## Clarifications

### Session 2026-08-12

- Q: Quando uma chamada ao gerador externo (Fronteira A ou B) falha de forma transitória durante a matriz de 5.400 execuções — rate limit, erro 5xx ou timeout — e não por defeito do código gerado, o que o sistema deve fazer? → A: Tentar novamente com backoff exponencial limitado; se persistir, marcar a execução como falha de infraestrutura e prosseguir com as demais execuções da matriz, sem abortar a rodada.
- Q: Se a matriz de 5.400 execuções (≤72h de wall-clock) for interrompida no meio — queda de energia, crash, parada manual — o sistema deve retomar pulando combinações (gerador, condição, tarefa, seed) já persistidas, ou um reinício do zero é aceitável? → A: O executor DEVE ser retomável — pular no reinício qualquer combinação que já tenha registro persistido.
- Q: Na amostra de dupla anotação de falhas (FR-024), quando os dois anotadores discordam da categoria, como o rótulo final é decidido? → A: Um terceiro anotador independente resolve a discordância por maioria.
- Q: Para o caso de borda "descrição ambígua ou impossível → recusa explícita", a detecção deve ser uma checagem dedicada antes da geração, ou é aceitável deixar o loop normal esgotar `MAX_ITER` e reportar falha padrão? → A: Híbrido — o `planner` sinaliza casos óbvios (entidades faltantes, restrições contraditórias) antes de qualquer tentativa de geração; ambiguidade mais sutil segue o loop iterativo normal.
- Q: O caso de borda "descrição cuja solução excede a capacidade de simulação → rejeitar na entrada" hoje só é aplicado ao dataset curado (na ingestão). Para uso ao vivo pelo pesquisador (US1), como a rejeição "na entrada" deve funcionar, já que a contagem de qubits só existe depois do código gerado? → A: O `planner` extrai a contagem de qubits declarada/inferível dos requisitos e rejeita antes de qualquer chamada ao `generator`, caso exceda o teto configurado.

---

## User Scenarios & Testing

### User Story 1 — Obter um circuito verificado a partir de uma descrição (Priority: P1)

Um pesquisador descreve em linguagem natural o circuito que precisa. O sistema
produz um circuito, verifica-o automaticamente contra um critério de corretude
objetivo e, se falhar, tenta corrigir usando o diagnóstico da falha. O
pesquisador recebe o circuito acompanhado do veredito de verificação.

**Why this priority**: é a fatia mínima que entrega valor real. Sem ela nada
mais existe, e ela sozinha já é utilizável.

**Independent Test**: submeter 20 descrições com resposta de referência conhecida
e confirmar que o sistema devolve, para cada uma, um circuito e um veredito
correto — inclusive vereditos de falha, que devem ser reportados e não mascarados.

**Acceptance Scenarios**:

1. **Given** uma descrição válida cuja solução o sistema acerta de primeira,
   **When** o pedido é submetido, **Then** o sistema devolve o circuito com
   veredito de aprovação e registro de uma única tentativa.
2. **Given** uma descrição cuja primeira tentativa produz artefato inexecutável,
   **When** o sistema detecta a falha, **Then** ele regenera usando o diagnóstico
   e registra ambas as tentativas no histórico.
3. **Given** uma descrição cuja solução o sistema não alcança dentro do limite de
   tentativas, **When** o limite é atingido, **Then** o sistema devolve status de
   falha com a última tentativa e o histórico completo de erros — nunca um
   resultado apresentado como válido.
4. **Given** um circuito funcionalmente correto porém que consome recursos muito
   acima da referência, **When** a verificação de recursos roda, **Then** o
   sistema sinaliza o excesso e tenta uma rodada de otimização.

---

### User Story 2 — Evitar uso de interfaces obsoletas (Priority: P2)

O pesquisador recebe artefatos que usam apenas construções válidas na versão
corrente das bibliotecas alvo, mesmo quando o conhecimento prévio do gerador está
desatualizado.

**Why this priority**: é a principal causa isolada de falha em geração para este
domínio, e é resolvível sem alterar o gerador. Depende de US1 existir, mas é
independentemente mensurável.

**Independent Test**: rodar um conjunto de descrições cuja solução envolve
construções que mudaram entre versões, e comparar a taxa de uso de construção
obsoleta com e sem o mecanismo de consulta ativado.

**Acceptance Scenarios**:

1. **Given** uma descrição cuja solução envolve uma construção renomeada em
   versão recente, **When** o sistema gera, **Then** o artefato usa a construção
   atual.
2. **Given** que o gerador produziu uma construção obsoleta, **When** o
   diagnóstico identifica a causa como desatualização, **Then** o sistema
   reconsulta a fonte de referência antes de regenerar — e não apenas repete a
   geração.
3. **Given** uma consulta à fonte de referência, **When** o material recuperado
   inclui construções obsoletas, **Then** elas chegam ao gerador explicitamente
   rotuladas como não utilizáveis.

---

### User Story 3 — Medir se o sistema realmente melhora o resultado (Priority: P3)

O pesquisador executa a comparação entre o sistema completo e as variantes de
controle sobre o conjunto de avaliação, e obtém as métricas que sustentam ou
refutam as hipóteses do trabalho.

**Why this priority**: é a contribuição científica. Depende de US1 e US2 estarem
prontas, mas é o que a dissertação de fato defende.

**Independent Test**: executar a matriz completa e verificar que o relatório
produzido contém, para cada combinação de gerador e condição, todas as métricas
primárias com intervalo de variação entre seeds.

**Acceptance Scenarios**:

1. **Given** a matriz experimental configurada, **When** a execução termina,
   **Then** existe um registro imutável por execução contendo entrada, saída,
   veredito, tentativas e custo.
2. **Given** os registros de uma rodada, **When** o relatório é gerado, **Then**
   as métricas de corretude aparecem em camadas separadas, nunca agregadas em
   índice único.
3. **Given** duas condições que diferem em um único componente, **When** a
   ablação é calculada, **Then** o relatório atribui o ganho ao componente
   isolado.
4. **Given** itens canônicos e suas variantes perturbadas, **When** o relatório é
   gerado, **Then** a diferença de desempenho entre eles aparece como métrica
   própria por gerador e condição.

---

### User Story 4 — Demonstrar execução em dispositivo físico (Priority: P4)

O pesquisador executa um subconjunto dos artefatos aprovados em dispositivo
quântico real e obtém a comparação entre comportamento simulado e medido.

**Why this priority**: fortalece a defesa ao mostrar o ciclo fechado até
execução física, mas o trabalho permanece completo sem ela. Deliberadamente
opcional.

**Independent Test**: submeter 12 artefatos aprovados ao dispositivo e verificar
que o relatório apresenta a degradação de fidelidade em função do consumo de
recursos.

**Acceptance Scenarios**:

1. **Given** um artefato aprovado em simulação, **When** submetido ao
   dispositivo físico, **Then** o resultado medido é registrado ao lado do
   simulado.
2. **Given** indisponibilidade ou fila excessiva do dispositivo, **When** o prazo
   configurado expira, **Then** a etapa é marcada como não executada sem
   bloquear as demais entregas.

---

### User Story 6 — Demonstrar o sistema interativamente para a defesa (Priority: P6)

O pesquisador mostra o sistema funcionando ao vivo: insere uma descrição de
circuito, observa a geração, vê cada um dos quatro vereditos de verificação e
acompanha o laço de correção ao longo das iterações quando falha.

**Why this priority**: comunica a contribuição muito melhor do que tabelas de
métricas, mas não responde a nenhuma das hipóteses. É estritamente opcional,
começa somente depois de M5 (análise completa) e é explicitamente condicional
ao tempo restante — se não ocorrer, nada na dissertação fica enfraquecido. Não
deve consumir tempo antes que a matriz experimental esteja completa.

**Independent Test**: submeter uma descrição ao vivo na interface de
demonstração e confirmar que os quatro vereditos de camada aparecem
corretamente para uma execução que acerta de primeira, para uma que exige
correção ao longo de iterações, e para uma que esgota `MAX_ITER`.

**Acceptance Scenarios**:

1. **Given** uma descrição em linguagem natural, **When** submetida, **Then**
   o código gerado e os quatro vereditos de camada são exibidos.
2. **Given** uma tarefa que falha e é corrigida, **When** executa, **Then**
   cada iteração é exibida com o diagnóstico que motivou a tentativa seguinte.
3. **Given** uma tarefa que esgota o `MAX_ITER`, **When** o limite é atingido,
   **Then** a falha é exibida explicitamente — nunca uma última tentativa
   apresentada como resultado.

---

### Edge Cases

- Descrição ambígua ou impossível de satisfazer → o sistema deve recusar
  explicitamente, não produzir artefato plausível e errado. Casos óbvios
  (entidades faltantes, restrições contraditórias) são sinalizados pelo
  `planner` antes de qualquer tentativa de geração; ambiguidade mais sutil
  segue o loop iterativo normal até `MAX_ITER` e reporta falha padrão.
- Artefato funcionalmente correto mas com convenção de ordenação invertida em
  relação à referência → categoria de veredito própria, distinta de erro.
- Artefato correto a menos de fator de fase global → deve ser aceito.
- Artefato que tenta acessar recursos externos ao ambiente de execução → deve
  ser bloqueado antes da execução.
- Referência de avaliação incorreta → deve ser detectada por verificação
  independente antes de qualquer rodada.
- Descrição cuja solução excede a capacidade de simulação disponível → rejeitar
  na entrada, não falhar durante a execução. O `planner` extrai a contagem de
  qubits declarada ou inferível dos requisitos e rejeita antes de qualquer
  chamada ao `generator`, caso exceda o teto configurado.
- Falha transitória de infraestrutura durante uma execução da matriz (rate
  limit, erro 5xx ou timeout do gerador externo) → o sistema tenta novamente
  com backoff exponencial limitado; se persistir, marca a execução como falha
  de infraestrutura e prossegue com as demais execuções, sem abortar a rodada
  nem contá-la como falha do gerador.

---

## Requirements

### Functional Requirements

**Geração e verificação**

- **FR-001**: O sistema DEVE aceitar uma descrição em linguagem natural e
  produzir um artefato de circuito acompanhado de veredito de verificação.
- **FR-002**: O sistema DEVE verificar cada artefato em camadas ordenadas —
  executabilidade, viabilidade no alvo, corretura funcional e consumo de
  recursos — e reportar o resultado de cada camada separadamente.
- **FR-003**: O veredito de corretura funcional DEVE ser produzido por
  verificação determinística e reexecutável, NUNCA por julgamento de modelo de
  linguagem.
- **FR-004**: O sistema DEVE aceitar como correto um artefato que difira da
  referência apenas por fator de fase global.
- **FR-005**: O sistema DEVE distinguir divergência de convenção de ordenação de
  divergência funcional, reportando-as como categorias distintas.
- **FR-006**: O sistema DEVE comparar consumo de recursos entre artefato gerado e
  referência sob condições idênticas de preparação.

**Correção iterativa**

- **FR-007**: Ao detectar falha, o sistema DEVE classificar sua causa e escolher
  a ação corretiva correspondente, em vez de repetir a mesma tentativa.
- **FR-008**: O sistema DEVE encerrar após um número máximo configurável de
  tentativas e reportar falha explícita, sem apresentar resultado não verificado
  como válido.
- **FR-009**: O sistema DEVE registrar todas as tentativas de uma execução,
  incluindo as malsucedidas.
- **FR-010**: O sistema DEVE oferecer ponto de revisão humana opcional,
  desativado por padrão em execuções experimentais.

**Consulta a fontes de referência**

- **FR-011**: O sistema DEVE consultar fontes de referência versionadas antes de
  gerar, associando a cada trecho recuperado a versão a que corresponde e se está
  obsoleto.
- **FR-012**: O sistema DEVE preservar a unidade semântica do material
  recuperado, mantendo íntegras as unidades que descrevem uma mesma construção.
- **FR-013**: O sistema DEVE combinar busca por correspondência literal de
  identificador e busca por similaridade de intenção.
- **FR-014**: Material obsoleto recuperado DEVE chegar ao gerador rotulado como
  não utilizável, em vez de simplesmente omitido.
- **FR-015**: O sistema DEVE separar material de referência de interface de
  material descritivo de algoritmo, entregando-os ao gerador de forma
  distinguível.

**Avaliação**

- **FR-016**: O conjunto de avaliação DEVE cobrir níveis crescentes de
  dificuldade, do elementar ao dependente de restrições do alvo físico.
- **FR-017**: Todo item canônico do conjunto de avaliação DEVE ter variante
  perturbada pareada.
- **FR-018**: Toda referência de avaliação DEVE ser verificada por construção
  independente e checagem de propriedades, em processo automatizado e bloqueante.
- **FR-019**: O sistema DEVE executar a matriz completa de geradores × condições
  × itens × seeds e persistir cada execução em registro imutável.
- **FR-020**: O sistema DEVE suportar condições de controle que desabilitem
  isoladamente a consulta a fontes e a correção iterativa.
- **FR-021**: O sistema DEVE reportar métricas de corretude em camadas separadas,
  jamais agregadas em índice único.
- **FR-022**: O sistema DEVE reportar custo e latência por execução resolvida.
- **FR-023**: O sistema DEVE reportar a diferença de desempenho entre itens
  canônicos e perturbados, por gerador e condição.
- **FR-024**: O sistema DEVE permitir classificação das falhas segundo taxonomia
  fechada, com registro de concordância entre anotadores; discordâncias na
  amostra de dupla anotação DEVEM ser resolvidas por um terceiro anotador
  independente, com decisão por maioria.

**Execução segura e reprodutibilidade**

- **FR-025**: Artefatos gerados DEVEM ser executados isoladamente do processo
  principal, com limite de tempo e restrição de acesso a recursos externos.
- **FR-026**: Toda execução DEVE registrar identificador de rodada, seed, versões
  de dependência e revisão de código.
- **FR-027**: Uma rodada completa DEVE ser reproduzível a partir de um único
  arquivo de configuração versionado.
- **FR-028**: O sistema DEVE reaproveitar respostas já obtidas para entradas
  idênticas, evitando custo em reexecuções de análise.
- **FR-029**: O sistema DEVE permitir retomar uma rodada da matriz
  interrompida sem reexecutar combinações de gerador, condição, tarefa e seed
  que já possuam registro persistido.
- **FR-030**: O sistema DEVE sinalizar como não-satisfazível, antes de
  qualquer tentativa de geração, descrições com entidades faltantes ou
  restrições contraditórias identificáveis a partir dos requisitos extraídos;
  ambiguidade não detectável nesta etapa segue o fluxo normal de correção
  iterativa até o limite de tentativas.
- **FR-031**: O sistema DEVE rejeitar, antes de qualquer chamada ao gerador,
  descrições cuja contagem de qubits extraída pelo planner exceda a
  capacidade de simulação configurada.

### Key Entities

- **Descrição de tarefa**: enunciado em linguagem natural, nível de dificuldade,
  restrições, referência associada, marcação de variante perturbada.
- **Artefato**: o circuito produzido em uma tentativa.
- **Referência**: a resposta esperada, com seu tipo de critério de comparação e
  tolerância.
- **Veredito**: resultado por camada de verificação, com métricas associadas.
- **Registro de erro**: iteração, camada, categoria e diagnóstico estruturado.
- **Decisão corretiva**: ação escolhida, justificativa e orientação para a
  próxima tentativa.
- **Execução**: uma combinação de gerador, condição, tarefa e seed, com todo o
  histórico e custo.
- **Unidade de referência recuperada**: trecho, origem, versão, marcação de
  obsolescência e relevância.

---

## Success Criteria

- **SC-001**: Dado um conjunto de descrições com referência conhecida, o sistema
  devolve veredito verificável para 100% delas — incluindo os vereditos de falha.
- **SC-002**: A taxa de artefatos que passam pela verificação de executabilidade
  na condição completa supera a da geração direta em pelo menos 20 pontos
  percentuais absolutos.
- **SC-003**: A taxa de artefatos funcionalmente corretos na condição completa
  supera a da condição sem correção iterativa em pelo menos 15 pontos percentuais
  absolutos.
- **SC-004**: A taxa de uso de construções obsoletas cai pelo menos 70% com a
  consulta a fontes ativada, em relação à geração direta.
- **SC-005**: O gerador local alcança ao menos 80% da corretude funcional do
  gerador de referência quando ambos operam na condição completa.
- **SC-006**: A mediana de tentativas até sucesso permanece igual ou inferior a 3
  entre as execuções bem-sucedidas.
- **SC-007**: A razão de consumo de recursos entre artefato gerado e referência
  não piora entre a condição de geração direta e a condição completa.
- **SC-008**: A ablação atribui o ganho a componentes isolados com sobreposição
  de intervalo de variação entre seeds inferior a 50%.
- **SC-009**: 100% das referências de avaliação passam pela verificação
  independente antes da primeira rodada experimental.
- **SC-010**: Uma rodada arquivada é reproduzida a partir de sua configuração com
  divergência de métricas primárias inferior a 2 pontos percentuais.
- **SC-011**: A classificação de falhas atinge concordância entre anotadores
  (Cohen's κ) igual ou superior a 0,70.
- **SC-012**: A diferença entre itens canônicos e perturbados é reportada para
  todas as combinações de gerador e condição.

---

## Assumptions

- O conjunto de avaliação será construído pelo autor; não existe benchmark
  público adequado com oráculo executável para este escopo.
- A capacidade de simulação disponível localmente limita os itens de avaliação a
  um porte modesto; nenhum item excede esse limite.
- O acesso a dispositivo físico é gratuito porém sujeito a fila imprevisível —
  por isso US4 é opcional.
- US6 depende apenas de tempo restante após M5; é estritamente opcional e não
  enfraquece a dissertação se não ocorrer.
- Geradores acessados por serviço externo têm custo monetário; o orçamento é
  restrição real e exige piloto prévio.
- Os enunciados de avaliação são gerados pelo autor e não são adversariais; a
  execução isolada mira segurança operacional razoável, não resistência a
  ataque.
- Nenhuma versão de biblioteca alvo muda durante a janela experimental; se mudar,
  a matriz é reexecutada.

## Dependencies

- Fontes públicas de documentação versionada das bibliotecas alvo.
- Acesso a pelo menos dois geradores externos e um gerador executável localmente.
- Ambiente de simulação com aceleração por GPU disponível localmente.
- Acesso a plano gratuito de dispositivo quântico físico (apenas US4).

## Out of Scope

- Busca por vantagem quântica ou execução em escala.
- Treinamento ou ajuste fino de qualquer gerador.
- Proposição de novo algoritmo quântico.
- Mitigação de erro em dispositivo físico.
- Uso em produção ou hardening contra código adversarial.
