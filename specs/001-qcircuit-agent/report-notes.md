# Notas para a redação do relatório

**Feature**: `001-qcircuit-agent` | **Início deste registro**: 2026-09-11

> **Renomeado de `dissertation-notes.md` em 2026-09-11** (migração v1→v2,
> ver `MIGRATION.md`): o entregável passou de dissertação com experimento
> controlado para produto com relatório. O conteúdo abaixo não foi reescrito
> por causa disso — os achados, números e limitações continuam válidos como
> estão, só a moldura mudou de "material da dissertação" para "material do
> relatório" (ver `MIGRATION.md` §6, "O que o relatório ganha"). Onde uma
> entrada específica ficou obsoleta pela mudança de escopo (ex.: uma
> pergunta em aberto sobre uma tarefa que não existe mais em v2), ela
> permanece registrada e marcada como tal quando encontrada — nunca apagada
> em silêncio, pelo mesmo princípio de append-only que já regia este arquivo
> antes da migração.

**Fronteira entre os três documentos de registro do projeto** (defina aqui,
não redecida a cada edição):

- `research.md` — **por que decidimos X**. Decisão/Razão/Alternativas para
  cada escolha de implementação.
- `estado-e-aprendizados.md` — **estado do projeto**: o que está construído,
  o que está pendente, riscos vivos. É um SNAPSHOT — reescrito conforme o
  projeto avança, seções ficam obsoletas e são substituídas, não acumuladas.
- **Este documento (`report-notes.md`)** — **material de redação**: o
  que encontramos, com que evidência, e por que importa para o relatório
  em si — achados metodológicos, números a citar, limitações a declarar,
  conteúdo de apêndice. É **append-only em espírito**: nada é removido
  porque uma fase do projeto terminou. Um achado registrado aqui continua
  válido (e continua precisando ser citado) mesmo depois que a tarefa que o
  produziu está feita e arquivada.

**Onde o conteúdo se sobrepõe entre este arquivo e `estado-e-aprendizados.md`,
a versão completa mora AQUI** — `estado-e-aprendizados.md` referencia a
seção correspondente deste documento em vez de restatá-la, para que as duas
cópias não divirjam com o tempo. Onde uma decisão de implementação for
necessária para entender um achado, este documento referencia o `D<n>`
correspondente de `research.md` em vez de repeti-lo.

**Convenção de manutenção**: como `research.md`, este arquivo é atualizado a
cada tarefa que produz achado, número ou limitação nova — não só ao final
do projeto. Uma entrada nova aqui acompanha o commit que a produziu, e
nunca é removida por uma fase ter terminado — no máximo, marcada como
superada por um achado posterior, com o achado anterior preservado para
contexto (ver, por exemplo, a nota em F4 sobre a contagem ter mudado de
quatro para cinco erros).

---

## Findings

Cada achado: o que foi observado, a evidência, por que generaliza, e onde
deve entrar no relatório.

> ### Os três achados principais, para um público de engenharia de software
>
> A maior parte do que segue é específica de verificação de circuitos. Estes
> três não são, e são os que devem aparecer em primeiro plano no relatório —
> não no meio da lista:
>
> **[F11](#f11) — uma regra só se propaga se for enunciada sobre uma CLASSE
> e tiver um MECANISMO que falha quando violada.** Testado contra as duas
> explicações rivais e decidido pelo registro: os Princípios I e IV nasceram
> com mecanismo e nunca foram violados; os Princípios II e III, no MESMO
> documento e com a mesma autoridade, não tinham mecanismo e custaram cinco
> findings. Autoridade do documento não discrimina nada. Inclui F21 como caso
> particular.
>
> **[F23](#f23) — um sistema que sugere o próprio critério de aceitação
> produz uma checagem que não pode falhar, e é a prestatividade que causa
> isso.** Mesma estrutura de snapshot testing e de pedir a um LLM que escreva
> os testes do código que ele gerou. Inclui a autoaplicação incômoda: dois
> critérios de sucesso deste projeto foram emendados após medição (HARKing do
> lado do critério), e a auditoria por ordem de commits está registrada.
>
> **[F19](#f19) — um teste fora do regime de produção passa independentemente
> de quão bom ele seja.** Cinco testes de determinismo isolados passaram
> enquanto o pipeline divergia em 15%. A cobertura é o PRODUTO de quão bem o
> teste exercita o código e de quão perto sua entrada está da real; a segunda
> é um fator, não uma parcela.

### F1 — Oráculos mais estreitos que seus enunciados rejeitam respostas corretas em silêncio

**Observado**: três instâncias independentes, em três tiers diferentes, da
mesma estrutura de defeito — um oráculo automatizado que é internamente
consistente (nunca lança exceção, sempre compara exatamente o que foi
programado) mas testa uma propriedade MAIS ESTREITA do que o enunciado da
tarefa realmente pede, rejeitando silenciosamente uma resposta correta.

**Evidência**:
- **GHZ estrela vs. cadeia** (`ghz_3q`, T044/D3c): `h(0);cx(0,1);cx(0,2)`
  (estrela) e `h(0);cx(0,1);cx(1,2)` (cadeia) preparam o MESMO estado a
  partir de `|000⟩` — `Statevector(star).equiv(Statevector(chain))` é
  `True`, mas `Operator(star).equiv(Operator(chain))` é `False`. O
  enunciado pedia um estado; o oráculo testava uma unitária completa sobre
  os 2ⁿ estados da base computacional.
- **Somador com "vai-um" encadeado** (T044/D3d): um somador de 2 bits em que
  a saída de vai-um do primeiro estágio controla gates do segundo tem
  comportamento dependente de implementação nos 240 casos "não físicos" (de
  256 possíveis) do domínio completo — mesmo com os 16 casos físicos
  (ancillas iniciando em `|0⟩`) corretos nos dois lados. Corrigido tornando
  a tarefa **flat** (controles só sobre entradas originais) e declarando essa
  restrição no próprio enunciado, não só no oráculo.
- **Convenção de sinal QUBO→Ising** (T046/D3f): `x_i = (1-z_i)/2` e
  `x_i = (1+z_i)/2` são AMBAS convenções padrão na literatura, produzindo
  Hamiltonianos de sinal oposto. Sem declarar qual, o oráculo aceitaria
  implicitamente só uma das duas respostas igualmente corretas. Cada
  enunciado `qubo_ising_*.json` declara a convenção exata.

**Por que generaliza**: a estrutura vale para qualquer benchmark de código
gerado com oráculo automatizado em que (a) o espaço de implementações
corretas é mais amplo que uma forma canônica única e (b) o oráculo compara
contra uma referência que cobre só um subconjunto desse espaço sem que isso
seja declarado. Se não detectado, TODOS os geradores testados são
penalizados igualmente, e a taxa de sucesso medida fica sistematicamente
abaixo da real — por um motivo sem relação com a capacidade dos modelos. A
mesma estrutura apareceria em geração de SQL contra um schema com índices
alternativos, otimização de código contra um gabarito que não é o único
ótimo, ou prova formal contra uma tática específica quando outras válidas
existem.

**Contramedida reprodutível**: para cada tarefa, perguntar explicitamente
"o oráculo aceita toda implementação correta do que o enunciado pede, ou só
a que eu tinha em mente?" — e preferir ESTREITAR O ENUNCIADO a ALARGAR O
ORÁCULO sempre que isso não sacrificar o que a tarefa pretende testar.

**Onde entra no relatório**: seção metodológica própria, não nota de
processo — registrado explicitamente como candidato a isso em D3g. É uma
contribuição sobre desenho de benchmark para código gerado, independente do
domínio de circuitos quânticos.

**Fonte**: `research.md` D3c, D3d (Achado 2), D3f, D3g (síntese e
generalização); `estado-e-aprendizados.md` §2.1, §9.

---

### F2 — Checks por medição podem ser estruturalmente cegos, não apenas frouxos

**Observado**: a checagem de sanidade por medição real (3 seeds,
`AerSimulator`) da QFT reportava fidelidade de Hellinger **1,0000** para um
circuito que computava a QFT **INVERSA** — o sinal de fase inteiro trocado,
indistinguível de correto sob essa métrica, para qualquer tolerância.

**Evidência**: QFT de qualquer estado de base computacional produz
magnitude uniforme sobre todas as saídas, independente de as fases estarem
certas — uma propriedade matemática da transformação, não um limiar mal
calibrado. Nenhum ajuste de `SANITY_FIDELITY_MIN` teria corrigido isso: o
check estava cego por construção, não permissivo. Verificado que a mesma
lacuna estrutural se generaliza a qualquer oráculo cuja distribuição-alvo
(derivada da construção alternativa) seja espalhada, não só QFT — medido em
T045: Simon tem distribuição EXATAMENTE uniforme sobre 2ⁿ resultados
(`max_prob = 1/2ⁿ`, o pior caso observado); Grover sub-ótimo mede
`max_prob≈0,47`; QAOA p=1 com ângulos realistas mediu `max_prob` entre
0,11 e 0,37 nas três instâncias construídas.

**Correção**: compor o circuito primário com o inverso de uma construção
alternativa independente antes de medir, transformando qualquer divergência
de fase em vazamento de probabilidade mensurável para fora de um alvo
nítido — o mesmo bug de sinal invertido passou a medir **0,0000** após a
correção. Aplicado automaticamente (`PEAKEDNESS_THRESHOLD=0.9`, calculado
por tarefa, não decidido por família) sempre que a distribuição-alvo tem
pico abaixo do limiar.

**Por que generaliza**: a lição transferível não é "calibre melhor a
tolerância" — é que testar um verificador contra um bug INJETADO
deliberadamente revela lacunas estruturais que ajustar tolerância nunca
revela. Qualquer checagem de corretude baseada em amostragem/medição sobre
um alvo espalhado tem o mesmo risco, em qualquer domínio onde "distribuição
quase uniforme" seja uma saída legítima e não só um sintoma de erro.

**Onde entra no relatório**: seção sobre desenho de oráculos de
verificação (mesma seção de F1, ou adjacente) — a contramedida por
composição com a inversa é a peça reaproveitável.

**Fonte**: `research.md` D3d (Achado 3), D3e-1; `estado-e-aprendizados.md`
§2.2.

---

### F3 — Um diagnóstico incorreto é pior que nenhum

**Observado**: o loop de reparo recebeu um diff estrutural posicional
(`expected_gate_sequence[i]` vs. `actual_gate_sequence[i]`) que, numa rodada
real contra `ghz_3q`, relatou `[2] cx(1,2) vs cx(0,2)` — apontando como erro
a ÚNICA parte que estava certa (topologia em estrela é GHZ válido a partir
de `|000⟩`) e nada dizendo sobre o erro real da mesma rodada (três portas H
aplicadas, em vez de uma só).

**Evidência**: o gerador local, dentro do laço real do agente, **seguiu a
prescrição do diff** e reproduziu o mesmo `cx(0,2)` como "correção" nas
iterações **1, 3 e 5** — sem nunca convergir dentro do teto de `MAX_ITER`.
O mesmo código e o mesmo diff (colados manualmente, sem outro contexto da
rodada) foram apresentados a um modelo de fronteira em conversa nova: o
modelo de fronteira **ignorou a prescrição do diff** e identificou as
portas H extras por conta própria, produzindo um circuito correto.
Removida a renderização posicional (mantendo os campos brutos no payload,
sem custo — o dado vem gratuito do circuito já desserializado), rodando a
mesma tarefa de novo com o gerador local:

| | diff posicional presente | diff posicional removido |
|---|---|---|
| iteração final | 5 (teto de `MAX_ITER`) | 5 |
| status | `failed_semantic` | `success` |

A contagem de iterações não mudou (duas das cinco tentativas em ambos os
casos eram perdas por símbolos alucinados sem relação — `cx_decompose`,
`u3` — não pelo diff); o que mudou foi o desfecho: converge exatamente na
5ª tentativa sem o diff posicional, nunca converge com ele.

**Por que generaliza**: alinhamento posicional de sequência de gates
pressupõe uma ordenação canônica que não existe para circuitos
equivalentes — por construção, produz falsos positivos sempre que a
referência e o código gerado usam decomposições diferentes, porém
igualmente válidas (a mesma classe de ambiguidade de F1, agora no lado do
DIAGNÓSTICO em vez do VEREDITO). Comparação de contagem por tipo de gate
(um multiset, não uma ordem) permaneceu sólida no mesmo caso (`h: 1 vs 3`,
sinal correto o tempo todo) — o problema nunca foi a contagem, foi a
prescrição posicional ao lado dela competindo por atenção com uma alegação
falsa. Isto não é uma limitação de capacidade do modelo local: ele fez
exatamente o que um diagnóstico estruturado deveria permitir (confiar no
sinal fornecido em vez de re-derivar tudo do zero) — o diagnóstico é que
estava errado.

**Consequência para a análise (T064)**: a taxonomia qualitativa de erros
DEVE distinguir, para toda execução malsucedida que passou pelo `critic`,
falha causada pelo modelo (não produziu o circuito correto apesar de
diagnóstico correto) de falha causada por feedback enganoso (o diagnóstico
continha uma alegação incorreta que direcionou a tentativa seguinte para o
lugar errado). A matriz C1–C5 não controla essa variável hoje — nenhuma
condição isola "loop com diagnóstico correto" de "loop com diagnóstico
potencialmente enganoso" (D16).

**Onde entra no relatório**: seção sobre desenho de loops de reparo
iterativo — citável como resultado independente de qual hipótese central
(H1–H4) se confirme, e relevante à literatura de self-repair/self-debug em
geração de código em geral, não só circuitos quânticos.

**Fonte**: `research.md` D14, D16; `estado-e-aprendizados.md` §2.3.

---

### F4 — Construção independente pegou cinco erros reais de método que revisão de código não pegaria

**Observado**: ao longo da construção do dataset canônico e perturbado
(T044–T048), a disciplina de construção independente exigida pelo Princípio
V/FR-018 (toda referência verificada por uma SEGUNDA implementação, escrita
sem olhar a primeira) pegou cinco erros de método genuínos — nenhum deles
seria detectado só lendo o circuito de referência e concordando que "parece
certo".

**Evidência** (em ordem cronológica de descoberta):

1. **Direção do loop da QFT invertida** (T044/D3d): a primeira
   implementação de `qft()` processava qubits em ordem crescente com
   controle no qubit de índice maior — compilava, executava, produzia uma
   unitária ERRADA. `Operator.equiv()` contra `qiskit.circuit.library.
   QFTGate` retornou `False` para n=2,3,5,8. Corrigido processando do
   índice mais alto para o mais baixo, controle no qubit de índice menor.
2. **Deutsch-Jozsa/Simon/Bernstein-Vazirani classificados como
   `oracle_kind="distribution"`** quando deveriam ser `"statevector"`
   (D3c/D3d): a classificação original foi escrita de memória, nunca
   verificada, até construir o oráculo de DJ para T044 forçar o teste da
   afirmação.
3. **Somador ripple-carry com ancilla encadeada** (T044/D3d, ver F1): o
   circuito primário estava correto nos 16 casos físicos; a checagem de
   construção alternativa discordou nos 240 casos não físicos, revelando a
   dependência de implementação.
4. **Convenção de sinal QUBO→Ising** (T046/D3f, ver F1): duas convenções
   padrão, sinal oposto, sem declaração no enunciado original.
5. **Controle fixo em vez de variável no oráculo perturbado de
   `dj_balanced_6q_perturbed`/`dj_balanced_4q_perturbed`** (T048/D3i): a
   função `_deutsch_jozsa()` do conjunto PERTURBADO usava `qc.cx(j,
   n_input)` com `j` fixo (posição do bit menos significativo de `secret`)
   repetido por bit setado, em vez de `qc.cx(i, n_input)` variando por bit
   — como CX é autoinverso, isso colapsaria silenciosamente para uma
   função de um único bit (repetição ímpar) ou para a identidade
   (repetição par), nunca a função balanceada de múltiplos bits pretendida.
   Pego ao imprimir o diagrama do circuito para derivar o texto do prompt,
   ANTES de qualquer arquivo de tarefa ser escrito — o primeiro dos cinco
   erros a ocorrer dentro do próprio processo de construção do conjunto
   PERTURBADO, não do canônico.

**Por que generaliza**: verificação independente de ground truth é barata
em relação ao custo de descobrir o erro depois de publicado — a taxa de
acerto observada aqui (5 erros reais em ~150 oráculos construídos ao longo
de T044–T048) é evidência de que o mecanismo funciona como desenhado, não
apenas burocracia de processo. Justifica o custo de exigir construção
independente em TODA tarefa de um dataset de benchmark, não só nas que
"parecem arriscadas" — os erros 1, 3 e 5 especificamente não pareciam
arriscados até serem encontrados.

**Onde entra no relatório**: evidência de suporte para a seção
metodológica sobre Princípio V/FR-018 — quantifica o valor da disciplina de
construção independente com uma contagem concreta, não uma alegação
qualitativa.

**Fonte**: `research.md` D3d ("O que isso diz sobre o desenho do
benchmark"), D3f, D3i; `estado-e-aprendizados.md` §3 (nota: esse parágrafo,
escrito antes de D3i, contava só quatro — o quinto foi encontrado depois,
na construção do conjunto perturbado).

---

### F5 — Perturbações vazias teriam diluído `delta_perturbacao` se não fossem checadas por instância

**Observado**: ao construir as 60 variantes perturbadas (T048), várias
combinações candidatas de (tarefa canônica × família de perturbação D12)
seriam VAZIAS — produziriam exatamente o mesmo alvo/unitária que a tarefa
canônica, tornando `delta_perturbacao` artificialmente zero para essa
combinação não por o gerador reconhecer a tarefa (o que a métrica pretende
medir), mas porque não havia perturbação genuína para reconhecer.

**Evidência**: verificado computacionalmente por instância
(`Statevector`/`Operator` `.equiv(...reverse_qargs())` para ordenação de
qubits; `.equiv()` pós-RZ para fase relativa) antes de atribuir qualquer
família, não assumido por nome de família:
- **Grafos-ciclo simétricos**: as três instâncias `qaoa_maxcut_*` (T2) são
  invariantes sob reversão completa de registrador — todo grafo-ciclo Cₙ
  tem a reflexão i → n-1-i como automorfismo, um fato estrutural sobre
  ciclos, não coincidência das três instâncias construídas.
- **Strings marcadas palíndromas**: `grover_3q`/`grover_4q` (T2) têm
  strings marcadas (`101`, `1001`) que são palíndromas — a reversão de
  registrador mapeia o valor marcado nele mesmo.
- **RZ num único estado de base**: Bernstein-Vazirani e QPE (T2) colapsam
  para um ÚNICO estado de base computacional — um RZ em qualquer qubit
  desse alvo é fase global pura, invisível a `Statevector.equiv()`
  (tolerante a fase global por definição).
- Também encontrado, mesma estrutura: dois termos Z-string cobrindo TODO o
  registro em T3 (`ising_zzz_3q`, `ising_zzzz_4q`); seis instâncias em T4
  (subconjuntos GHZ/Ising/Z-string simétricos sob a reversão i → 4-i do
  registro de 5 qubits fixo de `linear_5`).

No total, 14 instâncias candidatas foram identificadas como vazias antes de
serem descartadas da família correspondente — nunca enviadas como tarefa.

**Por que generaliza**: o padrão subjacente é único e previsível a partir
de T2 em diante — uma perturbação é um no-op exatamente quando o conjunto
de qubits que uma estrutura (grafo, termo, string marcada) toca já é
simétrico sob a relabeling que a perturbação aplicaria. Isso não precisou
ser redescoberto a cada tier; tornou-se uma checagem ESPERADA, não uma
surpresa. Qualquer dataset de perturbação sobre entidades com simetria
estrutural (grafos, strings de bits, Hamiltonianos) corre o mesmo risco.

**Consequência de análise, adjacente**: a exclusão sistemática de famílias
inválidas por tarefa individual (em vez de forçar uma distribuição uniforme
4/4/4/3/3 em todo tier) produz uma distribuição final desigual por família
(11/14/15/11/9 nas 60 tarefas, ver tabela em D3j) — o que significa que
efeitos de família e de tier ficam parcialmente confundidos, e
`delta_perturbacao` quebrado POR FAMÍLIA é descritivo, não inferencial,
nestes tamanhos de célula (ver "Threats to validity" abaixo).

**Onde entra no relatório**: seção metodológica sobre construção do
conjunto de avaliação (contaminação de treino / Princípio IV) — como
evidência de que "aplicar uma perturbação" não é uma operação segura por
padrão, precisa de verificação own-instance antes de contar como controle
de memorização.

**Fonte**: `research.md` D3j (corpo principal e a subseção "T048
concluído... contabilidade final das 60 perturbadas").

---

### F6 — Reconhecer um padrão de falha conhecido não confirma que ele se aplica: a correção de `GATES_SUBSET_OF`

**Observado**: durante o desenho da gramática de asserção (US3, D19), a
validação de nomes de gate em `GATES_SUBSET_OF` foi justificada como "um
nome de gate digitado errado torna a asserção vacuamente verdadeira,
alargando silenciosamente o que passa — mesma direção de falha de
D3c/D3d/D3f" (F1, acima). O usuário endossou essa razão explicitamente antes
de qualquer implementação ("Particularly good: rejecting unknown gate
names rather than failing open... Same failure direction as D3c/D3d/D3f").
Ao implementar `_evaluate_gate_restriction`, derivando a lógica exata de uma
checagem de subconjunto (`used_gates - allowed_gates`, aprovado sse a
diferença é vazia), ficou claro que a alegação estava ERRADA: uma checagem
de subconjunto é fail-closed por construção — um circuito que usa de fato o
gate pretendido, com o nome correto, FALHA contra um conjunto com um nome
digitado errado; não foi possível construir nenhum cenário em que um nome
errado tornasse a asserção vacuamente verdadeira.

**Evidência**: nenhum teste automatizado precisou revelar o erro — derivar
manualmente a lógica de conjunto ao escrever a função bastou.
`test_gates_subset_typo_fails_closed_not_open`
(`tests/unit/test_assertions.py`) registra o comportamento correto como
regressão. A correção foi feita nos comentários de `state.py`/
`assertions.py` como uma correção explícita ("Correction versus an earlier
draft of this design..."), não uma reformulação silenciosa da mesma frase, e
comunicada ao usuário no mesmo turno em que foi descoberta.

**Por que generaliza**: a alegação original era convincente PRECISAMENTE
por casar superficialmente com um padrão de falha já estabelecido e
documentado no próprio projeto (três instâncias prévias, F1 acima) — "isto
se parece com o padrão X, logo deve ter a falha do padrão X" é um atalho de
raciocínio que substitui derivar a lógica do caso concreto por reconhecer
uma forma familiar. Casar com um padrão conhecido é motivo para checar com
mais cuidado, não confirmação de que o padrão realmente se aplica. O
endosso do usuário reforçou a confiança na alegação — um segundo
julgamento, de fora, chegando à mesma conclusão antes de qualquer
verificação formal — o que tornou mais fácil, não mais difícil, deixar
passar sem derivar a lógica primeiro: dois julgamentos concordantes
pareceram confirmação redundante quando na verdade eram o mesmo atalho
aplicado duas vezes, por duas partes. Esta é uma classe de erro diferente de
F1–F5: não um defeito no artefato sendo verificado, mas um defeito no
PRÓPRIO RACIOCÍNIO DE DESENHO que justificou uma decisão de implementação —
encontrado e corrigido ao derivar o código, antes de qualquer execução ou
publicação, não depois de um bug em produção.

**Contramedida reprodutível**: para qualquer alegação da forma "isto causa o
mesmo modo de falha que X", derivar explicitamente a lógica do caso
concreto (aqui: o que uma checagem de subconjunto realmente faz sob um nome
incorreto) antes de aceitar a alegação como razão de desenho — mesmo, ou
especialmente, quando a alegação já foi endossada por outra pessoa. Um
endosso externo não é uma segunda derivação independente se ninguém, dos
dois lados, checou a lógica concreta.

**Onde entra no relatório**: nota metodológica sobre revisão de desenho
assistida por LLM em geral, não específica a circuitos quânticos — o risco
não é "o modelo erra sozinho", é "o modelo reconhece um padrão familiar de
um projeto real e para de derivar a lógica concreta, e um revisor humano
que já confia no padrão (por tê-lo visto acontecer três vezes antes) tem o
mesmo incentivo a parar de checar". Relevante a qualquer processo de
revisão de código ou de desenho que se apoie em precedente ("isso é como
aquele bug que já vimos") como atalho de julgamento em vez de sinal para
verificar com mais cuidado.

**Fonte**: `src/qcagent/state.py`/`src/qcagent/validators/assertions.py`
(docstrings de correção); `tests/unit/test_assertions.py::
test_gates_subset_typo_fails_closed_not_open`; `research.md` D19.

---

### F7 — O exercício de validação a frio definiu o escopo real da gramática de asserção mais do que qualquer revisão de desenho

**Observado**: antes de implementar a gramática de asserção (US3), três
tarefas de tiers diferentes — `qft_5q` (T2), `qubo_ising_3var` (T3),
`ghz_linear5_full` (T4) — foram escritas à mão, sem consultar a
especificação da gramática, especificamente para forçar à tona os pontos em
que um usuário real tropeçaria. Um quarto exercício, depois de decidir
dividir `MEASURES` em duas formas sintáticas (nua vs. com lista), usou
`reversible_half_adder_4q` para testar essa divisão contra um oráculo real
antes de aceitar a implementação. O exercício revelou três limites de
escopo genuínos que nenhuma quantidade de revisão da gramática em abstrato
havia revelado — a primeira proposta da gramática (quatro categorias, sem
`INPUT`, sem menção a recursos/topologia) tinha passado por uma rodada
inteira de revisão do usuário sem que nenhum destes três pontos viesse à
tona.

**Evidência**:
- **`qft_5q` — cego para transformação geral sem `INPUT`**: toda asserção
  desta gramática, sem um mecanismo de preparar entrada não-trivial, só
  pode testar comportamento a partir de `|0...0⟩`. Verificado
  computacionalmente: a QFT aplicada a `|0...0⟩` produz a mesma
  superposição uniforme que um `H` em cada qubit isoladamente produziria —
  nenhuma asserção de amplitude/probabilidade/autoestado ancorada só em
  `|0...0⟩` consegue distinguir uma QFT correta de uma implementação que
  não é QFT nenhuma, porque a saída coincide para essa entrada específica.
  Este achado motivou diretamente o prefixo `INPUT(...) THEN <asserção>`
  (D19, item 4) — sem o exercício a frio, essa lacuna não tinha aparecido
  na primeira proposta da gramática.
- **`qubo_ising_3var` — fraca onde o conteúdo é uma derivação numérica**:
  escrever a única asserção não-vazia possível (`PHASE_DIFF` entre dois
  estados de base) exigiu expandir a substituição QUBO→Ising à mão (seis
  coeficientes, várias linhas de álgebra) antes de saber o que escrever —
  a MESMA conta que construir o circuito exige. Ver "Threats to validity"
  para os números exatos verificados. Registrado como limitação de
  cobertura, não alargada: aceitar uma derivação pronta equivaleria a
  aceitar uma referência disfarçada.
- **`ghz_linear5_full` (T4) — recursos e topologia inteiramente fora da
  gramática**: nenhuma das quatro categorias de asserção tem qualquer
  forma de expressar "este circuito respeita o `coupling_map`" ou "a
  profundidade está dentro do limite" — são propriedades do CIRCUITO, não
  do ESTADO. Decisão resultante: não criar uma quinta categoria de
  asserção sobre topologia, e sim surfar a transpilação bem-sucedida
  contra o `coupling_map` (já computada por `static_check`) como evidência
  sem referência no relatório de garantia (US4, ainda não implementado) —
  a asserção declara propriedades de estado; o relatório declara o que foi
  verificado por qualquer meio, incluindo meios que não são asserções.
- **Contraste medido no mesmo exercício**: a mesma gramática, aplicada a
  preparação de estado ou a propriedades qualitativas (`ghz_linear5_full`
  em si, sem o recorte de topologia acima — autoestado coletivo, restrição
  de gate set), não exigiu nenhuma derivação — só conhecimento conceitual
  do que a tarefa pede. A fraqueza não é uniforme sobre todo o produto; é
  concentrada exatamente nas tarefas cujo enunciado É uma derivação.

**Por que generaliza**: nenhum dos três achados era previsível a partir da
gramática vista de cima — a primeira proposta (quatro categorias cobrindo
literalmente os quatro exemplos de FR-010) parecia completa por construção,
porque foi desenhada para cobrir exatamente esses exemplos. O que a
revisão de desenho não pode fazer, e o exercício a frio pode, é forçar a
pergunta "o que eu escreveria de verdade para ESTA tarefa" contra tarefas
reais e variadas — a lacuna de `INPUT` só apareceu por tentar escrever uma
asserção não-trivial para uma transformação real, não por analisar a
gramática em abstrato. É o mesmo argumento estrutural de F1 (um oráculo
mais estreito que o enunciado rejeita respostas corretas em silêncio),
aplicado à gramática em vez de ao oráculo: definir o escopo de uma
ferramenta de verificação exige testá-la contra casos reais e variados
ANTES de publicá-la, não inferir o escopo a partir do desenho da própria
ferramenta.

**Onde entra no relatório**: seção metodológica sobre desenho de linguagem
de verificação — evidência de que validação a frio contra instâncias reais
e heterogêneas (não just os exemplos que motivaram o desenho) é uma etapa
obrigatória antes de aceitar uma gramática de verificação como suficiente,
independente do domínio de circuitos quânticos. Também sustenta diretamente
a redação do relatório de garantia (US4): os três achados acima —
não só o caso QUBO — precisam de menção explícita nesse relatório sempre
que a tarefa em questão se encaixar num dos três padrões, não apenas
ficarem registrados aqui.

**Fonte**: exercício de validação a frio da gramática de asserção (v2, US3),
antes de qualquer implementação; `research.md` D19; "Threats to validity"
abaixo (achado QUBO em detalhe).

---

### F8 — Honestidade na prosa não sobrevive a um campo estruturado que diz o contrário: o texto dizia NOT VERIFIED e o status dizia `success`

**Observado**: o relatório de garantia de um run sem asserções e sem
`oracle_ref` renderizava, corretamente, "FUNCTIONAL CORRECTNESS: NOT
VERIFIED. No assertions were declared for this circuit, so nothing about its
behavior was checked..." — e o mesmo run terminava com `status="success"`. A
prosa era honesta; o sistema ainda assim afirmava aprovação, uma camada para
fora, no campo que ferramentas leem. `success` significava apenas "nenhuma
camada reportou erro", e no caminho de produto nenhuma camada tinha checado
nada.

**Evidência**:
- Saída real de `routing.py::finalize` para esse estado, impressa lado a
  lado: `status = success` seguido do texto NOT VERIFIED.
- O teste obrigatório do Princípio II (`test_report.py::
  test_no_correctness_claim_without_verified_assertion`, T095) estava VERDE
  o tempo todo, e estava certo: ele verificava a prosa, e a prosa não mentia.
  O teste guardava a camada que um humano lê, não a camada que uma agregação
  lê. Nenhum teste existente cobria a relação entre as duas.
- A revisão de desenho dos três relatórios canônicos, feita antes da
  implementação, também não pegou: os exemplos mostrados eram TEXTO
  renderizado, e o `status` não fazia parte do que foi revisado. A
  divergência só apareceu ao rodar o caminho real de `finalize` para colar a
  saída exata, que imprime os dois juntos.
- Consumidores que teriam sido enganados: `analysis/metrics.py` (T059,
  taxa de sucesso por tier), qualquer resumo de CI, qualquer agregação de
  `RunRecord.status`. No caminho da suíte o risco era nulo (`oracle_ref`
  sempre presente, `success` sempre significava equivalência verificada);
  no caminho de produto, todo run sem asserções contaria como sucesso.
- Achado junto, mesma classe: `RunRecord.status` (`bench/schema.py`) não
  listava `assertion_not_evaluable`. Um run que terminasse assim falharia a
  validação no momento da persistência, depois do compute já gasto.

**Correção**: `status="completed_unverified"`, valor distinto de `success`,
e `success` passou a exigir que algo real tenha sido verificado e passado
(`semantic.passed` OU `functional_correctness_verified`).
`terminal_status()` recebe o PRÓPRIO objeto de relatório que `finalize`
devolve, em vez de recomputar as condições, então status e texto não podem
divergir por construção. A métrica da suíte não mudou (as sete asserções
`status == "success"` de `test_us1_flow.py` passam intocadas). A
alternativa descartada foi uma regra de consumo ("nenhum consumidor lê
`status` sem ler também o relatório"): uma invariante que depende de
consumidores cooperarem é quebrada pela primeira coisa que agregue o campo
sozinho. A metade menor do problema, na própria prosa, foi corrigida junto:
o veredito vinha por último, depois de três linhas em formato de "sim"
(`Executed`, `Transpiled`, `Requirements`), e agora vem primeiro.

**Por que generaliza**: qualquer sistema que renderiza um veredito para
humanos ao lado de um código de status para máquinas tem essa superfície de
falha, e ela é invisível a quem só revisa o texto. Formas conhecidas: job de
CI verde com avisos no log; HTTP 200 com corpo de erro; runner de testes com
exit code 0 e testes pulados; scanner de segurança "passed" com "scan
incomplete" na saída. Em todos, o texto pode estar perfeitamente honesto e a
decisão ainda sai errada, porque decisões em escala (dashboards, gates de
merge, taxas agregadas) são tomadas sobre o campo, não sobre a prosa. A prosa
é lida uma vez por uma pessoa; o campo é lido por toda ferramenta, para
sempre.

**Correção a esta entrada, registrada em vez de reescrita**: a versão
original deste achado afirmava que, com `terminal_status()` recebendo o
objeto de relatório, "status e texto não podem divergir por construção". Era
falso quando foi escrito. `terminal_status()` ainda decidia `success` também
por `semantic.passed`, e o relatório ignorava `semantic` inteiramente: todo
run da suíte que PASSAVA sua comparação com referência saía com
`status="success"` e um texto dizendo "nothing about its behavior was
checked". Era a mesma divergência desta entrada, na direção oposta:
subdeclaração e uma afirmação falsa, onde antes havia superdeclaração. Os
testes unitários escritos para a correção não pegaram, porque só construíam
estados sem referência. Quem pegou foi o primeiro teste ponta a ponta do
caminho da suíte (T098), que roda o grafo real e checa, em todo run, que
status e veredito concordam. O mesmo teste achou outros sete bugs na mesma
passada (ver `tasks.md` T092/T098). A alegação só se tornou verdadeira quando
a referência entrou no relatório e "verificado" passou a ser decidido num
único lugar (`GuaranteeReport.functional_correctness_verified`), que
`terminal_status()` apenas lê. A lição da própria correção reforça o achado:
afirmar uma propriedade "por construção" sem testá-la no sistema montado é o
mesmo erro de revisar a prosa sem olhar o campo.

**Contramedida reprodutível**: para toda negação na saída renderizada,
perguntar "o que diz o campo estruturado ao lado dela?". O tipo do status
precisa conseguir REPRESENTAR "terminou mas não verificou"; se não consegue,
ele vai arredondar para aprovação. Derivar status e texto de um mesmo objeto,
e testar no nível do campo, não só da prosa.

**Onde entra no relatório**: seção metodológica sobre relato honesto de
garantia (Princípio II), independente do domínio de circuitos quânticos. É
também a demonstração mais direta de que um teste obrigatório verde não
garante a propriedade que motivou o teste, se ele guarda a camada errada.

**Fonte**: `src/qcagent/nodes/routing.py::terminal_status`/`finalize`;
`src/qcagent/state.py` (`AgentState.status`); `bench/schema.py`
(`RunRecord.status`); `tests/unit/test_routing.py::
test_clean_run_that_verified_nothing_is_completed_unverified_not_success`,
`test_semantic_pass_earns_success_keeping_the_suite_metric_unchanged`,
`test_finalize_status_and_report_cannot_disagree`; `tasks.md` T096b.

---

### F9 — Checagem determinística sobre premissa extraída por LLM: requisitos vetam, nunca estabelecem, e ficam fora do laço de reparo

**Observado**: T091 checa os requisitos que o `planner` extrai da descrição
(`n_qubits`, `gate_set`) contra o circuito gerado. A comparação é
determinística (um inteiro, uma diferença de conjuntos); a PREMISSA não é,
ela é a leitura de um LLM. O peso de um resultado depende da direção, e por
isso o desenho é assimétrico:
- requisito que PASSA: diz só "o circuito concorda com o que o planner leu".
  Não estabelece `functional_correctness_verified`;
- requisito que REPROVA: circuito e descrição discordam sobre algo
  diretamente checável. VETA a alegação de corretude no caminho de produto;
- valor que não dá para avaliar (`"three"`, `"hadamard"` como nome de gate):
  `passed=None`, "não checável", que não veta nada e nunca é reportado como
  reprovação do circuito;
- no caminho da suíte, um requisito reprovado NÃO veta `semantic.passed`: um
  oráculo verificado é verdade-terreno (Princípio IV), e quando os dois
  discordam, quem errou foi o planner.

Uma violação de requisito é reportada e bloqueia `success`, mas não entra na
taxonomia fechada de `error_type` e não dispara `retry_generation`.

**Evidência de que a premissa é frágil de formas que não aparecem na
checagem**:
- **Coerção silenciosa antes de qualquer checagem**: com `value: str | int |
  list[str] | None`, o Pydantic transformava `"value": true` num requisito
  de 1 qubit, `false` num de 0 qubits e `3.0` em `3` (enquanto já recusava
  `2.5`). Os três viravam requisitos CHECADOS como se o planner quisesse
  dizer aquilo. Um teste escrito para confirmar que a guarda de `bool` no
  checador pegava o caso falhou, porque a guarda nunca via um bool: a
  coerção acontecia antes. Corrigido com `StrictInt`, depois de verificar
  que só bool e float integral mudam de resultado, ambos fora do contrato
  que o próprio prompt do planner declara (`string | integer | array of
  string | null`), e que a única resposta real gravada (qwen2.5-coder:7b)
  emite um int de verdade.
- **Vocabulário do extrator ≠ vocabulário do checador**: essa mesma resposta
  real emitiu `gate_set` como `['H', 'CX']`, em maiúsculas. Normalizado; um
  `"hadamard"` vira não checável em vez de reprovação.
- **A mesma premissa usada para RECUSAR entrada do usuário, antes da
  geração** (achado ponta a ponta, T092, ainda em aberto):
  `planner.py::check_assertions` valida o comprimento dos kets das
  asserções DO USUÁRIO contra o `n_qubits` que o LLM extraiu. Se o planner
  lê 3 qubits numa tarefa de Bell de 2, `PROBABILITY(|11>) ~= 0.5`, correta
  para o circuito que de fato seria construído, é recusada como "malformed
  assertion" com `status="rejected_input"`, e a mensagem atribui ao usuário
  um erro que é da extração. Diferente dos casos acima, aqui a premissa de
  LLM não só deixa de ser vetável: ela ESTABELECE uma recusa, antes de
  qualquer circuito existir para desempatar. **Decidido e corrigido**: a
  contagem declarada pelas próprias asserções do usuário prevalece; uma
  divergência com a extraída é tratada como evidência de que a extração
  errou (o requisito `n_qubits` é corrigido e a correção registrada no
  trace), não como asserção malformada; asserções que discordam ENTRE SI
  continuam recusadas, porque isso sim é erro do usuário. Refinado em
  seguida: a correção silenciosa só vale quando DUAS OU MAIS asserções
  concordam na largura, e então aparece também no relatório de garantia.
  Quando UMA única asserção contradiz a leitura do planner, o pedido é
  recusado como ambíguo e pergunta ao usuário: são duas fontes, uma de
  cada lado, e nada desempata entre uma extração errada e um erro de
  digitação no ket (`|0>` querendo dizer 2 qubits). Corrigir em silêncio
  deixaria um único caractere mudar a largura da tarefa; uma linha no
  relatório só informaria depois, e justamente a quem cometeu o erro, o
  leitor menos propenso a reler com cuidado.

**Por que fica fora do laço de reparo — o raciocínio de F3**: F3 mostrou que
o gerador local SEGUE a prescrição de um diagnóstico estruturado mesmo quando
ela está errada. Um diff posicional apontou `cx(0,2)` como erro, e o
gerador reproduziu a "correção" nas iterações 1, 3 e 5 sem nunca convergir.
Se uma violação de requisito alimentasse `retry_generation`, um requisito
mal extraído (ex.: `n_qubits=3` para uma tarefa de 4 qubits) viraria o
diagnóstico "circuit has 4 qubits, requirement states 3", uma prescrição
para QUEBRAR um circuito correto. É a estrutura de F3, com um agravante: lá
o diagnóstico errado vinha de uma comparação determinística contra uma
referência verificada; aqui viria de uma comparação determinística contra a
leitura de outro modelo. O determinismo da comparação LAVARIA a origem da
premissa, e a saída chegaria ao gerador com a credibilidade de uma checagem
determinística carregando o erro de um LLM. É exatamente o tipo de
julgamento de modelo que o Princípio I mantém fora do caminho de veredito,
entrando pela porta de um diagnóstico.

**Por que generaliza**: vale para qualquer pipeline em que um LLM extrai uma
especificação que código determinístico depois checa: o determinismo da
comparação não se transfere para a premissa. Um "passou" contra uma premissa
extraída mede concordância entre dois artefatos produzidos pelo sistema, não
correção contra o mundo. Um "reprovou" é mais informativo, mas ainda não diz
qual dos dois está errado, e por isso não pode virar instrução corretiva
automática.

**Contramedida reprodutível**: classificar cada checagem pela PROVENIÊNCIA
da sua premissa, não pelo determinismo da comparação. Premissa de origem LLM
pode vetar uma alegação, nunca estabelecê-la; valor não avaliável vira
"não checável", nunca reprovação; e não entra num laço de reparo como
diagnóstico sem uma decisão explícita. Na fronteira onde a premissa entra no
sistema, recusar o fora-de-contrato em vez de interpretá-lo.

**Decisão deixada em aberto de propósito**: se violações de requisito devem
retroalimentar o gerador é uma emenda à taxonomia fechada e uma tensão real
com o Princípio I. Hoje elas são reportadas e bloqueiam `success`.

**Onde entra no relatório**: seção sobre desenho de verificação com LLM no
laço, ao lado de F3 (diagnóstico incorreto é pior que nenhum) e do Princípio
I. Independente do domínio de circuitos quânticos.

**Fonte**: `src/qcagent/validators/requirements.py`;
`src/qcagent/report.py::GuaranteeReport.functional_correctness_verified`;
`src/qcagent/state.py::Requirement.value` (StrictInt) e
`RequirementOutcome`; `tests/unit/test_requirements.py`;
`tests/unit/test_routing.py::
test_failed_requirement_does_not_veto_an_oracle_verified_success`; F3
acima; `tasks.md` T091.

---

### F10 — 22 testes ponta a ponta acharam nove bugs que ~220 testes unitários não acharam, e a maioria era a mesma falha: o veredito de garantia errado

**Observado**: T092/T098 acrescentaram 22 testes que rodam o grafo REAL
(planner, gerador e critic com LLM roteirizado que grava prompts; sandbox
real; `assertion_check`, roteamento e `finalize` reais) e checam, em todo
run, que o `status` e o veredito do relatório concordam. Escritos antes das
correções, falharam contra o código existente e acharam nove bugs que os
~220 testes unitários e de contrato da época (256 hoje, depois que as
correções ganharam os seus) não pegavam, todos passando verdes.

**Evidência — a concentração**: quatro dos nove eram o mesmo defeito, o
relatório dizendo algo diferente do que foi de fato verificado:
- **veredito velho**: `assertion_results` sobrevivia de uma tentativa para a
  seguinte, e o relatório dizia "FUNCTIONAL CORRECTNESS: VERIFIED" sobre
  código que não chegou a executar, ao lado de `failed_static`;
- **referência reprovada ainda verificada**: um circuito que falhava na
  comparação com o oráculo mas passava nas asserções saía VERIFIED;
- **corte por recursos escondido**: um run interrompido por excesso de
  recursos mostrava VERIFIED sem mostrar o resultado que o fez parar,
  porque a linha de recursos só era renderizada com `coupling_map`;
- **referência ignorada**: a mesma divergência na direção oposta. Todo run
  da suíte que PASSAVA no oráculo dizia "nothing about its behavior was
  checked" ao lado de `status="success"`.

Os três primeiros são superdeclaração; o quarto é status e texto se
contradizendo. A classe é uma só. Os outros cinco eram de outras classes:
queda do grafo em circuitos com `measure_all()`, `measure`/`barrier` contados
como gates, FR-012 não cumprida (o gerador nunca via QUAL asserção falhou),
e duas frases falsas ou quebradas no veredito.

**Um décimo bug, da mesma classe, achado depois**: ao implementar a decisão de
que a largura do registro vem das asserções do usuário (F9), uma checagem
direta (não um destes testes) mostrou que nada comparava a largura do
circuito com a da asserção. `PROBABILITY(|11>) ~= 0.5` num circuito de 3
qubits PASSAVA: `int("11", 2)` = 3 indexava `|011>`, outro estado de base. E
`EIGENSTATE_OF`/`QUBIT` derrubavam o grafo por dimensão incompatível. Hoje
largura divergente é violação nomeada.

**Por que a concentração é o achado, não coincidência**: cada componente
estava certo sozinho, e cada um tinha teste unitário verde. `generator`
limpava os resultados que existiam quando foi escrito. `report.py` decidia
bem a partir dos campos que recebia. `finalize` montava o relatório com os
campos que conhecia. `terminal_status` decidia o status com o que via. A
falha estava na COMPOSIÇÃO: um campo novo que um nó mais antigo não sabia
limpar, um resultado que um construtor não passava adiante, uma decisão
tomada em dois lugares que podiam discordar. Nenhum teste de componente vê
isso, porque a propriedade quebrada ("o veredito corresponde ao que o
sistema verificou") não pertence a componente nenhum. Ela só existe no
sistema montado. Para um produto cujo valor inteiro é não superdeclarar, é
exatamente onde era de esperar que os bugs se acumulassem. O Princípio II
é uma propriedade do todo, e só um teste do todo a testa.

**A generalização — o defeito tem direção arbitrária, e três formas**:
veredito e verificação real podem divergir em QUALQUER direção sempre que
nada os amarra a uma fonte única. Os dez bugs mostram três formas do mesmo
defeito:
- **superdeclaração**: o veredito afirma mais do que foi verificado (veredito
  velho sobre código que não executou; referência reprovada saindo
  VERIFIED; VERIFIED escondendo o corte por recursos que parou o run);
- **subdeclaração**: o veredito afirma menos (a referência ignorada, dizendo
  "nothing about its behavior was checked" sobre um circuito que tinha
  passado em equivalência unitária exata, com `status="success"` ao lado);
- **verificação de outra coisa**: o veredito está certo sobre a checagem que
  rodou, mas a checagem não foi da propriedade que ele nomeia (o bug 10:
  "PASS" para `PROBABILITY(|11>)`, calculado sobre `|011>`).

A causa comum é estrutural, não de cuidado. Nas duas primeiras formas, a
decisão sobre "o que foi verificado" era tomada em mais de um lugar, ou
reconstruída a partir de campos que um nó mais novo acrescentou e um nó
mais antigo não conhecia. Na terceira, nada amarrava o registro que a
asserção descreve ao registro do circuito avaliado. Por isso a correção que
funcionou foi estrutural: "verificado" é decidido em UM lugar
(`GuaranteeReport.functional_correctness_verified`), que o `status` só lê;
a largura declarada pela asserção é checada contra a do circuito antes de
qualquer avaliação. Superdeclarar é a direção mais perigosa para este
produto, porque é a que produz confiança indevida. Mas subdeclarar é o
mesmo defeito, e corrigir só uma direção deixa a classe aberta. Foi
exatamente o que aconteceu aqui: a correção de F8 fechou a superdeclaração
no status e abriu a subdeclaração no relatório, e só um teste que checava
a concordância nos dois sentidos pegou.

**O acidente de T095 — pior que nenhum teste**: o teste obrigatório do
Princípio II, `test_cannot_construct_a_lying_report`, continuou VERDE depois
que `reference` virou campo obrigatório do relatório. Ele levantava
`ValidationError` pelo campo FALTANDO, não pelo campo proibido
(`functional_correctness_verified=True`), e teria continuado verde com
`extra="forbid"` apagado, que é a garantia inteira. Um teste obrigatório
que passa pelo motivo errado é pior que nenhum teste: sem teste, a lacuna é
visível; com ele, o relatório de testes afirma uma cobertura que não
existe, a mesma superdeclaração que o teste existe para impedir. Agora ele
afirma o erro específico (`extra_forbidden` no campo proibido), e isso foi
confirmado por mutação: remover `extra="forbid"` o faz falhar.

**Contramedida reprodutível**: (1) para uma propriedade de sistema, um teste
de sistema que a verifica em TODO run, não um caso escolhido, e nos DOIS
sentidos (`assert_status_and_report_agree`); (2) decidir "verificado" num único lugar
e fazer o resto LER essa decisão, o que elimina a classe de divergência por
construção em vez de caso a caso; (3) todo teste que afirma que algo é
recusado precisa afirmar o motivo da recusa, e os testes de garantia
precisam ser confirmados por mutação, não só por estarem verdes.

**Onde entra no relatório**: seção metodológica sobre verificação de
sistemas com LLM no laço, junto de F8. Independente do domínio quântico.
Vale para qualquer produto cuja promessa central é uma propriedade de
composição.

**Fonte**: `tests/integration/test_us3_flow.py`, `test_us4_flow.py`,
`_harness.py`; `tests/unit/test_report.py::test_cannot_construct_a_lying_report`;
`src/qcagent/report.py::GuaranteeReport.functional_correctness_verified`;
`tasks.md` T092/T098; F8.

---

<a id="f11"></a>

### F11 — Uma regra enunciada sobre uma instância não se propaga; enunciada sobre uma classe, sim

**O que aconteceu**: `Statevector(qc)` e `Operator(qc)` levantam `QiskitError`
em qualquer circuito que carregue uma medição, e código gerado real termina em
`measure_all()` o tempo todo. Esse defeito foi encontrado ponta a ponta em T092,
no avaliador de asserções, e corrigido lá: `_prepared_statevector` passou a
remover medições FINAIS e a devolver "não avaliável" para medição/reset no meio
do circuito. A correção era certa e a docstring até registrou a causa
("took the whole graph down").

O que não aconteceu foi perguntar onde mais a mesma construção existia. Os três
caminhos de oráculo de referência em `semantic.py` — `_check_exact` (via
`Operator`), `_check_by_composition` (via `psi.evolve`) e `check_statevector`
(via `Statevector`) — tinham o defeito idêntico e o mantiveram. Nenhum teste
unitário de `semantic.py` usava circuito medido: todos construíam circuitos
nus, sem `measure_all()`. O caminho ficou não percorrido, e a suíte ficou verde
por 339 testes.

A primeira execução ao vivo da suíte completa morreu na primeira tarefa que
chegou ao `semantic_check`. A exceção escapou do grafo e levou o processo: 360
runs planejados viraram zero registros e um traceback.

**Por que era plausível não ver**: a correção de T092 tinha todas as marcas de
uma correção completa — foi achada por um teste real, corrigida na origem,
documentada, e com teste de regressão. O que faltou não foi rigor no conserto,
foi escopo na pergunta. "Onde mais este mesmo `Statevector(...)` aparece?" é
uma busca de trinta segundos que não foi feita porque o bug já parecia
resolvido.

**O que o defeito revelou além de si mesmo**: a suíte de regressão não tinha
contenção. Uma exceção em uma execução destruía todas as outras, incluindo as
já concluídas em memória. Uma suíte de regressão que custa horas por defeito
não é rodada com frequência suficiente para ser uma suíte de regressão
(Princípio III), e o modo de falha é autorreforçante: quanto mais cara a
execução, menos vezes se roda, mais defeitos se acumulam entre execuções.

**Como foi fechado** (os três, deliberadamente separados):

1. **A classe, não o sítio**: o primitivo mudou para `validators/circuits.py`
   e os dois lados — asserções e oráculos — passaram a importá-lo. Não é
   reuso por economia; é para que a regra ("medição final não altera o
   veredito; medição no meio significa 'não posso responder'") não possa
   divergir entre os caminhos, porque só existe uma vez.
2. **O veredito ausente não pode parecer um veredito**: quando a checagem não
   roda, `unitary_equiv`/`state_equiv` ficam `None`, não `False`, e nenhuma
   fidelidade é reportada. `False` afirmaria que houve comparação e deu
   negativo; imprimir `fidelidade=0.0000` afirmaria uma medida que não
   existe. É F10 outra vez, na direção do subclaim.
3. **Contenção com registro alto**: `runner.py::_run_one` captura a exceção,
   grava `status="harness_error"` com o traceback e segue. O status é
   deliberadamente distinto de `infrastructure_error`: os dois saem do
   denominador, mas `infrastructure_error` é instabilidade do mundo e rotina,
   enquanto `harness_error` é defeito nosso e invalida o baseline —
   `analysis/metrics.py` imprime um aviso ANTES de qualquer taxa. Registrar
   bug próprio no balde que ninguém conta contra nós é exatamente como uma
   suíte aprende a parecer saudável enquanto está quebrada.

**O corolário imediato, achado pela própria contenção**: com a contenção no
lugar, a execução seguinte não quebrou — completou, com as quatro tarefas em
`harness_error` porque a coleção `qdocs` do Qdrant tinha sumido (volume
recriado). Isso é pior num aspecto específico: em vez de um traceback óbvio, a
suíte produziu um arquivo de resultados completo e uniforme, que se parece com
uma medição do sistema. Daí a terceira defesa, `require_populated_index`: a
suíte recusa iniciar sem índice, pela mesma razão que já recusava iniciar sem
referências verificadas (Princípio IV). Coleção VAZIA conta como ausente — ela
existe, `search()` devolve zero chunks sem reclamar, e a suíte mediria um
gerador sem RAG nenhum, reportado com o nome do sistema que tem RAG.

**A generalização, afiada pelo terceiro caso — e não é "corrigi o sítio em
vez da classe":**

A formulação inicial deste finding era que a correção foi aplicada ao lugar
onde o bug apareceu e não à classe do bug. Verdade, mas fraca demais, porque
sugere descuido pontual. Os três casos deste projeto mostram algo mais
específico e mais incômodo:

**A classe correta é HERANÇA DE ESTADO AMBIENTE**, e não "parâmetro de
requisição" nem "sítio versus classe". As três instâncias decisivas são a
mesma regra — *nunca herde o que altera a medição* — aplicada uma vez e não
propagada para o próximo portador de estado ambiente:

| # | a regra existia para | não foi aplicada a | distância |
|---|---|---|---|
| 1 | `num_ctx`, herdado do default do servidor (D10b) | `temperature`, herdada do Modelfile (F15) | mesmo dicionário `options`, mesma chamada HTTP |
| 2 | `temperature`, agora fixada (F15) | **estado interno do processo servidor**, herdado do que ele fez antes (F19) | mesmo servidor, mesma sessão |
| 3 | ambos, mais o corpus fixado em `qdocs_points` | `.cache/llm`, herdado da execução anterior (F18) | mesma máquina, mesmo diretório |

Duas outras instâncias são da mesma família, com estado herdado de outro
tipo: o primitivo de remoção de medições aplicado a um caminho de oráculo e
não aos outros três (bug 11), e `except QiskitError` como contrato implícito
sobre como a biblioteca falha, cego a `TypeError` (bug 19).

**Reformulação de 2026-09-24, decidida contra o registro e não por analogia.**

A pergunta que a forçou: a disciplina de PRÉ-REGISTRO foi aplicada com rigor
às hipóteses deste projeto (T090c, H-inc, F16) e não foi aplicada aos
critérios de sucesso, onde SC-007 e SC-008 acabaram emendados após medir
(F23). Isso é F11 noutro registro? Não é código, não é ambiente, não é estado
— é uma disciplina metodológica que não atravessou para o domínio vizinho.

**A tentação a rejeitar primeiro**: generalizar para "regras não se propagam
além da instância onde foram aprendidas". Isso unifica tudo e **destrói o que
torna F11 um finding**. A força de F11 é prever: "estado ambiente herdado"
permitiu ENUMERAR candidatos — driver de GPU, binário do Ollama,
`PYTHONHASHSEED` — e dois viraram campos controlados. "Regras não se propagam"
não enumera nada; prevê tudo e portanto nada.

**Mas há uma forma intermediária, e o registro a decide.** O discriminante
estava neste repositório o tempo todo, em duas regras de qualidade
equivalente e destinos opostos:

| | como foi enunciada | propagou? |
|---|---|---|
| **Princípio I** | "**TODA** afirmação de corretude sobre um circuito gerado DEVE derivar de um verificador determinístico" — quantificada sobre uma CLASSE | **sim** — inclusive para `assertions.py`, escrito muito depois, sem ninguém precisar lembrar |
| **D10b** | "`num_ctx` fixado explicitamente em cada chamada" — quantificada sobre UM PARÂMETRO | **não** — nem `temperature`, nem estado do servidor, nem cache |

Mesmo autor, mesmo repositório, mesma qualidade de justificativa. A diferença
é o QUANTIFICADOR.

Logo a forma profunda de F11 não é sobre ambiente, e também não é o vago
"regras não se propagam":

> **Uma regra enunciada sobre uma INSTÂNCIA não se propaga. Uma regra
> enunciada sobre uma CLASSE se propaga.** Enunciar a classe é o trabalho — e
> quem acabou de resolver o caso concreto é justamente quem tem menos motivo
> para fazê-lo, porque para ele a regra já é óbvia.

Explica o histórico inteiro sem exceção: o primitivo de remoção de medições
foi enunciado sobre `_prepared_statevector`; `ParameterBindingError` sobre
`check_energy`; a emenda de taxonomia sobre "este arquivo" — todas instâncias,
todas falharam em propagar. Os Princípios I-IV, todos quantificados sobre
classes, propagaram sem manutenção. E o pré-registro foi enunciado sobre
EXPERIMENTOS, nunca sobre "qualquer critério pelo qual este trabalho será
avaliado", então não alcançou SC-007 nem SC-008.

**Duas explicações rivais, testadas contra o inventário completo de regras —
e o resultado muda a prescrição.**

*Rival 1 — autoridade do documento.* O Princípio I vive na constituição, que
se declara normativa; D10b vive em `research.md`, que registra decisões.
Talvez o que propague seja ONDE a regra está, não COMO foi quantificada.

*Rival 2 — mecanismo de imposição.* O Princípio I tem
`test_architecture.py`, que falha quando violado. D10b não tinha nada. Talvez
a cadeia seja: quantificada sobre classe → torna-se imponível por mecanismo →
propaga.

**O teste decisivo**: existe alguma regra quantificada sobre CLASSE, SEM
mecanismo, que tenha propagado assim mesmo?

**Não. E os contraexemplos estão dentro da própria constituição**, o que
resolve as duas rivais de uma vez:

| princípio | quantificação | mecanismo | quando | violações registradas |
|---|---|---|---|---|
| **I** — verificação determinística | classe ("TODA afirmação…") | `test_architecture.py` | **desde o 1º commit**, 2026-09-04 | **nenhuma** |
| **IV** — referências testadas | classe ("TODA tarefa…") | `validate_oracles.py` como portão | 2026-09-09 | **nenhuma** |
| **II** — honestidade sobre garantia | classe | `report.py` (campo computado, `extra=forbid`) | **2026-09-23**, depois das falhas | **F8, F10** |
| **III** — regressão verificável | classe ("TODA mudança…") | campos controlados em `compare.py` | **2026-09-23**, depois das falhas | **F13, F15, F18** |

**Duas ressalvas metodológicas, antes de ler a tabela como simétrica:**

1. **A coluna "quando" é um confundidor parcial.** I e IV ganharam mecanismo
   cedo; II e III em 2026-09-23, DEPOIS das falhas. A comparação real é
   "mecanismo cedo vs. mecanismo tarde", não "mecanismo vs. nenhum". O que a
   tabela sustenta com força é a **direção negativa**: II e III foram violados
   exatamente durante o período em que não tinham mecanismo. O período
   pós-correção de II e III tem **um dia de idade e ainda não é evidência de
   nada** — se eles voltarem a ser violados agora, a tese de mecanismo é que
   sofre.
2. **Sobrevivência amostral.** A tabela lista regras que visivelmente
   propagaram ou visivelmente falharam. Uma regra sem mecanismo cujo caso
   adjacente NUNCA surgiu parece ter propagado quando apenas nunca foi
   desafiada. Com N=4, uma classificação errada move a conclusão. Há pelo
   menos uma assim neste projeto, marcada abaixo como **sem oportunidade** —
   e não conta como apoio.

**Rival 1 está REFUTADA.** Os quatro princípios estão no mesmo documento, com
a mesma autoridade declarada, no mesmo arquivo. Dois propagaram sem
manutenção; dois foram violados repetida e caramente. A autoridade do
documento não discrimina nada.

**Rival 2 SOBREVIVE e é a carga.** O que separa I e IV de II e III é
exatamente uma coisa: I e IV nasceram com um mecanismo que falha; II e III só
ganharam o seu depois de as violações os forçarem. O Princípio II — "nenhuma
saída afirma corretude sem verificação" — estava escrito, era normativo, era
quantificado sobre classe, e o sistema mesmo assim reportou `success` com o
texto dizendo NOT VERIFIED (F8). Escrever não bastou. Nem escrever na
constituição.

**Então a prescrição muda**: enunciar a classe é o PRIMEIRO passo, não o
passo. A cadeia causal completa é

> quantificar sobre uma classe → **isso torna um mecanismo possível** →
> o mecanismo é o que propaga.

O quantificador é necessário e insuficiente, e a necessidade tem uma razão
mecânica, não retórica: **não se consegue escrever um mecanismo para uma regra
enunciada sobre uma instância.** Um teste para "`num_ctx` deve ser explícito"
só pode checar `num_ctx`; ele não tem como alcançar `temperature`. Já "nenhuma
entrada ambiente pode ser herdada" é enumerável — e foi exatamente enumerá-la
que produziu os campos controlados.

**Isto unifica F11 e F21 numa afirmação mais apertada que qualquer das duas:**

> Uma regra só se propaga se for (a) enunciada sobre uma CLASSE, o que torna um
> mecanismo possível, e (b) dotada de um MECANISMO QUE FALHA quando violada.
> Classe sem mecanismo é aspiração — os Princípios II e III são a prova, e
> custaram cinco findings. Mecanismo sem classe é uma checagem pontual: pega
> aquele caso e nenhum vizinho.

F21 ("campo gravado que nada verifica é decoração") é o caso particular desta
regra aplicado a campos de registro; F11 é o caso geral aplicado a regras.

**Refinamento que o registro também dá**: um mecanismo de escopo instância
detecta TARDE. `route_action` levanta em `error_type` desconhecido — mecanismo
real, mas enunciado sobre "este arquivo": pegou o bug 20 em produção, duas
horas dentro de uma execução. `test_taxonomy_closed.py`, que enumera a
taxonomia inteira contra os três lugares, pega em tempo de autoria. Mesmo
defeito, mesma família de mecanismo; o que muda o custo é a quantificação.

**A previsão muda de alvo, e fica finita e checável hoje.**

O perigo não são as regras enunciadas sobre instâncias. Uma regra de escopo
estreito é visivelmente estreita, e ninguém confia nela além do seu caso. O
perigo são as **regras quantificadas sobre CLASSE e SEM mecanismo, porque
parecem prontas**: normativas, bem justificadas, no documento certo. O
Princípio II é a prova — estava na constituição, quantificado sobre classe,
com a justificativa correta, e o sistema emitia `status="success"` ao lado de
um relatório dizendo NOT VERIFIED.

Auditoria da constituição, de `research.md` e dos contratos. Esta é a lista de
onde vêm os próximos findings:

| regra (classe, sem mecanismo que falhe) | onde | custo do mecanismo | estado |
|---|---|---|---|
| "Código gerado NUNCA executa no processo principal" | constituição | **barato** — teste de AST proibindo `exec`/`eval`/`compile` sobre código gerado fora de `validators/sandbox.py`, espelhando `test_architecture.py`, ~20 linhas | os testes cobrem o comportamento DO sandbox (denylist, timeout, reciclagem); nenhum afirma que nada o contorna |
| "Atualização de versão exige rodada de regressão" | constituição | **caro/impossível em teste** — nenhum teste força um humano a rodar 3 h 26 min | parcial: `compare.py` RECUSA comparar versões diferentes, o que detecta mas não força. **Rotular como não imposta** |
| "Hardware real NÃO PODE ser apresentado como veredito" | constituição | barato quando US5 existir (estender o teste de vocabulário de `report.py`) | **SEM OPORTUNIDADE**: US5 não está implementada, `hardware_note` é sempre `None`. A regra nunca foi desafiada — não conta como propagação |

Regras que a auditoria encontrou **já com mecanismo**, e portanto fora da
lista: "chunk obsoleto DEVE chegar rotulado, não filtrado"
(`test_us2_flow.py::test_scenario3_...`), "erro de infraestrutura NUNCA
contabiliza como erro do modelo" (`analysis/metrics.py` + `test_metrics.py`),
FR-017 (teste de vocabulário em `test_report.py`, estendido ao DOM em
`test_ui_verdict_rendering.py`), e o próprio F21 (`compare.py`).

**As duas ações que a lista prescreve** são diferentes e não devem ser
confundidas: construir o mecanismo barato (primeira linha, agora), e
**rotular explicitamente como NÃO IMPOSTAS** as duas restantes, para que
ninguém as leia como garantias. Uma regra sem mecanismo que se anuncia como
não imposta é honesta; a mesma regra sem rótulo é a decoração de F21 aplicada
a princípios em vez de campos.

**O que a reformulação prevê, na forma antiga** — auditar toda regra deste
projeto enunciada sobre uma instância,
enunciar sua classe, e então perguntar se existe mecanismo. Inventário
concreto em duas colunas, não exortação. A própria F11 é o caso demonstrativo:
como "corrigi o sítio errado" (instância) não previu nada; como "estado
ambiente herdado" (classe) produziu na hora uma lista verificável — e os dois
itens dessa lista que viraram campos controlados só pararam de ser risco
quando `compare.py` passou a recusar comparação, isto é, quando ganharam
mecanismo.

**Por que a formulação importa**: "corrigi o sítio em vez da classe" descreve
o passado e não prevê nada. "Todo estado herdado do ambiente que possa alterar
a medição tem de ser fixado explicitamente e registrado" **prevê onde está a
quinta instância** — basta enumerar o que o experimento ainda herda sem
declarar. O inventário atual, feito por essa regra:

- versão do driver da GPU e do runtime CUDA: herdados, não registrados;
- versão do próprio binário do Ollama: registrada (`lib_versions["ollama"]`),
  mas nunca fixada — um upgrade muda a saída sem aviso;
- estado do contêiner Qdrant (segmentos, merges): herdado; hoje inofensivo
  porque a ordenação virou total (F17), mas era exatamente o portador da
  instância 3 de F17;
- relógio e fuso: entram no `run_id` por desenho, inofensivos;
- `PYTHONHASHSEED`: herdado; hoje inofensivo porque nada no caminho de
  veredito depende de ordem de iteração de `set`, o que é uma afirmação que
  vale a pena testar em vez de assumir.

**O inventário lido contra o que de fato variou entre as duas execuções** — e
é aqui que a regra deixa de ser especulação:

**`PYTHONHASHSEED`: já testado, e passou, por acidente de desenho.** Verificado
que NÃO está fixado em lugar nenhum — nem no Dockerfile, nem no compose, nem
no `.env`, nem no ambiente do sandbox — e que `hash("qc")` de fato difere
entre processos Python consecutivos. As execuções A e B foram processos
separados, logo rodaram com sementes de hash DIFERENTES. Se qualquer coisa no
caminho de veredito dependesse de ordem de iteração de `set`, teria aparecido
nos 0/360. Não apareceu.

O raciocínio importa mais que a conclusão, porque é ele que se reusa: **uma
variável não controlada que varia entre as execuções comparadas é testada por
elas, de graça.** Uma variável não controlada que fica CONSTANTE entre as
execuções não é testada por elas de forma alguma — o zero não diz nada sobre
ela. A pergunta a fazer de qualquer resultado de reprodutibilidade não é "o
que foi controlado?", é "o que variou?". O que variou foi testado; o que ficou
constante continua em aberto.

Limite honesto dessa conclusão: ela cobre os caminhos que os 360 runs
percorreram, não o código inteiro (é F19 aplicada a si mesma). E parte do
mérito é defensivo, não sorte: os pontos onde este código itera `frozenset`
para compor saída legível — nomes de porta, instruções não-unitárias,
ofensores — já usam `sorted(...)`.

**Driver da GPU, runtime CUDA e binário do Ollama: NÃO testados, e silenciosos
de um jeito específico.** Ficaram constantes nas duas execuções, então o
0/360 nada diz sobre eles. O modo de falha deles é o pior possível para um
trabalho acadêmico: só se manifestam em OUTRA máquina ou depois de um
upgrade — exatamente quando alguém tenta reproduzir os resultados, que é
quando ninguém está por perto para notar que a causa foi o ambiente.

**Correção aplicada, e por que registrar não bastava**: `ollama` estava
gravado em `lib_versions` desde a primeira execução e nada o verificava —
o mesmo buraco que `qdocs_points` tinha. **Um campo gravado que nada checa
não protege nada**; ele só cria a impressão de proteção, que é pior que a
ausência dela. `ollama` passou a campo controlado: comparação através de um
upgrade agora recusa.

O stack de GPU não é observável daqui — a GPU é do host, `nvidia-smi` não
existe neste contêiner, e a API do Ollama não expõe driver nem CUDA. Em vez
de inventar um campo que pareça controlado, ele é **declarado** pelo operador
(`QCAGENT_GPU_STACK`) e tratado em dois regimes: não declarado → AVISO
explícito de que o eixo não foi verificado; declarado e diferente → recusa
dura como qualquer outro campo controlado. O aviso em vez de recusa não é
abrandamento: recusar em "unrecorded" bloquearia toda comparação já feita, e
um portão que sempre dispara ensina a ser contornado — o mesmo argumento que
aposentou o limiar de 5%.

Os dois estão listados aqui porque a regra os aponta, e é isso que separa um
finding de uma lista de casos.

O padrão não é "esqueci de procurar". Em todos os casos a regra estava
ESCRITA, com a justificativa correta, e o portador seguinte do mesmo problema
estava ao lado — no mesmo dicionário, no mesmo servidor, no mesmo diretório.
A distância não era conceitual nem física. **Uma regra documentada sobre um
portador de estado ambiente não se propaga para o portador seguinte.**

Por que isso acontece, e por que revisão não pega: a regra é lida como um
FATO SOBRE AQUELE CÓDIGO ("este `except` trata o caso de medição") e não como
uma INVARIANTE DO SISTEMA ("nenhum caminho de verificação pode receber
circuito não-unitário"). Quem escreve conhece a diferença no momento de
escrever; quem lê depois — inclusive o próprio autor, semanas ou horas
depois — lê a instância. O comentário que explica POR QUE é justamente o que
dá a impressão de completude: um trecho bem documentado parece resolvido.

A consequência prática, que é o que vale levar: **quando uma regra merece um
comentário explicando por quê, ela merece um mecanismo**. Um teste que
enumera os caminhos (como `test_taxonomy_closed.py` passou a fazer para a
taxonomia), um primitivo compartilhado que só existe uma vez (como
`validators/circuits.py`), ou uma checagem de cobertura da invariante. Um
comentário não propaga; código compartilhado e teste enumerativo propagam.

**As duas generalizações originais, que seguem valendo:**

**1. Corrigir o sítio em vez da classe deixa um clone vivo.** O defeito não
foi encontrado e consertado mal — foi encontrado e consertado BEM, com teste
de regressão e docstring explicando a causa. O que faltou foi escopo na
pergunta final. "Está corrigido?" responde-se naturalmente sobre o lugar que
falhou; a resposta útil é sobre a CONSTRUÇÃO que falhou. `Statevector(qc)`
sobre circuito possivelmente medido aparecia em quatro lugares; um foi
corrigido e três seguiram idênticos por meses. A contramedida é mecânica e
custa trinta segundos: antes de fechar o item, `grep` pelo padrão, não pelo
sintoma.

**2. Cobertura sobre entrada irrealista não é cobertura.** Esta é a mais
transferível das duas, e a mais desconfortável, porque o painel de cobertura
mostrava `semantic.py` exercitado. E estava — por circuitos que nenhum gerador
deste sistema jamais escreveria. Todos os testes construíam circuitos nus,
sem `measure_all()`, enquanto o produtor real de entrada para aquelas funções
termina em `measure_all()` quase sempre. A métrica de cobertura mede linhas
executadas, não plausibilidade da entrada, e as duas divergem exatamente onde
importa: as linhas estavam verdes e a primeira entrada real derrubou o
processo.

A regra que teria bastado sozinha, sem nenhuma das outras contramedidas deste
relatório: **o teste unitário de um verificador precisa usar a forma de
entrada que o sistema realmente produz** — não uma forma didática dela. Onde
existe um produtor identificável a montante (aqui, o gerador), a fixture
deveria derivar da saída dele, não de uma construção à mão que o autor do
teste acha representativa.

**A mesma classe, quatro vezes mais, na mesma sessão** — o que eleva isto de
anedota a padrão:

*Bug 14.* Com o oráculo corrigido, a suíte completa foi lançada e morreu aos 6
min 49 s, na primeira tarefa cujo código de fato transpilou:
`StaticResult.circuit_qpy` guarda bytes QPY crus, e `model_dump(mode="json")`
tenta decodificá-los como UTF-8. `bench/run_single.py` já excluía esse campo,
com um comentário dizendo que ele é "never JSON-safe", desde muito antes. O
conhecimento estava no repositório; não estava aplicado no ponto onde os bytes
eram escritos em disco. Nenhum smoke run alcançou isso porque só há QPY quando
o código transpila — e nos smokes nada transpilava.

*Bug 14b, e este era meu.* A contenção que eu tinha acabado de escrever
envolvia só a chamada do grafo, não a construção e serialização do registro.
Por isso o bug 14 derrubou a suíte inteira apesar da contenção existir. Uma
contenção que cobre só metade do caminho crítico dá a confiança de estar
protegido sem a proteção — pior que não ter, porque a próxima execução longa é
lançada sem supervisão. Sobreviver ao grafo não basta: o resultado ainda
precisa sobreviver a ser escrito.

*Bug 16, o quarto, e de outra família.* `_parse_planner_response` chamava
`json.loads` sem tratamento: um JSON inválido vindo do planner escapava como
exceção e derrubava a execução. Não é "corrigido no sítio errado" — é caminho
de erro que nunca existiu, porque todo teste do planner alimentava resposta
bem-formada. Um modelo de 7B emitindo JSON inválido é saída ROTINEIRA, não
excepcional; o único motivo de nunca ter aparecido é que nada antes tinha
rodado o planner contra um modelo real 360 vezes. A escolha de status foi a
parte substantiva: `aborted`, e explicitamente nem `rejected_input` (culpar o
pedido do usuário por falha de extração nossa é F3) nem `infrastructure_error`
(o provedor respondeu; esse balde sai do denominador e esconderia uma
fraqueza real do sistema sob teste).

*Bug 17, o quinto — e este é a demonstração mais forte do finding, porque fui
eu quem o cometeu, horas depois de escrever F11.* Ao corrigir o bug 16 eu
tratei o parse de JSON do planner e **não procurei os outros parsers de saída
de LLM no repositório**. Existe exatamente mais um, `critic.py::
_parse_hint_response`, com a mesma estrutura linha a linha: `re.search` por um
objeto JSON, `json.loads`, indexação de chaves, zero tratamento. A execução
completa seguinte levantou `JSONDecodeError` lá, em duas tarefas.

Ou seja: escrevi a contramedida ("antes de fechar o item, `grep` pelo padrão,
não pelo sintoma"), e no defeito seguinte não a executei. Isso diz algo sobre
o custo real de contramedidas que dependem de disciplina — o mesmo argumento
que este projeto já aceitou para invariantes que dependem de consumidores
cooperarem. Uma regra que só existe num documento é uma regra que será
esquecida exatamente quando o contexto estiver carregado, que é quando ela
importa.

A correção do crítico, porém, NÃO é a mesma do planner, e a diferença é
instrutiva: a AÇÃO do crítico (`route_action`) é determinística e não passa
por LLM nenhum (Princípio I) — o modelo só escreve a justificativa e a dica
em linguagem natural. Logo, dica malformada deve DEGRADAR (segue sem dica),
não abortar: perde-se qualidade da próxima tentativa, não corretude. No
planner era o contrário — sem requisitos não há o que gerar. Mesma família de
defeito, mesmo ponto de falha, tratamentos opostos, e o que decide é o que
cada saída significa para o resto do sistema.

*Bug 19, o sexto, e o mais literal de todos.* A correção do bug 11 fez
`prepared_statevector` capturar `QiskitError`. Um circuito parametrizado sem
valores ligados (ansatz de VQE/QAOA) não levanta `QiskitError` — levanta
`TypeError: ParameterExpression with unbound parameters cannot be cast to a
float`. Logo, o caminho de oráculo voltou a quebrar, na mesma função que eu
acabara de consertar, por uma família de exceção que a captura não cobria.

E o repositório já sabia: vinte linhas acima, no MESMO arquivo, a classe
`ParameterBindingError` existe com a docstring "Qiskit's own failure here is a
bare `TypeError` (...) that doesn't say why" — escrita para `check_energy` e
nunca aplicada aos caminhos statevector/unitário. Terceira ocorrência da mesma
classe dentro de `semantic.py`, e a segunda em que o conhecimento necessário
estava escrito no próprio módulo.

O padrão que isto expõe, mais fino que "corrigi o sítio errado": **uma captura
de exceção define um contrato implícito sobre como o código abaixo falha**, e
esse contrato é invisível. `except QiskitError` parece total porque a
biblioteca é Qiskit; não é, porque Qiskit deixa `TypeError` de aritmética
escapar. Nenhuma revisão de código nota isso, e nenhum teste com entrada
didática o alcança.

*Bug 20, o sétimo — e o único que uma defesa existente pegou.* A correção do
bug 11 criou o `error_type` `NonUnitaryCircuit`, emitido por `semantic.py` e
registrado na taxonomia fechada em data-model.md. Não foi adicionado a
`_RETRY_GENERATION_ERRORS` em `critic.py`. Na execução ao vivo, o primeiro
circuito com medição no meio produziu o veredito novo, o roteamento não o
conhecia, e `route_action` levantou:

    ValueError: unroutable error_type 'NonUnitaryCircuit' — closed taxonomy violated

O comentário acima daquele conjunto, escrito muito antes por outro motivo, diz
exatamente o que aconteceu: "uma emenda de taxonomia que esquecer de atualizar
este arquivo falha ruidosamente em vez de rotear errado em silêncio". Eu fiz a
emenda, esqueci o arquivo, e o mecanismo me pegou.

Duas leituras, e as duas importam:

**A favor**: esta é a única das sete falhas desta sessão que uma salvaguarda
projetada capturou, e ela capturou na direção certa — ruidosa, nomeando o
valor exato e a invariante violada. É o argumento empírico a favor de
taxonomias fechadas com verificação explícita em vez de `else: pass`.

**Contra**: pegou em produção, depois de duas horas de execução, não em
teste. Meus testes do bug 11 exercitaram `semantic.py` isoladamente e nunca
alimentaram o `error_type` resultante em `route_action`. Testei o COMPONENTE,
não o CAMINHO — que é literalmente a lição de F11, cometida por mim pela
terceira vez na mesma sessão, agora em forma de teste em vez de código.

A correção de classe, e não de sítio, é um teste que enumera a taxonomia e
afirma que `route_action` trata cada entrada. Enquanto a lista de tipos e o
roteamento forem dois lugares mantidos à mão, alguém vai esquecer de novo;
uma verificação que percorre os dois torna o esquecimento impossível em vez
de meramente ruidoso.

**O que os sete juntos dizem**: o defeito não é distração pontual, é o escopo
padrão da pergunta "está corrigido?". A resposta natural é sobre o sítio que
falhou. A resposta útil é sobre a construção — e, quando a correção é uma
salvaguarda, sobre o caminho inteiro que ela promete cobrir.

**Onde entra no relatório**: junto de F10, como o caso em que a generalização
de F10 (veredito e verificação real divergem sempre que algo além da própria
checagem decide o veredito) se manifesta na direção do subclaim, e como
evidência da tese de Princípio III sobre custo de execução da suíte.

**Fonte**: `src/qcagent/validators/circuits.py`;
`src/qcagent/validators/semantic.py`; `bench/runner.py::_run_one`,
`::require_populated_index`; `tests/unit/test_semantic_measured_circuits.py`;
`tests/integration/test_runner_contains_failures.py`; `analysis/metrics.py`;
F10; T092.

---

### F12 — A suíte de testes destruía o índice de retrieval, e nada ligava as duas coisas

**O que aconteceu**: `tests/unit/test_index.py` precisa de um Qdrant REAL —
o modo `:memory:` ignora índices de payload em silêncio, então os dois checks
exigidos por contrato não podem ser feitos contra ele. Para consegui-lo, os
testes usavam a coleção de PRODUÇÃO: `ensure_collection(..., recreate=True)`
(que apaga e recria) e uma fixture que deletava a coleção no teardown.

Consequência: **todo `pytest` apagava o corpus ingerido**. E a próxima
execução da suíte de regressão media um gerador sem retrieval nenhum,
reportado com o nome do sistema que tem retrieval.

**Por que ficou invisível tanto tempo**: nada conecta os dois eventos. Os
testes ficam verdes — eles limpam o que sujaram, corretamente, do ponto de
vista deles. O índice some. A próxima pessoa a rodar a suíte vê resultados
ruins e não tem motivo para suspeitar do `pytest` que rodou antes. Os dois
sintomas que observei — "a coleção sumiu" logo após um run verde, e depois de
novo — pareceram, na primeira vez, um volume Docker recriado. Só a terceira
ocorrência, com o log do Qdrant aberto mostrando `DELETE /collections/qdocs`
com timestamp exatamente igual ao do meu `pytest`, identificou a causa.

**A parte perigosa não é o dano, é o formato do dano**: um índice ausente não
faz a suíte falhar. Faz ela produzir 360 resultados uniformemente ruins, que
têm exatamente a aparência de uma medição do sistema. Sem `require_populated_
index` (F11), esse teria sido o "baseline" registrado — e o número teria
entrado no relatório.

**Como foi fechado, em duas camadas deliberadamente diferentes**:

1. **A causa**: os testes passaram a usar uma coleção descartável
   (`qdocs_test_index`), redirecionando o global que `index.py` lê. Nem a
   criação nem o teardown tocam mais no nome real.
2. **A classe**: `tests/conftest.py` registra a contagem de pontos da coleção
   real no início da sessão e FALHA a sessão no fim se ela mudou. Corrigir o
   único teste que fazia isso não impede o próximo; "não mexa em `qdocs`" é
   precisamente o tipo de invariante que depende de todo mundo lembrar. Esta
   percebe.

**Relação com o guard de rede**: é o mesmo defeito que `NetworkAccessInTests`
já endereçava, num recurso que não é a rede. Um teste que alcança estado
mutável compartilhado fora do seu sandbox produz falhas que não são atribuíveis
ao código sob teste — e, neste caso, produz falhas num OUTRO processo, horas
depois, sem rastro. A lição generalizada: todo recurso compartilhado que os
testes tocam precisa ou de isolamento por construção, ou de um detector; a
boa vontade não é mecanismo.

**Onde entra no relatório**: metodologia — validade dos números da suíte de
regressão, junto de F11 e do Princípio III. O ponto citável é que a ameaça
mais séria à validade não foi um resultado errado, foi um resultado
plausível produzido por um sistema que não era o sistema sob teste.

**Fonte**: `tests/unit/test_index.py::TEST_COLLECTION` e a fixture `client`;
`tests/conftest.py::pytest_sessionstart`/`pytest_unconfigure`;
`bench/runner.py::require_populated_index`; logs do contêiner Qdrant
(`DELETE /collections/qdocs`); F11.

---

### F13 — O corpus de retrieval é raspado ao vivo a cada ingestão, e uma falha HTTP transitória o encolhe em silêncio

**O que aconteceu**: duas execuções de `make index`, mesmo código, mesma
configuração, produziram **1020 e 1019 chunks**. A diferença apareceu como um
número no log e quase passou como ruído. Não é ruído: `collect_chunks()` busca
as ~221 páginas de documentação por HTTP no momento da ingestão, e uma delas
(`qiskit.circuit.library.SGate`) respondeu `503 Service Unavailable`. O
tratamento é `print(f"  SKIP {url}: {exc}")` e `continue` — a ingestão segue e
**termina com código 0**.

O comportamento em si é defensável no ponto onde foi escrito, e a docstring diz
por quê: "at this scale (200+ pages), one dead link must not abort the whole
ingestion run". O problema não é a tolerância, é que ela é silenciosa e o
resultado é a variável independente do trabalho inteiro.

**Por que isto é mais sério do que parece**: a tese que a suíte de regressão
existe para medir é sobre RAG. O corpus É o tratamento. Se duas execuções da
suíte usam corpora diferentes:

- SC-008 ("duas execuções do MESMO código divergem em menos de 5% das
  tarefas") deixa de medir a estabilidade do harness e passa a medir
  estabilidade do harness MAIS deriva do corpus, sem separar as duas;
- uma comparação antes/depois de uma mudança no gerador atribui ao gerador
  qualquer efeito de uma página que entrou ou saiu do índice no meio;
- e nada no arquivo de resultados registrava qual corpus produziu os números.

**A forma do defeito é a mesma de F12**: não produz falha, produz um resultado
plausível. Um índice com 1019 páginas em vez de 1020 não quebra nada — gera
números ligeiramente diferentes que se parecem com efeito da mudança sob teste.

**O que foi feito agora** (mitigação, não correção): `lib_versions` de cada
`RunRecord` passou a carregar `qdocs_points`. Isso não torna o corpus
reprodutível; torna a irreprodutibilidade **detectável**, que é o mínimo
exigível para que uma comparação entre duas execuções seja honesta. Duas
execuções com `qdocs_points` diferente não são comparáveis, e agora dá para
saber disso lendo o arquivo em vez de adivinhando.

**O que ainda falta decidir** (não decidido unilateralmente — muda o desenho da
ingestão, e o mesmo raciocínio de D15 e do pinning do fastembed se aplica):

1. **Cachear o HTML raspado** num diretório/volume versionado, de modo que
   `make index` releia o cache em vez da rede — o análogo direto de D15 e do
   cache pinado de modelos. Torna a ingestão reprodutível e offline.
2. **Manifesto do corpus**: uma lista de URLs esperadas com hash do conteúdo;
   a ingestão FALHA se alguma faltar, em vez de pular. Transforma o defeito de
   silencioso em ruidoso sem cachear nada.
3. **Aceitar a deriva e sempre reingerir antes de comparar** — a opção barata,
   e a pior: depende de disciplina humana para uma invariante que já se sabe
   que ninguém verifica.

Minha recomendação é (1) com (2) como verificação, pela mesma razão já aceita
duas vezes neste projeto: um pipeline que às vezes falha por motivos fora do
código ensina a ignorar falhas.

**Onde entra no relatório**: "Threats to validity", como a ameaça mais séria
aos números da suíte, e na metodologia junto de D15. O ponto citável: num
sistema RAG, o corpus é um parâmetro experimental, e um parâmetro que muda
sozinho entre execuções invalida comparações sem nunca se anunciar.

**Fonte**: `src/qcagent/retrieval/ingest.py::collect_chunks` (o `SKIP`);
logs das duas ingestões (1020 vs 1019, `SKIP ... SGate: 503`);
`bench/runner.py::run_suite` (`qdocs_points` em `lib_versions`); D15; F12.

---

### F14 — Um laço de reparo que quase nunca converge depois de engatar: 331 de 335 falhas esgotaram as 5 iterações

**O número**: na primeira execução completa ao vivo (360 runs, baseline em
"Measured results"), das 335 falhas que chegaram a gerar código, **331
terminaram por esgotamento de `MAX_ITER=5`**. As outras 4 são
`rejected_input`, que recusa antes de gerar. Nenhuma falha saiu do laço por
qualquer outro caminho.

Junto disso, `verificado@1 = 0,0%`: nenhum dos 341 runs verificou corretude
funcional na primeira tentativa. Os 6 sucessos levaram 2, 2, 3, 3, 5 e 5
iterações.

**A leitura ingênua está errada.** "Zero acertos de primeira, e o laço resgata
6" parece um laço que funciona pouco mas funciona. O `331/335` diz outra
coisa: o laço tem essencialmente UM modo de término, e é a desistência. Ele
não escolhe entre convergir e desistir conforme a dificuldade da tarefa — ele
desiste quase sempre, e os 6 sucessos são a cauda, não o comportamento.

**Por que isto é finding sobre laços de reparo e não sobre este gerador**: o
custo de um diagnóstico errado escala com `MAX_ITER`. Cinco iterações de um
diagnóstico certo e cinco de um errado custam exatamente o mesmo — mesmo
número de chamadas de LLM, mesmo tempo, mesma energia. O que difere é apenas
se alguma delas podia funcionar. Nesta execução, 112 runs (39% das falhas
estáticas) receberam `retry_retrieval` para um `NameError` sobre símbolo que
EXISTE: **mais documentação não acrescenta uma linha de `import`**. A ação era
estruturalmente incapaz de resolver a falha, e foi repetida cinco vezes.

Daí a conexão com F3, mais forte aqui que no caso original. F3 dizia que um
diagnóstico incorreto é pior que nenhum, porque manda o destinatário na
direção errada. Num laço automático a afirmação vira quantitativa: **o
prejuízo de um diagnóstico incorreto é multiplicado pelo orçamento de
iterações**, sem nenhum mecanismo que perceba que as tentativas não estão se
aproximando. O laço não tem noção de progresso; tem contador.

**A consequência de desenho, que vale fora deste projeto**: aumentar
`MAX_ITER` é a reação instintiva a um laço que não converge, e é a reação
errada enquanto o roteamento estiver errado — multiplica o custo pelo mesmo
fator em que multiplica as chances, e as chances são zero quando a ação não
endereça a causa. A pergunta anterior a "quantas tentativas?" é "esta ação
pode, em princípio, corrigir esta falha?". Se não pode, nenhum orçamento
resolve.

**O que ainda NÃO está estabelecido**: tudo acima é compatível com duas
explicações rivais — (a) o roteamento manda o modelo para o lado errado, e
consertá-lo faz o laço convergir; (b) o gerador não melhora com feedback
nenhum, e o laço nunca convergiria nem com diagnóstico perfeito. O baseline
NÃO separa as duas, e afirmar (a) agora seria exatamente o erro que F6
descreve: reconhecer um padrão conhecido e tomar isso por confirmação. A
predição registrada em "Measured results" existe para separá-las: se a classe
corrigida passar a convergir em 1-2 iterações, é (a), e fica sendo a
evidência mais forte deste projeto de que **roteamento diagnóstico, e não
orçamento de iterações, determina se um laço de reparo funciona**. Se
continuar esgotando, é (b), e o alvo passa a ser o gerador.

**Onde entra no relatório**: capítulo sobre o laço de reparo, como o resultado
principal sobre ele, com F3 como antecedente conceitual. Independente do
domínio quântico: vale para qualquer sistema que classifique um erro e
escolha uma ação de correção automática.

**Fonte**: baseline `ce9614fa3a6f60a6` (360 runs); `analysis/metrics.py`
(`mean_iterations_to_success=3,33`, `verificado@1=0,0%`); classificação dos
287 `failed_static` pelo erro da última tentativa; F3; F6; T090c.

---

### F15 — Um seed fixo não torna o gerador determinístico, e o controle da predição foi o que revelou isso

**O que aconteceu**: a predição registrada antes da correção de roteamento
declarou `compila@1` como CONTROLE — a métrica mede a tentativa 1, que
acontece antes de existir qualquer roteamento, logo nenhuma mudança no
crítico pode movê-la. Com seeds fixos, prompt e corpus idênticos, ela tinha
de voltar igual.

Voltou **10,9% → 15,6%**.

Investigação direta: das 360 duplas (tarefa, seed) compartilhadas entre as
duas execuções, **94 (26,1%) produziram um erro de tentativa 1 DIFERENTE** —
mesmo modelo, mesmo seed, mesmo prompt, mesmo índice (`qdocs_points=1019` nas
duas). Exemplos: `bv_6q` seed 3 falhou importando `X` numa execução e `CNOT`
na outra; `bell_psi_plus_2q_perturbed` seed 2 compilou numa e não na outra.

**Causa raiz**: `ollama_client.py` enviava `num_ctx`, `seed` e `num_predict`,
e **nunca `temperature`** — herdada do Modelfile do modelo. Medido contra o
servidor: mesmo prompt, mesmo seed, 4 chamadas → **2 saídas distintas**; com
`temperature=0` → **4 idênticas**. Detalhe revelador: a chamada discrepante é
a PRIMEIRA, o que indica dependência de estado quente (carga do modelo, cache
KV) — exatamente o que difere entre duas execuções de suíte separadas.

**A ironia metodológica**: D10b já tinha estabelecido esta regra exata, para
`num_ctx`, com a mesma justificativa ("nunca herdado do default do servidor",
porque um valor herdado em silêncio muda a medição sem deixar rastro) e sobre
o mesmo objeto — o dicionário `options` da mesma chamada HTTP. A regra estava
certa, estava escrita, e não foi generalizada para os outros parâmetros de
amostragem que moram no mesmo dicionário. É F11 mais uma vez, agora entre um
parâmetro e seus vizinhos literais.

**O custo**: a comparação antes/depois de T090c é confundida. Parte dos 50%
de divergência por tarefa entre as duas execuções é a correção, parte é
ruído, e os dados não separam as duas. Só sobrevive a conclusão sobre o
efeito GRANDE que não apareceu (MAX_ITER 98,8 → 98,9), porque ruído de poucos
pontos não esconde um efeito grande.

**O que isto significa para SC-008**: o critério pede que duas execuções do
MESMO código divirjam em menos de 5% das tarefas. Com 26,1% de divergência já
na tentativa 1, **SC-008 não era alcançável na configuração medida**, e nunca
tinha sido testado porque esta foi a primeira vez que duas execuções completas
existiram para comparar. A medição honesta de SC-008 exige uma execução
duplicada com `temperature=0` — ainda não feita.

**Por que o controle valeu mais que o tratamento**: sem ele, o salto de
`compila@1` teria sido lido como efeito da correção — "compila@1 subiu 43%" é
uma frase citável, plausível e completamente falsa, porque a correção atua em
tentativas ≥2 e a métrica mede a tentativa 1. O único motivo de isso não ter
entrado no relatório é ter escrito ANTES qual número não podia se mover. Uma
predição registrada não serve só para poder estar errada sobre o efeito;
serve para que um efeito impossível seja reconhecido como ruído em vez de
celebrado como resultado.

**Contramedida aplicada**: `temperature` pinado em 0,0 e enviado
explicitamente, com o valor configurável para quem quiser amostragem
deliberada. A generalização da regra de D10b: **todo parâmetro de amostragem
que afeta a saída é fixado explicitamente na chamada, nunca herdado** — e o
teste que a mantém é `tests/unit/test_ollama_determinism.py`.

**Onde entra no relatório**: metodologia, ao lado de D10b, e em "Threats to
validity" como a ameaça que invalidava comparações entre execuções. O ponto
citável: num experimento com LLM no laço, o parâmetro mais perigoso é o que
não se declara, porque o default é invisível e nada no resultado revela que
ele estava lá.

**Fonte**: execuções `ce9614fa3a6f60a6` e `6cf69f6ab7f3d2c0`; teste direto de
determinismo contra o servidor Ollama; `src/qcagent/llm/ollama_client.py`;
`analysis/compare.py` (divergência 50,0%); D10b; F11; F14.

---

### F17 — Determinismo tem mais de uma fonte, e corrigir a mais óbvia não resolve: o empate na fusão RRF

**O que aconteceu**: F15 identificou `temperature` não fixada como causa da
não-reprodutibilidade e corrigiu. A correção estava certa e era necessária.
Duas execuções COMPLETAS do MESMO código com `temperature=0`:

| medida | antes de F15 | com `temperature=0` | SC-008 exige |
|---|---|---|---|
| divergência por tarefa | 50,0% | **36,7%** | < 5% |
| tentativa 1 divergente | 26,1% | **28,3%** | 0% |

A divergência na tentativa 1 **não se moveu**. Em retrospecto isso é óbvio e
eu deveria ter previsto: o teste que fiz para validar `temperature=0` foram 4
chamadas do MESMO prompt, quentes, em sequência. Ele provou que o modelo é
determinístico dado um prompt — e não prova nada sobre o prompt ser o mesmo.

**A segunda fonte**: o RETRIEVER. Cinco consultas idênticas devolveram 2
sequências de chunks distintas. Decomposição:

- Ollama com `temperature=0`: 5/5 saídas idênticas, com prompt curto E com
  prompt longo (~4k tokens). **Determinístico.**
- Retrieval: mesmo CONJUNTO de chunks em todas as execuções, **ORDEM
  diferente**.

A causa é visível nos scores: a fusão RRF produz empates EXATOS com
frequência — `C4XGate:0.50000` e `circuit:0.50000` na mesma resposta — e o
Qdrant resolve o empate na ordem em que os segmentos entregaram. O conjunto é
estável; a ordem não.

**Por que a ordem importa tanto quanto o conjunto**: a ordem dos chunks é a
ordem em que eles aparecem no prompt do gerador. Dois chunks empatados
trocados de posição são um PROMPT DIFERENTE, e um modelo determinístico
alimentado com prompt diferente responde diferente. O sistema tinha dois
geradores de aleatoriedade em série; silenciar um deixou o outro intacto e a
métrica quase igual.

**Correção**: ordenação total por `(-score, doc_id)` no cliente, com
over-fetch de 3× antes do corte. O `doc_id` é único por chunk, então a ordem
é total e não sobra ambiguidade para o layout dos segmentos preencher. O
over-fetch é necessário porque um empate que ATRAVESSA o corte é resolvido
pelo servidor, e nenhuma ordenação no cliente recupera um chunk que nunca foi
devolvido. Verificado depois: 8 consultas idênticas, 1 única ordenação, em
três consultas diferentes.

**A lição, que é sobre método e não sobre Qdrant**: ao diagnosticar
não-determinismo, o instinto é procurar A fonte. Havia duas, em série, e a
primeira era a famosa — todo mundo sabe que LLM amostra. A segunda estava num
componente que ninguém chama de estocástico: uma busca vetorial é "só um
índice", até que dois scores empatam. **Um sistema com N fontes de
não-determinismo em série não fica reprodutível quando N-1 são corrigidas, e
a métrica não melhora proporcionalmente — ela mal se move**, o que pode ser
lido erroneamente como "a correção não funcionou".

O procedimento que eu deveria ter seguido desde o início, e que só segui na
segunda rodada: **decompor por componente antes de corrigir** — testar
determinismo de cada estágio isoladamente (gerador com prompt fixo, retriever
com consulta fixa), em vez de corrigir o suspeito provável e reexecutar 2h
para descobrir.

**Contagem correta das fontes, verificada antes de escrever este número**:
DUAS, não três. A terceira suspeita — o planner divergindo em `qft_3q` — é a
MESMA fonte que o gerador, aparecendo num segundo ponto de chamada. Testado
com o prompt exato do planner sob o mesmo protocolo que expôs o gerador:

    warm, 4 calls:       467850e60903, 536ab226bec9, 536ab226bec9, 536ab226bec9
    first-after-load x3: 467850e60903, 467850e60903, 467850e60903
    warm again, 3 calls: 536ab226bec9, 536ab226bec9, 536ab226bec9

Assinatura idêntica à do gerador: duas saídas estáveis, uma para a primeira
chamada após carga fresca e outra para as chamadas seguintes. Logo o inventário
é:

1. `temperature` herdada do Modelfile — **nossa**, corrigida (F15);
2. empate de RRF resolvido pela ordem dos segmentos — **nossa**, corrigida
   (F17, esta entrada);
3. estado interno do servidor de inferência — **não nossa**, em DOIS pontos de
   chamada (planner e gerador), mesma causa (F19).

A distinção importa para o relatório: "três fontes em série" e "duas, uma
delas vista em dois lugares" sugerem coisas diferentes sobre a arquitetura. A
segunda é a verdadeira, e é melhor notícia — significa que há um único
mecanismo a controlar, não dois.

**Estado de SC-008**: ainda NÃO satisfeito. As duas correções (F15 + F17)
estão no código e testadas, mas a medição que vale exige duas novas execuções
completas. Até lá, SC-008 permanece uma afirmação não verificada, e nenhuma
comparação antes/depois é interpretável.

**Fonte**: execuções `487eb6111036c783` e `5a4be658c01a1439` (temperature=0,
`qdocs_points=1019`, mesmo SHA); `analysis/compare.py` (36,7%); teste de
determinismo por componente; `src/qcagent/retrieval/hybrid.py::search`;
`tests/unit/test_retrieval_determinism.py`; F15; F16.

---

### F18 — O cache de respostas torna a segunda execução um replay, e o teste de reprodutibilidade vira vacuoso

**O que aconteceu**: para validar as correções de F15 e F17 antes de gastar 4
horas, rodei um piloto de 20 tarefas duas vezes. Resultado: **0% de
divergência em todas as medidas** — tentativa 1, status final, sequência
completa de erros, e `final_code` idêntico em 20/20.

Parecia confirmação perfeita. Não era. O tempo denunciou: execução 1 em 8m51s,
execução 2 em **2m24s**. Um fator de 3,7×.

`llm/base.py` mantém um cache em disco de respostas, chaveado por
`(system, prompt, seed)` (FR-028, existe para custo). Com retrieval agora
determinístico, os prompts da execução 2 eram idênticos aos da 1 → todas as
chaves bateram → **a execução 2 não chamou o modelo**. O teste provou que o
cache funciona. Sobre determinismo do pipeline, não provou nada.

**Por que isto é especialmente perverso**: o cache produz exatamente o
resultado que a hipótese prevê. Um teste de reprodutibilidade contra um cache
retorna 0% de divergência SEMPRE, por construção, inclusive num sistema
completamente não-determinístico. É um teste que não pode falhar — e um teste
que não pode falhar não é um teste.

Pior: o cache só começou a mascarar agora. Enquanto o retrieval era
não-determinístico (F17), os prompts variavam, as chaves variavam, o cache
errava, e as execuções eram genuinamente independentes. **Consertar F17 foi o
que ativou o mascaramento.** Cada correção de reprodutibilidade aproximou os
prompts, e ao ficarem idênticos o cache passou a servir tudo. O mecanismo que
invalida a medição foi ligado pela própria melhoria que a medição queria
verificar.

**O erro de método é meu e é o mesmo pela terceira vez**, com o agravante de
ter acontecido dentro do exercício desenhado para evitá-lo:

| validação | o que provei | o que concluí |
|---|---|---|
| `temperature=0` | 4 chamadas do MESMO prompt, quentes | "o gerador é determinístico" |
| ordenação RRF | 8 consultas idênticas ao retriever | "o pipeline é determinístico" |
| piloto 20×2 | 2 execuções com cache quente | "não há terceira fonte" |

Em todos os três, o teste cobria um componente e a conclusão falava do
sistema. F17 formulou essa lição explicitamente — "decompor por componente
antes de corrigir" — e eu a violei na validação seguinte.

**Consequências para o procedimento, não só para o código:**

1. **Medir SC-008 EXIGE limpar `.cache/llm` entre as duas execuções.** Sem
   isso o resultado é 0% por construção. Isto é agora parte da definição do
   critério, não uma nota de rodapé.
2. **O replay precisa ser visível no registro.** Uma execução servida por
   cache não é uma execução, e nada no `RunRecord` dizia isso. Acrescentar a
   contagem de acertos de cache torna um replay detectável por quem lê os
   dados depois, em vez de depender de alguém reparar num tempo suspeito.
   (O tempo foi o único sinal aqui, e só porque era 3,7×.)

**A lição transferível**: qualquer camada de memoização entre o experimento e
o sistema sob teste transforma "repetir o experimento" em "reler o resultado".
Caches existem para custo e são legítimos; o problema é que a mesma
propriedade que os torna úteis — resposta idêntica para entrada idêntica — é
indistinguível da propriedade que o experimento quer medir. **Um experimento
de reprodutibilidade tem de rodar com o cache frio, e o registro tem de provar
que rodou.**

**Fonte**: pilotos `6302f98e145955ed` e `f05e0b708f49a75b` (8m51s vs 2m24s,
0% divergência, cache quente); `src/qcagent/llm/base.py::generate`
(`_cache_load`); F15; F17.

---

<a id="f19"></a>

### F19 — Um teste fora do regime de produção passa independentemente de quão bom ele seja

**A generalização de F11 e F17, e a lição metodológica mais cara deste
projeto** — cobrada quatro vezes na mesma sessão, três delas depois de eu já
a ter escrito.

**O caso que a cristalizou**: para verificar que o pipeline ficara
determinístico, testei o gerador do Ollama de todas as formas que consegui
imaginar, e **todas passaram**:

| teste isolado | resultado |
|---|---|
| mesmo prompt, 4 chamadas | 4/4 idênticas |
| mesmo prompt, `temperature=0`, prompt de 18k caracteres | 4/4 idênticas |
| `num_predict` 256 e 4096 | idênticas nos dois |
| prompt-alvo intercalado com prompts longos diferentes | idêntico em todos |
| prompt-alvo depois de A, depois de B, depois de A-e-B | idêntico em todos |

Cinco testes, nenhum defeito. Conclusão razoável: o gerador é determinístico.

O piloto de 20 tarefas rodado duas vezes — cache frio, dois processos, ordem
real de tarefas — divergiu em **15% das sequências de erro e 5/20 dos códigos
gerados**. O defeito estava lá o tempo todo. Nenhum dos cinco testes o
alcançava, porque nenhum reproduzia as condições de produção.

**O padrão, que é o mesmo do bug 11**: os testes unitários de `semantic.py`
eram corretos, numerosos e verdes, sobre circuitos que nenhum gerador jamais
escreveria (sem `measure_all()`). Aqui os testes de determinismo eram
corretos, numerosos e verdes, sobre condições que nenhuma execução real
apresenta (mesmo prompt, mesmo processo, cache quente). **Em ambos os casos a
qualidade do teste era irrelevante, porque o regime estava errado.**

Daí a formulação que vale fora deste repositório:

> A cobertura de um teste é o produto de duas coisas: quão bem ele exercita o
> código, e quão perto sua entrada e seu ambiente estão dos reais. A segunda
> é um FATOR, não uma parcela. Quando ela é zero, nenhum valor da primeira
> compensa — e as ferramentas que medimos (linhas cobertas, número de casos,
> mutação) só enxergam a primeira.

**Por que erra-se sistematicamente para esse lado**: o teste isolado é o que
se consegue escrever rápido, é determinístico, roda em milissegundos e dá uma
sensação de rigor proporcional ao número de variações que se enumera. Eu
enumerei cinco variações do regime ERRADO e li a lista como profundidade. O
regime de produção é caro (14 minutos por piloto aqui) e por isso é o último
lugar onde se olha, quando deveria ser o primeiro a validar qualquer
afirmação sobre o sistema.

**A regra operacional que adoto daqui**: uma afirmação sobre o SISTEMA só é
sustentada por uma execução no regime do sistema. Testes isolados servem para
localizar e explicar um defeito já observado, e para impedir que ele volte —
não para estabelecer que ele não existe. Quando o custo do regime real é
proibitivo, a afirmação correspondente tem de sair mais fraca, não o teste
mais barato.

**O agravante honesto**: F17 já dizia "decompor por componente antes de
corrigir", e F18 já registrava o mesmo erro com o cache. Escrevi as duas e
repeti o erro na validação seguinte às duas. Isso é evidência a favor da tese
central de F11 — uma regra escrita num lugar não se propaga, nem para o código
ao lado, nem para o próprio autor na tarefa seguinte — e argumento a favor de
mecanismos em vez de lembretes: o que finalmente pegou o defeito não foi
lembrar da regra, foi um procedimento (rodar o piloto em duas execuções frias)
que a impunha.

**Quinta instância (F28, 2026-09-26)**, e a que mostra que "regime de
produção" não basta como regra: o piso de ruído zero foi medido com duas
execuções completas, frias, no ambiente real — exatamente o que esta entrada
prescreve — e ainda assim no regime errado. As duas repetiam a mesma
sequência de chamadas, então testavam "a mesma execução se repete?"; a
pergunta de que o portão e toda comparação antes/depois dependem é "uma
tarefa independe das outras?". O teste passou e a pergunta não foi feita. A
regra se refina: o regime tem de corresponder à PERGUNTA, não só ao
ambiente — e a pergunta de uma comparação envolve dois históricos
diferentes, que um replay nunca produz.

**Fonte**: cinco testes de determinismo isolados (todos verdes); pilotos
`5dfdc4d31e6d9f68` e `b2dab2cf17c16b39` (frios, 15% de divergência de
sequência, 5/20 códigos diferentes); teste do ponto de chamada do planner
(mesma assinatura, F17); bug 11; F11; F17; F18.

---

### F20 — Duas montagens do mesmo grafo divergiram sem ninguém decidir, e tornaram a inspeção manual incomparável com a suíte

**O que aconteceu**: `bench/run_single.py` (inspeção manual) e
`bench/runner.py` (suíte) montavam o MESMO grafo de oito nós, cada um por
conta própria. Descobertas ao extrair a montagem única exigida por US6:

| | `run_single.py` | `runner.py` |
|---|---|---|
| seed | **nenhum passado** → default 42 dos nós | 1, 2, 3 explícitos |
| flag de seed na CLI | **não existia** | via `config.yaml` |
| `WorkerPool` | `size=2, recycle_after=50` | `size=6` (settings) |
| `max_qubits` | `20` escrito à mão | `20` escrito à mão |
| `temperature` | não passado (default do cliente) | `settings.ollama_temperature` |

**A consequência que importa**: toda observação feita por inspeção manual
rodou com **seed 42**, que a suíte nunca executa. As duas não são
comparáveis para a mesma tarefa, e nada dizia isso. Pior: `run_single` não
tinha sequer uma flag para escolher o seed, então não havia como tornar a
observação comparável mesmo sabendo do problema.

**E o efeito é grande, não marginal.** Na última execução limpa, `ghz_3q`
tem sucesso **apenas no seed 2** e falha em 1 e 3. Uma demonstração por
`run_single` sem seed explícito falharia pelo motivo errado — não porque o
sistema não resolve GHZ, mas porque saiu num seed que não converge.

**Auditoria do que dependia disso**: a única conclusão registrada obtida por
`run_single` é "Evidência qualitativa antecipada para H1 — RAG antes/depois
em `ghz_3q`". Ela **sobrevive**, porque é uma comparação INTERNA: os dois
braços (sem RAG / com RAG) rodaram pelo mesmo caminho, com o mesmo seed 42, e
a conclusão é sobre a diferença entre eles, não sobre o nível absoluto. O que
ela não pode fazer é ser cruzada com os números da suíte para `ghz_3q` — e
isso agora está dito na própria entrada, em vez de ficar implícito.

**Por que isto não é "só um refactor"**: nenhuma das cinco diferenças foi
decidida. Todas apareceram porque duas cópias da mesma construção foram
mantidas em paralelo, e cada uma evoluiu quando alguém mexeu num lado. É F11
de novo — a regra ("o caminho de inspeção deve ser o caminho real") estava
certa e escrita no docstring do `run_single`, que diz explicitamente que
`run_task()` existe para ser reusado pela suíte "em vez de re-derivar". A
suíte re-derivou.

**Contramedida mecânica, não documental**: `tests/contract/
test_single_graph_assembly.py` falha se qualquer módulo fora de `graph.py` e
`live.py` chamar `build_graph(` (AST, não grep), e afirma que `seed` é
obrigatório e keyword-only em `build_live_graph`. Um default de seed é
exatamente o que produziu a deriva: dois chamadores discordando em silêncio
enquanto ambos pareciam corretos.

**Fonte**: `src/qcagent/live.py` (montagem única);
`tests/contract/test_single_graph_assembly.py`; execução limpa
`99960870239e97e7` (ghz_3q: seed 1 `failed_static`, seed 2 `success`, seed 3
`failed_static`); F11.

---

### F21 — Um campo gravado que nada verifica é decoração, e um documento que descreve um ambiente nunca usado é a mesma coisa

**A pergunta que expôs isto**: "se o container `app` não está rodando, onde a
suíte de 360 execuções rodou?" Resposta, verificada por comando e não por
memória: no **venv do sandbox**, `/home/agent/.venvs/qcagent/bin/python3`. O
`docker compose ps -a` — que inclui containers PARADOS — lista apenas
`qdrant`. A imagem `quantum-rag-app:latest` foi construída há cinco dias,
validada uma vez, e **nenhum container `app` jamais existiu**.

D15 declarava que o agente rodava em container. Nunca rodou. Todo número
deste projeto — baseline, as 3 h 26 min de SC-007, e o 0/360 em que a tese
mais se apoia — veio de um ambiente diferente do declarado.

**E os registros não permitiam descobrir isso.** `lib_versions` gravava
versões de pacote e nada que identificasse o ambiente: sem hostname, sem
executável, sem digest de imagem. "Onde isto rodou?" só era respondível pela
memória de quem rodou.

**O padrão geral, que é o finding**: um campo gravado sem NENHUM consumidor
que falhe em caso de divergência não protege nada — ele apenas cria a
impressão de proteção, que é pior que a ausência dela, porque quem lê o
registro conclui que aquilo foi conferido. Quatro instâncias neste projeto:

| campo | gravado desde | verificado a partir de | o que o descuido custou |
|---|---|---|---|
| `ollama` (versão) | a primeira execução | 2026-09-22 | nada ainda — um upgrade teria misturado dois sistemas em silêncio |
| `qdocs_points` | F13 | F13 (mesmo dia) | corpus encolheu de 1020 para 1019 sem aviso |
| `gpu_processor` | v1 | **nunca funcionou** | `None` em 360/360 registros, com o spec afirmando que havia um guard |
| ambiente (host, python, container) | **não existia** | 2026-09-23 | todo número do projeto obtido fora do ambiente declarado, sem rastro |

**A regra que passa a valer**: todo campo do registro é ou (a) verificado por
alguma coisa que FALHA quando diverge, ou (b) explicitamente rotulado como
descritivo. Não há terceira categoria. `gpu_stack` é o primeiro caso tratado
sob a regra nova: não é observável de dentro do contêiner, então é declarado
pelo operador e AVISA em vez de recusar — honesto porque diz o que é, em vez
de fingir verificação.

**O caso do `gpu_processor` é o mais instrutivo dos quatro**, porque o código
do guard EXISTIA. `assert_full_gpu_offload` estava escrito, testado por
ninguém, chamado por ninguém — e não teria funcionado se chamado, porque
invoca `ollama ps` e `nvidia-smi` por subprocesso, binários que vivem no host
Windows enquanto o agente só alcança o Ollama por HTTP. Um guard existente,
inalcançável, e um spec afirmando que ele abortava execuções. Agora mede por
`/api/ps` (`size_vram/size`), grava o resultado, e roda ANTES do reset de
estado — deliberadamente, porque `/api/ps` só reporta modelo carregado e o
reset descarrega: aquecer antes e descarregar depois adiciona a checagem sem
mudar o protocolo sob o qual o 0/360 foi medido.

**O que NÃO se retrata como desastre**: a razão substantiva de D15 —
`multiprocessing` com `fork` em Linux, nunca `spawn` do Windows — valeu em
todas as execuções. Verificado nos dois ambientes: ambos Linux 7.0.12, ambos
`fork`, mesmas versões de qiskit/aer/numpy/scipy. O que falhou foi o
MECANISMO descrito, não a propriedade exigida. E o 0/360 continua internamente
válido, porque as duas execuções comparadas rodaram no mesmo ambiente.

**O que fica em aberto, e é testável**: se o resultado se mantém ENTRE
ambientes. A geração não muda (os dois falam com o mesmo Ollama no host), mas
a verificação roda localmente — `Statevector`, `Operator.equiv()`, tolerâncias
— e BLAS ou despacho de CPU diferentes mexem nos últimos bits. 0/360 entre
dois ambientes genuinamente diferentes seria uma afirmação muito mais forte
que 0/360 dentro de um. É uma execução de ~3,5 h e o `compare.py` já recusa
comparar ambientes diferentes, então a comparação precisará ser feita com a
consciência de que ela cruza a fronteira de propósito.

**Consequência registrada: o baseline de 0/360 fica ÓRFÃO, por decisão.**
Acrescentar `hostname`/`python`/`platform`/`mp_start_method`/`containerized`
aos campos controlados torna as execuções `99960870239e97e7` e
`7de38e77ac071bd3` incomparáveis mecanicamente: seus registros não têm os
campos novos, e campo ausente conta como divergência (regra deliberada — uma
execução anterior ao protocolo não pode ser mostrada como tendo-o cumprido).

Resolvido por DECLARAÇÃO, não por re-execução: **o 0/360 permanece como
resultado REPORTADO, não como alvo vivo de comparação.** Está medido,
registrado e citável; o que ele não é mais é o "antes" de um `compare.py`. A
próxima execução completa da suíte estabelece a nova referência, já com
identidade de ambiente completa. Quem tentar diferenciar contra os dois runs
antigos vai receber uma recusa — e a recusa está CERTA, não é regressão. Esta
nota existe para que ninguém conclua que algo quebrou.

**Consequência 2: o guard de GPU muda o protocolo, e a equivalência é
suposta, não testada.** A sequência agora é: aquecer o modelo → verificar
offload → descarregar → execução começa a frio. A antiga era: descarregar →
execução começa a frio. Raciocinei que as duas terminam no mesmo estado
(modelo descarregado) e portanto são equivalentes, e o raciocínio parece
certo — mas "provavelmente equivalente" é exatamente o que F19 diz que
precisa ser testado, e não é porque o raciocínio é meu que ele escapa da
regra. Um ciclo aquecer/descarregar pode deixar estado residual que um
"nunca aquecido" não deixa; nada verificou isso.

**Precisão sobre o que a próxima execução testa, porque é mais estreito do
que parece**: duas execuções sob o protocolo NOVO testam que o protocolo novo
é internamente determinístico — se der 0/360 de novo, o aquecer/descarregar
não introduziu não-determinismo. Isso NÃO testa equivalência com o protocolo
antigo. Para isso seria preciso comparar uma execução nova contra uma antiga,
que é justamente o que a orfandade acima impede por mecanismo. As duas
consequências desta mudança se cruzam: a segunda pergunta tornou-se
inrespondível pela primeira. Registrado como limitação conhecida, não como
algo a contornar — se a equivalência importar depois, o caminho é reexecutar
o protocolo antigo deliberadamente, com os campos novos gravados, e comparar.

**Fonte**: `docker compose ps -a`; `sys.executable` das execuções;
`src/qcagent/config.py::environment_identity`;
`src/qcagent/llm/ollama_client.py::assert_full_gpu_offload_http`;
`bench/runner.py::verify_gpu_offload`; `tests/unit/test_gpu_offload_guard.py`;
D15 (emendada); F13; F15.

---

### F22 — "este circuito satisfaz X?" e "gere um circuito que satisfaça X" são operações diferentes, e a interface as tinha fundido

**O que aconteceu**: FR-018 pôs a distribuição de saída na tela, e com ela um
botão que transforma um resultado observado numa asserção — a rampa de entrada
para US3, porque ver o que o circuito faz é como alguém descobre o que
afirmar. Testado ponta a ponta:

    1. execução sem asserções  -> |00> 50%, |11> 50%
       rascunhos gerados       -> PROBABILITY(|00>) ~= 0.5, PROBABILITY(|11>) ~= 0.5
    2. asserções declaradas    -> failed_semantic, AMBAS violadas

Não era bug. Declarar a asserção disparava uma **geração nova**, e a segunda
produziu um circuito diferente — seis Hadamards e dois CNOTs — que
legitimamente não satisfazia asserções derivadas do primeiro. O sistema estava
certo; a interface é que prometia outra coisa.

**A confusão é conceitual, não de affordance.** São duas operações distintas:

| | "este circuito satisfaz X?" | "gere um circuito que satisfaça X" |
|---|---|---|
| objeto | artefato que EXISTE | artefato que ainda não existe |
| custo | imediato, sem LLM | minutos, geração nova |
| asserção é | uma PERGUNTA sobre o que está na tela | uma ESPECIFICAÇÃO para o que vier |
| resultado | veredito sobre aquele circuito | veredito sobre um circuito novo |

A interface só tinha a segunda, então a primeira era expressa acionando a
segunda — e o resultado só coincidia quando o gerador era confiável, que é
precisamente o regime que este projeto mediu como raro (1,7% de sucesso).
Quanto pior o gerador, mais a rampa de entrada falha, que é o oposto do que se
quer de uma rampa de entrada.

**Correção**: `/api/check` avalia asserções contra o QPY ARMAZENADO da
execução na tela. Sem LLM, sem regeneração, instantâneo. Duas exigências de
desenho, porque senão a mesma confusão volta noutra forma:

1. **As duas ações são visual e verbalmente distintas.** "Check this circuit"
   fica junto da distribuição, diz explicitamente "the circuit above", e seu
   resultado NÃO é renderizado como uma execução: sem lista de tentativas, sem
   tempo decorrido, sem painel de código. "Build circuit" continua sendo a
   geração. O botão do rascunho passou de "assert this" para "use as
   assertion" — ele agora alimenta as duas ações, e dizer qual seria mentir
   sobre a outra.
2. **Um check que passa É verificação funcional daquele circuito** com
   respeito àquelas asserções, então o relatório pode legitimamente dizer
   VERIFIED. O que ele não pode ser é ambíguo sobre QUAL circuito: o veredito
   nomeia o token da execução. Por isso o token é por execução e não "a
   última" — "a última" muda em silêncio quando há uma segunda aba aberta.

O relatório vem de `_build_guarantee_report`, o mesmo construtor da execução
normal. Um segundo construtor seria a terceira instância de F8/F10, e o que
ele divergiria seria justamente o veredito.

**Capacidade adjacente, registrada e NÃO construída**: `/api/check` é quase
toda a máquina de uma funcionalidade que o produto não tem — **verificar um
circuito que o usuário mesmo escreveu, sem geração alguma**. Falta só aceitar
código colado em vez de um token. Argumentavelmente é mais útil na prática que
a geração: o problema real de quem trabalha com Qiskit raramente é escrever o
circuito, é saber se o que escreveu faz o que ele pensa que faz. Toda a
maquinaria de verificação deste projeto — asserções, tri-estado, relatório de
garantia honesto — se aplica igual. Fica anotado como próximo passo natural,
não como escopo atual.

**O que este finding NÃO cobre, e que se revelou ao testar a correção**:
separar as duas operações resolveu a confusão sobre QUAL circuito está sendo
julgado, e criou imediatamente um problema mais fundo — uma asserção
rascunhada a partir da saída observada e checada contra aquele mesmo circuito
passa por construção. F23 trata disso, e é o achado mais forte dos dois.

**Fonte**: `src/qcagent/ui/session.py::check_stored_circuit`;
`src/qcagent/ui/app.py::check`; `tests/unit/test_check_stored_circuit.py`;
sequência observada ao vivo (50/50 -> rascunho -> failed_semantic antes,
-> VERIFIED depois); F8; F10; F23.

---

<a id="f23"></a>

### F23 — Um sistema que sugere o próprio critério de aceitação produz uma checagem que não pode falhar, e é a prestatividade que causa isso

**O resultado mais transferível deste projeto.** Não é sobre computação
quântica, nem sobre LLMs especificamente; é sobre de onde vem o critério.

**O mecanismo**: quanto mais um sistema ajuda a escrever a asserção, mais a
asserção descreve **o que o sistema fez** em vez de **o que o usuário
queria**. No limite — quando o critério é gerado inteiramente a partir da
saída observada — a checagem é uma tautologia: o artefato satisfaz o critério
porque o critério foi lido do artefato. E o modo de falha é invisível, porque
o que aparece na tela é `VERIFIED`.

A ajuda é a causa, não um efeito colateral. Uma interface que deixasse o
usuário sozinho diante de uma caixa de texto vazia não teria este problema —
teria o problema oposto (ninguém escreve asserção nenhuma, e nada é
verificado, que é exatamente o buraco que US3 existe para tapar). Os dois
extremos falham, e falham em direções opostas: **sem ajuda, nada é
verificado; com ajuda demais, tudo "verifica" e nada é verificado.**

**Evidência medida, neste sistema, ao vivo:**

    execução (sem asserções declaradas) -> completed_unverified
      distribuição observada: |00> 25%, |01> 25%, |10> 25%, |11> 25%
      rascunhos oferecidos pela interface: PROBABILITY(|00>) ~= 0.25, ... (os quatro)

    checagem com os rascunhos    -> verified=True    circular=True
    checagem com intenção escrita -> verified=False   circular=False
      (PROBABILITY(|00>) ~= 0.5 / PROBABILITY(|11>) ~= 0.5, um Bell de verdade)

O circuito estava **errado**: pedia-se um estado de Bell e produziu-se
superposição uniforme de quatro estados. A checagem contra os próprios
rascunhos devolveu VERIFIED, corretamente em relação àquelas asserções e
catastroficamente em relação ao que alguém lendo a tela concluiria. O mesmo
circuito, contra uma asserção que expressa INTENÇÃO, reprova.

**Instâncias conhecidas fora deste projeto** — é isto que torna o achado
legível para um público de engenharia de software e não só de computação
quântica:

1. **Snapshot testing.** A primeira execução grava a saída como "esperada", e
   todo teste subsequente compara contra aquilo. Se a implementação original
   estava errada, o snapshot grava o erro como especificação, e toda regressão
   *em relação ao comportamento correto* fica permanentemente invisível — o
   teste passa para sempre. Estrutura idêntica: o critério veio do artefato.
2. **Pedir a um LLM que escreva os testes do código que o mesmo LLM gerou.**
   Mesma falha, em escala, e prática comum. É o caso mais perigoso dos três
   porque PARECE verificação independente: há um artefato de código e um
   artefato de teste, escritos em momentos diferentes, em arquivos
   diferentes, e nada na aparência revela que a fonte do critério e a fonte
   do comportamento são a mesma.

   **E a mitigação que todo mundo tenta primeiro — "então use outro modelo
   para escrever os testes" — é muito mais fraca do que parece.** O erro não
   se origina no modelo; origina-se no ENUNCIADO DO REQUISITO. Um segundo
   modelo, recebendo o mesmo requisito mal formulado, erra da mesma forma:
   a ambiguidade está no texto, não na cabeça de quem o lê. Trocar de modelo
   muda a fonte do ARTEFATO sem mudar a fonte do CRITÉRIO, e é exatamente a
   segunda que precisava mudar. Dois modelos distintos lendo o mesmo
   requisito ambíguo produzem erros correlacionados pelo mesmo motivo que um
   modelo lendo-o duas vezes produz.

A versão deste projeto está entre as duas: o rascunho é derivado
mecanicamente da saída (como um snapshot), mas é oferecido como conveniência
de escrita (como o LLM que "ajuda" com os testes).

**A contramedida, na forma geral:**

> Uma checagem só é significativa quando seu critério tem uma fonte
> INDEPENDENTE do artefato checado.

Com precisão: o que precisa ser independente é a **ORIGEM do critério**, não
a identidade de quem o escreveu. Um critério não adquire independência por ser
editado levemente, por ser escrito noutra linguagem, por vir de outra execução
do mesmo modelo, nem por vir de um modelo diferente — se todos derivam do
mesmo enunciado ambíguo ou do mesmo artefato observado, a origem é uma só.

Na prática isso deixa duas fontes genuinamente independentes:

- **um humano declarando intenção** — "eu queria 50/50, não 25% em quatro" —
  que é conhecimento que não existe em lugar nenhum do artefato;
- **uma especificação escrita ANTES do artefato existir**, que não pode ter
  sido contaminada por ele, e cuja anterioridade é verificável (data de
  commit, ordem no histórico).

Vale enunciar as duas explicitamente porque a lista do que NÃO conta é longa e
contraintuitiva, e porque a primeira coisa que se tenta — trocar de modelo —
está nela.

E a contramedida operacional que este projeto adotou, porque a regra sozinha
é exatamente o tipo de coisa que se esquece no momento em que importa (F11):
**tornar a dependência detectável e declará-la na saída.** `check_stored_
circuit` devolve `circular=True` quando TODA asserção checada foi
auto-rascunhada daquela execução, e a interface diz, ali mesmo, que a
checagem passa por construção e que só o usuário pode decidir se aqueles eram
os valores desejados. Não bloqueia — bloquear destruiria a rampa de entrada
que US3 precisa — mas impede que a tautologia se apresente como verificação.

**Generalização para quem for aplicar isto noutro lugar**: se uma ferramenta
gera o critério, ela precisa registrar essa proveniência junto do veredito, e
o veredito precisa carregá-la até a tela. Um snapshot deveria dizer "este
valor foi gravado da execução N, nunca revisado por ninguém"; uma suíte
escrita por LLM deveria dizer quais testes vieram do mesmo modelo que escreveu
o código. Em todos os casos a informação existe no momento da criação e é
descartada — e é precisamente a informação sem a qual o veredito não pode ser
interpretado.

**A autoaplicação, que fecha o círculo e incomoda**: "uma especificação
escrita ANTES do artefato existir, cuja anterioridade é verificável" descreve
exatamente o que desenvolvimento orientado a especificação produz. Os FRs e
SCs de `spec.md` SÃO critérios independentes — **desde que não tenham sido
emendados depois de medir o artefato.** Dois foram.

`SC-007` passou de 3 h para 4 h depois de medir 3 h 26 min. `SC-008` foi
reescrito depois de medir divergência. As duas emendas estão argumentadas e
eu continuo achando as duas certas — o teto de 3 h era estimativa anterior a
qualquer medição, e o limiar de 5% de SC-008 conflatava coisas de naturezas
diferentes. Mas o argumento não é o ponto: **um critério emendado depois de
observar o artefato deixa de restringi-lo e passa a descrevê-lo.** É o mesmo
mecanismo do rascunho auto-gerado, numa escala mais lenta e mais respeitável.

Consequência: **a propriedade de independência é POR CRITÉRIO e POR VERSÃO,
não por documento.** "SC-007 passa" e "SC-003 passa" não são evidências do
mesmo tipo, e um relatório que os liste na mesma tabela sem distinção está
fundindo duas coisas.

A auditoria é mecânica, que é justamente a questão — a ordem dos commits a
torna verificável em vez de afirmada:

| critério | última alteração | relação com a medição | status |
|---|---|---|---|
| SC-001 … SC-006, SC-009 | `401dd58`, 2026-09-11 | anterior à primeira execução (2026-09-19) | **independente** |
| SC-007 | `a837d85`, 2026-09-23 | emendado APÓS medir 3 h 26 min | **descritivo** |
| SC-008 | `a837d85`, 2026-09-23 | reescrito APÓS medir 50%/36,7% de divergência | **descritivo** |

**O nome estabelecido disso é HARKing** (*Hypothesizing After the Results are
Known*, Kerr 1998): apresentar como *a priori* uma hipótese formulada depois
de ver os dados. O que SC-007 e SC-008 fizeram é o análogo do lado do
CRITÉRIO em vez do lado da hipótese — o limiar, e não a previsão, foi
ajustado depois da observação.

Citar a literatura aqui não é ornamento: ela já explica por que o passo parece
inócuo, e explica melhor do que eu tinha explicado. Nenhum passo isolado é
errado. Medir é certo. Descobrir que o teto era uma estimativa sem base é
certo. Corrigi-lo com justificativa registrada é certo. **A circularidade só
fica visível quando a sequência é colapsada** — e quem escreve vive a
sequência, não o colapso. É por isso que o remédio nunca é "tenha mais
cuidado": é registrar a ordem de modo que o colapso seja reconstruível por
terceiros, que é o que a ordem dos commits faz aqui.

**A simetria incômoda, e ela é sobre este trabalho:**

A contramedida padrão para HARKing é PRÉ-REGISTRO — dizer de antemão o que
contaria. Este projeto fez exatamente isso, e com rigor, **do lado das
hipóteses**:

- a predição de T090c escrita ANTES de aplicar a correção de roteamento,
  incluindo as condições de refutação — e foi refutada nos próprios termos
  que ela declarou;
- H-inc (reparo incremental) com quatro condições de falsificação nomeadas
  antes de qualquer teste, mais o risco de ancoragem registrado antes de
  medi-lo;
- F16, cuja tese É que nomear de antemão o que NÃO pode mudar é o que
  distingue ruído de resultado.

E do lado dos critérios de sucesso, a mesma disciplina não foi aplicada. A
regra existia, estava escrita, estava sendo executada com cuidado — num lado
só.

**Autoconsistência, que vale uma linha**: `circular=True` É a regra de
proveniência que a generalização acima prescreve, aplicada a este próprio
sistema — o critério carrega a informação de onde veio, e o veredito a leva
até a tela. O projeto implementou a recomendação antes de a articular, o que
importa porque mostra que a regra é **implementável**, não apenas aconselhável:
custou uma função de dez linhas, um campo no payload e um parágrafo na
interface.

**Onde entra no relatório**: capítulo de metodologia, como o achado mais
transferível do trabalho, e independente do domínio quântico. Liga-se a F16 (um
controle que dispara vale mais que uma hipótese que confirma): ambos são sobre
a diferença entre um resultado que poderia ter sido diferente e um que não
poderia.

**Fonte**: `src/qcagent/ui/session.py::_is_circular` e
`::check_stored_circuit`; `tests/unit/test_check_stored_circuit.py`
(incluindo o circuito inerte que "verifica" contra a própria inércia);
sequência medida ao vivo no container; F16; F22.

---

### F24 — `library_version="1.2.4"` estava em todos os 1.019 chunks, e o conteúdo não era da 1.2.4

**O que o campo afirmava**: todo ponto da coleção `qdocs` carrega
`library_version="1.2.4"`, e o retriever filtra por ele (`target_version`,
T035 existe para que esse filtro seja rápido). A leitura natural é "o corpus
documenta a versão que o runtime tem".

**O que o conteúdo era**: `ingest.py` raspa as páginas SEM versão da
documentação (`/api/qiskit/circuit_library`), que servem a versão MAIS
RECENTE (2.x), e carimba em cada chunk a constante `LIBRARY_VERSION`. O campo
nunca foi derivado do conteúdo nem conferido contra o runtime; foi atribuído.
Verificado contra o Qiskit instalado (1.2.4):

- **24 classes indexadas não existem no runtime** — `GraphStateGate`,
  `PhaseOracleGate`, `FullAdderGate`, `HalfAdderGate`, `AndGate`, `OrGate`,
  `MCMTGate`, `IntegerComparatorGate`, `WeightedSumGate`,
  `PauliProductRotationGate`, … — além de funções 2.x como `efficient_su2`,
  `pauli_two_design`, `excitation_preserving`, `unitary_overlap`,
  `hamiltonian_variational_ansatz`, e métodos como `QuantumCircuit.box`.
- **Um símbolo existe nas duas versões com NATUREZA diferente**:
  `qiskit.circuit.library.grover_operator` é, na 1.2.4, um **submódulo**
  (o arquivo `grover_operator.py`); na 2.x é uma **função**. O corpus
  documenta `grover_operator(oracle, state_preparation=None, ...)`. O import
  funciona, a chamada levanta `TypeError: 'module' object is not callable`.
  Idem `phase_estimation`.

**O custo medido no baseline `ce9614fa3a6f60a6`**: **27 dos 287
`failed_static` (9,4%) terminaram num erro ensinado pelo corpus** — 5
`ImportError` de símbolo 2.x, **21 dos 28 `TypeError`** (20 `grover_operator`,
1 `phase_estimation`: o modo de falha modal de `TypeError` inteiro é este) e 1
`AttributeError` (`qc.box`). Em todas as tentativas: 56 `ImportError` e 94
`'module' object is not callable`, em 28 runs. Nesses casos `retry_retrieval`
não é só ineficaz: **é a causa**, e repeti-lo reapresenta a mesma página.
Amostrados também os 12 `QiskitError` finais (rótulo de Pauli `"Z0"`,
dimensão de `StatePreparation`, norma de amplitude, formas incompatíveis):
**nenhum** corresponde a uso documentado na 2.x — são erros do modelo. Idem
`GR`/`GRZ` sem `phi` (a assinatura no corpus é a mesma da 1.2.4) e
`cu1`/`cu3`/`cphase` (removidos na 1.0; memória do pré-treino, não do corpus).

**A versão fixada estava disponível o tempo todo**: a documentação expõe
URLs versionadas (`/docs/en/api/qiskit/1.2/...`, 200). O índice
`1.2/circuit_library` lista 126 páginas da biblioteca e **nenhuma** de
`GraphStateGate`, `PhaseOracleGate` ou `grover_operator`;
`1.2/qiskit.circuit.library.grover_operator` responde 404. A correção real é
raspar a versão fixada, não filtrar a 2.x — um filtro de importabilidade
deixaria passar `grover_operator` (importável, natureza errada) e qualquer
mudança de assinatura, e seria mitigação parcial.

**Por que é o mesmo defeito de F21, e não um descuido de ingestão**: o campo
foi GRAVADO, nada o CONFERIU, e ele AFIRMAVA algo sobre a origem do conteúdo
que o conteúdo não sustentava. T033 ("adicionar metadados `library_version`")
está marcada como feita e está feita — o campo existe. O que nunca existiu foi
a pergunta "este chunk é mesmo da 1.2.4?". Um filtro por um campo não
verificado é pior que nenhum filtro: dá ao retriever, e a quem lê o código, a
garantia de que a versão está controlada. É F8 no nível do corpus: um campo
estruturado dizendo o contrário da realidade, e todo o resto confiando no
campo.

**Contramedida**: (1) ingestão a partir das URLs `/1.2/`; (2) o campo passa a
ser CHECADO na ingestão — todo símbolo de topo indexado precisa resolver no
runtime fixado para um objeto do tipo documentado (classe/função, não
submódulo), e falha aborta a ingestão em vez de pular (F13: tolerância
silenciosa sobre a variável independente do trabalho); (3) M1 (`recall@8`)
reavaliado, como D17 exige a cada mudança significativa do corpus.

**Fonte**: coleção `qdocs` (1.019 pontos, payloads extraídos 2026-09-25);
`src/qcagent/retrieval/ingest.py` (`LIBRARY_VERSION`, `_INDEX_PAGES`);
runtime `~/.venvs/qcagent`, qiskit 1.2.4; baseline `ce9614fa3a6f60a6`; F8;
F13; F21.

---

### F25 — Retrieval não entrega conhecimento negativo: 104 dos 112 "símbolos inexistentes" nunca existiram, e nenhuma página diz isso

**A leitura anterior** (baseline, F14): as duas linhas de 39% dos
`failed_static` eram OPOSTAS — `NameError` sobre símbolo existente
(retrieval não acrescenta um `import`) e `ImportError` sobre símbolo
inexistente, "onde `retry_retrieval` é a ação certa, mais documentação pode
corrigir". A correção de T090c separou a primeira e deixou a segunda roteada
para retrieval.

**Verificado símbolo a símbolo** (112 runs cuja última tentativa foi
`ImportError`, contra o runtime 1.2.4 e contra o corpus):

| classe | runs | exemplos |
|---|---|---|
| **nunca existiu** em versão nenhuma do Qiskit | **104 (92,9%)** | `H` 26, `RZ` 24, `CNOTGate` 20, `CNOT` 12, `RY` 7, `Hadamard` 7 |
| ensinado pelo corpus 2.x (F24) | 5 (4,5%) | `GraphStateGate`, `PhaseOracleGate` |
| existe, módulo/natureza errados | 2 | `SparsePauliOp` de `circuit.library`; `initialize` |
| **removido** — o caso `u3` | **1 (0,9%)** | `PauliSumOp` |

Sobre todas as 570 tentativas com `ImportError` (36 símbolos): 499 (87,5%)
nunca existiram, 56 (9,8%) vieram do corpus, 12 eram o módulo errado, 2
removidos.

**Por que retrieval não podia corrigir**: o caso `u3` funcionou porque `u3`
EXISTIU e foi removido — há uma página que diz "removido, use `circuit.u()`",
e retrieval tem uma correção para encontrar. `H` nunca existiu; **o corpus
documenta o que existe, não o que não existe**, e nenhuma página contradiz
`from qiskit.circuit.library import H`. A informação necessária — "`H` não é
um símbolo deste módulo; `HGate` é" — é conhecimento negativo, e um corpus de
documentação não o contém por construção.

**A consequência medida**: depois de uma tentativa falhar num símbolo
inventado, a tentativa seguinte importa **o mesmo símbolo de novo em 60%**
das transições no baseline, e entre 58% e 68% nas seis execuções completas
existentes (`ce9614fa`, `6cf69f6a`, `487eb611`, `5a4be658`, `7de38e77`,
`99960870`). A linha de 39% de "símbolo inexistente" foi roteada, antes e
depois de T090c, para uma ação que em ~99% dos casos não tinha correção a
oferecer — a mesma falha estrutural que T090c consertou na outra linha, não
identificada nesta.

**Correção a uma hipótese que eu havia levantado**: supus que a consulta de
retrieval derivava do símbolo ausente, fazendo de `H` uma consulta patológica
de um caractere. Não deriva: `retriever.py::_build_query_text` concatena
enunciado, requisitos e o `retrieval_hint` do crítico. O que o crítico
efetivamente escreveu no hint não é verificável — ver F27.

**A saída de desenho**: derivar a correção do RUNTIME em vez de esperar que a
documentação a contenha — o mecanismo de `u3` generalizado, e o de
`MissingImport` (T090c) estendido. A fonte de verdade é o namespace do Qiskit
instalado, nunca a lista de símbolos indexada (F24: ela contém símbolos que o
runtime não tem). Protótipo sobre os 36 símbolos observados: resolve **105
dos 112 runs (94%)** e 524 das 570 tentativas (92%) com três regras
determinísticas — tabela de aliases (F26), sufixo `Gate`, normalização de
caixa/sublinhado. Os não resolvidos (`HamiltonianVariationalAnsatz`,
`PhaseExp`, `PauliSumOp`, …) não têm equivalente na 1.2.4.

**Sobre a taxonomia**: a divisão que importa não é "inventado vs obsoleto" —
obsoleto já tem categoria (`DeprecatedAPI`) e mecanismo próprios, e
distinguir inventado de removido exigiria o histórico de versões, que não está
indexado, para separar 104 de 1. A divisão é pela AÇÃO disponível: há um
símbolo real próximo no runtime (correção determinística, `retry_generation`)
ou não há (`HallucinatedSymbol`, retrieval como hoje).

**Fonte**: baseline `ce9614fa3a6f60a6`; as seis execuções completas acima;
`src/qcagent/validators/static.py::_importable_symbols`;
`src/qcagent/nodes/retriever.py`; "Exemplo trabalhado: o caso `u3`"; F3; F14;
F24.

---

### F26 — Os símbolos inventados não são aleatórios: são o vocabulário do PennyLane aplicado ao Qiskit

**O padrão**: dos 499 `ImportError` sobre símbolo que nunca existiu no Qiskit
(todas as tentativas do baseline), conferidos contra o PennyLane 0.38
instalado no mesmo venv:

| origem do nome | tentativas | símbolos |
|---|---|---|
| **nome EXATO de operação do PennyLane** | **261 (52%)** | `RZ` 118, `CNOT` 48, `Hadamard` 44, `RY` 36, `PauliZ` 9, `X` 4, `PauliX` 1, `RX` 1 |
| nome do PennyLane + sufixo `Gate` do Qiskit | 94 (19%) | `CNOTGate` 85, `HadamardGate` 5, `PauliZGate` 2, `ToffoliGate` 2 |
| `H` — não é nome do PennyLane 0.38 | 121 (24%) | provavelmente o método `qc.h` em maiúscula, ou notação de livro-texto |
| outros | 23 (5%) | `HamiltonianVariationalAnsatz`, `CU3`, `PhaseExp`, … |

**71% dos símbolos inventados são a nomenclatura de outro framework**, às
vezes híbrida com a convenção do Qiskit (`CNOTGate` = nome do PennyLane com o
sufixo do Qiskit). Não é alucinação no sentido de nome sem origem: é
**transferência de vocabulário entre bibliotecas do mesmo domínio**, vinda do
pré-treino — o PennyLane não está no corpus (`source` ∈ {`qiskit_api`,
`migration_guide`}).

**Por que isto importa para a correção**: explica por que uma tabela curta de
aliases resolve o que busca aproximada não resolveria. `difflib` entre
`Hadamard` e `HGate` não acha nada; entre `CNOT` e `CXGate`, também não — os
nomes não são grafias próximas, são NOMES DE OUTRO SISTEMA para o mesmo
objeto. A tabela é um mapeamento entre vocabulários, e é pequena porque o
vocabulário de portas é pequeno.

**Por que importa fora deste projeto**: num domínio com vários frameworks
concorrentes para as mesmas operações, o erro dominante de um gerador de código
não é inventar — é confundir qual framework está escrevendo. Isso sugere uma
classe de mitigação que retrieval não oferece: fixar o vocabulário do
framework-alvo no prompt, ou traduzir entre vocabulários na validação.

**O que NÃO está estabelecido**: a atribuição é por coincidência de nome, não
por evidência causal. `RZ`/`RY`/`X` também são notação de livro-texto, e parte
dos 52% pode vir daí; o que separa as hipóteses é `Hadamard` e `PauliZ`, que
não são notação de livro-texto e são nomes exatos do PennyLane. `H` (24%) é a
exceção que o padrão não explica, e está registrado como tal.

**Fonte**: baseline `ce9614fa3a6f60a6`; `pennylane` 0.38.0 no venv
`qcagent`; F25.

---

### F27 — O trace de cada run é acumulado e descartado, e era exatamente o que o diagnóstico de F25 precisava

**O que aconteceu**: para saber se `retry_retrieval` falhou em corrigir `H`
por falta de conteúdo ou por consulta ruim, era preciso ver o que o crítico
pediu (`retrieval_hint`) e o que o retriever devolveu. Nada disso existe nos
resultados. `AgentState.trace` acumula, a cada nó, a consulta enviada, o
número de chunks e as decisões — e `RunRecord` (`bench/schema.py`) persiste
24 campos, nenhum deles o trace, a `CriticDecision`, o hint ou os ids dos
chunks recuperados. Ao fim do run, tudo isso é descartado.

**Consequência**: o diagnóstico post-hoc do comportamento de retrieval é
IMPOSSÍVEL em qualquer run já feito — incluindo os 2.160 das seis execuções completas. A hipótese "a consulta
derivada de `H` é patológica" só pôde ser corrigida lendo o código do
retriever; se verificá-la exigisse dado, não haveria como. F25 se apoia no
conteúdo do corpus, não no comportamento observado do retriever, por falta de
escolha.

**A ironia**: o próprio código já enuncia a regra — em `state.py`, sobre
`ErrorRecord`: *"a failure mode that only appears in a trace nobody persists
is a failure mode nobody measures."* Ela foi aplicada aos erros do planner e
não ao trace inteiro. É F11 mais uma vez (regra enunciada sobre uma instância
não se propaga) e F21 numa forma nova: F21 era informação gravada e nunca
checada; esta é informação **coletada e jogada fora** — o dado existiu em
memória durante o run e nunca chegou ao disco.

**Contramedida (barata)**: persistir o trace no `RunRecord`, ou no mínimo, por
iteração, a `CriticDecision` (ação, `rationale`, `retrieval_hint`) e os
`doc_id` dos chunks recuperados. O custo é espaço em disco; não há custo de
LLM nem de tempo de execução.

**Fonte**: `src/qcagent/state.py` (`trace`, comentário de `ErrorRecord`);
`bench/schema.py::RunRecord`; `src/qcagent/nodes/retriever.py`; F11; F21;
F25.

---

### F28 — O piso de ruído zero media REPLAY, não independência: a saída de uma tarefa depende da tarefa que rodou antes dela

**Como apareceu**: antes de reindexar o corpus (T111), uma checagem de
premissa — o piso zero tinha sido medido com Ollama 0.34.1, o host agora roda
0.34.4. Seis runs de S0 (`f5a69657457574a3`) repetidos a frio
(`4c19589509bcf833`, config só com `dj_constant_4q` e
`qaoa_maxcut_4q_perturbed`): `dj_constant_4q` saiu **byte-idêntico nos 3
seeds, trace incluído**; `qaoa_maxcut_4q_perturbed` divergiu **nos 3**, e 2
viraram de `success` para `failed_static`.

**Onde diverge** (o trace persistido por T112 permitiu achar em minutos): no
PRIMEIRO passo, o planner, cujo prompt é só o enunciado, mesmo seed,
`temperature=0`. Uma execução escreveu `gate_set = ["Hadamard", ...]`, a
outra `["H", ...]`.

**A causa, isolada**: a mesma tarefa rodada SOZINHA, duas vezes, cada uma
depois do unload do modelo → **idêntica nas duas**, e igual ao planner de S0.
Precedida de `dj_constant_4q` no mesmo estado de servidor → diferente.
`bench/runner.py::reset_generator_state` descarrega o modelo **uma vez por
execução da suíte**, não por (tarefa, seed); a partir daí, o cache interno de
prompt/KV do Ollama carrega estado de uma tarefa para a seguinte, e esse
estado muda a resposta. A docstring da função já descrevia o mecanismo entre
EXECUÇÕES ("the second inherits the first's cache"); ele age igualmente entre
TAREFAS dentro de uma execução.

**O que isso faz com o piso de ruído zero** (runs `99960870`/`7de38e77`):
aquelas duas execuções tinham a mesma ordem de tarefas e o mesmo histórico de
chamadas, então reproduziram o mesmo estado de servidor em cada ponto. O zero
mediu **determinismo de replay** — mesma história, mesma saída — e não que o
resultado de uma tarefa independe das outras. O número está certo; a leitura
"o sistema é determinístico, diferenças entre braços dispensam estimativa de
ruído" estava errada, e foi escrita por mim na predição de T111/T113.

**Por que isto é mais grave que ruído**: ruído se cancela; isto não. Qualquer
intervenção que mude o prompt da tarefa k muda o estado herdado pela tarefa
k+1, que muda sem ter sido tocada. Em S0→S1 o corpus novo altera o contexto
de TODAS as tarefas, então o estrato B — o controle — se moveria por efeito
do estrato A, e o controle dispararia sem que nada nele tivesse mudado. É o
mesmo desenho de falha de F15 (um parâmetro implícito do servidor) e de F18
(uma memoização entre o experimento e o sistema), agora com a unidade de
análise errada: a suíte trata (tarefa, seed) como independentes, e não são.

**Consequências**:
1. Toda comparação por tarefa entre execuções com qualquer diferença de
   prompt — incluindo T090c (`ce9614fa` → `6cf69f6a`) — está confundida por
   contaminação cruzada, além do ruído de F15 já registrado.
2. S0 (`f5a69657`) não serve como braço de comparação: precisa ser refeito
   sob a mesma política de reset que S1 e S2 usarem.
3. SC-008 e o portão de T101b: o piso "zero" vale para replays da mesma
   configuração, não para comparações antes/depois — que é o uso do portão.

**É a quinta instância de F19.** A checagem de piso zero foi feita num regime
— replay de uma sequência de chamadas idêntica — que não correspondia à
pergunta que importava, que era se as tarefas são independentes. O teste
passou, e a pergunta não foi feita. Diferente das quatro anteriores, aqui o
teste era caro, completo e no ambiente de produção; o regime errado não era
o ambiente, era a HISTÓRIA de chamadas, que as duas execuções compartilhavam
por construção.

**A contramedida disponível**: unload por (tarefa, seed), para que cada run
dependa só da própria história. Custa um carregamento de modelo por run
(segundos; +5-10 min no subconjunto de 48, +30-60 min na suíte de 360 — o
que pesa contra o teto de 4 h de SC-007). Muda o que a suíte mede e o seu
custo, então não é decidida unilateralmente.

**Decidido e validado (2026-09-26)**: `reset_per_run: true`, padrão em
`RunConfig` e em `config.yaml` — para a suíte inteira, não só para o
experimento, porque o argumento do estrato B vale para o produto: o portão de
`compare.py` existe para localizar uma regressão numa tarefa, e sob
contaminação uma mudança real na tarefa 3 se espalha para 4..120. **Checagem
de independência**: as mesmas 6 (tarefa, seed) em duas ordens — tarefas
invertidas E seeds invertidos, cache de disco frio em cada ordem
(`75ffb6d1b523bbe8`, `3692b5d527adc945`) — saíram **6/6 byte-idênticas,
trace incluído**. Sob o protocolo novo, o resultado de uma (tarefa, seed) não
depende da ordem. É n=6: suficiente para mostrar que o mecanismo foi
removido, não para afirmar independência sobre 360.

**Observação lateral, não conclusão**: sob reset por run, os 3 seeds de cada
uma das 2 tarefas produziram o MESMO `final_code`. No S0 antigo,
`qaoa_maxcut_4q_perturbed` tinha o seed 1 falhando e os seeds 2 e 3 com
sucesso; agora os três têm sucesso, idênticos. Se isso se sustentar, a
diferença entre seeds medida em "Os seeds NÃO são redundantes" era em boa
parte história, não seed — e os 3 seeds seriam em boa parte redundantes sob
o protocolo novo. Duas tarefas não sustentam isso; o S0 refeito (16 tarefas
× 3 seeds) mede.

**Proveniência imperfeita, registrada**: as duas execuções da checagem
gravaram `git_sha=41517c1`, commit que NÃO continha o código de reset que
elas rodaram (estava no working tree, commitado depois em `7d0468f`).
`git_sha()` não detectava árvore suja; passou a marcar `-dirty` (`aca59d2`) —
F21 aplicado à proveniência.

**Fonte**: `results/f5a69657457574a3` (S0), `results/4c19589509bcf833`
(checagem), duas execuções isoladas de `qaoa_maxcut_4q_perturbed`
(2026-09-26); `bench/runner.py::reset_generator_state`; "PISO DE RUÍDO
DE REPLAY MEDIDO: ZERO"; F15; F18; F19.

---

### F16 — Um controle que dispara vale mais que uma hipótese que confirma

**O achado mais transferível deste projeto, e não é sobre computação
quântica nem sobre laços de reparo.**

**O que aconteceu**: antes de corrigir o roteamento de `MissingImport`, a
predição registrada declarou duas métricas como CONTROLES — `compila@1` e
`verificado@1` — com a razão explícita: ambas medem a TENTATIVA 1, que
acontece antes de existir qualquer roteamento, logo nenhuma mudança no
crítico pode movê-las. Com seeds fixos, prompt e corpus idênticos, tinham de
voltar iguais.

`compila@1` voltou **10,9% → 15,6%**.

Um aumento de 43% relativo. Na direção certa. Numa métrica de compilação,
logo após uma correção que faz exatamente código compilar. **É um resultado
publicável, e é falso.** A correção atua em tentativas ≥2; a métrica mede a
tentativa 1. Não havia mecanismo causal possível.

O que o salto realmente media era ruído de amostragem não declarado (F15):
26,1% das duplas (tarefa, seed) produziram tentativa 1 diferente entre as
duas execuções.

**Por que isso teria entrado no relatório**: todos os filtros normais de
qualidade falhariam. O número veio de um pipeline testado (405 testes), sobre
360 runs, com identificação completa de ambiente registrada, produzido por
uma ferramenta de métricas com teste de mutação. A revisão de código não
pegaria — não há bug. A revisão estatística não pegaria — a diferença é real
nos dados. O tamanho de amostra não ajudaria: mais runs estimariam o número
errado com mais precisão. **A única coisa que separou ruído de resultado foi
ter escrito ANTES qual número não podia se mover.**

**A assimetria que dá o título**: uma hipótese confirmada é compatível com o
experimento estar certo E com o experimento estar quebrado de um jeito que
por acaso produz o padrão esperado — F6 é exatamente isso, e ocorreu duas
vezes neste projeto. Um controle que dispara não tem essa ambiguidade: ele
afirma que algo mudou que NÃO PODIA mudar, e isso é falso sob qualquer
interpretação em que o experimento esteja íntegro. Confirmação é evidência
fraca sobre a validade do instrumento; um controle violado é evidência forte,
e negativa, e imediata.

Daí a regra prática, que é a contribuição metodológica: **ao registrar uma
predição, nomear separadamente o que DEVE mudar e o que NÃO PODE mudar.** A
segunda lista custa uma frase e é a que detecta instrumento quebrado. Uma
predição só com efeitos esperados pode ser confirmada por um experimento
inválido; uma com controles, não.

**Corolário sobre escolher controles**: os dois que funcionaram aqui não
foram escolhidos por intuição, e sim por ARGUMENTO ESTRUTURAL — "a tentativa
1 ocorre antes do roteamento existir" é uma afirmação sobre a ordem de
execução do sistema, verificável lendo o código, independente dos dados. Um
controle escolhido assim é forte. Um escolhido por "isto provavelmente não
muda muito" é só mais uma métrica.

**Segundo uso, não antecipado**: um controle violado CALIBRA o ruído. O salto
de 4,7 pontos em `compila@1` estabelece o piso: nenhum efeito menor que isso
é distinguível de ruído com n=360 nesta configuração. Isso reclassificou
automaticamente a queda de sucesso (1,8% → 1,1%) como indistinguível, e
deixou de pé apenas a refutação sobre MAX_ITER (98,8% → 98,9%), onde o efeito
previsto era grande e o observado é zero.

**Onde entra no relatório**: capítulo de metodologia, como afirmação
independente do domínio — vale para qualquer avaliação empírica de sistema
com LLM no laço, onde a tentação de reportar a métrica que se moveu na
direção certa é estrutural, e onde a não-determinismo do gerador garante que
alguma métrica sempre terá se movido. É uma afirmação mais forte e mais
transferível que qualquer coisa que este projeto diga sobre laços de reparo.

**Fonte**: predição registrada em T090c (escrita antes da correção);
execuções `ce9614fa3a6f60a6` e `6cf69f6ab7f3d2c0`; F15 (causa do ruído); F6
(o modo de falha simétrico, do lado da confirmação); F14.

---

## Measured results

Todo número citável, como foi obtido, e ressalva relevante.

### PREDIÇÃO REGISTRADA ANTES DA CORREÇÃO (T090c) — para poder estar errada

Escrita **antes** de aplicar a correção de roteamento e antes de rodar a
suíte de novo. O ponto de registrar é que a execução seguinte seja um TESTE e
não uma confirmação: um resultado previsto por escrito pode ser refutado, um
resultado interpretado depois do fato não pode.

**Hipótese**: o que determina se um laço de reparo converge é a QUALIDADE DO
DIAGNÓSTICO, não o orçamento de iterações. 112 runs gastaram 5 iterações numa
ação (`retry_retrieval`) que não pode acrescentar uma linha de `import`.

**Controles — devem ficar IGUAIS, e se mudarem a comparação está contaminada:**

| métrica | baseline | por que não pode se mover |
|---|---|---|
| `compila@1` | 10,9% | mede a tentativa 1, que acontece ANTES de existir qualquer roteamento — não há histórico de erro ainda |
| `verificado@1` | 0,0% | conta sucessos com `iterations==1`; os 6 sucessos levaram 2,2,3,3,5,5 |

Com seeds fixos, prompt do gerador inalterado e MESMO índice
(`qdocs_points=1019`, F13 — **não reingerir antes da execução seguinte**), a
tentativa 1 é determinística. Estes dois números voltando diferentes significa
que algo não intencional mudou, não que a correção funcionou.

**Efeitos esperados (previsão do orientador, registrada como dele):**

1. queda substancial do tempo de parede, bem abaixo de 2 h 45 min, porque as
   falhas deixam de custar 5 iterações cada;
2. convergência em 1-2 iterações para a classe corrigida;
3. o sistema passar a ALCANÇAR verificação funcional com frequência — hoje
   quase nunca chega lá, então ainda não se sabe se o gerador acerta a física.

**Correção de minha parte à formulação de (3)**: `verificado@1` não pode medir
isso (é controle, acima). A métrica correta é **quantos runs alcançam um
veredito semântico**, e a física do gerador é a taxa de aprovação CONDICIONAL
a chegar lá:

| métrica de tratamento | baseline | previsão |
|---|---|---|
| alcançou veredito semântico | 50/341 = **14,7%** | sobe muito; é o denominador que a correção destrava |
| aprovados dentre os que chegaram | 6/50 = **12,0%** | **se mantiver ~12% com denominador maior, a física do gerador é a próxima parede** |
| taxa de sucesso | 1,8% | sobe, mas limitada por 12% acima |
| iterações até sucesso (média) | 3,33 | cai |
| esgotou MAX_ITER | 331/335 = 98,8% | cai muito; é o indicador mais direto da hipótese |
| tempo de parede | 165 min | cai |

**O que refutaria a hipótese**, explicitamente:

- `esgotou MAX_ITER` continuar perto de 98% depois da correção — significaria
  que a classe corrigida não era o gargalo e que o laço não converge por outro
  motivo;
- `alcançou veredito semântico` subir pouco — significaria que resolver o
  import só revela o erro seguinte, e que os 39% de "símbolo inexistente"
  dominam assim que os imports saem do caminho;
- tempo de parede não cair — significaria que o custo estava em outro lugar
  que não as iterações desperdiçadas.

O terceiro cenário é o mais informativo se ocorrer: seria evidência de que
`max_iter=5` é gasto de qualquer forma, por qualquer causa, e que o problema
não é roteamento e sim que o gerador não melhora com feedback nenhum.

---

### RESULTADO DA PREDIÇÃO — REFUTADA (T090c, execução `6cf69f6ab7f3d2c0`, 2026-09-20)

A predição registrada acima foi escrita antes da correção justamente para
poder estar errada. **Está.** Registrado como medido.

| métrica | antes | depois | predição | veredito |
|---|---|---|---|---|
| esgotou MAX_ITER | 98,8% | **98,9%** | "cai muito" | **REFUTADA** |
| alcançou veredito semântico | 14,7% | **15,0%** | "sobe muito" | **REFUTADA** |
| taxa de sucesso | 1,8% | **1,1%** | "sobe" | refutada (caiu, dentro do ruído) |
| aprovados dentre os que chegaram | 12,0% | 7,4% | "~12% se física for a parede" | inconclusivo (n=54) |
| tempo de parede | 165 min | 108 min | "cai" | **CONFUNDIDO** — cache quente (F18); ver correção abaixo |
| `harness_error` | 19 | **1** | — | corrigidos bugs 17/19/20 |
| `compila@1` (CONTROLE) | 10,9% | **15,6%** | "não pode mudar" | **CONTROLE DISPAROU — ver F15** |

O classificador funciona mecanicamente: **374 diagnósticos `MissingImport`**
na execução depois, contra 0 antes. A ação mudou, a dica passou a nomear a
linha exata, e nada disso moveu a convergência.

**As duas condições de refutação que eu mesmo escrevi se realizaram**, nas
palavras registradas antes do fato: "esgotou MAX_ITER continuar perto de 98%
— significaria que a classe corrigida não era o gargalo", e "alcançou
veredito semântico subir pouco — significaria que resolver o import só revela
o erro seguinte". Ambas.

**Por que eu esperava outra coisa, e o erro de método que cometi**: um smoke
de 4 runs depois da correção mostrou 1 sucesso e 2 chegando ao semântico
(contra 0 antes), e eu li aquilo como confirmação antecipada. Quatro runs.
Com o ruído medido depois (F15), quatro runs não distinguem nada. É F6 outra
vez — reconhecer o padrão esperado e tomar o reconhecimento por evidência —
e desta vez no papel de quem coleta o dado, não de quem o interpreta.

**O que o resultado permite afirmar mesmo com o ruído de F15**: o efeito
previsto era GRANDE (MAX_ITER cairia "muito"), e o observado é ZERO (98,8 →
98,9). Ruído de poucos pontos não mascara um efeito grande. A refutação do
ponto principal é sólida, ainda que as diferenças pequenas (sucesso 1,8 vs
1,1) sejam indistinguíveis de ruído.

**O que sobrevive como ganho real** — e aqui preciso RETIRAR parte de uma
afirmação anterior:

- **19 → 1 `harness_error`** (bugs 17/19/20). Este é estrutural: são defeitos
  corrigidos, não amostragem.
- **−34% de tempo de parede (165 → 108 min): CONFUNDIDO, retirado como
  evidência.** Eu atribuí a queda a pular a chamada de LLM do crítico em 374
  reparos determinísticos, e afirmei que era "estrutural, não amostral". Não
  é. O cache de respostas em disco (F18) não foi limpo entre as duas
  execuções, e os prompts que as duas compartilham exatamente — **as ~360
  chamadas do planner (prompt = só o enunciado, idêntico por construção) e as
  ~360 chamadas de geração da tentativa 1** — eram acertos de cache na
  execução "depois". São ~720 de ~3.900 chamadas de LLM, ~18%, servidas do
  disco em vez de geradas.

  A medida que expôs isto foi a execução de piso de ruído, com cache
  deliberadamente frio: **~31 s por run contra 18-21 s das execuções
  anteriores**. As execuções anteriores eram mais rápidas porque eram
  parcialmente replay, não porque o sistema ficou mais rápido.

  O que sobra de verdadeiro: pular a chamada do crítico em `MissingImport`
  economiza uma chamada real por ocorrência, e isso é um ganho genuíno de
  desenho. Sua MAGNITUDE é desconhecida, porque a única medição que existe
  está contaminada. Não vai para o relatório como número.

  Registro isto explicitamente porque era a única linha da tabela de T090c
  que eu tinha marcado como CONFIRMADA, e porque o erro é o mesmo de F16 na
  direção oposta: lá, um número que não podia se mover moveu e eu quase o
  celebrei; aqui, um número que se moveu por um motivo que eu não havia
  considerado, e que eu chamei de estrutural sem ter checado o cache.
- **19 → 1 `harness_error`** (bugs 17/19/20).

**A explicação rival que os dados agora favorecem**: nem (a) "roteamento é o
gargalo" nem exatamente (b) "o gerador não melhora com feedback". O histórico
de erros de um run típico depois da correção mostra o mecanismo:

    MissingImport, WrongGateDecomposition, WrongGateDecomposition, MissingImport

O modelo acrescenta o import quando avisado, compila, falha no semântico,
recebe dica semântica, **regenera do zero e perde o import de novo**. O laço
oscila entre dois modos de falha, consertando um ao quebrar o outro. A causa
é de desenho e é anterior a qualquer roteamento: cada tentativa é uma geração
nova que recebe os dois últimos ERROS mas não as partes que já funcionavam da
tentativa anterior. Antes da correção isso era invisível, porque nada passava
do estático.

Isso NÃO estava nas duas hipóteses de F14 e é a contribuição real desta
execução: **o laço não acumula progresso**. Roteamento correto é necessário e
não suficiente; o que falta é o reparo ser incremental em vez de
regenerativo. Fica como a próxima hipótese a testar, não como conclusão —
uma execução, com o ruído de F15 ainda no lugar.

---

### PREDIÇÃO REGISTRADA — reparo incremental (T090d), escrita antes de qualquer teste

Mesma disciplina de T090c, pelo mesmo motivo: o padrão de oscilação é
convincente, e é exatamente por isso que precisa de uma forma declarada de
estar errado. F6 já aconteceu duas vezes neste projeto — uma na correção de
`GATES_SUBSET_OF`, outra quando li um smoke de 4 runs como confirmação
antecipada de T090c. Não há terceira.

**Observação que motiva a hipótese** (execução `6cf69f6ab7f3d2c0`, histórico
de erros típico de um run depois da correção de roteamento):

    MissingImport, WrongGateDecomposition, WrongGateDecomposition, MissingImport

O modelo acrescenta o import quando avisado, compila, falha no semântico,
recebe dica semântica, regenera e **perde o import de novo**.

**Hipótese (H-inc)**: o laço não converge porque cada tentativa é uma geração
NOVA. O gerador recebe os dois últimos ERROS, mas nunca o artefato que já
funcionava parcialmente. Reparo regenerativo desfaz progresso; reparo
incremental (editar o código anterior) não.

**Intervenção a testar**: passar ao gerador o CÓDIGO da tentativa anterior
junto do erro, com instrução de EDITAR em vez de reescrever.

**O que medir, e o que cada resultado significa:**

| métrica | valor atual | H-inc prevê |
|---|---|---|
| reincidência do mesmo `error_type` após ter sido resolvido | a medir (é a assinatura da oscilação) | **cai para perto de zero** |
| esgotou MAX_ITER | 98,9% | cai substancialmente |
| alcançou veredito semântico | 15,0% | sobe |
| taxa de sucesso | 1,1% | sobe |
| `compila@1` (CONTROLE) | — | **não pode mudar**: a tentativa 1 não tem código anterior para editar |

A métrica primária é a **primeira linha**, não a taxa de sucesso: ela mede o
mecanismo proposto diretamente. Sucesso depende também da física, que H-inc
não afirma corrigir.

**Condições de refutação, declaradas antes:**

1. **A reincidência não cair.** Se o mesmo erro resolvido volta na mesma
   proporção mesmo com o código anterior no prompt, o problema não é falta de
   contexto — é o modelo não conseguir editar cirurgicamente, e H-inc está
   errada na sua premissa causal.
2. **Reincidência cair e MAX_ITER não cair.** Significaria que a oscilação era
   real mas não era o gargalo: o laço para por outro motivo, e consertar a
   oscilação só troca qual erro fica pendente no fim.
3. **Sucesso subir sem a reincidência cair.** Seria efeito de outra coisa
   (mais contexto ajuda de modo difuso), não do mecanismo proposto — e eu
   deveria dizer isso, não creditar H-inc.
4. **`compila@1` mudar.** Contaminação, como em F15: a tentativa 1 não tem
   tentativa anterior, logo não pode ser afetada.

**Risco conhecido da intervenção, registrado antes de medi-lo**: mostrar o
código anterior pode ancorar o modelo num desenho errado, impedindo o
abandono de uma abordagem ruim. Isso apareceria como reincidência baixa E
sucesso estagnado — casos que param de oscilar mas convergem para algo
errado. É um resultado distinto de (1) e (2) e deve ser reportado como tal,
não como ruído.

**Pré-condição**: só é mensurável depois de SC-008 e do piso de ruído reais
(F15). Com 26,1% de divergência na tentativa 1, nenhuma das linhas acima é
interpretável.

---

### PISO DE RUÍDO DE REPLAY MEDIDO: ZERO — 0/360 idênticos sob sequência de chamadas fixa (runs `99960870239e97e7` e `7de38e77ac071bd3`, 2026-09-22)

> **Corrigido em 2026-09-26 (F28).** Título original: "PISO DE RUÍDO MEDIDO:
> ZERO. O sistema é determinístico". O que foi mostrado é **0/360
> replay-idênticos sob uma sequência de chamadas fixa**: as duas execuções
> tinham a mesma ordem de tarefas e, portanto, o mesmo histórico de estado no
> servidor em cada ponto. Continua sendo um resultado forte — poucos sistemas
> com LLM no laço podem afirmá-lo. O que a redação original implicava, e que
> NUNCA foi medido, é que o resultado de uma (tarefa, seed) independe das
> demais. Não independe: com o unload feito uma vez por suíte, o cache de
> prompt/KV do Ollama leva estado de uma tarefa para a seguinte e muda a
> saída a `temperature=0` (F28). As afirmações abaixo que dependiam da
> independência estão marcadas no próprio lugar.

**Duas execuções completas, mesmo código, mesmo corpus, cache frio nas duas.
Divergência em TODAS as medidas: 0.**

| medida | divergência | IC 95% |
|---|---|---|
| status por (tarefa, seed) | **0/360 = 0,0%** | [0,0%, 1,1%] |
| classificação da tentativa 1 | **0/360 = 0,0%** | [0,0%, 1,1%] |
| `final_code` byte a byte | **0/360 = 0,0%** | [0,0%, 1,1%] |
| sequência completa de erros | **0/360 = 0,0%** | [0,0%, 1,1%] |
| vetor de resultado por tarefa | **0/120 = 0,0%** | [0,0%, 3,1%] |
| pares discordantes (McNemar) | **0** | — |

**SC-008a (camada determinística): APROVADO.** 360 pares com `final_code`
byte-idêntico, 0 vereditos discordantes.

**SC-008b (piso do gerador): o piso é ZERO**, com o limite superior do IC em
1,1% por (tarefa, seed) — não se prova zero eterno com 360 amostras, mas
observou-se 0/360.

**Verificação anti-replay (exigida por F18)**: ambas as execuções levaram
~205 min e limparam `.cache/llm` antes de começar. Uma execução servida por
cache levou 2 min 24 s quando medida em F18. As duas pagaram geração completa.

**Eu estava errado, e é a terceira posição que tomo nesta questão.** A
sequência, registrada porque o erro do meio é instrutivo:

1. *"Igualdade exata é o critério certo"* — premissa: toda fonte encontrada
   era defeito nosso. Correto por acidente.
2. *"Igualdade exata é inatingível; o estado do servidor de inferência não é
   controlável por configuração"* — **errado**, e errado pelo motivo exato
   que F19 descreve. Concluí "não controlável" de sondas isoladas (prompt
   repetido, carga/descarga do modelo, prompts intercalados). Nenhuma delas
   era o regime de produção. Escrevi F19 e violei F19 na conclusão seguinte.
3. *"É controlável, e o sistema é determinístico"* — medido no regime de
   produção, 0/360. **[Corrigido, F28: o que se mediu é replay-identidade
   sob sequência fixa. Era o regime de produção para a pergunta "a mesma
   execução se repete?", e não para "uma tarefa independe das outras?" — a
   que o portão e toda comparação antes/depois fazem. Quarta posição,
   portanto, e a mesma lição de F19.]**

O que tornou (2) falso foi um protocolo, não uma descoberta: descarregar o
modelo antes da execução e fixar `keep_alive` para impedir recarga no meio.
O estado interno do motor não é imprevisível; é apenas **herdado**, e herdado
é exatamente o que D10b, F15 e F17 já mandavam nunca fazer. A regra que
faltava aplicar era a mesma, pela quarta vez, agora ao estado do processo
servidor em vez de a um parâmetro da requisição.

**Consequência para o portão (T101b): a proposta de McNemar fica
DESNECESSÁRIA e é retirada.** Ela existia para tolerar um piso de ruído que
não existe. Com piso zero, o portão original de `compare.py` está correto
como está: qualquer mudança por tarefa É uma mudança real, e sair com código
1 numa regressão não gera falso positivo nenhum. A camada estatística seria
complexidade paga para resolver um problema medido como inexistente.

> **Retirada condicionada (F28).** A premissa era "o piso é zero"; o zero é de
> replay. Uma comparação antes/depois muda prompts, e sob contaminação entre
> tarefas uma mudança real na tarefa k se espalha para k+1..N — o diff por
> tarefa vira mancha em vez de ponto, e a função do portão (localizar a
> regressão numa tarefa) falha. Com `reset_per_run` (padrão desde F28), a
> retirada volta a valer SE a independência for medida; até essa medição,
> T101b não está resolvida.

O que o portão PRECISA ganhar, em vez disso, é a garantia de que as duas
execuções comparadas foram produzidas sob o protocolo que torna o zero
válido: recusar a comparação quando `lib_versions` divergir nos campos
controlados (`ollama_temperature`, `qdocs_points`, `generator_state`,
`ollama_num_ctx`). Sem isso o zero vira convenção, e uma invariante que
depende de todo mundo lembrar do protocolo será quebrada — o mesmo argumento
de F8/F10, aplicado à comparação em vez de ao veredito.

**O que isto destrava**: a comparação antes/depois de T090c pode ser refeita
com validade. Todos os deltas pequenos declarados ininterpretáveis em
"Threats to validity" tornam-se mensuráveis — não porque o ruído foi
estimado, mas porque foi ELIMINADO. **[Corrigido, F28: só sob
`reset_per_run`. Refazer T090c no protocolo antigo reproduziria a
contaminação cruzada, porque a correção muda os prompts.]**

---

### Os seeds NÃO são redundantes sob `temperature=0` — e isso decide SC-007

**Hipótese testada** (proposta pelo orientador): se `temperature=0` é argmax,
o seed não deveria ter efeito; os três seeds por tarefa produziriam saída
idêntica, dois terços dos 360 runs seriam custo puro, a suíte cairia para
~69 min e SC-007 passaria sem perder cobertura.

**Refutada, com o mesmo número nas duas execuções:**

| dentro de UMA execução, ao longo dos 3 seeds | run A | run B |
|---|---|---|
| `final_code` idêntico entre seeds | 41/120 = 34,2% | 41/120 = 34,2% |
| status idêntico entre seeds | 98/120 = 81,7% | 98/120 = 81,7% |
| sequência de erros idêntica | 63/120 = 52,5% | 63/120 = 52,5% |

Em ~66% das tarefas os três seeds produzem CÓDIGO DIFERENTE. O Ollama usa o
seed mesmo com `temperature=0` — a decodificação não é argmax puro. E o
efeito é **determinístico**: run A e run B concordam nos três números e nas
mesmas tarefas, o que confirma que seed é uma entrada reprodutível do
sistema, não ruído.

> **Confundido (F28).** Os seeds 1, 2 e 3 de uma tarefa rodaram em
> sequência sobre o mesmo estado de servidor: o seed 2 herdava a história do
> seed 1. Parte da diferença entre seeds pode ser história, não seed. A
> concordância entre run A e run B é replay e não separa as duas causas. A
> checagem de independência com ordem de seeds invertida sob `reset_per_run`
> separa.

**O que a dimensão de seed compra (run A):**

| | com 3 seeds | só seed 1 | retido |
|---|---|---|---|
| tarefas com sucesso em ≥1 seed | 4 | 2 | **50%** |
| tarefas alcançando veredito semântico | 40 | 30 | **75%** |

Dois dos quatro sucessos — `ghz_3q` e `qaoa_maxcut_4q_perturbed` — só
existem nos seeds 2 ou 3. Cortar seeds não remove custo redundante; remove
metade da evidência de sucesso.

**Portanto SC-007 não se resolve por corte de seeds, e a decisão vai para o
teto.**

### Emenda a SC-007: teto de 4 h, derivado de medição em vez de estimativa

**Decisão**: o teto passa de 3 h para **4 h**, com a medição a frio (3 h 26
min) registrada como referência.

**Razão**: o número 3 h foi escrito antes de qualquer execução existir — era
uma estimativa, e as únicas medições que pareciam confirmá-la (2 h 45 min)
estavam contaminadas por cache quente (F18). O propósito do teto é o
Princípio III: a suíte tem de ser barata o bastante para ser rodada com
frequência. 3 h 26 min para 360 gerações completas com verificação satisfaz
esse propósito — é uma execução noturna, que é exatamente o regime para o
qual a suíte foi desenhada.

Duas condições tornam a emenda honesta em vez de conveniente:

1. **Não se corta cobertura para caber num número.** Foi o que a checagem de
   seeds testou, e cortar custaria 50% dos sucessos. O teto cede porque o
   custo é real e a cobertura vale mais que o número.
2. **O teto emendado é folga medida, não aspiração.** 4 h dá ~16% de margem
   sobre 3 h 26 min, o suficiente para variação de hardware sem esconder uma
   regressão de desempenho — se a suíte passar de 4 h, algo mudou de verdade.

**Alternativa rejeitada — paralelizar por tarefa**: o `WorkerPool` suporta
(D1b), mas execuções concorrentes compartilham o servidor Ollama, cujo estado
interno acabou de se revelar determinante para a saída (F19). O zero medido
depende de uma execução sequencial com estado resetado. Paralelizar trocaria
reprodutibilidade — o resultado mais forte deste projeto — por 90 min de
parede. Moeda errada.

---

### Segunda emenda a SC-007 — por PROTOCOLO, não por medição (F28, 2026-09-26)

**O que muda**: o protocolo sob o qual SC-007 é medido, não o teto. A suíte
passa a rodar com `reset_per_run: true` — unload do modelo antes de cada
(tarefa, seed).

**Por que isto NÃO é a mesma manobra da primeira emenda, duas vezes**: a
primeira ajustou um LIMIAR a uma MEDIÇÃO — 3 h virou 4 h depois de medir 3 h
26 min — e F23 já a classifica como descritiva: ela descreve o sistema, não o
restringe. Esta segunda muda o PROTOCOLO por uma razão substantiva e anterior
a qualquer número: sem reset por run, a saída de uma tarefa depende da
anterior (F28), e o portão de `compare.py` não consegue localizar uma
regressão — a função pela qual a suíte existe. O custo é uma CONSEQUÊNCIA
aceita do protocolo, não o motivo da mudança. Se o custo tivesse de caber no
teto, o teto seria reajustado outra vez — e seria a mesma manobra. Por isso:

**O teto de 4 h NÃO é reajustado ao custo do reset.** Medido na checagem de
independência: ~3 s de espera fixa após o pedido de unload, mais ~3,5 s de
recarga do modelo na primeira chamada de cada run — **~6-7 s por run, ~+40
min sobre 360 runs**, o que coloca a suíte em torno de **4 h 05 min** e
provavelmente REPROVA SC-007 por poucos minutos. Se reprovar, é reportado
como reprovado, com a causa. Duas saídas legítimas existem e nenhuma é mexer
no teto: (1) substituir a espera fixa de 3 s por uma consulta ao estado do
servidor (`/api/ps`) até o descarregamento se confirmar — engenharia, não
critério; (2) se o S0 refeito confirmar que os seeds são redundantes sob o
protocolo novo (F28, observação lateral), a pergunta sobre o número de seeds
é reaberta com dados que a primeira emenda não tinha. A segunda é decisão
de escopo e não é tomada aqui.

**Status F23**: SC-007 continua descritivo pela primeira emenda; esta não o
agrava nem o repete, porque não toca o limiar.

---

### SC-007 REPROVADO a frio, e a primeira execução limpa (run A, `99960870239e97e7`, 2026-09-22)

**O número honesto de SC-007: 205 min 47 s (3 h 26 min) contra o teto de
3 h — REPROVADO por 14%.**

O "2 h 45 min, aprovado com 15 min de margem" registrado no baseline media um
sistema parcialmente em replay: o cache de respostas em disco nunca fora limpo
(F18), e ~18% das chamadas de LLM eram servidas do disco. A margem de 15 min
era o cache. Esta é a primeira execução COMPLETA e FRIA da suíte, e o ritmo
sobe de 18-21 s para 33,4 s por run.

**Primeira execução sem nenhum defeito nosso**: `harness_error = 0` em 360
runs, contra 19 no baseline. Bugs 17, 19, 20 e 21 confirmados corrigidos sob
carga real — incluindo os caminhos de ansatz parametrizado, que sozinhos
custavam 15 crashes. O denominador é 360, sem nada excluído, pela primeira
vez.

**Condições, todas registradas em `lib_versions` do próprio arquivo:**
`temperature=0`, ordenação de RRF determinística, cache de respostas FRIO,
estado do servidor de inferência resetado antes da execução
(`generator_state=reset_before_run`), corpus fixo em `qdocs_points=1019`,
mesmo SHA.

| métrica | run A (limpa) | baseline (confundida) |
|---|---|---|
| tempo de parede | **205,8 min (REPROVA SC-007)** | 165,1 min (cache quente) |
| `harness_error` | **0** | 19 |
| denominador | **360** | 341 |
| sucesso | 6 (1,7%) | 6 (1,8%) |
| `failed_semantic` | **76** | 44 |
| `failed_static` | 278 | 287 |
| `compila@1` | 16,7% | 10,9% |
| `verificado@1` | **0,0%** | 0,0% |

**`verificado@1 = 0,0%` sobre 360 runs limpos** é agora um zero robusto no
sentido forte: execução sem exclusões, sem defeitos nossos, sem replay.

**O que NÃO se afirma aqui**: `failed_semantic` subiu de 44 para 76 enquanto
`failed_static` caiu — mais runs alcançando verificação funcional, que é a
direção que a correção de `MissingImport` deveria produzir. **Não é reportado
como efeito.** É exatamente para decidir se um deslocamento de 32 runs excede
o ruído que a execução B existe; creditar agora seria F16 outra vez, com o
controle já construído e ignorado.

**Consequência para T102**: SC-007 reprovado exige a decisão que a própria
tarefa previa — paralelizar por tarefa (o `WorkerPool` suporta, D1b) ou
reduzir seeds. Não decidida unilateralmente: muda o que a suíte mede. Ver
"Open questions".

---

### PREDIÇÃO REGISTRADA — corpus na versão fixada (T111), depois corretor de símbolo (T113), medidos SEPARADAMENTE — escrita antes de qualquer teste (2026-09-26)

**Por que em duas etapas e medidas entre elas**: as duas intervenções atuam no
mesmo caminho, e o corretor consertaria erros que o corpus criou. Medidas
juntas, o efeito do corretor sairia inflado e nenhuma das duas teria efeito
atribuível. Ordem: corpus primeiro (remove a causa), corretor depois (trata o
que o corpus não pode conter, F25).

**Subconjunto, não a suíte**: a métrica de mecanismo não precisa das 120
tarefas. 16 tarefas × 3 seeds = 48 runs (~25 min a frio, contra 3 h 26 min),
em dois estratos tirados da execução `99960870239e97e7`:

- **Estrato A — erros ensinados pelo corpus** (8): `dj_constant_4q`,
  `dj_constant_4q_perturbed`, `dj_balanced_4q`, `simon_6q_perturbed`,
  `grover_3q`, `grover_4q`, `ising_weighted_maxcut_4q`,
  `ising_field_coupling_4q_perturbed`.
- **Estrato B — só símbolos inventados** (8): `bell_phi_plus_2q`, `ghz_5q`,
  `qft_5q`, `w_state_5q`, `qpe_4q`, `bv_4q`, `reversible_half_adder_4q`,
  `qaoa_maxcut_4q_perturbed`.

O piso de ruído medido é zero (runs `99960870`/`7de38e77`), então diferenças
entre braços no mesmo subconjunto não precisam de estimativa de ruído. Três
braços: **S0** (código e corpus atuais), **S1** (corpus 1.2), **S2** (corpus
1.2 + corretor). A suíte completa roda uma vez, depois de S2, só para o número
ponta a ponta.

> **Emenda de protocolo (2026-09-26), texto registrado acima mantido como
> escrito.** (1) A frase sobre o piso zero estava errada: o zero é de replay
> (F28), e sem reset por run o estrato B se moveria por efeito do estrato A.
> Os três braços rodam com `reset_per_run: true`; o S0 original
> (`f5a69657`) foi descartado como braço e é refeito sob o mesmo protocolo,
> ANTES de qualquer mudança no corpus. Métricas, estratos, previsões e
> condições de refutação não mudam. (2) A suíte completa deixa de ser parte
> da sequência: roda se houver tempo, é reportada à parte, e nada é
> condicionado a ela — a própria predição diz que o número ponta a ponta
> provavelmente não se move, e o corpus é corrigido porque está errado, não
> porque o efeito foi medido.

**Métricas**: (m1) taxa de erros ensinados pelo corpus — `ImportError` de
símbolo ausente no runtime mas presente no corpus antigo, mais
`'module' object is not callable`, mais `AttributeError` de método 2.x;
(m2) **taxa de repetição do mesmo símbolo** — fração das transições
`ImportError(s)` → tentativa seguinte que importa `s` de novo; (m3)
`compila@1`; (m4) sucesso e `esgotou MAX_ITER`.

| métrica | S0 → S1 (corpus) prevê | S1 → S2 (corretor) prevê |
|---|---|---|
| m1, estrato A | **cai para ~0** | já ~0; não pode subir |
| m2, estrato B | **não muda** (CONTROLE: o corpus não contém nem contradiz `H`) | **cai para perto de zero** |
| m2, estrato A | cai (sai a contribuição do corpus) | cai no que restar |
| `compila@1` | pode mudar (a tentativa 1 lê o corpus novo) | **não pode mudar** (CONTROLE: o corretor atua em tentativas ≥ 2) |
| sucesso / `esgotou MAX_ITER` | move pouco | **move pouco — ver abaixo** |

**Por que o sucesso ponta a ponta provavelmente NÃO se move, declarado
antes**: o precedente direto é `MissingImport` (T090c). Aquela correção estava
certa — a classe estava mal roteada, a ação nova era a certa — e
`esgotou MAX_ITER` foi de 98,8% para 98,9%. Dois mecanismos já medidos
explicam, e os dois se aplicam aqui: (1) resolver um erro estático só revela o
seguinte, e o seguinte costuma ser semântico; (2) o reparo é REGENERATIVO — o
reparo incremental (T090d) não foi implementado — e o histórico
`MissingImport, WrongGateDecomposition, WrongGateDecomposition, MissingImport`
mostra o modelo perdendo, ao regenerar, a correção que tinha acabado de
aplicar. Um `HGate` corrigido na tentativa 2 pode voltar a `H` na tentativa
4. Se isso acontecer, m2 cai menos do que o previsto, e a causa é a
oscilação, não o corretor — o que é distinguível olhando se a reincidência é
imediata (corretor falhou) ou após uma tentativa limpa (oscilação).

**Condições de refutação:**

1. **m1 não cair no estrato A em S1** — o corpus não era a causa desses
   erros, e F24 superestima seu custo.
2. **m2 cair no estrato B em S1** — o controle disparou: algo além do corpus
   mudou entre S0 e S1 (F15/F18), e a comparação S0→S1 está contaminada.
3. **m2 não cair no estrato B em S2** — o modelo não obedece a uma correção
   explícita de símbolo, e a premissa do corretor (a informação faltante era
   o nome) está errada.
4. **`compila@1` mudar entre S1 e S2** — contaminação, como em F15.
5. **sucesso subir substancialmente em S2** — não refuta nada, mas contraria
   o precedente de `MissingImport`, e a explicação teria de ser procurada
   antes de ser creditada ao corretor (F6).

---

### BASELINE — primeira execução completa da suíte ao vivo (T102, 2026-09-19)

**Este é o ponto de referência do Princípio III**: o número contra o qual toda
mudança futura é medida. Registrado como medido, sem nenhuma correção aplicada
depois de observá-lo — inclusive os defeitos nossos que ele expôs.

Identificação (do próprio `runs.jsonl`, não de anotação à mão):

| campo | valor |
|---|---|
| `run_id` | `ce9614fa3a6f60a6` |
| `git_sha` | `3ef5c217` |
| modelo | `qwen2.5-coder:7b`, 100% GPU confirmado antes da largada |
| `qdocs_points` | 1019 (ver F13 — corpus não reprodutível; comparações exigem este número igual) |
| qiskit / langgraph / fastembed | 1.2.4 / 0.2.76 / 0.3.6 |
| configuração | 120 tarefas × 3 seeds (1,2,3), `max_iter=5` |

**SC-007: aprovado NESTA MEDIÇÃO, mas a medição está contaminada.** 165 min
03 s (2 h 45 min) de parede contra o teto de 3 h, incluindo os 2 min 54 s da
pré-condição do Princípio IV. Margem de 15 min.

**Ressalva descoberta depois, e é séria**: esta execução rodou com o cache de
respostas em disco parcialmente quente (F18) — havia smokes e pilotos antes
dela. A primeira execução com cache DELIBERADAMENTE frio anda a ~31 s por run
contra os 18-21 s das execuções anteriores, o que projeta ~3,1 h. Ou seja
**SC-007 pode falhar com cache frio**, e o "aprovado" acima mede um sistema
parcialmente em replay. A execução de piso de ruído (D20) é a primeira
completa e fria e vai dar o número honesto. Até então, o tempo de parede de
QUALQUER execução registrada antes dela não é citável.

A margem de 15 min, lida assim, não era folga: era o cache.

**Distribuição por tier** (runs; `completed_unverified` e `aborted` foram zero
em todos os tiers e estão omitidos):

| tier | success | failed_semantic | failed_static | rejected_input | harness_error | total |
|---|---|---|---|---|---|---|
| t1 | 4 | 13 | 87 | 1 | 3 | 108 |
| t2 | 1 | 10 | 93 | 2 | 2 | 108 |
| t3 | 0 | 10 | 54 | 1 | 7 | 72 |
| t4 | 1 | 11 | 53 | 0 | 7 | 72 |
| **todos** | **6** | **44** | **287** | **4** | **19** | **360** |

**Taxas** (denominador = 341 "attempted", exclui os 19 `harness_error`):

| métrica | valor |
|---|---|
| taxa de sucesso | 1,8% |
| sucesso por tier | t1 3,8% · t2 0,9% · t3 0,0% · t4 1,5% |
| compila@1 | 10,9% |
| verificado@1 | **0,0%** |
| `completed_unverified` | 0,0% |
| iterações até sucesso (média) | 3,33 |
| latência média por run | 26,8 s |
| custo | US$ 0 (gerador local, D10) |

**MAX_ITER contra outros modos de falha** — o número mais informativo da
execução inteira:

- **331 das 335 falhas esgotaram as 5 iterações.**
- As outras 4 são `rejected_input`, que nem chega a gerar.
- Ou seja: **quando o laço de reparo entra, ele praticamente nunca sai por
  sucesso** — sai por esgotamento. Combinado com `verificado@1 = 0,0%`, o laço
  não está resgatando casos difíceis; está gastando cinco chamadas de LLM para
  chegar ao mesmo lugar. Cada falha custa o máximo possível, o que é também a
  explicação direta de por que SC-007 ficou apertado.

**Por que `failed_static` (287 runs = 84% dos attempted), classificado pelo
erro da ÚLTIMA tentativa:**

| causa | runs | % dos failed_static |
|---|---|---|
| **import faltando** (`NameError` sobre símbolo que EXISTE em Qiskit/numpy) | **112** | **39,0%** |
| símbolo inexistente (`ImportError`/`ModuleNotFoundError`) | 112 | 39,0% |
| `TypeError` | 28 | 9,8% |
| `QiskitError` | 12 | 4,2% |
| `CircuitError` | 11 | 3,8% |
| `AttributeError` | 5 | 1,7% |
| resto (ValueError, símbolo obsoleto, timeout, sintaxe) | 7 | 2,4% |

O import faltando é estável entre tiers — 46,0% / 36,6% / 33,3% / 37,7% dos
`failed_static` de t1/t2/t3/t4 — ou seja, não é artefato de uma família de
tarefa.

**A distinção que importa e que o roteamento não fazia**: as duas linhas de
39% parecem a mesma coisa e são opostas. `ImportError: cannot import name
'CNOTGate'` é símbolo que NÃO EXISTE — `retry_retrieval` é a ação certa, mais
documentação pode corrigir. `NameError: name 'QuantumCircuit' is not defined`
é símbolo que EXISTE e só não foi importado — **nenhuma quantidade de
documentação recuperada acrescenta uma linha de `import`**. Os dois estavam
classificados como `HallucinatedSymbol` e roteados para `retry_retrieval`,
então 112 runs gastaram cinco iterações numa ação que estruturalmente não
podia resolver a falha. É F3 no laço de reparo: o diagnóstico manda o modelo
por um caminho que não endereça o problema.

**Nossos próprios defeitos, contados à parte (19 runs, 5,3%)** — o baseline
NÃO é limpo, e `analysis/metrics.py` diz isso antes de qualquer taxa:

| bug | runs | o quê |
|---|---|---|
| 19 | 15 | `ParameterExpression` não ligado levanta `TypeError`, fora do `except QiskitError` |
| 17 | 3 | `_parse_hint_response` sem tratamento de JSON malformado |
| 20 | 1 | `NonUnitaryCircuit` emitido mas ausente de `_RETRY_GENERATION_ERRORS` |

Concentrados em t3/t4 (7 e 7 de 72) porque é lá que vivem os ansätze
parametrizados (VQE/QAOA/QUBO), que disparam o bug 19.

**Ressalvas para citar junto do número:**

1. `qdocs_points=1019`, não 1020 — uma página caiu por 503 na ingestão (F13).
   Comparação com outra execução exige este campo igual.
2. 19 runs não mediram o sistema, mediram bugs nossos. As taxas acima têm
   denominador 341, e os 19 aparecem separados, nunca diluídos.
3. `verificado@1 = 0,0%` sobre 341 runs é um zero real, não ausência de dado.
4. Fidelidade média sai `n/a`: nenhum oráculo distribucional chegou a rodar,
   consequência de 84% parar em `failed_static`.


### Gerador local — benchmark de throughput (2026-08-12, RTX 3070 8 GB)

| | qwen2.5-coder:7b | qwen3-coder:30b |
|---|---|---|
| Tamanho | 4,7 GB | 19 GB |
| Processor (`ollama ps`) | **100% GPU** | 67%/33% CPU/GPU |
| Prefill | **492 tok/s** | 36 tok/s |
| Geração | **74,7 tok/s** | 14,1 tok/s |
| Por chamada C5 (~5k in / 400 out) | ~15,6 s | ~167 s |
| Braço local extrapolado (1.800 exec. × 2,5 chamadas) | **~20 h** | **~209 h** |

O 30B fica ~10× fora do orçamento contra a meta de 72 h da matriz completa
— **rejeitado por tempo de execução, não por qualidade**, distinção que
deve constar no relatório (D10).

**Ressalva — artefato de aquecimento**: a primeira medição do 7B deu **8
tok/s** de prefill e sugeriu falsamente execução em CPU. Causa:
`load_duration` de 23 s contaminando o número (modelo ainda não quente em
VRAM). Toda medição de throughput citada neste relatório exige
aquecimento prévio confirmado — o número acima (492 tok/s) é pós-aquecimento.
Registrar esse artefato explicitamente na seção de metodologia experimental
como um cuidado de medição, não só como nota de rodapé.

**Fonte**: `research.md` D10; `estado-e-aprendizados.md` §4.

### WorkerPool — amortização do custo de `import qiskit`

Medido via `scripts/bench_pool.py`, 20 submits sequenciais, um único
worker, dentro do container Linux (D15/fork):

| | wall_time_s | exec_time_s | overhead_s |
|---|---|---|---|
| submit #1 | **1,5829** | 0,0011 | 1,5818 |
| submits #2–20 (média) | **0,0007** | 0,0005 | 0,0002 |

Extrapolado para as ~27.000 chamadas da matriz completa (5.400 execuções
base × até ~5 tentativas): pagar 1,58 s por chamada custaria **~11,9 h**
contra a meta de 72 h — exatamente o custo que o pool existe para evitar.

**Ressalva**: este resultado depende de `fork` (Linux/container) e NÃO vale
sob `spawn` nativo do Windows — razão estrutural (não só de conveniência)
por trás de D15 exigir que desenvolvimento e matriz experimental rodem
sempre no mesmo ambiente containerizado.

**Fonte**: `research.md` D1b.

### Retrieval — recall@8 e MRR, evolução ao longo da expansão do corpus

| Etapa | chunks | recall@8 | MRR | Nota |
|---|---|---|---|---|
| Piloto (corpus pequeno) | 186 | 0,9000 | 0,657 | validação de mecanismo, não previsão de escala |
| Corpus expandido, antes de qualquer correção | 1.020 | **0,7302** | 0,5300 | M1 (≥0,85) FALHA aqui |
| + prefixo de registro (`[class]`/`[method]`/`[migration]`) | 1.020 | **0,7619** | 0,5336 | ganho real do prefixo: modesto |
| + correção de ground truth (`also_correct`) | 1.020 | **0,9524** | 0,7275 | M1 PASSA |

**Decomposição por tipo de consulta, número final** (`make eval-retrieval`,
1.020 chunks, prefixo + gabarito corrigido):

| query_type | n | recall@8 | MRR |
|---|---|---|---|
| exact_identifier | 13 | 1,0000 | 0,9487 |
| intent_phrasing | 50 | 0,9400 | 0,6700 |

**Ressalva importante para o relatório**: a maior parte da queda aparente
de 0,90 para 0,73 NÃO era degradação real do sistema de recuperação — era
subestimação do gabarito de avaliação. Checagem sistemática (não por
amostragem) contra os 44 alvos `intent_phrasing` do tipo
`QuantumCircuit.<método>` mostrou que **26 de 44 (59%)** tinham um chunk
irmão `[class]` legitimamente correto (ex.: `RXGate` para a consulta
"rotate about X axis", quando o gabarito só reconhecia
`QuantumCircuit.rx`) que o corpus pequeno original nunca continha como
distrator — o gabarito nunca precisou distinguir os dois até o corpus
crescer. O ganho REAL atribuível ao prefixo de registro (isolando o efeito
da correção de gabarito) foi de **0,7302 → 0,7619** — os dois efeitos
precisam ser reportados separadamente, nunca como um número único.

**Falsos negativos genuínos remanescentes** (2 de 50, não explicados por
ambiguidade de gabarito): "rotate about X axis" retorna
`Quaternion.from_axis_rotation` no topo em vez de `QuantumCircuit.rx`/
`RXGate`; "rotate about Y axis" retorna `RZXGate`. Ambos defeitos genuínos
do ramo denso, candidatos a exemplo qualitativo na seção de limitações.

**Fonte**: `research.md` D17, D17-1.

### Exemplo trabalhado, NÃO medição: o caso `u3` como lacuna de corpus rastreada

**Nenhum tamanho de efeito é afirmado a partir daqui, e a razão é dupla.** O
que segue é um MECANISMO rastreado, com a causa identificada e a correção
verificada — não uma medição de quanto o RAG ajuda.

Duas execuções da mesma tarefa (`bench/tasks/t1_primitives/ghz_3q.json`),
antes e depois de a recuperação estar ativa:

- **Sem RAG**: três de quatro falhas eram API inexistente —
  `qiskit.extensions` (removido no Qiskit 1.0), `cx_decompose` e `u3`
  (nunca existiram como método de `QuantumCircuit`).
- **Com RAG**: zero erros de `DeprecatedAPI` em cinco tentativas. Nenhum
  dos três símbolos reapareceu.

O caso do `u3` é o mais forte dos três, porque a CAUSA é rastreável, não só
correlação: confirmado como lacuna de CORPUS (o texto de correção `u3 → u`
não estava no índice na primeira ingestão — verificado por busca de texto
direta), corrigido na ingestão seguinte (`_GATE_DEPRECATED_RE`/
`_GATE_REPLACEMENT_METHOD_RE` em `chunking.py` passaram a marcar
`deprecated=True, replacement="QuantumCircuit.u()"`), e não voltou a
aparecer depois da correção.

**Por que a contagem "3 de 4 falhas" e "zero em cinco tentativas" NÃO é um
efeito medido** (revisto em 2026-09-23, depois de F15/F19/F20):

1. **As execuções são anteriores à correção de F15.** `temperature` não
   estava fixada, logo os dois braços rodaram no regime em que duas execuções
   idênticas divergiam em 26% das saídas da tentativa 1. Não é só que o seed
   diferia do da suíte — **os dois lados da comparação eram
   não-determinísticos**.
2. **n = 1**: uma tarefa, um seed, num sistema que agora sabemos oscilar
   fortemente entre seeds — `ghz_3q` converge só no seed 2 e falha em 1 e 3.

Meu argumento anterior de que "a comparação interna sobrevive" vale para o
DESENHO (os dois braços usaram o mesmo caminho) e não para o PODER
ESTATÍSTICO. Com n=1 sob não-determinismo, a diferença observada é compatível
com variação sozinha. Apresentar isso como evidência de magnitude seria usar
uma medição fora do regime em que ela foi obtida — precisamente o erro que
F19 nomeia, cometido no próprio documento que o registra.

**O que sobrevive, e é forte**: o caso `u3` tem CAUSA IDENTIFICADA, não
correlação. Foi confirmado como lacuna de corpus por busca direta no índice
(o texto de correção `u3 → u` não estava lá), corrigido na ingestão seguinte
com a mudança nomeada em `chunking.py`, e não reapareceu depois. Isso é um
mecanismo demonstrado ponta a ponta: sintoma → causa no corpus → correção →
desaparecimento do sintoma. Vale no relatório como EXEMPLO TRABALHADO de como
uma falha de RAG se diagnostica, e é independente de qualquer tamanho de
efeito.

**A versão medida ficou barata e está disponível** (não feita aqui; a
interface tem prioridade): a suíte é replay-idêntica (0/360 sob sequência
de chamadas fixa), `analysis/compare.py` já faz comparação por tarefa com
recusa quando as condições diferem, e o nó de recuperação pode ser
desligado. Duas execuções completas sob o protocolo controlado dariam o
efeito do RAG com o mesmo rigor que qualquer outro número deste projeto.
**[Corrigido, F28: "qualquer diferença observada seria real" exige
`reset_per_run`; desligar o retrieval muda todos os prompts, e no protocolo
antigo cada tarefa carregaria o efeito das anteriores.]**

**Fonte**: `estado-e-aprendizados.md` §5 — este achado NÃO está registrado
em `research.md`; recuperado do único outro documento de estado do projeto
ao escrever este arquivo.

---

## Threats to validity

Tudo que limita o que pode ser afirmado a partir deste desenho experimental.

- **Todo tempo de parede registrado antes da execução de piso é inválido
  (F18).** O cache de respostas em disco nunca foi limpo entre execuções, e
  as chamadas com prompt idêntico (planner de toda tarefa, geração da
  tentativa 1) eram servidas do disco: ~720 de ~3.900 chamadas, ~18%. Medido
  a frio, o ritmo é ~31 s/run contra 18-21 s antes. Consequências: o ganho de
  −34% atribuído à correção de roteamento foi retirado, e **SC-007 pode
  falhar a frio** — o "2 h 45 min" tinha 15 min de margem que eram o cache.
- **Dois critérios de sucesso foram emendados DEPOIS de medir, e por isso
  descrevem o sistema em vez de restringi-lo (F23).** A independência de um
  critério é por critério e por versão, não por documento:
  - **SC-001 a SC-006 e SC-009**: alterados pela última vez em `401dd58`
    (2026-09-11), antes da primeira execução completa (2026-09-19). São
    critérios independentes no sentido forte — foram escritos sem conhecer o
    artefato, e a anterioridade é checável na ordem dos commits.
  - **SC-007**: teto passou de 3 h para 4 h em `a837d85` (2026-09-23), depois
    de medir 3 h 26 min. A emenda é argumentada (o 3 h era estimativa anterior
    a qualquer medição, e as medições que pareciam cumpri-lo tinham cache
    quente), e ainda assim "SC-007 passa" não é evidência do mesmo tipo que
    "SC-003 passa".
  - **SC-008**: reescrito no mesmo commit, depois de medir 50% e depois 36,7%
    de divergência.

  Nenhuma das duas emendas é desonesta, e ambas estão registradas com o
  raciocínio. O que não se pode fazer é citá-las como se restringissem o
  sistema: elas o descrevem.
- **Uma checagem contra critério auto-rascunhado não é evidência (F23).**
  A interface oferece rascunhos de asserção derivados da distribuição
  observada; checá-los contra o mesmo circuito passa por construção, inclusive
  quando o circuito está errado (medido: circuito uniforme de 25% "verificado"
  contra asserções que descreviam seus próprios 25%). Qualquer número ou
  demonstração que dependa de uma checagem com `circular=True` não sustenta
  nada sobre corretude.
- **A replay-identidade não é independência (F28).** O que se mostrou é
  0/360 idênticos sob uma sequência de chamadas fixa — forte, e raro em
  sistemas com LLM no laço. Não se mostrou, e é falso no protocolo em que
  todas as execuções até 2026-09-26 rodaram, que o resultado de uma (tarefa,
  seed) independe das anteriores: o estado de cache do servidor atravessa
  tarefas e muda a saída a `temperature=0`. Toda comparação por tarefa entre
  execuções com prompts diferentes — T090c incluída — carrega essa
  contaminação, e a diferença entre seeds medida dentro de uma execução
  mistura efeito de seed com efeito de história. A partir de F28 as
  execuções usam `reset_per_run`; números anteriores a isso não devem ser
  comparados por tarefa com números posteriores.
- **Zeros são robustos; deltas pequenos não são (F15, F19).** `verificado@1 =
  0,0%` sobre 341 runs é um zero REAL: ruído de amostragem pode mover um
  número, não pode fabricar 341 ausências de sucesso na primeira tentativa. A
  recíproca também vale e é a parte inconveniente: **todo delta pequeno e
  não-nulo da história deste projeto está ininterpretável até o piso de ruído
  ser medido** — inclusive `compila@1` 10,9% → 15,6% (que a correção medida
  não podia causar, F16), a taxa de sucesso 1,8% → 1,1%, e a fidelidade média
  condicional 12,0% → 7,4%. Nenhum deles deve ser citado como efeito.

- **SC-008 NÃO está satisfeito e nunca esteve (F15, F17).** Duas fontes de
  não-determinismo em série: `temperature` não fixada (corrigida) e empates
  da fusão RRF resolvidos arbitrariamente pelo Qdrant (corrigida). Medido:
  50,0% de divergência por tarefa antes, 36,7% com só a primeira corrigida.
  As duas correções estão no código; **a medição que as valida ainda não foi
  feita**. Nenhum número comparativo deste relatório deve ser lido como efeito
  de um tratamento enquanto isso não for refeito.
- **Duas execuções do mesmo código divergiam em 26,1% já na tentativa 1
  (F15).** `temperature` não era fixada, e um seed sozinho não torna o Ollama
  determinístico. Isso invalidava qualquer comparação antes/depois e tornava
  SC-008 inalcançável. Corrigido (`temperature=0`), mas **as duas execuções já
  registradas carregam o ruído** e não devem ser usadas para atribuir efeitos
  pequenos.
- **O corpus de retrieval não é reprodutível entre ingestões (F13).** É
  raspado ao vivo, e uma resposta HTTP transitória derruba uma página em
  silêncio com a ingestão saindo com código 0 — 1020 vs 1019 chunks em duas
  execuções do mesmo código. Como o corpus é o tratamento num sistema RAG,
  duas execuções da suíte só são comparáveis se `qdocs_points` (agora
  registrado em `lib_versions`) coincidir. Enquanto não for pinado, SC-008
  mede estabilidade do harness MAIS deriva do corpus, sem separar as duas.

- **QAOA e VQE H₂ com parâmetros fixos medem fidelidade de CONSTRUÇÃO do
  ansatz, não capacidade de OTIMIZAÇÃO.** `gamma`/`beta` (QAOA, T045) e
  `theta` (VQE H₂, T045) são entregues exatos no enunciado — removendo a
  liberdade de escolha de parâmetro que tornaria a tarefa "encontre bons
  parâmetros" em vez de "reproduza fielmente este circuito parametrizado
  específico". Uma taxa de sucesso alta nessas 6 tarefas (3 QAOA + 3 VQE)
  NÃO deve ser lida como evidência de que um gerador sabe otimizar
  QAOA/VQE — só que sabe reproduzir um circuito já especificado. Precisa
  de menção explícita sempre que resultados dessas 6 tarefas forem citados
  na análise de erro (T064) ou em qualquer figura agregada. Fonte: D3e,
  D3e-3.
- **`delta_perturbacao` quebrado POR FAMÍLIA de perturbação é descritivo,
  não inferencial, nestes tamanhos de célula.** A distribuição final das 5
  famílias D12 nas 60 tarefas perturbadas é 11/14/15/11/9 (relative_phase/
  gate_set_restriction/qubit_ordering/symbolic_parameterization/
  composition) — não uniforme, porque várias combinações (tarefa × família)
  são estruturalmente vazias ou mudariam a física medida (ver F5). Efeitos
  de família e de tier ficam parcialmente confundidos. A métrica que
  carrega peso inferencial é o `delta_perturbacao` AGREGADO (canônica vs.
  perturbada, por gerador e por condição, T063/FR-023) — com 60 pares
  completos, essa agregação tem amostra suficiente; a quebra por família
  não tem, e uma célula pequena (ex.: `composition`, 9 tarefas no total, 2-3
  por tier) não deve ser lida como evidência mais forte do que realmente é.
  Fonte: D3j.
- **Teleportação está ausente do conjunto canônico.** O protocolo exige
  funcionar para um estado de entrada ARBITRÁRIO; nem `oracle_kind=
  "unitary"` nem `"statevector"` capturam isso, e fixar um estado de
  entrada específico admitiria circuitos acidentalmente corretos só para
  aquele estado — pior que omitir a tarefa. Substituída por aritmética
  booleana reversível no conjunto T1. O oráculo conceitualmente correto
  (fidelidade de canal sobre K estados de entrada aleatórios) está esboçado
  como trabalho futuro, não implementado — a convenção de como o circuito
  GERADO expõe "qual qubit é a entrada" não existe hoje, e defini-la mal
  criaria uma nova categoria de falso negativo. Um dos algoritmos mais
  citados de computação quântica está ausente do dataset; precisa constar
  explicitamente como limitação de cobertura, não ser omitido em silêncio.
  Fonte: D3d (Achado 1); `estado-e-aprendizados.md` §2.4.
- **A verificação por composição (acima de 12 qubits) é PROBABILÍSTICA, não
  exata.** `Operator.equiv()` materializa uma matriz densa 2ⁿ×2ⁿ — viável
  até ~13 qubits (268 MB em 12 qubits; 4,3 GB, inviável em 14). Acima
  disso, `check_alternative_construction` usa composição com a inversa +
  5 estados Haar-aleatórios (`random_statevector`), com probabilidade de
  falso positivo desprezível mas não nula. `SemanticResult.
  verification_method` registra qual caminho foi usado por execução — a
  análise DEVE poder segmentar por método, e qualquer figura que agregue
  resultados de tarefas acima e abaixo de 12-13 qubits sem essa segmentação
  mistura um teste exato com um probabilístico. Fonte: D3b.
- **A linguagem de asserção de US3 (v2) é forte para preparação de estado e
  propriedades qualitativas, fraca para tarefas cujo conteúdo inteiro é uma
  derivação numérica.** Achado do próprio desenho da gramática (não de uma
  execução): validando a sintaxe proposta a frio contra `qubo_ising_3var`
  (T3) — "aplique a fase diagonal exp(-i·γ·H) onde H vem de expandir um
  QUBO por uma substituição declarada" — a ÚNICA asserção não-vazia
  possível (`PHASE_DIFF` entre dois estados de base) exigiu expandir a
  substituição QUBO→Ising à mão (seis coeficientes, várias linhas de
  álgebra) antes de saber o que escrever: `PHASE_DIFF(|000>, |111>) ~=
  -0.5`, verificado obtendo H(+++)=-0.25, H(---)=0.75, γ=0.5. Essa mesma
  derivação é exatamente o que CONSTRUIR o circuito exige — para esta
  classe de tarefa, "saber o que quero verificado" e "saber como
  implementar" colapsam na mesma conta, contradizendo diretamente a
  premissa central de US3 (spec.md: a asserção deve ser escrevível por
  quem sabe o que quer mas não como implementar). Contraste medido no
  mesmo exercício: a mesma gramática, aplicada a preparação de estado
  (GHZ) ou a propriedades qualitativas (autoestado coletivo, restrição de
  gate set), não exige nenhuma derivação — só conhecimento conceitual do
  que a tarefa pede. **A gramática não foi alargada para cobrir este
  caso** — alargá-la para aceitar uma derivação pronta equivaleria a
  aceitar uma referência disfarçada, o que anularia o ponto de US3
  (verificação SEM referência). Registrado como limitação de cobertura,
  não como lacuna a fechar. Fonte: exercício de validação a frio da
  gramática de asserção (v2, US3), antes de qualquer implementação.
- **As 50 consultas sintéticas de avaliação de recall (`tests/retrieval/
  queries.jsonl`, T040) foram autoradas pela mesma pessoa/processo que
  construiu e ingeriu o corpus.** Consequência demonstrada, não hipotética:
  D17-1 encontrou que 26 de 44 alvos `intent_phrasing` tinham uma resposta
  irmã legitimamente correta que o gabarito original não reconhecia,
  porque foi autorado contra um corpus de 186 chunks que nunca continha as
  duas versões do mesmo conceito competindo (D17-1). Isso já foi corrigido
  para essas 26 entradas especificamente (campo `also_correct`), mas o
  padrão geral — quem escreve as consultas de avaliação conhece a estrutura
  do corpus que construiu — é um viés estrutural do desenho, não eliminado
  pela correção pontual, e deve ser declarado como tal. Fonte: `research.md`
  T040 (`tasks.md`), D17-1 (consequência medida).

---

## Open questions for the advisor

### SC-007 reprovado a frio (205,8 min vs 180): paralelizar ou reduzir seeds?

Medido em 2026-09-22 na primeira execução completa com cache frio. A opção
importa porque muda o que a suíte mede, e T102 previa a decisão sem escolher:

- **Paralelizar por tarefa** (o `WorkerPool` já suporta, D1b): preserva 120
  tarefas × 3 seeds, logo preserva o poder estatístico do teste de McNemar
  proposto em T101b. Risco: execuções concorrentes ao MESMO servidor Ollama
  compartilham o estado interno que F19 mostrou influenciar a saída — a
  paralelização pode aumentar o piso de ruído, isto é, comprar tempo com
  reprodutibilidade, que é a moeda errada para este projeto.
- **Reduzir para 2 seeds**: leva a ~2,3 h, dentro do teto, e não toca no
  determinismo. Custo: menos pares (task, seed) discordantes, portanto menos
  poder para detectar regressão — precisamente a capacidade que o piso de
  ruído está sendo medido para quantificar.
- **Terceira via, não prevista em T102**: aceitar que 3 h era um teto
  calibrado contra medições com cache quente e re-derivá-lo do custo real.
  O teto existe para que a suíte seja rodável com frequência (Princípio III);
  3 h 26 min ainda satisfaz esse propósito. Emendar SC-007 seria honesto se a
  justificativa for essa — e desonesto se for só para fazer o número passar.

**Recomendo decidir DEPOIS do piso de ruído (run B)**, porque a escolha entre
paralelizar e cortar seeds depende de quanto poder estatístico existe hoje, e
esse número ainda não existe.


Itens genuinamente em aberto, não decisões pendentes de implementação.

> **Nota datada, 2026-09-15** (migração v1→v2, ver `MIGRATION.md`): duas das
> perguntas abaixo — o segundo anotador para κ e a calibração de descarte de
> D12 — **deixaram de estar em aberto**, mas não porque alguém respondeu:
> deixaram de existir como perguntas porque o trabalho que as fazia
> perguntas (T064, o critério de descarte via piloto C5) foi removido do
> escopo. É uma distinção que importa para o relatório — "resolvido por
> remoção" não é o mesmo que "resolvido", e um leitor futuro não deve
> confundir os dois. Os itens permanecem abaixo, marcados individualmente,
> em vez de apagados — o mesmo padrão não-destrutivo de `research.md`
> (D8/D9/D12).

- **Título formal do projeto.** Três nomes em circulação:
  `qcircuit-agent`, "Quantum-RAG" (nome do diretório do repositório), "LLM
  Quantum Copilot". "Quantum RAG" colide com o termo já estabelecido na
  literatura para "recuperação acelerada por algoritmos quânticos"
  (quantum-accelerated retrieval) — um risco de confusão que pesa contra
  essa opção. Fonte: `estado-e-aprendizados.md` §7.
- **Reunião com o orientador.** Pendente desde o início do projeto (ver
  `estado-e-aprendizados.md` §7). ~~O congelamento de escopo M2 (dataset e
  conjunto de geradores imutáveis, ver `plan.md`) é o último ponto barato
  para incorporar qualquer mudança de direção — a reunião precisa
  acontecer antes de M2, não depois.~~ **SUPERADA em 2026-09-15** (migração
  v1→v2): `plan.md` não fala mais em "conjunto de geradores imutáveis" —
  M2, hoje, é só "`validate_oracles.py` 120/120 verde" mais uma nota de
  estabilidade da suíte de referências, não um congelamento de escopo
  contra o qual medir a urgência da reunião.

  Isso não é só uma correção de referência cruzada — é uma inversão real,
  e material de relatório por si só. Em v1, o conjunto de tarefas
  PRECISAVA ficar congelado em M2 porque a matriz experimental comparava
  geradores × condições sobre o MESMO instrumento de medida: adicionar uma
  tarefa no meio do experimento mudaria o que estava sendo medido a meio
  do caminho, invalidando a comparação entre braços que já tinham rodado
  contra o conjunto antigo e os que rodariam contra o novo. Em v2 não há
  mais braços a comparar — a suíte de regressão não está isolando o efeito
  de nada contra um instrumento fixo, está checando se o sistema ainda
  passa nas tarefas que já passava. Sob esse critério, **crescer a suíte
  só pode aumentar a cobertura de regressão, nunca invalidar uma
  comparação que não existe mais** — adicionar uma tarefa nova é
  estritamente uma melhoria, não um risco a conter atrás de um
  congelamento. A pressão que fazia M2 ser "o último ponto barato para
  mudar de direção" em v1 não tem equivalente em v2: não há mais uma
  janela que se fecha, porque não há mais um instrumento de medida
  compartilhado para proteger.
- **Segunda anotação independente para o cálculo de Cohen's κ (T064,
  FR-024, v1).** ~~A taxonomia qualitativa de erros exige dupla anotação em
  20% da amostra (150 falhas estratificadas), com discordâncias indo a um
  terceiro anotador que decide por maioria. Depende de disponibilidade de
  um terceiro — sem isso resolvido, trava na semana 11 do cronograma.~~
  **SUPERADA em 2026-09-15** (migração v1→v2): T064 foi removida do escopo
  (`MIGRATION.md` §3 — "a remoção de T064 elimina o risco mais frágil do
  projeto"). Não há mais taxonomia com dupla anotação, logo não há mais
  segundo anotador a arranjar — a pergunta não foi respondida, deixou de
  existir. Fonte original: `spec.md` v1 (κ ≥ 0,70), `tasks.md` v1 T064
  (ambos reescritos em v2; a citação acima é histórica).
- **Calibração de descarte das perturbações (D12, v1).** ~~O critério —
  descartar uma perturbação onde o gerador de fronteira, na condição
  completa (C5), não passe de 20% de acerto — exige RODAR geradores contra
  as 60 tarefas perturbadas. Essa decisão só pode ser tomada no piloto
  (T055), não antes; até lá, as 60 variantes perturbadas construídas em
  T048 são candidatas, não confirmadas.~~ **SUPERADA em 2026-09-15**
  (migração v1→v2): o critério de descarte dependia da condição C5 e do
  piloto T055, nenhum dos dois existe mais (`research.md` D12, marcada
  SUPERADA na migração). As 60 variantes perturbadas de T048 permanecem
  construídas e verificadas — mudam de função (controle de contaminação →
  teste de robustez, `MIGRATION.md` §2), sem precisar de nenhuma calibração
  de descarte para isso. De novo: resolvida por remoção do critério, não
  por uma resposta à pergunta original.
- **Nota, não pergunta em aberto**: "treinar ou ajustar fino qualquer
  gerador" já está explicitamente listado em Out of Scope (`spec.md`) —
  não é uma extensão a decidir, é uma exclusão já fixada. Registrado aqui
  só para que uma leitura futura deste documento não reabra a pergunta sem
  necessidade.

---

## Reproducibility appendix material

Material para a seção de reprodutibilidade/apêndice metodológico.

**Ambiente canônico** (D15): container Linux via `docker-compose.yml`
(`app` + `qdrant`), Ollama nativo no host Windows, alcançado via
`host.docker.internal:11434`. Desenvolvimento e a matriz experimental
completa DEVEM rodar nesta mesma configuração — nunca uma mistura de
execução nativa Windows e containerizada entre sessões, porque o
`WorkerPool` (D1b) depende de `fork` (herança copy-on-write, só disponível
nativamente no Linux) para a amortização medida de ~1,58 s → ~0,0002 s por
chamada; sob `spawn` nativo do Windows a mesma otimização não existe.

**Hardware de referência** (`plan.md`): Ryzen 7 5700X, 32 GB RAM, RTX 3070
8 GB. IBM Quantum open plan para a validação em hardware real (US4, T068).

**Versões pinadas** (`plan.md`, D1, D5b):

| Componente | Versão |
|---|---|
| Python | 3.11 |
| Qiskit | 1.2.4 |
| qiskit-aer | 0.15.1 (CPU por padrão — ver D1; variante `-gpu` opcional) |
| Qdrant | 1.12 (imagem `qdrant/qdrant:v1.12.x` fixada) |
| Framework de orquestração | LangGraph |
| Validação de dados | Pydantic v2 |
| Embeddings | fastembed (denso + esparso BM25/IDF) |

**Como uma execução é reproduzida a partir de config**: `run_id = hash(config
+ git_sha + timestamp)` (`config.py`, T015) — todo `RunRecord` carrega
`git_sha` e `lib_versions` (incluindo a versão do Ollama, consultada em
tempo de execução via `GET /api/version` do host, já que o Ollama não é
mais fixado por tag de imagem desde que saiu do compose — D15 item 3;
fallback `"unknown"` se o host estiver inacessível). `num_ctx` gravado é o
valor EFETIVO enviado na requisição (D10b), nunca herdado de default de
servidor. Execução dirigida por `config.yaml` (`make eval`).

**Convenção de hash de snapshot do Qdrant** (T036b, `contracts/
retrieval.md`): `snapshot(client, out_dir)` cria um snapshot da coleção via
`POST /collections/{name}/snapshots`, baixa para `out_dir`, e retorna nome,
caminho local e **sha256 do arquivo**. Esse hash entra no `run_id` —
permite reconstruir bit a bit, numa semana posterior do cronograma,
exatamente o corpus recuperável no momento em que uma rodada foi executada,
mesmo que a documentação upstream (Qiskit release notes, etc.) tenha
mudado no intervalo. Chamado ao fim da ingestão e antes de cada rodada
experimental.

**Escala da matriz experimental** (`plan.md`): 3 geradores (2 de fronteira
via API + 1 local) × 5 condições (C1–C5) × 120 tarefas (60 canônicas + 60
perturbadas) × 3 seeds = **5.400 execuções**. Meta de wall-clock: ≤72h.
Corpus de documentação: ~15k unidades (chunks).

---

## To measure

Números que o relatório provavelmente precisa, ainda não registrados em
nenhum lugar — não reconstruídos de memória, listados aqui como pendência.

- **Validação pendente, amarrada à US7 — o gerador otimiza para as
  asserções e ignora o resto do pedido?** (`tasks.md` T090b). Desde T090b
  o gerador vê as asserções declaradas desde a primeira tentativa. O risco
  é um circuito que satisfaz o que foi afirmado e ignora o resto do que foi
  pedido. **Por que não foi medido ainda**: nenhuma das 120 tarefas da suíte
  declara asserção, então seus prompts são byte a byte idênticos antes e
  depois (fixado por teste), e um antes/depois na suíte sairia igual por
  construção; e o runner da suíte (`bench/runner.py`, US7) não existe.
  **Por que só o oráculo mede isso**: um circuito que satisfaz as asserções
  e ignora o resto passa em todas elas por definição, e só a comparação com
  a referência verificada o denuncia. **Desenho**: (1) um subconjunto de
  tarefas da suíte recebe asserções escritas A FRIO a partir do enunciado,
  nunca do oráculo (mesmo protocolo de F7), cobrindo os três tipos de
  escopo que F7 achou; (2) cada tarefa roda em dois braços com os mesmos
  seeds: asserções declaradas mas OCULTAS do gerador, e asserções
  VISÍVEIS; (3) os dois braços são pontuados pela comparação com a
  referência (`semantic_check`), não pelas asserções; (4) métricas por
  tarefa, não só agregadas: taxa de acerto contra o oráculo em cada braço,
  e a assinatura exata do risco, **"todas as asserções passam E o oráculo
  reprova"**, comparada entre braços. Um aumento dessa assinatura no braço
  visível é evidência direta do risco; uma queda na taxa de acerto sem
  aumento da assinatura é outro problema e precisa ser separado dele.
  **Precondições**: runner da US7; tarefas com asserções; retrieval
  disponível (Qdrant fora do ar no ambiente atual) ou stub declarado como
  tal no resultado.
- **Valor real de Cohen's κ** (T064) — a meta é ≥0,70 (`spec.md`), mas
  nenhuma anotação dupla foi executada ainda; depende também da pergunta
  em aberto sobre o segundo anotador.
- **`delta_perturbacao` agregado real**, por gerador e por condição (T063)
  — nenhuma execução da matriz ocorreu ainda; toda a discussão de F5 e da
  limitação correspondente é sobre o DESENHO da métrica, não seu valor.
- **Custo em USD e tempo real extrapolado do piloto** (T055, fecha D8
  — teto de iterações —, D9 — idioma dos prompts —, D12 — descarte de
  perturbação —, e o orçamento de API) — nenhum piloto formal rodou ainda.
- **Resultado do piloto formal de D4** (modelo de embedding) — não
  bloqueante para prosseguir (D17-1, já que M1 passa sem ele), mas ainda
  não executado; os dois falsos negativos genuínos remanescentes (rotação
  em X/Y) são o material de partida se/quando esse piloto rodar.
- **Validação em hardware IBM real** (US4, T068) — `results/{run_id}/
  hardware.jsonl` ainda não populado; nenhuma tarefa foi executada contra
  hardware físico até o momento deste registro.
- **Recall@8 pós-expansão final do corpus**, se o corpus crescer de novo
  além dos 1.020 chunks atuais — D17 exige reavaliação de M1 a cada
  expansão significativa; o número de 0,9524 vale para o corpus como está
  hoje, não é uma garantia permanente.
