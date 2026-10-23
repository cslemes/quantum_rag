<!--
NOTA AO AUTOR (remover antes da versão final).

GRAU DE EVIDÊNCIA. Cada achado traz, entre colchetes, o grau da evidência:
  [a] medido, com número e denominador;
  [b] mecanismo traçado em um caso — ilustração, nunca efeito medido;
  [c] fino — afirmado nas notas sem nenhum dos dois.
Os achados de grau [c] estão listados também no relatório de entrega, para decidir o que cortar.

CONFLITOS COM O CAPÍTULO 5 (o capítulo 5 é a autoridade; onde diverge, a nota está velha — não escolhi em silêncio):
  1. §5.2 diz que a taxa de regressão é "estável entre os dois estados anteriores". A leitura defensável é a mais fraca
     usada em 6.5 (ambos os estados anteriores caem numa faixa de 46–64% e a rodada C fica abaixo dela). §5.2 precisa da mesma redação.
  2. §5.3 atribui o "zero em 360" a um protocolo que inclui `reset_per_run`. As notas (F28; "Piso de ruído de replay medido: zero")
     dizem que o zero foi medido sob reset único, no Ollama 0.34.1, e que mede determinismo de replay. §5.3 precisa ser corrigido.
  3. §5.7 ainda carrega a predição da re-execução em 0.34.4 (5 a 9 de 120), aposentada. Os números das execuções E e F e a
     comparação C×E (inclusive 34/120 e 102/120 abaixo) NÃO estão no capítulo 5; este capítulo os usa com a marca "[a pôr no cap. 5]".
  4. O esqueleto fala em "vinte e dois achados"; as notas vão até F32.

LEITURAS A CONFIRMAR.
  - "Lado consultivo" (6.5): li como "o enunciado do teste — hipótese, predição ou pedido de verificação — e não o código sob teste".
    As quatro instâncias usadas estão no texto; confirme se são as suas quatro.
  - 6.4(c): o portão de versão, uma checagem de início de execução, FOI o que recusou. O que nenhuma checagem anterior ou
    feita em outro lugar teria pego é a atualização entre a leitura e o lançamento. Escrevi assim; uma atualização DURANTE a
    execução continua sem cobertura.
  - "102 de 120" (6.4): é o número de tarefas com código final diferente entre C e E; o status final difere em 36/120.
-->

# 6. Achados de engenharia

Este capítulo reúne o que a construção e a medição do sistema ensinaram sobre
*como* construir e medir um sistema desse tipo, e não sobre computação
quântica. Cada seção parte de uma afirmação, lista as instâncias em que ela foi
observada, diz com que evidência, e então diz o que a afirmação significa fora
deste projeto. Os achados estão agrupados por tema porque a unidade que se
repete é o tema, não o episódio: o mesmo defeito reaparece em lugares que não
têm nada em comum, e é isso que o torna um achado.

**Convenções.** Todo número carrega, onde se aplica, a build do servidor
Ollama sob a qual foi obtido, porque o capítulo mostra (§6.4 e §6.5) que o
mesmo modelo, o mesmo código e a mesma semente dão resultados por tarefa
diferentes entre builds. As siglas das execuções são as do capítulo 5. Cada
achado traz o grau da sua evidência entre colchetes: **[a]** medido, com
número e denominador; **[b]** mecanismo traçado num caso, apresentado como
ilustração e nunca como efeito medido; **[c]** afirmado nas notas sem nenhum
dos dois. Toda verificação neste trabalho é determinística; o modelo gera e
propõe, e nada neste capítulo atribui a ele um veredito.

---

## 6.1 Critérios de correção que falham em silêncio

**A afirmação.** Um critério de correção automatizado pode ser internamente
consistente — nunca lança exceção, compara exatamente o que foi programado — e
ainda assim testar algo diferente do que o enunciado pede. Quando isso
acontece, a falha não aparece como erro: aparece como uma taxa de sucesso mais
baixa, ou mais alta, por um motivo que não tem relação com o que se queria
medir.

### Oráculos mais estreitos que o enunciado

Três instâncias independentes, em três tiers diferentes, da mesma estrutura.

- **GHZ em estrela contra GHZ em cadeia** (`ghz_3q`). `h(0); cx(0,1); cx(0,2)` e
  `h(0); cx(0,1); cx(1,2)` preparam o mesmo estado a partir de `|000⟩`:
  `Statevector(estrela).equiv(Statevector(cadeia))` é verdadeiro. Mas
  `Operator(estrela).equiv(Operator(cadeia))` é falso. O enunciado pedia um
  estado; o oráculo testava a unitária inteira sobre os 2ⁿ estados da base.
- **Somador com "vai-um" encadeado.** Com as ancillas iniciando em `|0⟩`, os
  16 casos físicos estavam corretos nos dois lados; nos 240 casos "não físicos"
  dos 256 possíveis o comportamento dependia da implementação. A correção foi
  tornar a tarefa plana e declarar a restrição no enunciado, não só no oráculo.
- **Convenção de sinal QUBO→Ising.** `x_i = (1−z_i)/2` e `x_i = (1+z_i)/2` são
  ambas convenções padrão, e dão Hamiltonianos de sinal oposto. Sem declarar
  qual, o oráculo aceitava implicitamente uma de duas respostas igualmente
  corretas.

**Evidência [b].** Cada instância foi verificada por computação no caso
concreto (os três resultados acima são calculados, não opinião). O que *não*
foi medido é o efeito agregado: as notas afirmam que a taxa de sucesso fica
"sistematicamente abaixo da real", mas nenhuma execução quantifica quanto. São
três ilustrações independentes de um defeito, não uma estimativa dele.

### Perturbações vazias

Uma perturbação é um não-operador quando o conjunto de qubits que uma
estrutura toca já é simétrico sob a perturbação. Grafos-ciclo são invariantes
sob reversão do registrador (a reflexão `i → n−1−i` é automorfismo de todo
ciclo); strings marcadas palíndromas são mapeadas em si mesmas; um `RZ` sobre
um alvo que colapsa em um único estado de base é fase global. Tais variantes
tornariam a métrica de sensibilidade à perturbação artificialmente zero — não
porque o gerador reconhecesse a tarefa, mas porque não havia nada a
reconhecer.

**Evidência [a, sem denominador].** 14 combinações candidatas (tarefa canônica
× família de perturbação) foram identificadas como vazias, por verificação
computacional por instância (`Statevector`/`Operator` `.equiv` após a
perturbação), e descartadas antes de virarem tarefa. As notas registram o 14,
mas não o total de combinações candidatas; a fração não é recuperável.

### Validação circular

Um sistema que sugere o próprio critério de aceitação produz uma verificação
que não pode falhar, e é a ajuda que causa isso. Quanto mais a interface ajuda
a escrever a asserção a partir do que o circuito *fez*, mais a asserção
descreve o artefato e menos descreve o que o usuário queria; no limite o
critério é lido do artefato e a checagem é uma tautologia. O modo de falha é
invisível porque o que aparece na tela é `VERIFIED`.

**Evidência [b].** Um caso, ao vivo. Pediu-se um estado de Bell; o circuito
gerado produziu superposição uniforme de quatro estados (`|00⟩`, `|01⟩`,
`|10⟩`, `|11⟩`, 25% cada). A interface ofereceu como rascunho as quatro
asserções `PROBABILITY(|xy⟩) ≈ 0,25`. Checado contra elas, o circuito deu
`verified=True` e `circular=True`; checado contra a intenção escrita
(`PROBABILITY(|00⟩) ≈ 0,5`, `PROBABILITY(|11⟩) ≈ 0,5`), deu `verified=False`.
O circuito estava errado e a checagem contra os rascunhos disse o contrário,
corretamente em relação àquelas asserções. É uma ilustração do mecanismo; a
frequência com que usuários aceitariam rascunhos não foi medida.

**Generalização.** A contramedida geral é que uma checagem só é significativa
quando a *origem* do critério é independente do artefato checado. A
independência é da origem, não de quem escreve: um critério não se torna
independente por ser editado, escrito noutra linguagem, vir de outra execução
do mesmo modelo, nem de um modelo diferente — se todos derivam do mesmo
requisito ambíguo ou do mesmo artefato, os erros são correlacionados pelo
mesmo motivo que um modelo lendo duas vezes o mesmo texto erra duas vezes.
Isso alcança **snapshot testing** (a primeira execução grava a saída como
esperada, e se a implementação original estava errada o snapshot registra o
erro como especificação, tornando invisível toda regressão em relação ao
comportamento correto) e **testes escritos por um LLM para código escrito por
um LLM**, que parecem verificação independente — há dois artefatos, em
arquivos e momentos diferentes — enquanto a fonte do critério e a fonte do
comportamento são a mesma. Trocar o modelo que escreve os testes muda a fonte
do artefato sem mudar a fonte do critério, e é a segunda que precisava mudar.
*(Esta generalização é um argumento por analogia com práticas conhecidas, não
um resultado medido neste trabalho: [c] enquanto afirmação sobre práticas
externas, [b] enquanto afirmação sobre este sistema.)*

### Investigado e não confirmado: o orçamento de recursos "frouxo"

Registra-se também uma suspeita que **não** se confirmou, porque ela mostra
como um achado falso se forma. O orçamento de recursos é relativo: o teto é
2,0× a profundidade da referência *transpilada*. Em duas tarefas perturbadas
(`ghz_linear5_full_perturbed`, `ising_linear5_mixed_perturbed`) a referência
transpilada tem profundidade 25 e 27, contra 5 e 7 das gêmeas não perturbadas.
Concluiu-se que o teto (50 e 54) era frouxo e que a checagem de recursos quase
não discriminava nessas duas tarefas — mais uma instância da família
"critério mais largo que o enunciado".

A comparação era inválida: a gêmea não perturbada é *outra tarefa*, e sua
profundidade não é linha de base da versão perturbada, porque a perturbação
(uma QFT sobre cinco qubits numa linha) custa de fato cerca de 25 de
profundidade. O referencial correto é uma solução natural da própria tarefa.
Quatro implementações corretas naturais por tarefa, todas verificadas
equivalentes à referência, deram profundidade 20–26 na primeira (referência
25) e 23–27 na segunda (referência 27) — perto da referência, com razão entre
0,80 e 1,04. O teto de 2× é tão estrito aqui quanto nas demais tarefas. Nada
estava errado, nenhuma tarefa foi excluída, e a alegação foi retratada.

**Evidência [a, n pequeno].** 4 implementações por tarefa, 2 tarefas; as
profundidades acima. O que importa para o argumento é o outro lado: a
alegação original já tinha sido registrada como achado de calibração e
generalizada para a família dos oráculos estreitos *antes* de a linha de base
ser conferida, porque casava com um padrão estabelecido (§6.5, "reconhecer o
padrão esperado"). Aqui o padrão não se aplicava.

---

## 6.2 Verificadores cegos

**A afirmação.** Um verificador pode ser cego por construção, e não apenas
frouxo. A diferença decide o que se faz: um verificador frouxo se corrige
apertando uma tolerância; um cego não se corrige assim, e nenhum limiar o
conserta.

### Cegueira de fase em verificação por medição

A checagem de sanidade por medição real (três sementes, `AerSimulator`) da QFT
reportava **fidelidade de Hellinger 1,0000** para um circuito que computava a
QFT *inversa*, com o sinal de fase inteiro trocado. A QFT de qualquer estado de
base computacional produz magnitude uniforme sobre todas as saídas,
independentemente de as fases estarem certas; é uma propriedade da
transformação, não um limiar mal calibrado. Nenhum ajuste de
`SANITY_FIDELITY_MIN` teria corrigido isso.

A correção foi compor o circuito primário com o inverso de uma construção
alternativa independente antes de medir, o que converte qualquer divergência
de fase em vazamento de probabilidade para fora de um alvo nítido: o mesmo
erro de sinal passou a medir **0,0000**. A lacuna não era exclusiva da QFT.
Medido sobre as tarefas construídas: a distribuição-alvo de Simon é exatamente
uniforme sobre 2ⁿ resultados (`max_prob = 1/2ⁿ`); o Grover sub-ótimo mede
`max_prob ≈ 0,47`; o QAOA com p=1 e ângulos realistas mediu entre 0,11 e 0,37
nas três instâncias construídas.

**Evidência [a] para a propriedade, [b] para a demonstração.** Os valores de
`max_prob` por tarefa são calculados (o denominador é cada uma das tarefas
construídas citadas). A demonstração de que o verificador era cego é um único
bug injetado deliberadamente (QFT inversa): 1,0000 antes, 0,0000 depois.

### O que a construção independente pegou

A disciplina de exigir que toda referência seja verificada por uma segunda
implementação, escrita sem olhar a primeira, pegou cinco erros de método
durante a construção do conjunto canônico e do perturbado: a direção do laço
da QFT invertida (`Operator.equiv` contra `QFTGate` deu falso para n = 2, 3, 5
e 8); três algoritmos (Deutsch–Jozsa, Simon, Bernstein–Vazirani) classificados
como `oracle_kind="distribution"` quando deviam ser `"statevector"`, de memória
e nunca verificado; o somador com ancilla encadeada (§6.1); a convenção de
sinal QUBO→Ising (§6.1); e um controle fixo em vez de variável no oráculo
perturbado de dois Deutsch–Jozsa, que, sendo o `CX` autoinverso, colapsaria
silenciosamente para uma função de um único bit.

**Evidência [a] para a contagem, [c] para o contrafactual.** Cinco erros, cada
um reproduzido por computação. As notas afirmam que nenhum seria detectado "só
lendo o circuito de referência e concordando que parece certo", mas isso é um
contrafactual que nenhuma medição sustenta, e o total de referências
construídas (o denominador) não está registrado junto da contagem.

### O escopo real de uma gramática, definido por uso e não por revisão

Antes de implementar a gramática de asserções, três tarefas de tiers
diferentes foram escritas à mão, sem consultar a especificação, para forçar à
tona onde um usuário tropeçaria. O exercício revelou limites que uma rodada
inteira de revisão da gramática proposta não revelara. O mais claro: toda
asserção, sem um mecanismo de preparar entrada, só testa comportamento a
partir de `|0…0⟩`, e a QFT aplicada a `|0…0⟩` produz a mesma superposição
uniforme que um `H` em cada qubit — nenhuma asserção ancorada só em `|0…0⟩`
distingue uma QFT correta de uma implementação que não é QFT nenhuma. Isso
motivou o prefixo `INPUT(…) THEN <asserção>`.

**Evidência [b] para cada limite, [c] para a comparação.** O caso da QFT foi
verificado por computação. A afirmação de que o exercício a frio definiu o
escopo "mais do que qualquer revisão de desenho" é uma comparação entre dois
métodos feita num único projeto, sem controle: é uma observação, não uma
medida.

**Generalização.** Testar um verificador contra um defeito *injetado* revela
lacunas estruturais que nenhum ajuste de tolerância revela, e o teste de
cegueira deve ser feito contra o pior caso do domínio, não contra o caso
típico. Qualquer checagem de corretude por amostragem sobre um alvo espalhado
tem o mesmo risco em qualquer domínio em que "distribuição quase uniforme" seja
uma saída legítima e não só um sintoma de erro — por exemplo, um teste que
compara histogramas de saída de um modelo estatístico cujo comportamento
correto é, ele mesmo, disperso.

---

## 6.3 Vereditos que não correspondem ao verificado

**A afirmação.** O que o sistema *diz* ter verificado e o que ele de fato
verificou podem divergir, e a divergência não fica no texto: ela passa para o
campo que as ferramentas leem. A prosa honesta não sobrevive a um campo
estruturado que afirma o contrário.

### Honestidade em prosa não sobrevive a um campo que diz outra coisa

O relatório de garantia de uma execução sem asserções e sem referência
renderizava, corretamente, "FUNCTIONAL CORRECTNESS: NOT VERIFIED" — e a mesma
execução terminava com `status="success"`. A prosa era honesta, e o sistema
ainda assim afirmava aprovação, uma camada acima, no campo que ferramentas
leem. `success` significava apenas "nenhuma camada reportou erro", e nesse
caminho nenhuma camada tinha checado nada. O teste obrigatório do princípio de
honestidade estava verde o tempo todo, e estava certo: verificava a prosa, que
não mentia. Guardava a camada que um humano lê, não a que uma agregação lê.
Nem a revisão de desenho pegou, porque os exemplos revisados eram texto
renderizado e o `status` não fazia parte do que se revisou.

**Evidência [b].** Um caso, impresso lado a lado a partir do caminho real de
`finalize`. Os consumidores que teriam sido enganados (a agregação de taxa de
sucesso por tier, qualquer resumo de CI) são identificados por leitura do
código; nenhum foi observado enganado.

### Divergência nas duas direções

Vinte e dois testes ponta a ponta, que executam o grafo real e checam em toda
execução que o `status` e o veredito do relatório concordam, acharam **nove
bugs** que os cerca de 220 testes unitários e de contrato da época não
achavam, todos passando verdes. **Quatro dos nove** eram o mesmo defeito: o
relatório dizendo algo diferente do que foi verificado. Três eram
superdeclaração — um veredito velho sobrevivendo de uma tentativa para a
seguinte e dizendo "VERIFIED" sobre código que nem executou; uma referência
reprovada ainda verificada porque as asserções passavam; um corte por recursos
escondido atrás de "VERIFIED". O quarto era a direção oposta: toda execução da
suíte que *passava* no oráculo dizia "nothing about its behavior was checked"
ao lado de `status="success"`. Divergir para cima e para baixo é a mesma classe
de defeito, e um teste que cobrisse só uma direção teria deixado a outra.

**Evidência [a].** 4 de 9 bugs na mesma classe; 22 testes ponta a ponta contra
cerca de 220 unitários e de contrato. A concentração é a medida: o defeito
dominante vivia na *relação* entre dois campos, que nenhum teste unitário
exercia.

### Uma premissa extraída por LLM pesa em uma direção só

Os requisitos que o planner extrai da descrição (`n_qubits`, `gate_set`) são
checados de forma determinística contra o circuito gerado, mas a *premissa* é a
leitura de um modelo de linguagem. O desenho é assimétrico: um requisito que
passa diz apenas "o circuito concorda com o que o planner leu" e não
estabelece corretude; um requisito que reprova veta a alegação de corretude no
caminho de produto; um valor não avaliável é "não checável" e não vota. No
caminho da suíte um requisito reprovado não veta o veredito semântico, porque
um oráculo verificado é verdade-terreno e, quando discordam, errou o planner.
Antes da checagem, a coerção silenciosa do Pydantic transformava
`"value": true` num requisito de 1 qubit, `false` num de 0 e `3.0` em `3`,
tratando-os como requisitos checados.

**Evidência [b] para a coerção, [c] para a regra.** A coerção é um defeito
reproduzido. A regra "requisitos vetam, nunca estabelecem" é uma decisão de
desenho justificada por argumento, sem medida de que ela produza vereditos
melhores.

### Um campo gravado que nada verifica é decoração

Quatro campos do registro de execução foram gravados sem nenhum consumidor que
falhasse em caso de divergência: a versão do Ollama (gravada desde a primeira
execução, sem teste que a comparasse — um upgrade teria misturado dois
sistemas em silêncio); `qdocs_points`; `gpu_processor`, que era `None` em
**360 de 360** registros enquanto a especificação afirmava haver um guarda, e
cujo código (`assert_full_gpu_offload`) existia, não era chamado por ninguém e
não funcionaria se fosse, porque invocava `ollama ps` e `nvidia-smi` por
subprocesso, binários que vivem no host Windows enquanto o agente só alcança o
Ollama por HTTP; e o ambiente de execução (host, Python, contêiner), que não
era gravado. A pergunta que expôs isso foi "se o contêiner `app` não está
rodando, onde a suíte rodou?": no *venv* do sandbox. Nunca existiu um
contêiner `app`, e todo número do projeto até ali foi obtido fora do ambiente
declarado, sem rastro nos registros.

Duas instâncias vieram depois, no mesmo molde. O campo
`library_version="1.2.4"` estava em todos os 1.019 chunks do corpus de
recuperação, e o conteúdo não era da 1.2.4: o corpus foi raspado da
documentação sem versão, que serve a versão mais recente (2.x), e a constante
foi carimbada em cada chunk. 24 classes indexadas não existem no runtime 1.2.4.
E o painel de saúde da interface mostrava o tamanho do índice de recuperação
sem compará-lo a nada: era um campo sem consumidor que pudesse falhar, e
passou a mostrar o tamanho *com* o veredito contra o valor fixado e a recusar a
execução quando difere.

**Evidência [a].** `gpu_processor` ausente em 360/360 registros; 24 classes
indexadas ausentes do runtime sobre 1.019 chunks carimbados; o ambiente
declarado verificado por comando (`docker compose ps -a` lista apenas o
`qdrant`).

**Generalização.** A regra que sobra é binária: todo campo do registro é ou
verificado por algo que *falha* quando diverge, ou explicitamente rotulado como
descritivo. Não há terceira categoria, porque a terceira — o campo gravado e
não conferido — cria a impressão de proteção, que é pior que a ausência dela:
quem lê o registro conclui que aquilo foi conferido. Vale para qualquer sistema
com metadados de proveniência, de versão ou de ambiente: o metadado sem
consumidor que falha é o mesmo defeito que um relatório que afirma "verificado"
sem que ninguém tenha verificado.

---

## 6.4 Regras que não se propagam

**A afirmação.** Uma regra correta, enunciada num lugar, não alcança o código
ao lado. As notas registram a classe de maior rendimento como **estado ambiente
herdado**: tudo que o experimento herda do ambiente sem declarar nem fixar, e
que pode alterar a medição. A prescrição que as notas extraem não é "regras
não se propagam" (que prevê tudo e portanto nada), e sim que uma regra
enunciada sobre uma *instância* não se propaga, e uma enunciada sobre uma
*classe* pode se propagar *se existir mecanismo que falhe quando for violada*.

### Instâncias: o estado herdado e a pergunta que não se fez

- **Uma correção que não perguntou "onde mais".** `Statevector(qc)` e
  `Operator(qc)` levantam `QiskitError` em qualquer circuito que carregue uma
  medição, e código gerado real termina em `measure_all()` o tempo todo. O
  defeito foi achado e corrigido no avaliador de asserções, com teste de
  regressão. Os três caminhos de oráculo de referência em `semantic.py` tinham
  a construção idêntica e a mantiveram; nenhum teste unitário os exercia com
  circuito medido. A suíte ficou verde por 339 testes, e a primeira execução
  ao vivo morreu na primeira tarefa que chegou ao `semantic_check`: **360
  execuções planejadas viraram zero registros.** *[a]* O que faltou não foi
  rigor no conserto, foi escopo na pergunta.
- **A suíte de testes destruía o índice de recuperação.** `test_index.py` usava
  a coleção de produção com `recreate=True` e a apagava no teardown: todo
  `pytest` apagava o corpus ingerido, e a execução seguinte da suíte de
  regressão media um gerador sem recuperação, sob o nome do sistema que tem
  recuperação. O dano tinha a forma de uma medição: 360 resultados
  uniformemente ruins. *[b]* Identificado na terceira ocorrência, pelo log do
  Qdrant com um `DELETE /collections/qdocs` de timestamp idêntico ao do
  `pytest`.
- **O corpus é raspado ao vivo.** Duas ingestões do mesmo código deram **1.020
  e 1.019 chunks**: uma das ~221 páginas respondeu `503`, a ingestão registrou
  `SKIP` e terminou com código 0. O corpus é o tratamento, e nada no arquivo
  de resultados dizia qual corpus produziu os números. *[a, n = 1 página de ~221]*
- **Duas montagens do mesmo grafo.** A inspeção manual e a suíte montavam o
  mesmo grafo de oito nós, cada uma por conta própria: a inspeção sem semente
  (default 42 dos nós) e sem flag para escolhê-la, a suíte com 1, 2 e 3.
  Toda observação manual rodou com uma semente que a suíte nunca executa.
  *[a]* para a divergência enumerada (a tabela de parâmetros); o efeito
  atribuído à semente foi depois reinterpretado (§6.5).
- **O estado interno do servidor entre tarefas.** O descarregamento do modelo
  era feito uma vez por execução da suíte, não por (tarefa, semente); o cache
  interno de prompt e KV do Ollama carregava estado de uma tarefa para a
  seguinte (§6.5).

**O mecanismo, medido sobre as próprias regras do projeto [c].** Quatro
princípios da constituição do projeto, todos quantificados sobre uma classe
("toda afirmação de corretude…", "toda tarefa…", "toda mudança…"), dois
nasceram com um mecanismo que falha quando violado (um teste de arquitetura;
um portão de validação de oráculos) e nunca foram violados; dois só ganharam o
mecanismo depois de repetidas violações, e foram violados enquanto não o
tinham (os vereditos de §6.3; as comparações entre execuções). A autoridade do
documento não discrimina nada (os quatro estão no mesmo arquivo, com a mesma
autoridade declarada). O que sobrevive é: quantificar sobre a classe é
necessário e insuficiente, porque **não se escreve um mecanismo para uma regra
sobre uma instância** — um teste para "`num_ctx` deve ser explícito" só pode
checar `num_ctx`, não alcança `temperature`. As próprias notas listam as
limitações: N = 4, com a ordem temporal confundida com a presença do
mecanismo, e o período posterior à correção de dois deles com um dia de idade.
É uma tese bem formulada com evidência fina, e é marcada **[c]**.

### Defesa à distância: três formas, agora com magnitude

Um caso mais recente mostra o padrão sob uma forma mais traiçoeira: a
correção que existe, mas cuja garantia depende de uma verificação em outro
lugar.

**(a) Uma proteção que só dispara dentro de uma ferramenta que ninguém é
obrigado a usar.** A proteção contra deriva de versão do Ollama existia pela
metade: a versão estava em todo registro de execução, e `compare.py` se
recusava a comparar execuções de versões diferentes. A comparação de 1 para 7
sucessos entre a execução B (Ollama 0.34.4) e a C (0.35.1) foi feita em prosa,
lado a lado, fora dessa ferramenta. Uma verificação que só dispara dentro de
uma ferramenta de uso opcional não é uma verificação.

**(b) Correção que vale por causa de uma verificação a montante, e não por
recusa local.** A ferramenta de inspeção manual (`run_single.py`) construía o
cliente a partir das configurações e era o único caminho capaz de gerar uma
execução sem perfil e sem checagem da versão do servidor; a comparação aceitava
tal execução contra as históricas sem perfil. E o ramo legado do
`_graph_runner` (um cliente Ollama sem perfil) só não rodava porque
`check_environment` recusava antes. A correção em ambos os casos foi a recusa
*local*: a ferramenta exige perfil e passa pelo mesmo `build_client` e pela
mesma checagem; o ramo legado agora lança um erro que diz que uma execução
Ollama sem perfil não é permitida, com um teste que o chama diretamente, sem
passar por `check_environment`. A propriedade que vale porque outra checagem
dispara antes quebra em silêncio no dia em que alguém reordena ou condiciona
essa checagem.

**(c) A janela de 37 minutos.** O Ollama do host se atualizou sozinho entre
uma leitura que deu 0.40.7 e o lançamento da execução, que encontrou 0.40.8: as
duas leituras são do mesmo dia, a cerca de 37 minutos uma da outra. A leitura
anterior era válida quando feita e estava velha quando a execução começou.
Quem fosse confiar nela, ou em qualquer checagem feita em outro momento ou em
outro lugar, teria rodado em 0.40.8 sob a crença de 0.40.7. O que impediu isso
foi a recusa *no ponto de risco*: o portão de versão consulta o servidor no
início da execução e recusou. Este é o argumento mais forte para a recusa
local no ponto de uso, e a forma mais forte da afirmação: **a verificação tem
de ser feita onde e quando o risco se materializa, porque o estado que ela
protege muda por baixo dela, sem aviso, em escalas de minutos.** (O portão de
versão é, por desenho, uma checagem de início de execução; uma atualização
*durante* uma execução ele não pega. O cache de respostas é, desde então,
chaveado pela versão do servidor lida a cada chamada, o que fecha a repetição
silenciosa, mas não a mistura de duas builds numa mesma execução.)

**Evidência [a] para (a), [b] para (b), [b] para (c).** (a) é demonstrável
pelo próprio capítulo 5 (§5.7). (b) e (c) são casos únicos traçados nos
registros e no histórico de commits; o horário das duas leituras e do commit
da recusa os sustenta, mas é um evento.

**A magnitude.** A recusa que parecia pedantismo — fixar a versão, nomear as
duas, abortar, exigir um repinamento deliberado e registrado — preveniu que
duas builds fossem tratadas como a mesma. Entre as builds 0.35.1 (execução C) e
0.40.8 (execução E), mesmo arquivo de modelo, mesmo código do laço, mesma
semente e mesmos enunciados, **o código final difere em 102 das 120 tarefas**
e o status final difere em 36 das 120 (apenas 84 coincidem). *[a; a pôr no
cap. 5]* O host mudou de versão quatro vezes em 30 dias (0.34.1, 0.34.4,
0.35.1, 0.40.7, 0.40.8), a última em minutos; as notas contam a última como a
sexta instância do padrão do estado ambiente herdado e a primeira capturada de
antemão.

**Generalização.** Alcança qualquer pipeline cuja correção repousa numa
verificação a montante: uma checagem de entrada que o resto do código presume,
um *linter* que a integração contínua deveria rodar, uma validação de esquema
feita na borda e confiada no interior. A pergunta de projeto é: o que acontece
no módulo que está à jusante no dia em que a verificação a montante deixa de
rodar, é contornada ou fica velha? Se a resposta é "continua parecendo certo",
a garantia não é do módulo.

---

## 6.5 Medir o que se pensa estar medindo

**A afirmação.** A parte mais cara deste trabalho não foi construir o sistema,
foi garantir que cada número medido correspondia à pergunta que se achava
estar respondendo. Os defeitos aqui têm uma forma própria: não produzem falha,
produzem um resultado que parece medida.

### Um controle que dispara vale mais que uma hipótese que confirma

Antes de corrigir o roteamento de `MissingImport`, a predição registrada
declarou `compila@1` e `verificado@1` como **controles**: ambas medem a
tentativa 1, que acontece antes de existir qualquer roteamento, e nenhuma
mudança no crítico pode movê-las. Com sementes, prompt e corpus idênticos,
tinham de voltar iguais. `compila@1` voltou de **10,9% para 15,6%** (Ollama
0.34.1): um aumento relativo de 43%, na direção certa, numa métrica de
compilação, logo após uma correção que faz código compilar. Seria um resultado
publicável, e é falso: a correção atua em tentativas ≥ 2, e a métrica mede a
tentativa 1. O salto era ruído de amostragem não declarado: das 360 duplas
(tarefa, semente) compartilhadas entre as duas execuções, **94 (26,1%)**
produziram um erro de tentativa 1 diferente, com o mesmo modelo, semente,
prompt e índice. **[a]**

O espelho é igualmente instrutivo. Uma **refutação** é compatível com um
instrumento quebrado tanto quanto uma confirmação. O orientador propôs que,
sob `temperature=0`, as três sementes por tarefa seriam redundantes, o que
cortaria a suíte para um terço. A hipótese foi testada e refutada com números
que pareciam decisivos: em ~66% das tarefas as três sementes davam código
diferente, com o mesmo padrão nas duas execuções completas. Mas as sementes de
uma tarefa rodavam em sequência sobre o mesmo estado de servidor, e a
concordância entre as duas execuções, que fazia a refutação parecer sólida, era
replay. Sob reset por execução, as duas tarefas examinadas deram as três
sementes idênticas. **[b]** (duas tarefas; o que sustenta o achado é que a
evidência usada na refutação não distinguia a hipótese do artefato, não a
medida posterior.)

### N fontes de não-determinismo em série

Fixar a mais óbvia não resolve. **Fonte 1**: `temperature` não era enviada
pelo cliente, e era herdada do Modelfile (quatro chamadas com o mesmo prompt e
semente deram duas saídas distintas; com `temperature=0`, quatro idênticas;
Ollama 0.34.1). Corrigida, a divergência por tarefa foi de 50,0% para 36,7%,
e a da tentativa 1 **não se moveu** (26,1% → 28,3%): **fonte 2**, a ordem de
chunks devolvida pelo recuperador, porque a fusão RRF produz empates exatos
que o Qdrant desempata na ordem dos segmentos; o *conjunto* de chunks era
estável, a *ordem* não, e a ordem é a ordem em que aparecem no prompt. **Fonte
3**: o estado interno do servidor entre tarefas (cache de prompt e KV)
descarregado uma vez por execução, não por (tarefa, semente). **Fonte 4**: a
própria build do servidor (abaixo). **[a]**, com os números de cada etapa. O
teste que validou `temperature=0` foram quatro chamadas do mesmo prompt,
quentes, em sequência: provou que o modelo é determinístico dado um prompt, e
não que o prompt era o mesmo.

### Um teste fora do regime de produção passa, qualquer que seja a qualidade

Cinco testes isolados do gerador (mesmo prompt quatro vezes; prompt longo;
`num_predict` 256 e 4096; prompt-alvo intercalado com outros; prompt-alvo
depois de A, de B, de A e B) passaram todos. O piloto de 20 tarefas rodado duas
vezes, cache frio, dois processos, ordem real, divergiu em **15% das sequências
de erro e em 5 de 20 códigos gerados**. **[a]** O regime importa tanto quanto o
ambiente: o "piso de ruído zero", **0 em 360**, foi medido em produção e em
escala (execuções A e A2, Ollama 0.34.1), mas sob uma sequência de chamadas
fixa e um único descarregamento do modelo. Mediu determinismo de *replay* —
mesma história, mesma saída — e não que o resultado de uma tarefa independe das
outras. O número estava certo; a leitura estava errada. Seis execuções
repetidas a frio mostraram `dj_constant_4q` idêntica nas três sementes e
`qaoa_maxcut_4q_perturbed` divergente nas três; rodada sozinha, duas vezes,
idêntica; precedida de `dj_constant_4q`, diferente. Com o descarregamento por
(tarefa, semente), as seis (tarefa, semente) deram **6 de 6** byte-idênticas
em duas ordens. **[a, n = 6]**: mostra que o mecanismo foi removido, não que
há independência sobre 360.

### Reconhecer o padrão esperado não é evidência

Cometido duas vezes nas notas, e uma terceira depois. Primeiro, uma justificativa para a validação de
nomes de portas em `GATES_SUBSET_OF` ("um nome digitado errado torna a asserção
vacuamente verdadeira, mesma direção de falha das três instâncias anteriores")
era convincente por casar com um padrão estabelecido e foi endossada antes de
implementar; ao derivar a lógica de conjuntos, a alegação estava errada — uma
checagem de subconjunto é fail-closed por construção. **[b]** Depois, um *smoke*
de quatro execuções após a correção de `ImportError` mostrou um sucesso e dois
chegando ao semântico (contra zero antes) e foi lido como confirmação
antecipada; quatro execuções, com o ruído medido depois, não distinguem nada.
**[b]** E uma terceira vez, mais recente, descrita em §6.1: a alegação de orçamento
"frouxo" já tinha virado achado quando a linha de base foi conferida.

### Determinismo vale para a build em que foi medido

O nó planejador recebe só o enunciado da tarefa e um prompt de sistema fixo:
sem recuperação, sem tentativa anterior, sem estado acumulado. O código dele
não mudou, nem o de nenhum nó, do grafo ou da recuperação entre a execução C
(Ollama 0.35.1) e a E (0.40.8). Mesmo assim, **os requisitos que o planejador
devolveu diferem entre as duas builds em 34 das 120 tarefas** (28%): mesma
entrada, mesmos pesos (o arquivo do modelo não foi baixado de novo),
`temperature=0`, mesma semente, servidor reiniciado a cada execução. Em
`vqe_h2_r055`, por exemplo, o `output_format` saiu `"numeric"` em C e
`"fixed_circuit"` em E. **[a; a pôr no cap. 5]**

A generalização é que uma afirmação de determinismo sem qualificação é falsa.
Ela vale para uma build de servidor, e o "0 em 360" significa 0 em 360 *para
uma build* — e, pelo parágrafo anterior, para um regime de replay. Quem pensa
em fixar a semente e a temperatura como garantia de reprodutibilidade de um
modelo hospedado deve tratar a versão do servidor de inferência como parte
da semente.

### O replay: um número que parece medida e é cópia

Esta é a instância central da seção. A primeira execução E (7B, Ollama 0.40.8)
deu 7/120 sucessos, `compila@1` 20/120 e veredito semântico 57/120 — números
plausíveis, quase iguais aos da execução C — em **9 minutos** de execução,
contra os 72 da C. Era um replay do cache de respostas da C: o cache era
chaveado por `modelo|semente|system|prompt`, o *nome* do modelo não mudou, e a
build do servidor sob esse nome sim (0.35.1 → 0.40.8). O portão de versão
checou o servidor e passou; ele não vê o cache. **Nada na saída mostrava o
replay.** O único indício foi o tempo de parede, lido depois de as execuções
seguintes já estarem na fila: 117 dos 120 registros com `latency_s` abaixo de 5
segundos, e 13 arquivos novos no cache. **[a]**

O que torna o caso mais que um tropeço é a *direção* do erro. Um replay devolve
resultados idênticos entre builds. O número não notado teria lido como evidência
limpa e citável de que a build do servidor **não importa** — exatamente o
inverso do que a execução fria mediu em seguida (a divergência de 34 em 120 nas
saídas do planejador, o código final diferente em 102 de 120). Não é ruído
produzindo incerteza: é um artefato silencioso produzindo uma resposta
confiante com o sinal invertido. E a execução fria, ainda, teve o agregado
quase idêntico (7 contra 5 de 120, `compila@1` 20 contra 19): se a primeira
tivesse sido a única, e a segunda lida só pelo agregado, a conclusão errada teria
sobrevivido às duas.

O que mudou no instrumento: a chave do cache passou a incluir tudo de que a
resposta depende — o digest resolvido do modelo, a build do servidor (consultada
a cada chamada), os parâmetros de amostragem e `max_tokens`, de modo que uma
mudança é uma falha de cache fria, e não um acerto errado; um servidor que não
diz o que é não usa o cache. E toda execução termina declarando quantas
chamadas vieram do cache (`COLD`, `PARTLY WARM` ou `REPLAY`), em cada registro,
no `stderr` e em `cache_summary.json`. A lição não é sobre o cache: um replay
pode ser desejável (retomar uma execução interrompida). O perigo estava em ele
ser invisível, e é por isso que o remédio é a visibilidade, e não a proibição.

**Generalização.** Alcança qualquer sistema com memoização entre o experimento
e o sistema sob teste — caches de resposta de LLM, caches de build, resultados
de CI reaproveitados, testes de regressão contra respostas gravadas: se a
chave da memoização omite qualquer coisa de que a resposta depende, uma
mudança nessa coisa produz acertos errados, e a saída do teste parece idêntica
à de um sistema que não mudou.

### Uma premissa não verificada sob um teste que parecia discriminar

Registra-se aqui uma quarta instância de construir um teste discriminante sobre
uma premissa não verificada, e ela tem uma origem comum. O teste da contagem de
tokens assumia que o registro de erro armazenado serve de impressão digital da
tentativa: se o registro de erro é idêntico entre C e E e os tokens diferem,
a causa seria a contagem do servidor, e não tentativas intermediárias
diferentes. Não serve, e não pode servir: a taxonomia de erros é fechada, e
portanto com perda por desenho — dois circuitos quebrados de modos diferentes
colapsam para a mesma classificação. É a propriedade que a torna útil para
roteamento e inútil como impressão digital.

Os registros decidiram, sem rodar nada: das 18 tarefas de C e E com status,
iterações e código final iguais, 12 têm `input_tokens` idênticos e 6 diferem.
Nenhuma das 6 tem uma iteração (todas têm 2 a 5), de modo que a regra "uma
iteração prova mudança de contagem" não se aplica. Em 3 das 6 a variação de
tokens de entrada é igual à de saída (+10/+10, −45/−45, −5/−5): os tokens a
mais gerados numa tentativa voltam como entrada na seguinte, a assinatura de
uma tentativa intermediária diferente, não de contagem diferente. Em 5 das 6 o
texto guardado no *trace* difere (dicas e justificativas do crítico, requisitos
do planejador) sem que o registro de erro difira. As 12 com entrada idêntica
mostram que a contagem de prompt não mudou. **[a, n = 18 / 6]**: as 6 sustentam
"tentativas intermediárias diferentes com o mesmo registro de erro", e nenhuma
sustenta "a contagem mudou".

As quatro instâncias que as notas permitem reconstituir são: a hipótese de
que as sementes seriam redundantes sob `temperature=0` (a premissa, de que as
duas execuções comparadas eram independentes, era do orientador); o teto de 9
sucessos tratado como suspeito na predição de T090d (escrita no próprio
registro, e retratada: a heurística de teto estava errada, e o controle é que
decide); a premissa de que uma execução abortada por recursos tinha cinco
`ResourceExcess` quando tinha um (estava no pedido de verificação); e o teste de
contagem acima (também no pedido). Nas quatro, a premissa errada estava no
enunciado do teste, na hipótese, na predição ou no pedido de verificação, antes
de qualquer código rodar, e nenhuma foi produzida pelo código sob teste. Isso
importa para o remédio: o que falta a um teste discriminante não é
mais código, é uma checagem da premissa contra os registros *antes* de
construir o teste em cima dela, que é barata quando os registros existem.

---

### A leitura da taxa de regressão

"A taxa de regressão estava estável em ~55% e depois caiu" não sobrevive ao
espalhamento por semente da execução T102 (baseline de 19/09, Ollama 0.34.1,
341 execuções válidas): 10/19 = **52,6%**, 35/55 = **63,6%** e 18/39 =
**46,2%**. Três sementes não independentes dão uma faixa de 46% a 64% que a
agregação em 63/113 = 55,8% esconde. A afirmação defensável é mais fraca: os
dois estados anteriores (T102, 55,8%, limite inferior e anterior ao *trace*; e
a execução B, Ollama 0.34.4, 40/74 = 54,1%) caem na mesma faixa de 46–64%, e a
execução C (Ollama 0.35.1, 29/88 = 33,0%) fica abaixo dela. **[a]** Três
ressalvas continuam valendo: os estados diferem em protocolo, corpus e
contaminação; a composição do denominador mudou (chegar ao semântico foi de
113/341 para 74/120 e 88/120); e a queda B → C está confundida com a versão do
servidor.

### O instrumento fraco esconde o defeito do texto

Cinquenta e dois dos 120 enunciados da suíte, todos variantes perturbadas,
citam a tarefa-base pelo `task_id` ("the standard circuit as in the
ising_field_coupling_4q task"), um identificador interno vazando para o que
devia ser uma descrição autossuficiente. Ninguém viu antes, porque o gerador
local raramente chegava a algo que dependesse de interpretar o enunciado com
cuidado. Só um modelo capaz o bastante para ler com rigor, sem raciocínio para
contornar a ambiguidade (o braço sem raciocínio), recusou quatro tarefas no
planner, três pelo mesmo motivo. **[a]** (52/120 verificado na suíte; 4
recusas num braço.) É o mesmo mecanismo do teste fora do regime, do lado do
instrumento: o defeito estava no texto o tempo todo, e o gerador usado para
medir era fraco demais para tropeçar nele.

---

## 6.6 Diagnóstico e reparo

**A afirmação.** Num laço de reparo, o diagnóstico é a parte que decide, e um
diagnóstico incorreto é pior que nenhum: manda o gerador na direção errada com
a autoridade de um passo de verificação.

### Um diagnóstico incorreto é pior que nenhum

O laço de reparo recebeu um diff estrutural posicional (a porta `[i]` esperada
contra a obtida), que numa execução real contra `ghz_3q` apontou como erro
`cx(1,2)` contra `cx(0,2)` — a única parte certa, porque a topologia em
estrela é um GHZ válido — e nada disse do erro real (três portas H, em vez de
uma). O gerador local seguiu a prescrição e reproduziu o mesmo `cx(0,2)` como
"correção" nas iterações 1, 3 e 5. O mesmo código e o mesmo diff, colados
numa conversa nova com um modelo de fronteira, foram ignorados por ele, que
achou as portas H extras sozinho. Removida a renderização posicional, a mesma
tarefa com o gerador local passou de `failed_semantic` para `success` (na 5ª
tentativa, nas duas condições com o mesmo teto). **[b]** Uma tarefa, duas
condições, uma execução cada (Ollama 0.34.1). É uma ilustração do mecanismo.
O alinhamento posicional pressupõe uma ordenação canônica que não existe para
circuitos equivalentes, e por isso produz falsos positivos sempre que
referência e código usam decomposições diferentes, mas igualmente válidas.

A mesma estrutura apareceu depois, no laço, com o crítico. Nos três
Deutsch–Jozsa do braço de 30B no pod (Ollama 0.34.4), o gerador escreveu
Grover e o crítico, que não recebia o enunciado da tarefa, produziu dicas como
"verifique se o GroverOperator foi inicializado com o oráculo correto": cinco
tentativas, o mesmo algoritmo errado. O prompt do crítico era montado com o
tipo do erro, a mensagem e o código, e mais nada. A informação que desfaria o
erro (`expected_gate_counts = {h: 7, x: 1}` contra `actual = {Q: 1}`) existia e
era descartada, por uma tensão legítima: o conteúdo vinha da referência. **[b]**

### O laço quase sempre desiste

Das 335 falhas que chegaram a gerar código no baseline de 19/09 (execução
T102, Ollama 0.34.1, 341 execuções válidas), **331 terminaram por
esgotamento** das cinco iterações; as outras 4 foram recusadas na entrada. O
laço tem essencialmente um modo de término, a desistência, e os 6 sucessos são
a cauda, não o comportamento. A leitura ingênua ("zero acertos de primeira, e
o laço resgata 6") parece um laço que funciona pouco mas funciona. **[a]**
(331/335.) O custo de um diagnóstico errado escala com o limite de iterações:
cinco de um diagnóstico certo e cinco de um errado custam o mesmo em chamadas,
tempo e energia, e só difere se alguma delas podia funcionar.

### Retrieval não entrega conhecimento negativo

Das 112 execuções cuja última tentativa foi um `ImportError`, **104 (92,9%)**
foram sobre símbolos que nunca existiram em versão alguma do Qiskit (`H` 26,
`RZ` 24, `CNOTGate` 20, `CNOT` 12, `RY` 7, `Hadamard` 7); 5 (4,5%) foram
ensinados pelo corpus; 2 eram módulo ou natureza errados; 1 era um símbolo
removido. Sobre todas as 570 tentativas com `ImportError` (36 símbolos), 499
(87,5%) nunca existiram. Uma página de documentação diz o que existe; nenhuma
diz o que não existe. A hipótese de que "mais documentação corrige" tem o
sentido errado para esta classe. **[a]** (104/112; 499/570; contra o runtime
1.2.4 e o corpus.)

Os símbolos inventados não são aleatórios: dos 499, **261 (52%)** são nome
exato de operação do PennyLane 0.38 instalado no mesmo ambiente (`RZ` 118,
`CNOT` 48, `Hadamard` 44, `RY` 36), e 94 (19%) são o nome do PennyLane com o
sufixo `Gate` do Qiskit (`CNOTGate` 85): 71% é nomenclatura de outro
*framework*. **[a]** para a correspondência. A leitura causal, "transferência
de vocabulário vinda do pré-treino", é uma inferência (o PennyLane não está no
corpus) que nenhuma medida isolou: **[c]** para a causa.

### O trace descartado era o que o diagnóstico precisava

O trace de cada execução (consulta enviada, número de chunks, decisões do
crítico) era acumulado e descartado ao fim: o registro persistia 24 campos,
nenhum deles o trace. O diagnóstico post-hoc do comportamento de recuperação
era **impossível** em qualquer execução já feita (2.160 execuções em seis
execuções completas). O próprio código enunciava a regra sobre o histórico de
erros ("um modo de falha que só aparece num trace que ninguém persiste é um
modo de falha que ninguém mede"), aplicada ao erro do planner e não ao trace
inteiro. **[a]** (24 campos, 0 do trace, 2.160 execuções.)

### Com o enunciado à vista, o crítico re-planeja

Depois de o crítico passar a ver o enunciado, a primeira dica nos
Deutsch–Jozsa deixou de diagnosticar o Grover e passou a descrever a
construção pedida inteira. Crítico e planejador passaram a se sobrepor: cada
iteração é "planejar de novo com o erro acumulado à vista", e não reparo no
sentido estrito (alterar o artefato existente no que falhou). Isso não diminui
o resultado e não é um erro, mas o relatório tem de nomear o mecanismo: re-planejar
com o erro à vista convergiu onde um diagnóstico cego não convergia; não mostra
que o sistema conserta circuitos. **[b]** (a observação vem dos Deutsch–Jozsa
de um braço de n = 16.)

### O que a medição isolada mostrou

Três comparações, todas no subconjunto de 16 tarefas, com o gerador de 30B no
pod (Ollama 0.34.4), são as únicas em que uma variável foi isolada. **[a, n = 16]**

- **O vazamento ajudava.** A mudança que fechou o vazamento de informação
  derivada da referência (a única mudança entre R2 e R3) levou o sucesso de 9
  para 6: o vazamento valia 3 tarefas, e a diferença mede o que valia o
  vazamento, não o que vale o sistema.
- **Edição em vez de regeneração.** Passar o código anterior e pedir edição
  (R3 → R4, a única comparação com uma só variável) levou o sucesso de 6 para
  10 de 16, acima da banda 7–9 registrada antes. O custo também foi medido:
  alternâncias A→B→A caíram de 11 para 1, mas falhas idênticas consecutivas
  subiram de 5 para 11. Um diagnóstico mais firme reduz oscilação e aumenta
  fixação. O valor líquido é de quatro tarefas em 16.
- **Capacidade e engajamento do laço são inversamente relacionados.** No
  gerador local de 7B o laço engaja em todas as execuções do subconjunto (16 de
  16) e resgata seis de sete sucessos da execução C (Ollama 0.35.1); no modelo
  de fronteira engaja em zero a duas de 16, porque quase nada precisa de
  resgate. O laço é um instrumento de recuperação: o valor dele cresce à medida
  que o gerador piora.

**Generalização.** Qualquer laço de reparo mediado por um modelo tem de
distinguir três coisas que costumam vir juntas: **reparar** (alterar o que
falhou), **re-planejar** (gerar de novo com o erro à vista) e **diagnosticar**
(dizer por que falhou). Elas respondem a perguntas diferentes, falham de modos
diferentes, e um resultado positivo de uma delas não prova as outras. O
diagnóstico errado custa o mesmo que o certo e vale menos que nada, e a fonte
do diagnóstico precisa ter acesso ao que o gerador não sabe — sem ter acesso
ao que o benchmark sabe e o usuário real não saberia.
