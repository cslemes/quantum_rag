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

## Measured results

Todo número citável, como foi obtido, e ressalva relevante.

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

### Evidência qualitativa antecipada para H1 — RAG antes/depois em `ghz_3q`

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

**Ressalva**: isto NÃO substitui o experimento formal (C1 vs. C3, matriz
completa) — é evidência qualitativa de UMA tarefa, com mecanismo causal
explicado, não uma medição estatística. Vale como ilustração no
relatório (mecanismo > correlação), não como resultado de H1 em si.

**Fonte**: `estado-e-aprendizados.md` §5 — este achado NÃO está registrado
em `research.md`; recuperado do único outro documento de estado do projeto
ao escrever este arquivo.

---

## Threats to validity

Tudo que limita o que pode ser afirmado a partir deste desenho experimental.

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
