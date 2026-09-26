# Feature Specification: LLM Quantum Copilot

**Feature Branch**: `001-qcircuit-agent`
**Criada em**: 2026-08-11 | **Reescrita em**: 2026-09-11 (v2 — produto)
**Status**: Draft
**Input**: "Um software que gera circuitos quânticos a partir de descrição em
linguagem natural, verifica o que é verificável, transpila para hardware alvo e
executa em simulador ou dispositivo real — sendo explícito sobre o que garantiu
e o que não garantiu."

> **Mudança de escopo (v2)**. A v1 especificava um instrumento de pesquisa: um
> experimento controlado com cinco condições e ablação, para medir se
> recuperação e correção iterativa melhoram geração de circuitos. O entregável
> passou a ser **produto com relatório**. O sistema construído permanece; o
> aparato de medição sai. As 120 tarefas com referências verificadas mudam de
> função: eram instrumento experimental, agora são suíte de regressão.

---

## User Scenarios & Testing

### US1 — Obter um circuito que executa e respeita o pedido (Priority: P1) ✅ IMPLEMENTADA

O usuário descreve o circuito que precisa. O sistema gera, verifica o que é
verificável sem referência, corrige-se quando falha, e entrega código que
executa e transpila para a topologia alvo.

**Why this priority**: é o valor mínimo do produto. Elimina a classe de erro
mais frequente em geração de código quântico — API inexistente, código que não
roda, circuito que não cabe no hardware.

**Independent Test**: submeter 20 descrições e confirmar que toda saída ou
executa e transpila, ou reporta falha explícita.

**Acceptance Scenarios**:

1. **Given** uma descrição válida, **When** submetida, **Then** o sistema
   devolve código executável com o registro do que foi verificado.
2. **Given** uma tentativa que produz artefato inexecutável, **When** a falha é
   detectada, **Then** o sistema regenera usando o diagnóstico.
3. **Given** que o limite de tentativas é atingido, **When** isso ocorre,
   **Then** o sistema reporta falha explícita — nunca apresenta a última
   tentativa como resultado.

---

### US2 — Não receber código com interfaces obsoletas (Priority: P1) ✅ IMPLEMENTADA

O usuário recebe código que usa apenas construções válidas na versão corrente
das bibliotecas alvo, mesmo quando o conhecimento do gerador está desatualizado.

**Why this priority**: é a causa isolada mais frequente de falha no domínio, e
resolvê-la é o que torna o produto imediatamente útil.

**Independent Test**: comparar a taxa de construção obsoleta com e sem consulta
à documentação versionada.

**Acceptance Scenarios**:

1. **Given** uma descrição cuja solução envolve construção renomeada, **When** o
   sistema gera, **Then** o código usa a construção atual.
2. **Given** que o diagnóstico identifica desatualização, **When** o sistema
   corrige, **Then** reconsulta a fonte antes de regerar.
3. **Given** material obsoleto recuperado, **When** chega ao gerador, **Then**
   está rotulado como não utilizável, com a substituição indicada.

---

### US3 — Declarar o que o circuito deve fazer, e ter isso verificado (Priority: P1) 🆕

O usuário declara, junto da descrição, propriedades que o circuito deve
satisfazer — e o sistema as verifica por simulação, sem exigir um circuito de
referência.

Exemplos de propriedade: o estado final tem amplitude igual em dois estados de
base específicos; a medição de um registrador produz sempre o mesmo valor; o
circuito usa apenas um conjunto declarado de portas; a saída é autoestado de um
operador dado.

**Why this priority**: **é a história que torna o produto um produto.** Sem ela,
a corretude funcional só é verificável quando o usuário já tem a resposta — o
que anula o motivo de gerar. A asserção é o oráculo numa forma que o usuário
consegue fornecer.

**Independent Test**: submeter descrições com asserções conhecidamente
verdadeiras e conhecidamente falsas, e confirmar que o sistema aprova as
primeiras e reprova as segundas.

**Acceptance Scenarios**:

1. **Given** uma descrição com asserções, **When** o circuito é gerado, **Then**
   cada asserção é avaliada individualmente e o resultado de cada uma é
   reportado.
2. **Given** uma asserção que falha, **When** isso ocorre, **Then** a falha
   entra no loop de correção como diagnóstico, e a asserção violada é nomeada.
3. **Given** uma descrição sem asserção alguma, **When** o circuito é gerado,
   **Then** o sistema informa explicitamente que a corretude funcional não foi
   verificada.
4. **Given** uma asserção mal formada ou impossível de avaliar, **When**
   submetida, **Then** o sistema recusa explicitamente em vez de ignorá-la
   silenciosamente.

---

### US4 — Saber exatamente o que foi garantido (Priority: P1) 🆕

Toda saída vem acompanhada de um relatório de garantia: o que foi verificado,
como, e o que permanece não verificado.

**Why this priority**: é o diferencial e o risco central. Um produto de
verificação que exagera a própria garantia é pior que nenhum produto.

**Independent Test**: para cada combinação de verificações executadas, conferir
que o relatório enumera corretamente o verificado e o não verificado.

**Acceptance Scenarios**:

1. **Given** um circuito aprovado em execução e transpilação mas sem asserções,
   **When** o relatório é gerado, **Then** ele declara que a corretude funcional
   não foi verificada.
2. **Given** um circuito que satisfaz todas as asserções fornecidas, **When** o
   relatório é gerado, **Then** ele enumera as asserções verificadas e não
   afirma corretude além delas.
3. **Given** execução em dispositivo físico, **When** o resultado é apresentado,
   **Then** é rotulado como comportamento sob ruído, não como verificação.

---

### US5 — Executar o circuito (Priority: P2)

O usuário executa o circuito gerado em simulador e, opcionalmente, em
dispositivo quântico real, e vê os resultados.

**Why this priority**: fecha o ciclo do produto — o usuário não só recebe
código, mas vê o circuito rodar. A execução em hardware é opcional e depende de
credencial e fila externa.

**Acceptance Scenarios**:

1. **Given** um circuito aprovado, **When** executado em simulador, **Then** a
   distribuição de medidas é apresentada.
2. **Given** credencial de dispositivo físico, **When** o circuito é submetido,
   **Then** o resultado medido é apresentado ao lado do simulado, com a
   degradação de fidelidade visível.
3. **Given** indisponibilidade do dispositivo, **When** o prazo expira, **Then**
   a etapa é reportada como não executada, sem bloquear o resto.

---

### US6 — Usar o sistema por interface (Priority: P2) 🆕

O usuário opera o sistema por uma interface: escreve a descrição e as
asserções, acompanha as tentativas, vê o relatório de garantia e os resultados
de execução.

**Why this priority**: sem interface, o produto é uma biblioteca. Com ela, é um
produto.

**Acceptance Scenarios**:

1. **Given** uma descrição submetida pela interface, **When** o sistema
   trabalha, **Then** o progresso das tentativas é visível, não apenas o
   resultado final.
2. **Given** uma tarefa que falha, **When** o limite é atingido, **Then** a
   falha e o histórico de diagnósticos são exibidos.
3. **Given** um circuito gerado, **When** o usuário quer reaproveitá-lo,
   **Then** consegue copiar o código e o relatório de garantia.

---

### US7 — Garantir que mudanças não degradam o sistema (Priority: P2) 🆕

O mantenedor executa a suíte de regressão sobre as tarefas de referência antes
de adotar qualquer mudança em prompt, corpus, modelo ou pipeline.

**Why this priority**: sistemas sobre LLM degradam em silêncio. Esta história
transforma as 120 tarefas já construídas no ativo de qualidade do produto.

**Acceptance Scenarios**:

1. **Given** a suíte de regressão, **When** executada, **Then** produz taxa de
   sucesso por tier com `run_id`, seeds e versões registradas.
2. **Given** duas execuções da suíte, **When** comparadas, **Then** as
   diferenças por tarefa são apresentadas, não apenas o agregado.
3. **Given** uma referência da suíte, **When** o processo de validação roda,
   **Then** referências não verificadas bloqueiam a execução.

---

### Edge Cases

- Descrição ambígua ou impossível → recusa explícita, não artefato plausível.
- Asserção que contradiz a descrição → reportar o conflito, não escolher um
  lado.
- Circuito correto sob decomposição alternativa à esperada → aprovar; o produto
  verifica propriedades, não semelhança com uma implementação de referência.
- Circuito que excede a capacidade de simulação → recusar na entrada.
- Código gerado que tenta acessar recursos externos → bloquear antes de
  executar.
- Dispositivo físico indisponível → degradar sem bloquear.

---

## Requirements

### Functional Requirements

**Geração e correção**

- **FR-001**: O sistema DEVE aceitar descrição em linguagem natural e produzir
  um circuito acompanhado de relatório de garantia.
- **FR-002**: O sistema DEVE verificar executabilidade e viabilidade na
  topologia alvo, reportando cada uma separadamente.
- **FR-003**: Ao detectar falha, o sistema DEVE classificar sua causa e escolher
  a ação corretiva correspondente.
- **FR-004**: O sistema DEVE encerrar após um número máximo configurável de
  tentativas e reportar falha explícita.
- **FR-005**: O sistema DEVE registrar todas as tentativas, incluindo as
  malsucedidas.

**Consulta a fontes**

- **FR-006**: O sistema DEVE consultar fontes versionadas antes de gerar,
  associando a cada trecho a versão e o status de obsolescência.
- **FR-007**: Material obsoleto DEVE chegar ao gerador rotulado como não
  utilizável, com a substituição indicada.
- **FR-008**: O sistema DEVE combinar busca por identificador literal e por
  intenção.

**Verificação sem referência**

- **FR-009**: O sistema DEVE extrair da descrição os requisitos verificáveis
  (número de qubits, conjunto de portas, restrição de topologia) e verificá-los
  contra o circuito gerado.
- **FR-010**: O sistema DEVE aceitar asserções declaradas pelo usuário sobre o
  comportamento esperado e avaliá-las por simulação.
- **FR-011**: Cada asserção DEVE ser avaliada e reportada individualmente.
- **FR-012**: Asserção violada DEVE entrar no loop de correção como diagnóstico,
  nomeando a asserção.
- **FR-013**: Asserção mal formada DEVE ser recusada explicitamente, nunca
  ignorada.
- **FR-014**: Todo veredito DEVE ser produzido por verificação determinística,
  NUNCA por julgamento de modelo de linguagem.

**Relatório de garantia**

- **FR-015**: Toda saída DEVE vir acompanhada da enumeração do que foi
  verificado e do que não foi.
- **FR-016**: Na ausência de asserções, o sistema DEVE declarar que a corretude
  funcional não foi verificada.
- **FR-017**: O sistema NÃO PODE apresentar aprovação em executabilidade e
  restrições como equivalente a corretude.

**Execução**

- **FR-018**: O sistema DEVE executar o circuito em simulador e apresentar a
  distribuição de medidas.
- **FR-019**: O sistema DEVE suportar execução em dispositivo físico quando há
  credencial, degradando sem bloquear quando indisponível.
- **FR-020**: Resultado de dispositivo físico DEVE ser rotulado como
  comportamento sob ruído, nunca como verificação.
- **FR-021**: Código gerado DEVE executar isoladamente do processo principal,
  com limite de tempo e restrição de acesso externo.

**Interface**

- **FR-022**: A interface DEVE permitir submeter descrição e asserções.
- **FR-023**: A interface DEVE exibir o progresso das tentativas, não apenas o
  resultado final.
- **FR-024**: A interface DEVE exibir o relatório de garantia junto do código.

**Regressão**

- **FR-025**: O sistema DEVE executar a suíte de tarefas de referência e
  reportar taxa de sucesso por tier.
- **FR-026**: Toda execução da suíte DEVE registrar identificador de rodada,
  seeds e versões de dependência.
- **FR-027**: O sistema DEVE comparar duas execuções da suíte por tarefa, não só
  no agregado.
- **FR-028**: Referências da suíte DEVEM ser verificadas por construção
  independente, em processo bloqueante.

### Key Entities

- **Descrição** — o pedido em linguagem natural.
- **Asserção** — propriedade declarada pelo usuário, avaliável por simulação.
- **Requisito extraído** — restrição inferida da descrição (qubits, portas,
  topologia).
- **Circuito** — o artefato produzido.
- **Relatório de garantia** — o que foi verificado, como, e o que não foi.
- **Registro de erro** — iteração, camada, categoria, diagnóstico estruturado.
- **Tarefa de referência** — item da suíte de regressão, com sua referência
  verificada.
- **Execução de regressão** — uma rodada da suíte, com versões e seeds.

---

## Success Criteria

- **SC-001**: Em 95% das descrições válidas, a saída executa e transpila para a
  topologia alvo, ou reporta falha explícita.
- **SC-002**: A taxa de uso de construções obsoletas fica abaixo de 5%.
- **SC-003**: Asserções conhecidamente verdadeiras são aprovadas e
  conhecidamente falsas são reprovadas em 100% dos casos de teste.
- **SC-004**: Nenhuma saída afirma corretude funcional sem que ao menos uma
  asserção tenha sido verificada.
- **SC-005**: Um usuário sem familiaridade com o sistema consegue gerar um
  circuito com asserção verificada em menos de 5 minutos pela interface.
- **SC-006**: A mediana de tentativas até sucesso é igual ou inferior a 3.
- **SC-007** (emendado 2026-09-22 — ver report-notes.md): a suíte de regressão
  executa completa em menos de **4 horas**, com cache de respostas FRIO. O teto
  anterior de 3 h era estimativa anterior a qualquer medição; as execuções que
  pareciam cumpri-lo (2 h 45 min) tinham ~18% das chamadas servidas de cache
  (F18). Medido a frio: 3 h 26 min, em duas execuções independentes (205m47s e
  205m45s). Cortar seeds para caber em 3 h foi testado e rejeitado: custaria 50%
  das tarefas com sucesso, porque sob `temperature=0` o seed ainda altera a
  saída e os 3 seeds são cobertura real, não redundância. **[F28: essa
  diferença entre seeds foi medida com os seeds rodando em sequência sobre o
  mesmo estado de servidor, então mistura efeito de seed com efeito de
  história; a checagem de independência a separa.]**
  **2ª emenda (2026-09-26), por PROTOCOLO e não por medição — F28**: a suíte é
  medida com `reset_per_run: true` (unload do modelo antes de cada (tarefa,
  seed)). A razão é substantiva e anterior a qualquer número: sem isso a saída
  de uma tarefa depende da anterior, e o portão de `compare.py` não consegue
  localizar uma regressão numa tarefa. O custo (uma carga de modelo por run) é
  ACEITO como consequência do protocolo, e **o teto de 4 h não é reajustado a
  ele**: se a suíte exceder 4 h sob o protocolo, SC-007 é reportado como
  reprovado, com a causa. Ver report-notes.md, "Segunda emenda a SC-007".
  **Decisão de escopo (2026-09-26, mantenedor)**: a suíte roda **um seed**
  (120 runs, ~1 h 20 min estimado). Sob `reset_per_run` os três seeds foram
  byte-idênticos em 16/16 tarefas em todos os braços de T114 (F29); três seeds
  eram três cópias. A invariante que justifica um seed é verificada antes de
  cada execução pelo canário de protocolo (2 tarefas × 3 seeds, byte-idênticos,
  senão a suíte recusa rodar). O teto de 4 h não muda.
- **SC-008** (emendado — ver research.md D20 e report-notes.md F15/F17/F19):
  duas execuções da suíte sobre o mesmo código, corpus e configuração são
  comparadas em DUAS camadas, porque só uma delas está sob nosso controle:
  - **SC-008a (camada determinística — igualdade EXATA, 0%)**: requisitos
    extraídos, ordem e conjunto dos chunks recuperados, classificação de erro,
    ação de roteamento e veredito dado um mesmo código devem ser IDÊNTICOS.
    Qualquer divergência aqui é defeito nosso — as três encontradas até agora
    eram (F15, F17) — e é o que esta camada existe para pegar.
  - **SC-008b (camada do gerador — piso de ruído MEDIDO e reportado)**: a
    divergência de resultado por tarefa é uma propriedade empírica do
    servidor de inferência, não um limite que escolhemos. É medida por duas
    execuções completas com cache frio, reportada com intervalo de confiança,
    e **todo efeito alegado tem de exceder esse piso**.
  - A medição de SC-008 EXIGE limpar `.cache/llm` entre as duas execuções
    (F18) — sem isso o resultado é 0% por construção.
  - E EXIGE `reset_per_run` (F28). Duas execuções com a mesma ordem de tarefas
    medem replay-identidade; uma comparação antes/depois muda prompts, e sem
    reset por run a mudança numa tarefa se propaga às seguintes. O 0/360 de
    2026-09-22 é replay-identidade sob sequência fixa, não independência.
- **SC-009**: 100% das referências da suíte passam pela verificação
  independente.

> **Independência dos critérios (F23).** Um critério só restringe o artefato se
> sua origem for independente dele. Isso vale POR CRITÉRIO e POR VERSÃO, não
> por documento, e a ordem dos commits torna a checagem mecânica:
>
> | critério | última alteração | status |
> |---|---|---|
> | SC-001 … SC-006, SC-009 | 2026-09-11, antes da 1ª execução (2026-09-19) | **independente** |
> | SC-007 | 2026-09-23, após medir 3 h 26 min | **descritivo** — emendado pós-medição. A 2ª emenda (2026-09-26, F28) muda o PROTOCOLO de medição e não o teto, então não altera este status nem o repete |
> | SC-008 | 2026-09-23, após medir a divergência | **descritivo** — emendado pós-medição |
>
> As duas emendas estão argumentadas (ver report-notes.md e research.md D20) e
> não são desonestas. Mas "SC-007 passa" não é evidência do mesmo tipo que
> "SC-003 passa", e um relatório que as apresente lado a lado sem essa
> distinção funde duas coisas diferentes.

---

## Assumptions

- O usuário do produto sabe descrever o circuito que quer e formular ao menos
  uma propriedade esperada — não precisa saber implementá-lo.
- A suíte de referência foi construída pelo autor; não existe benchmark público
  adequado.
- A capacidade de simulação local limita os circuitos a porte modesto.
- O acesso a dispositivo físico é gratuito e sujeito a fila imprevisível.
- As descrições de entrada não são adversariais; o isolamento mira segurança
  operacional razoável, não resistência a ataque.

## Out of Scope

- Vantagem quântica ou execução em escala.
- Treinamento ou ajuste fino de gerador.
- Proposição de novo algoritmo quântico.
- Mitigação de erro em dispositivo físico.
- Verificação de corretude na ausência de asserção ou referência — o produto
  informa a lacuna, não a preenche.
- Operação multiusuário, autenticação, ou implantação em produção.

---

## Herança da v1

Permanece válido e construído: cascata de validação, loop de correção,
recuperação híbrida versionada, 120 tarefas com referências verificadas,
ambiente containerizado.

Removido com a mudança de escopo: as cinco condições experimentais, a ablação,
as hipóteses H1–H5, o controle de contaminação como instrumento, a análise de
concordância entre anotadores.

Os achados metodológicos registrados em `report-notes.md` permanecem
material do relatório — como lições de engenharia, não como resultados de
pesquisa.
