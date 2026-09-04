# Agente RAG com loop de validação executável para síntese de circuitos quânticos

## A tese central

O diferencial deste projeto não é "RAG aplicado a mais um domínio". É que **computação quântica é um dos raros domínios onde você tem um oráculo de correção gradual e automatizável**. Em geração de código comum, você valida com testes que alguém precisa escrever. Aqui você tem quatro níveis de verificação, todos gratuitos:

1. **Sintático/estrutural** — o código parseia e transpila para uma topologia alvo?
2. **Semântico exato** — a matriz unitária do circuito gerado é equivalente à da referência, a menos de fase global? (`Operator(qc).equiv()`)
3. **Estatístico** — a distribuição de medidas bate com a esperada? (fidelidade de Hellinger, TVD)
4. **Recursos** — profundidade, contagem de CNOTs e largura após transpilação.

Isso permite um loop de reparo com sinal muito mais rico do que "o teste falhou". Você devolve ao modelo o *traceback* da transpilação, ou a diferença entre distribuições, ou o fato de que o circuito está correto mas usa 3× mais CNOTs que o necessário. Essa é a contribuição defensável.

## Pergunta de pesquisa

> Em que medida um loop de validação executável, combinado a recuperação versionada de documentação, melhora a corretude e a eficiência de recursos de circuitos quânticos gerados por LLMs — e esse ganho é suficiente para aproximar um modelo local pequeno de um modelo de fronteira?

A segunda metade da pergunta é o que dá peso ao trabalho. Se o loop fizer um Qwen2.5-Coder 7B rodando local chegar perto de um modelo de fronteira em zero-shot, você tem um resultado com implicação prática real (custo, privacidade, soberania de dados).

## Arquitetura

Grafo de estados em LangGraph — você já domina o padrão:

```
[spec] → planner → retriever → generator → static_check
                       ↑                        ↓
                       └──── critic ←── semantic_check
                                            ↓
                                      resource_check → [done]
```

**Estado compartilhado:** especificação, código atual, chunks recuperados, histórico de erros, contador de tentativas, métricas parciais.

Pontos de projeto que importam:

- **`planner`** decompõe a especificação em requisitos verificáveis (nº de qubits, portas permitidas, propriedade esperada). Isso vira o contrato usado pelo `critic`.
- **`critic`** não é um LLM-as-judge genérico. Ele recebe o erro *estruturado* e decide a ação: re-recuperar documentação (erro de API), reescrever (erro semântico) ou otimizar (erro de recurso). Roteamento explícito, não implícito.
- **Checkpoint humano opcional** entre `semantic_check` e `resource_check`, para o modo interativo — e para você medir quantas intervenções humanas o sistema economiza.
- **Teto de iterações** (5 é um bom ponto de partida) para não mascarar fracasso com força bruta.

## Corpus de RAG

O ponto mais subestimado: **a principal fonte de alucinação em código Qiskit é *drift* de API**, não falta de conhecimento. O modelo aprendeu Qiskit 0.x e escreve `execute()`, `QuantumInstance`, `qiskit.providers.aer` — tudo removido.

Então:

- Documentação Qiskit e PennyLane **com metadado de versão e flag de depreciação** em cada chunk. Isso é o coração do retriever.
- Chunking *code-aware*: assinatura + docstring + exemplo permanecem no mesmo chunk. Chunking por caracteres destrói a utilidade aqui.
- Papers do arXiv (quant-ph) para descrição de algoritmos, separados dos docs de API — são registros diferentes e devem ser recuperados por rotas diferentes.
- Índice híbrido: BM25 para nomes de símbolo (`RZGate`, `SparsePauliOp`) + denso para intenção. Busca puramente densa erra feio em nome de API.

Você já tem pgvector e o padrão de RAG montado do projeto TDN — dá pra reaproveitar quase toda a infra.

## Dataset de avaliação

Você vai precisar construir. É trabalho, mas é também um entregável publicável por si só. Mire em 100–150 tarefas em quatro camadas:

| Camada | Conteúdo | Oráculo |
|---|---|---|
| T1 — Primitivas | Bell, GHZ(n), QFT(n), teleporte, Deutsch-Jozsa | Unitária exata |
| T2 — Algoritmos | Grover, QPE, VQE (H₂), QAOA MaxCut, Simon | Distribuição / energia |
| T3 — Formulação | Construir Hamiltoniano, ansatz sob restrição de portas | Unitária + estrutural |
| T4 — Hardware-aware | Transpilar para heavy-hex, minimizar CNOTs sob acoplamento | Recursos |

**Cuidado crítico com contaminação:** estado de Bell está em todo corpus de treino do planeta. Mitigação — inclua tarefas *compostas* e *perturbadas* ("GHZ de 5 qubits, mas com a fase relativa φ no terceiro qubit, usando apenas portas do conjunto {RZ, SX, CX}"). E teste explicitamente a hipótese de memorização comparando T1 puro contra T1 perturbado. Se a queda for grande, isso vira um achado do trabalho, não um problema.

## Baselines e ablação

Este é o esqueleto experimental. Cinco condições:

1. Zero-shot
2. Few-shot (sem recuperação)
3. RAG puro, sem loop
4. Loop puro, sem RAG
5. **RAG + loop (sistema completo)**

As condições 3 e 4 são obrigatórias — sem elas você não consegue afirmar de onde vem o ganho, e é a primeira coisa que a banca vai perguntar.

Modelos: um de fronteira via API (Claude), um de fronteira alternativo, e um local (Qwen2.5-Coder 7B no RTX 3070). Três modelos × cinco condições × ~120 tarefas × 3 sementes é rodável, mas orçe o custo de API antes de começar.

## Métricas

- **Corretude hierárquica** — `compila@1`, `unitária_equivalente@1`, `fidelidade_distribuição@1`. Reportar separado, nunca colapsar num número só.
- **Iterações até convergência** (e taxa de convergência dentro do teto).
- **Razão de eficiência de recursos** — profundidade gerada / profundidade da referência. Um circuito correto mas 4× mais profundo é inútil em hardware NISQ.
- **Custo** — tokens e latência por tarefa resolvida. É o que torna a comparação local vs. fronteira honesta.

## Infraestrutura

Aer com backend GPU (`qiskit-aer-gpu`) cobre a maior parte. No seu 3070 de 8 GB, statevector vai confortavelmente até ~22 qubits; acima disso o gargalo é VRAM, e você cai para CPU com os 32 GB até ~25. Nenhuma tarefa do dataset precisa passar disso.

Reserve um subconjunto pequeno (10–15 tarefas de T4) para rodar em hardware real no plano aberto do IBM Quantum. Não é para medir corretude — é para mostrar que o pipeline fecha o ciclo até execução física, o que vale muito na defesa. Conte com fila e planeje isso para a semana 9, não para a última.

Fixe a versão do Qiskit no início e documente. API mudando no meio do experimento invalida comparações.

## Cronograma (12 semanas)

- **1–2** — Revisão de literatura, decisão de versão, ambiente reproduzível (Docker + `uv`, como no Pizza-or-NotPizza).
- **3–4** — Construção do corpus e do retriever híbrido. Avaliação isolada de recuperação (recall@k em consultas sintéticas) antes de plugar no gerador.
- **5–6** — Dataset de tarefas + oráculos. **Teste unitário nas próprias referências** — referência errada contamina tudo silenciosamente.
- **7–8** — Grafo LangGraph completo, com telemetria por nó.
- **9–10** — Rodada experimental completa, incluindo o subconjunto em hardware real.
- **11** — Análise, ablação, análise de erros qualitativa (categorizar os fracassos é o que gera as melhores discussões).
- **12** — Escrita e empacotamento do release.

## Riscos honestos

- **Contaminação de treino** é o risco número um. Trate desde o desenho, não no final.
- **Corretude dos oráculos** — a referência precisa ser verificada independentemente. Equivalência unitária a menos de fase global tem pegadinhas (`Operator.equiv()` resolve, comparação ingênua de matrizes não).
- **Custo de API** pode estourar. Faça um piloto com 10 tarefas e extrapole antes de rodar tudo.
- **Escopo** — a tentação é adicionar mais modelos e mais tarefas. Congele o dataset na semana 6.

## Entregáveis

Dissertação, framework em código aberto, e o dataset de avaliação — que é a peça com maior chance de ser citada. Um workshop de QC + ML (QTML, ou as trilhas de código do NeurIPS/ICLR) é alvo realista para um artigo curto.




https://forum.modular.com/t/hackathon-qlabs-quantum-circuit-simulator-with-gpu-acceleration/1815