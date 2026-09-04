# Constituição — qcircuit-agent

**Versão**: 1.0.0 | **Ratificada**: 2026-08-11 | **Última emenda**: 2026-08-11

Projeto de pós-graduação em Inteligência Artificial (PUC-Rio). Estes princípios
governam todo `spec.md`, `plan.md` e `tasks.md` do repositório. Violações devem
ser justificadas explicitamente na seção *Complexity Tracking* do plano.

---

## Princípios fundamentais

### I. Verificação determinística é inegociável

Toda afirmação de corretude sobre um artefato gerado DEVE derivar de um
verificador determinístico e reexecutável. Julgamento por modelo de linguagem
NÃO PODE ser usado como oráculo de corretude — apenas como roteador de decisão
ou gerador de hipótese.

*Razão*: o valor científico do trabalho está em possuir um oráculo objetivo.
Substituí-lo por LLM-as-judge dissolve a contribuição.

### II. Reprodutibilidade antes de resultado

Nenhum resultado entra na dissertação sem `run_id`, seed registrada, SHA do
commit e versões de dependência fixadas. Toda rodada DEVE ser reproduzível por
um único comando a partir de um arquivo de configuração versionado.

*Razão*: uma banca pode pedir a reexecução. Um número que não se reproduz é um
número que não existe.

### III. Ablação obrigatória

Nenhum ganho pode ser reivindicado sem as condições de controle que isolam sua
origem. Se o sistema tem dois componentes, as quatro combinações DEVEM ser
medidas.

*Razão*: "o sistema completo é melhor que o baseline" não é um achado — é uma
observação. O achado é *qual parte* produziu o ganho.

### IV. Contaminação tratada no desenho, não na discussão

Todo item de avaliação DEVE ter variante perturbada pareada, criada antes da
primeira execução experimental. A diferença canônica-vs-perturbada É uma
métrica reportada, não uma ressalva no capítulo final.

*Razão*: memorização é a hipótese nula mais forte contra qualquer resultado
positivo em geração de código. Ela precisa ser medida, não argumentada.

### V. Oráculos são código testado

Referências de avaliação DEVEM ser verificadas independentemente por script
executado em CI, com construção alternativa e checagem de propriedades. Nenhum
oráculo entra na suíte sem passar.

*Razão*: uma referência incorreta corrompe o experimento em silêncio e só é
descoberta depois da escrita.

### VI. Resultado negativo é entregável

O projeto DEVE permanecer defensável caso a hipótese principal seja refutada. A
taxonomia de erros e o dataset são entregáveis independentes do sinal do
resultado.

*Razão*: amarrar a aprovação a um resultado positivo cria incentivo para
p-hacking e para adiar a rodada final até "dar certo".

---

## Restrições operacionais

- **Congelamento de escopo**: dataset e conjunto de modelos ficam imutáveis a
  partir do marco de congelamento definido no plano. Alterações posteriores
  exigem re-execução completa da matriz.
- **Fixação de versão**: versões de bibliotecas de simulação são pinadas
  exatamente. Atualização invalida comparações anteriores.
- **Orçamento**: toda rodada com custo monetário exige piloto extrapolado e
  aprovado antes da execução completa.
- **Isolamento de execução**: código gerado por modelo NUNCA executa no
  processo principal.

## Fluxo de desenvolvimento

1. `spec.md` descreve **o quê** e **por quê** — sem nomear tecnologia.
2. `plan.md` descreve **como** — e passa pelo *Constitution Check* antes e
   depois do desenho.
3. `tasks.md` agrupa tarefas por história de usuário, cada uma entregando valor
   verificável de forma independente.
4. Nenhuma fase experimental inicia sem que a fase anterior tenha passado seu
   portão de saída.

## Governança

Esta constituição prevalece sobre conveniência de implementação. Emendas exigem
incremento de versão semântica e registro da justificativa. Revisões de código
e de plano verificam conformidade explicitamente.
