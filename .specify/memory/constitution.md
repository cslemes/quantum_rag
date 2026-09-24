# Constituição — LLM Quantum Copilot

**Versão**: 2.0.0 | **Ratificada**: 2026-08-11 | **Emendada**: 2026-09-11

Trabalho de conclusão de pós-graduação em Inteligência Artificial (PUC-Rio),
na modalidade **produto com relatório**. Estes princípios governam `spec.md`,
`plan.md` e `tasks.md`.

> **Emenda 2.0.0** — o entregável passou de dissertação com experimento
> controlado para produto com relatório. Removidos os princípios III (ablação
> obrigatória), IV (contaminação no desenho) e VI (resultado negativo como
> entregável), que existiam para sustentar inferência experimental. Os
> princípios I, II e V permanecem, com função nova: garantia de qualidade em
> vez de rigor experimental. Acrescentado o princípio III (honestidade sobre
> garantia), que é a exigência central de um produto de verificação.

---

## Princípios fundamentais

### I. Verificação determinística é inegociável

Toda afirmação de corretude sobre um circuito gerado DEVE derivar de um
verificador determinístico e reexecutável. Julgamento por modelo de linguagem
NÃO PODE ser usado como veredito — apenas como roteador de decisão ou gerador
de hipótese.

*Razão*: o produto existe para dar garantia. Uma garantia produzida por LLM não
é garantia — é a mesma incerteza que o usuário já tinha, com uma camada a mais
de confiança injustificada.

### II. Honestidade sobre o nível de garantia

O produto DEVE informar, em toda saída, exatamente o que foi verificado e o que
não foi. NÃO PODE apresentar "executa e respeita as restrições" como
equivalente a "está correto".

Quando nenhuma propriedade verificável é fornecida, o produto DEVE dizer que a
corretude funcional não foi verificada — não omitir o fato.

*Razão*: é o diferencial do produto e o risco maior. Uma ferramenta que sugere
garantia que não tem é pior que nenhuma ferramenta, porque desloca a
desconfiança saudável do usuário.

### III. Regressão verificável

Toda mudança em prompt, corpus, modelo ou pipeline DEVE ser avaliada contra a
suíte de tarefas de referência antes de ser adotada. Resultados de regressão
são registrados com `run_id`, seeds e versões fixadas.

*Razão*: sistemas construídos sobre LLM degradam silenciosamente. Sem suíte de
regressão, não há como distinguir melhoria de sorte.

### IV. Referências são código testado

Toda tarefa da suíte de regressão DEVE ter sua referência verificada por
construção independente e checagem de propriedades, em processo automatizado e
bloqueante.

*Razão*: uma referência incorreta transforma a suíte de regressão em ruído e
mascara justamente as regressões que ela deveria pegar.

---

## Restrições operacionais

Cada restrição declara se é IMPOSTA por um mecanismo que falha quando violada,
ou se depende de disciplina. A distinção existe porque uma regra sem mecanismo
que não se anuncia como tal é lida como garantia — e não é (F11, F21).

- **Fixação de versão** *(parcialmente imposta)*: bibliotecas de simulação,
  imagem do vector store e modelo de embedding são pinados. Atualização exige
  rodada de regressão.
  → IMPOSTO: `require_pinned_model` recusa modelo de embedding fora da revisão
  fixada; `analysis/compare.py` RECUSA comparar execuções cujas versões
  controladas diferem.
  → **NÃO IMPOSTO**: nada força a rodada de regressão a acontecer. Nenhum
  teste pode obrigar alguém a gastar 3 h 26 min. Detectamos a divergência;
  não a prevenimos.
- **Isolamento de execução** *(imposto)*: código gerado por modelo NUNCA
  executa no processo principal.
  → `tests/contract/test_generated_code_isolation.py` reprova qualquer
  `exec`/`eval`/`compile` fora de `validators/sandbox.py`, por AST.
- **Hardware real não é verificação** *(não imposta — e nunca exercitada)*:
  execução em dispositivo físico demonstra comportamento sob ruído; NÃO PODE
  ser apresentada como veredito de corretude.
  → US5 não está implementada e `hardware_note` é sempre `None`, então a regra
  nunca foi desafiada. Não conta como regra que "funcionou": conta como regra
  sem oportunidade. Quando US5 existir, o mecanismo é barato — estender o
  teste de vocabulário de `report.py`.

## Fluxo de desenvolvimento

1. `spec.md` descreve **o quê** e **por quê** — sem nomear tecnologia.
2. `plan.md` descreve **como**, e passa pelo *Constitution Check*.
3. `tasks.md` agrupa tarefas por história de usuário, cada uma entregando valor
   verificável de forma independente.

## Governança

Esta constituição prevalece sobre conveniência de implementação. Emendas exigem
incremento de versão semântica e registro da justificativa.
