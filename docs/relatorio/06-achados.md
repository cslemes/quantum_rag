<!--
NOTA AO AUTOR (remover antes da versão final).

GRAU DE EVIDÊNCIA. Cada achado traz, entre colchetes, o grau da evidência:
  [a] medido, com número e denominador;
  [b] mecanismo traçado em um caso — ilustração, nunca efeito medido;
  [c] fino — afirmado nas notas sem nenhum dos dois.
Os achados de grau [c] estão listados também no relatório de entrega, para decidir o que cortar.

CONFLITOS COM O CAPÍTULO 5: resolvidos em 2026-10-23 (§5.2, §5.3, §5.7 e o esqueleto foram corrigidos; ver o histórico).
  Resta uma pendência: o texto de substituição do §5.3 para o resultado do planejador citado no pedido não existe nos registros da
  sessão; o parágrafo do §5.3 sobre as 34 de 120 foi escrito a partir das notas.

LEITURAS A CONFIRMAR.
  - "Lado consultivo" (6.5): as seis instâncias são as indicadas pelo autor; a terceira (GATES_SUBSET_OF) está rotulada como falha de revisão.
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

**Regra de redação.** Toda cifra em prosa nomeia a execução ou o estado do
sistema em que foi medida, e isso inclui o *estado do código* (corpus, correções
já aplicadas), não só a build do servidor. Nenhuma cifra de um estado anterior a
uma correção é usada no presente: é rotulada como histórica, com a execução e o
denominador, ou re-derivada no estado vigente (§6.5, "Uma cifra interna de antes
da correção"). Durações têm dois nomes fixos, tempo de relógio e tempo de
execução, nunca sem nome (capítulo 5, §5.6).

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
A mesma estrutura aparece em **snapshot testing**: a primeira execução grava a
saída como esperada e as seguintes comparam contra ela, de modo que, se a
implementação original estava errada, o snapshot registra o erro como
especificação e o critério vem do artefato. A mesma estrutura aparece em
**testes escritos por um LLM para código escrito por um LLM**: há dois
artefatos, em arquivos e momentos diferentes, e a fonte do critério e a do
comportamento é a mesma. Nenhum dos dois casos foi medido neste trabalho; são
analogias estruturais com o caso medido acima, e valem como tais. Pela mesma
estrutura, trocar o modelo que escreve os testes muda a fonte do artefato sem
mudar a fonte do critério.

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

**Evidência [a].** Cinco erros em **120 referências construídas** (uma por
tarefa da suíte: 114 circuitos QPY e 6 Hamiltonianos em JSON), cada erro
reproduzido por computação.

### O escopo de uma gramática, achado por uso

Antes de implementar a gramática de asserções, três tarefas de tiers
diferentes foram escritas à mão, sem consultar a especificação, para forçar à
tona onde um usuário tropeçaria. O exercício revelou limites de escopo. O mais claro: toda
asserção, sem um mecanismo de preparar entrada, só testa comportamento a
partir de `|0…0⟩`, e a QFT aplicada a `|0…0⟩` produz a mesma superposição
uniforme que um `H` em cada qubit — nenhuma asserção ancorada só em `|0…0⟩`
distingue uma QFT correta de uma implementação que não é QFT nenhuma. Isso
motivou o prefixo `INPUT(…) THEN <asserção>`.

**Evidência [b] para cada limite**, apresentados como ilustração. O caso da QFT
foi verificado por computação.

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

### Uma premissa extraída por um LLM: a coerção silenciosa

Os requisitos que o planner extrai da descrição (`n_qubits`, `gate_set`) são
checados de forma determinística contra o circuito gerado, mas a *premissa* é a
leitura de um modelo de linguagem. Antes da checagem, a coerção silenciosa do
Pydantic transformava `"value": true` num requisito de 1 qubit, `false` num de 0
e `3.0` em `3`, tratando-os como requisitos checados: um valor que o planner
não produziu como número virava um número a verificar. A regra de desenho que
governa o peso desses requisitos ("requisitos vetam, nunca estabelecem") é uma
decisão de desenho e está no capítulo 3 (§3.8).

**Evidência [b].** A coerção é um defeito reproduzido em casos individuais.

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
recuperação de então (o corpus 2.x, depois substituído pelo corpus 1.2 de 875
chunks, o das execuções B a G), e o conteúdo não era da 1.2.4: o corpus foi raspado da
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

### O código cortado que virou erro de sintaxe: o mecanismo

Na run F (1,5B, Ollama 0.40.8), 77 das 118 falhas repetiram o mesmo erro nas cinco tentativas, e **51** delas eram
um só modo: a geração degenerava em repetição até o teto de 4.096 tokens e nunca fechava a cerca do bloco de
código (média de 21.055 tokens de saída por execução, contra 2.239 nas demais). O mecanismo da rotulagem errada
tem três passos. (1) `_extract_code` procura um bloco com cerca de abertura **e** de fechamento; sem a de
fechamento ele cai no texto bruto, que começa pela cerca de abertura. (2) O sandbox executa esse texto, e o erro
é `invalid syntax (<unknown>, line 1)`. (3) O classificador de fechamento (§6.6) chama isso de `SyntaxError`.
"O modelo não terminou" virou "o modelo escreveu sintaxe errada", no registro, na string `error_type=SyntaxError`
mostrada ao gerador na repetição, e na contagem. A causa a montante é de decodificação: o Ollama 0.40.8 **não
envia penalidade de repetição por padrão** (um `repeat_penalty` não enviado deu saída idêntica à de 1.0 e diferente
da de 1.1), um parâmetro de amostragem herdado e nunca fixado, a mesma classe de F15. **[a]** (51 de 77; o texto
final das 51 começa por cerca aberta e termina no meio de uma frase; a equivalência "não enviado = 1.0" medida na
build.)

Duas correções, nenhuma reescreve F. O gerador agora rotula `GenerationTruncated` quando a resposta atinge o teto
**e** não fecha a cerca (nada é executado), do mesmo modo que o professor de destilação já tinha seu código
`truncated:finish_reason_length`. E o 1,5B ganha uma segunda configuração, **F-prime**, com penalidade de repetição
1.1, medida numa nova execução, porque a penalidade é parte da identidade do modelo; F continua sendo a comparação
de configuração idêntica contra E, e a afirmação de escala do capítulo 5 repousa nela. A previsão para F-prime foi
registrada antes de rodar (`distill-pilot-families.md`), e **falhou na quantidade que importava**: a degeneração
diminuiu (51 execuções para 18), mas a fração de falhas presas não caiu para perto dos 38,8% medidos nas que não eram
truncagem; subiu (65,3% para 67,2%), porque as falhas presas que não são truncagem passaram de 26 para 62 assim que o
programa passou a executar. O sucesso foi 0 de 120, abaixo da faixa prevista de 2 a 5, e longe do limiar de 10 que
reescreveria a narrativa do 1,5B. A confusão de decodificação era real (a executabilidade dobrou), mas não era o que
a narrativa sustenta. **[a]** (F-prime `cf4ba161…`, uma execução, 120 tarefas.) Uma previsão registrada que falha é o
resultado útil: a hipótese "o laço trava por culpa da decodificação" foi testada e refutada, e a premissa da
sensibilidade ao reparo ficou de pé, agora numa linha de base que não está confundida.

---

## 6.4 Regras que não se propagam

**A afirmação.** Uma regra correta, enunciada num lugar, não alcança o código
ao lado. As notas registram a classe de maior rendimento como **estado ambiente
herdado**: tudo que o experimento herda do ambiente sem declarar nem fixar, e
que pode alterar a medição. Nomear a classe permite enumerar os candidatos
(driver da GPU, binário do Ollama, estado interno do servidor), o que "regras
não se propagam" não permite.

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
- **O estado do processo-pai herdado por um `fork`.** Depois que o orquestrador
  usou o pool Rust do Qiskit (`SparsePauliOp.to_matrix()`, ou `Operator` de um
  `SparsePauliOp`), um *worker* do sandbox criado por `fork` a partir dele trava,
  até o *timeout* de 60 s, na mesma chamada dentro do código gerado; o cascata
  rotula o *timeout* `SyntaxError`. Reproduzido de forma determinística. A
  primeira correção, criar o pool antes, protegia só os *workers* que existiam
  naquele momento: um *worker* substituído depois (após *timeout* ou após 50 usos)
  é bifurcado do pai já contaminado, e o teste dessa trajetória travou. O
  executor da suíte de regressão estava exposto desde sempre, porque `main()`
  roda `verify_references` (que usa `Operator` de `SparsePauliOp` nos oráculos de
  energia) *antes* de criar o pool. O dano medido nas execuções A, A2, B, C, E, F
  e G foi de **um registro em A e o mesmo em A2** (§5.7). A correção estrutural é
  os *workers* serem interpretadores novos, não *forks*: a ordem deixa de
  importar. A reordenação de `main()` (criar o pool antes de `verify_references`)
  **não** foi aplicada, e a razão é o próprio padrão desta seção: ela protegeria
  por ordem, à distância, e deixaria a aparência de duas proteções onde há uma. A
  proteção é a recusa local (processos novos), e foi testada nas trajetórias de
  substituição, que a ordenação não cobre. *[a para o mecanismo, reproduzido; o alcance é o da varredura dos
  registros]*
- **Uma regra de parada que parou onde foi escrita.** O projeto já decidiu que uma
  falha idêntica repetida significa parar: `critic.py::_is_repeated_not_evaluable`
  aborta quando a mesma asserção volta "não avaliável" em duas iterações
  consecutivas, com a justificativa no código ("evidência de que regenerar não
  está convergindo"). Foi implementada para esse único tipo de erro e nunca chegou
  ao código ao lado: a falha idêntica repetida de qualquer outro tipo não é
  detectada, e as runs C, E, F e G gastam as cinco gerações em toda falha (§6.6).
  Além disso, o caminho onde a regra existe não é exercido pela suíte, que não usa
  asserções: nas runs medidas ela não pôde disparar nem uma vez. *Registro exato,
  porque não é um gêmeo perfeito de `assert_full_gpu_offload`:* aquela proteção não
  tinha chamador nenhum; esta tem chamador (`route_action`) e testes (unitários e
  de integração), e funciona no produto. O que ela compartilha é a forma: uma regra
  correta, enunciada num lugar, que as medições nunca tomam. A generalização que
  sai do detalhe: a regra não pôde disparar uma única vez em 461 execuções porque a
  suíte não tem asserções, de modo que ela está **viva no produto e morta nas
  medições**. A suíte exercita um subconjunto dos caminhos do produto, e uma
  funcionalidade que só dispara nos caminhos não exercitados **não está medida**,
  por mais bem que funcione. *[a]* para as
  contagens (nenhuma parada antecipada em 461 execuções falhas ou abortadas de C, E,
  G e F), *[b]* para a leitura do código.
- **O estado interno do servidor entre tarefas.** O descarregamento do modelo
  era feito uma vez por execução da suíte, não por (tarefa, semente); o cache
  interno de prompt e KV do Ollama carregava estado de uma tarefa para a
  seguinte (§6.5).

### Defesa à distância: quatro formas, agora com magnitude

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

**(d) A ausência de uma pré-condição fazendo o papel de autorização.** O
script do piloto de destilação precisava de uma credencial para chamar a API, e
ninguém precisou escrever "só gaste quando mandarem": enquanto a chave não estava
no `.env`, o script não gastava. Quando a chave foi posta lá para outro fim, o
script que eu só queria ver *iniciar* fez **40 chamadas reais** (US$ 0,0096)
antes de ser interrompido. Nada o recusou, porque a recusa nunca existiu: o que
existia era um impedimento ambiental que passava por controle. A correção é a
recusa *positiva e local*: o script exige `--authorize-spend USD` (um teto,
no mínimo o teto de parada), checado antes de a credencial ser sequer procurada,
e a função que chama a API exige um objeto de autorização, não um cliente. Uma
credencial presente não é permissão para gastar. *[b: um evento, rastreado nos
40 registros e no custo reportado pela API]*

**Evidência [a] para (a), [b] para (b), [b] para (c), [b] para (d).** (a) é demonstrável
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
teste feito para confirmar `temperature=0` foi de quatro chamadas do mesmo prompt,
quentes, em sequência: provou que o modelo é determinístico dado um prompt, e
não que o prompt era o mesmo.

### Um teste fora do regime de produção passa, qualquer que seja a qualidade

Cinco testes isolados do gerador (mesmo prompt quatro vezes; prompt longo;
`num_predict` 256 e 4096; prompt-alvo intercalado com outros; prompt-alvo
depois de A, de B, de A e B) passaram todos. O piloto de 20 tarefas rodado duas
vezes, cache frio, dois processos, ordem real, divergiu em **15% das sequências
de erro e em 5 de 20 códigos gerados** (estado de F15/F17, anterior ao reset por
execução; a build do servidor não foi registrada nesse ensaio). **[a]** O regime importa tanto quanto o
ambiente: o "piso de ruído zero", **0 em 360**, foi medido em produção e em
escala (execuções A e A2, Ollama 0.34.1), mas sob uma sequência de chamadas
fixa e um único descarregamento do modelo. Mediu determinismo de *replay* —
mesma história, mesma saída — e não que o resultado de uma tarefa independe das
outras. O número estava certo (re-derivado dos registros: nenhum dos 360 pares divergiu em status, código final, iterações, contagem de tokens nem sequência de erros, e as duas execuções levaram o mesmo tempo de parede por tarefa, mediana da razão 1,00, o que exclui que a segunda tenha sido servida pelo cache de respostas); a leitura estava errada. Seis execuções
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
era convincente por casar com um padrão estabelecido e foi confirmada na
revisão antes de implementar (a falha de revisão é tratada abaixo, entre as
seis premissas); ao derivar a lógica de conjuntos, a alegação estava errada — uma
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
uma build* — e, pelo parágrafo anterior, para um regime de replay. Sob o
protocolo vigente há agora uma repetição da suíte na mesma build: **0 em 120**
diferenças entre as execuções G e E (Ollama 0.40.8, uma repetição, uma semente),
e a invariância das três sementes na rodada B (Ollama 0.34.4, 120 em 120). Cada
medida vale para o seu escopo, e a mais forte não substitui as outras. Quem pensa
em fixar a semente e a temperatura como garantia de reprodutibilidade de um
modelo hospedado deve tratar a versão do servidor de inferência como parte
da semente.

### O replay: um número que parece medida e é cópia

Esta é a instância central da seção. A primeira execução E (7B, Ollama 0.40.8)
deu 7/120 sucessos, `compila@1` 20/120 e veredito semântico 57/120 — números
plausíveis, quase iguais aos da execução C — em **2,4 minutos de
execução**, contra os 66,1 da C (o intervalo do primeiro ao último registro foi de
8,5 contra 72,1). Era um replay do cache de respostas da C: o cache era
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

Registra-se aqui uma instância recente de construir um teste discriminante
sobre uma premissa não verificada. O teste da contagem de tokens assumia que o
registro de erro armazenado serve de impressão digital da
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

**Seis premissas erradas do lado consultivo.** A palavra "consultivo" cobre aqui
o enunciado do teste: a hipótese, a predição, o pedido de verificação e a
revisão. Em nenhuma das seis o erro foi produzido pelo código sob teste; todas
estavam no enunciado antes de qualquer código rodar.

1. **As sementes redundantes sob `temperature=0`.** Hipótese do orientador: as
   três sementes por tarefa seriam cópias, e a suíte poderia cair para um
   terço. A refutação rodou sobre um instrumento que contaminava as sementes
   umas com as outras (acima).
2. **`oracle_kind="resource"` para o tier 4 (D3h).** A especificação previa esse
   tipo de oráculo para as tarefas de recursos. Antes de qualquer construção,
   `grep` mostrou que o despacho de `make_semantic_check_node` não tem ramo para
   ele. As tarefas do tier 4 usam `statevector` ou `unitary`; o que as torna
   tier 4 é o mapa de acoplamento, e a checagem de recursos é ortogonal ao tipo
   de oráculo.
3. **`GATES_SUBSET_OF`: "vacuamente verdadeiro" para um nome de porta
   digitado errado. Falha de revisão, categoria distinta e pior.** A premissa
   errada nasceu na proposta de desenho; foi confirmada na revisão por
   reconhecimento de padrão ("mesma direção de falha das instâncias
   anteriores"), e não por derivação. Uma premissa que nasce errada é um erro;
   uma que passa pela revisão que existia para pegá-la é um erro com autoridade
   emprestada, porque a revisão a legitima. Só a derivação da lógica de
   conjuntos, ao implementar, a pegou.
4. **Os cinco `ResourceExcess` e a gêmea não perturbada.** A premissa do pedido
   de verificação era que a execução abortada por recursos tinha cinco
   `ResourceExcess`; tinha um, na quinta tentativa. A investigação que partiu
   dela adotou a profundidade da gêmea não perturbada como linha de base, e
   chegou ao orçamento "frouxo" retratado em §6.1: a gêmea é outra tarefa.
5. **O teste da contagem de tokens** (acima): o registro de erro não é impressão
   digital da tentativa.
6. **"Nenhuma verificação anterior à execução poderia ter pego a deriva de 37
   minutos."** Afirmada no pedido que originou esta própria seção. É falsa: o
   portão de versão, uma verificação de início de execução, foi o que recusou
   (§6.4(c)); o que nenhuma verificação feita antes ou em outro lugar pega é a
   atualização entre a leitura e o lançamento. **A sexta foi cometida enquanto a
   seção que documenta o padrão estava sendo escrita.**

O remédio comum às seis é barato quando os registros existem: checar a premissa
contra eles *antes* de construir o teste em cima dela.

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

### Holdout por família e treino útil estão em conflito direto

Um achado sobre o desenho do benchmark, não uma desculpa. Para destilar um modelo pequeno e ainda medir
generalização, escolheu-se uma fatia de **famílias retidas** (7 famílias, 24 das 120 tarefas), por uma regra cega
(ordenação por hash, sem olhar nenhum resultado), fixada antes de qualquer dado de treino. A regra de exclusão que
acompanhava a fatia, "nenhuma família de treino pode compartilhar mecanismo com uma família retida", foi aplicada
aos enunciados das 96 tarefas restantes: **64 das 96 nomeavam uma habilidade cuja única família de treino
compartilhava mecanismo com uma retida.** A habilidade real mais frequente (a fase diagonal exp(-iγH), 40
enunciados) saía porque o QAOA retido é esse circuito mais um misturador; saíam também as fases de Z-strings, QUBO
para Ising, fases controladas, a QFT e a QPE, Bernstein-Vazirani e Deutsch-Jozsa, a lógica reversível e Bell. Em
um domínio cujo espaço de algoritmos canônicos é pequeno e coberto densamente pela suíte, **uma fatia retida por
família e um treino útil estão em conflito direto**; aplicada com rigor, a fatia produz um resultado provavelmente
nulo nas duas partes. Não é um parâmetro a ajustar: é o desenho. A fatia (`heldout-v1`) foi **substituída, não
descartada em silêncio**: escolhida por regra cega antes de a consequência ser conhecida, e uma v2 escolhida agora,
com a consequência à vista, deixaria de ser cega; as 24 tarefas voltam ao conjunto de teste, a avaliação é sobre as
120, e a expectativa registrada de que a fatia fora da família leria 0 contra 0 fica superada. O que segura o
conjunto de teste de fora passa a ser o nível do enunciado e da resposta: a quase-duplicata lexical contra todo
enunciado de teste e a equivalência estrita do circuito contra as 120 referências. A afirmação final fica limitada
a: dados sintéticos verificados por oráculo, da mesma distribuição, melhoram um modelo pequeno em enunciados que ele
nunca viu; não é generalização fora da família. **[a]** (64 de 96, da varredura dos enunciados; a regra de
identidade de mecanismo é uma leitura operacional, descrita em `distill-family-selection.md`.)

### Uma cifra interna de antes da correção, citada no presente

É uma categoria à parte, e não uma subespécie da premissa não verificada. Uma
premissa errada produz uma *investigação* errada, que os registros ainda podem
pegar. Uma cifra velha, escrita no presente, produz um **número errado
publicado**. A fonte é a história do próprio projeto: uma medição que era
verdadeira quando feita, num estado do código que uma correção depois moveu, e
que continua circulando sem o estado em que valia. Quatro instâncias, achadas
por uma varredura dos capítulos 5 e 6:

- **"O import faltando é a causa dominante de falha do 7B, 39%."** A cifra
  (112 dos 287 `failed_static`) é do baseline de 19/09 (T102, Ollama 0.34.1),
  anterior ao roteamento de `MissingImport`. Nas execuções C e E (0.35.1 e 0.40.8)
  ele é 3,3% a 4,2% dos erros registrados e 3,3% a 3,6% dos `failed_static`
  finais. Foi proposta na revisão deste capítulo e **corrigida contra os
  registros antes de ser publicada** (§6.6).
- **`recall@8 = 0,9524` no §5.4.** Medida sobre o corpus 2.x de 1.020 chunks;
  o índice fixado das execuções B a G é o corpus 1.2 de 875 chunks, onde a mesma
  medida dá 0,9365 (59 de 63). Estava **publicada** no capítulo 5 sem estado e
  lida como o recall do sistema medido.
- **"72 minutos, para a suíte como configurada hoje"** (§5.6): o intervalo do
  primeiro ao último registro da run C (0.35.1), sem dizer qual medida era. As
  runs E e G (0.40.8) levaram 67–68 minutos de execução e 82–84 de relógio, e a
  primeira correção misturou as duas medidas (o 72 de C com o 81,7 de E). A
  correção que ficou é a regra de nomear a medida: tempo de relógio para "quanto
  leva", tempo de execução para "quanto cômputo consome".
- **"Não foi investigado"** (§5.3, o resumo do circuito serializado), texto que
  sobreviveu à investigação que o resolveu mais adiante no mesmo capítulo. Não é
  uma cifra, é a mesma falha em prosa.

O remédio é a regra de redação das convenções (cada cifra nomeia a execução e o
estado do código, e nenhuma cifra pré-correção vai para o presente) e a varredura
dos dois capítulos contra ela. **[a]** Quatro instâncias, uma delas capturada
antes da publicação; as outras três estavam no texto.

### O instrumento fraco esconde o defeito do texto

Na suíte de B e anteriores (antes de T116 reescrevê-los), cinquenta e dois dos
120 enunciados, todos variantes perturbadas, citavam a tarefa-base pelo
`task_id` ("the standard circuit as in the
ising_field_coupling_4q task"), um identificador interno vazando para o que
devia ser uma descrição autossuficiente. Ninguém viu antes, porque o gerador
local raramente chegava a algo que dependesse de interpretar o enunciado com
cuidado. Só um modelo capaz o bastante para ler com rigor, sem raciocínio para
contornar a ambiguidade (o braço sem raciocínio), recusou quatro tarefas no
planner, três pelo mesmo motivo. **[a]** (52/120 verificado na suíte anterior a T116; 4
recusas num braço. A suíte vigente, de C em diante, não tem esses
enunciados.) É o mesmo mecanismo do teste fora do regime, do lado do
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

**Import faltando, do 7B ao professor.** Na linha de base original, o import
faltando (`NameError` sobre símbolo que existe) era a causa final de **39,0% dos
`failed_static`** do 7B (112 de 287) e estava roteado como símbolo inexistente;
com o roteamento corrigido ele cai, nas execuções C e E (0.35.1 e 0.40.8), a 3,3%
a 4,2% de todos os erros registrados e a 3,3% a 3,6% dos `failed_static` finais, e
a 3 das 120 tarefas na primeira tentativa da execução E. O mesmo modo de falha aparece **uma vez em vinte** (uma permutação
cujo código não importava `QuantumCircuit`) num professor de classe de fronteira,
1 em 80 no piloto. **[b]** n = 1 do lado do professor: o que o achado sustenta é
que o modo de falha não é só de modelo pequeno, não que as taxas sejam comparáveis.

### Uma taxonomia fechada com um padrão que vaza: o `SyntaxError` que absorve tudo

O classificador de falhas do sandbox termina num rótulo de fechamento: tudo o
que ele não reconhece vira `SyntaxError` (a convenção do contrato, cujo exemplo
canônico é o código que nunca define `qc`, um `RuntimeError`). O rótulo não
diz o que o nome diz. Nos registros de erro de estágio estático:

| execução (build) | registros `SyntaxError` | erro de análise sintática de fato | exceção em tempo de execução |
|---|---|---|---|
| A (0.34.1) | 304 | 65 (21,4%) | 239 |
| B (0.34.4) | 366 | 93 (25,4%) | 273 |
| C (0.35.1) | 126 | 11 (8,7%) | 115 |
| E e G (0.40.8, idênticas) | 117 | 9 (7,7%) | 108 (`TypeError` 37, `CircuitError` 28, `QiskitError` 27, `ValueError` 16) |
| F, 1,5B (0.40.8) | 346 | 269 (77,7%) | 77 |

Na run E, **92%** dos registros `SyntaxError` não são erros de sintaxe. Além
das exceções comuns, o mesmo rótulo absorveu: o *timeout* de 60 s do sandbox (1
registro nas runs A e A2, e as onze declarações do piloto de destilação que o
defeito de `fork` perdeu), a resposta vazia de um professor que gastou todo o orçamento em
raciocínio (`finish_reason: length`, 16.096 tokens, nenhum código, registrada como
erro de sintaxe: não houve erro de sintaxe, porque não houve código), e, pelo desenho
anterior do executor, o *worker* morto, que só aparecia como o mesmo *timeout*
(não observado). **[a]** (contagens por registro de erro,
não por execução.)

**O que o rótulo faz com o reparo, dito sem exagero.** A taxonomia é o que
roteia o laço: `SyntaxError` está no conjunto que vai para `retry_generation`, o
mesmo de outros treze tipos, e a string `error_type=SyntaxError` é inserida
tanto no *prompt* de repetição do gerador quanto no *prompt* de dica do crítico.
Isso faz do vazamento um defeito de natureza diferente do irmão
`MissingImport`, que mandava a *ação* errada (`retry_retrieval` para um símbolo
que existe): aqui, para as exceções de tempo de execução e para a resposta vazia,
a ação (regenerar) é a certa e o que está errado é o **nome** mostrado ao modelo
e ao leitor, e as contagens por tipo. A ação só está errada para as condições de
infraestrutura (o *timeout* e o *worker* morto): regenera um código que não
estava errado, gasta uma das cinco iterações com ele, e diz ao gerador que o
código tem erro de sintaxe. Uma taxonomia fechada com um padrão que vaza
transforma o roteamento em sorteio para o que cai no padrão só quando a ação
depende da natureza da falha; quando não depende, o dano é a precisão do
registro, que é o que sustenta qualquer análise por tipo de erro. **[b]** para
os efeitos no laço (leitura do código de roteamento e um caso); **[a]** para as
contagens.

**O padrão pode ser estreitado? Opções e custo (o classificador não foi
alterado; mudá-lo muda o instrumento).**

1. *Manter e revelar* (custo nulo para as medições). Reclassificar na análise,
   pela mensagem, sem tocar o instrumento. Corrige as contagens e deixa o
   roteamento como está. É o que este capítulo faz.
2. *Tipos próprios para infraestrutura e para "nenhum circuito"*
   (`SandboxTimeout`/`WorkerFalhou`, `NenhumCircuito`). Mexe em quatro lugares: a
   taxonomia (`ERROR_TAXONOMY`), os conjuntos de roteamento do crítico, o
   contrato (`data-model.md`) e o teste que os mantém coerentes
   (`test_taxonomy_closed`), mais o classificador. Só altera execuções em que a
   condição ocorre: nos 479 códigos finais de C, E, F e G não ocorre nenhuma (0
   *timeouts*), então as medições existentes seguem comparáveis, e isso se
   verifica reexecutando o veredito estático, como foi feito para o executor. O
   ganho real de roteamento exige ainda uma ação nova (reexecutar o mesmo código
   sem gastar uma iteração); sem ela é só renomear.
3. *Separar as exceções de tempo de execução por família* (`TypeError`/`ValueError`
   de argumento, `CircuitError` de construção, `QiskitError`), deixando
   `SyntaxError` para a análise sintática. Muda a string que o modelo vê em 108
   dos 117 registros da run E: muda o *prompt*, logo as saídas, logo o
   instrumento. Custo: refazer as execuções de 120 tarefas (cerca de 70 a 84
   minutos de relógio por 7B nas runs E e G: 81,7 e 83,9), restabelecer o par de repetição (duas execuções
   por modelo) e reapresentar o capítulo 5 sem comparabilidade com C a G. O
   ganho é de nomes, não de ação.

Minha recomendação, a decidir: 1 agora; 2 quando as duas execuções de 1,5B
anteriores à destilação forem refeitas de qualquer forma, declarando a versão do
instrumento; 3 só se a análise por tipo de erro passar a ser um resultado do
trabalho.

**Generalização.** Uma taxonomia fechada serve ao roteamento e à análise ao mesmo
tempo, e um padrão que vaza serve mal aos dois sem avisar: o campo continua
preenchido, com um valor válido, e a única pista é a mensagem que ninguém
agregou. Vale para qualquer classificador de falhas com um caso "outros" que tem o
nome de um caso específico.

### O laço sempre desiste

No baseline de 19/09 (execução T102, Ollama 0.34.1, anterior ao roteamento de
`MissingImport`, 341 execuções válidas), 335 execuções falharam e **331 delas
esgotaram** as cinco iterações (as outras 4 foram recusadas na entrada). Nas runs
vigentes não é "quase sempre": é **sempre**. Toda execução que gerou código e não
terminou em sucesso chegou à quinta iteração: **113 de 113 na run C** (7B, Ollama
0.35.1; 112 falhas mais 1 abortada por recursos, também na quinta), **115 de 115
na E** e **115 de 115 na G** (7B, 0.40.8) e **118 de 118 na F** (1,5B, 0.40.8).
Nenhuma parou antes. **[a]** (denominadores acima; as execuções que terminam em
sucesso são as únicas que saem do laço.) O laço tem um único modo de término na
falha, o teto, e os sucessos são a cauda, não o comportamento. A leitura ingênua
("zero acertos de primeira, e o laço resgata alguns") parece um laço que funciona
pouco mas funciona.

A consequência de projeto está no capítulo 3 (§3.3): o laço tem um teto de
iterações e **nenhuma detecção de convergência**, de modo que cada falha custa
cinco gerações, e é o que torna o custo de um diagnóstico errado proporcional ao
teto: cinco de um diagnóstico certo e cinco de um errado custam o mesmo em
chamadas, tempo e energia, e só difere se alguma delas podia funcionar. A
proposta que isso sugere, com o custo medido, está no capítulo 8 (§8.2); este
capítulo só registra o fato.

### Uma repetição não é evidência de estar preso

A heurística óbvia para um laço que sempre desiste é parar quando a falha se
repete. Medida nos registros vigentes, a versão ingênua, parar na **segunda**
falha idêntica consecutiva (mesmo estágio, tipo e mensagem), **teria perdido 3
dos 7 sucessos da run C** (7B, Ollama 0.35.1): `ghz_5q`, `ghz_linear5_endpoints` e
`ghz_linear5_scattered_even` saíram depois de exatamente uma repetição. Quase
metade (43%) dos sucessos dessa run veio depois de uma única repetição. Nas runs E
e G (7B, 0.40.8; 5 sucessos) e F (1,5B; 1 sucesso), nenhum teria sido perdido.
Parar na **terceira** falha idêntica não perde nenhum sucesso em nenhuma das três
runs (o maior bloco de falhas idênticas antes de um sucesso foi 2). **[a]**
(3/7 em C, 0/5 em E, 0/1 em F; n pequeno, e o limiar de 3 é seguro *nessas* runs,
não em geral.) Uma única repetição não distingue "preso" de "convergindo devagar";
a heurística plausível foi refutada pela medição antes de existir, e isso vale
mais que a proposta do §8.2.

Duas ressalvas sobre a família. As três tarefas resgatadas são todas GHZ. Com n = 3
pode ser coincidência, mas indica que o limiar interage com a família, e a
proposta tem de dizê-lo: em E os dois sucessos GHZ (`ghz_linear5_mixed`,
`ghz_linear5_scattered_even`) não tiveram repetição alguma, de modo que a
interação, se existe, é família por build, e não foi mostrada. **[b]** para a
interação (três casos, uma run).

### Dois terços das falhas "travadas" do 1,5B são uma truncagem, rotulada como erro de sintaxe

Das 77 falhas do 1,5B (run F, Ollama 0.40.8) com o mesmo erro nas cinco tentativas,
**51** são um só modo: o código final é o texto bruto que começa com uma cerca de
código aberta e termina no meio de uma frase, num laço de repetição ("Apply the
phase oracle one last time ..."), e o erro é `invalid syntax (<unknown>, line 1)`.
Essas execuções gastaram em média 21.055 tokens de saída (cinco tentativas no teto de
4.096), contra 2.239 nas demais da F. A geração degenera em repetição até o teto, a
cerca de fechamento nunca é escrita, e a extração cai no texto bruto. É uma
**truncagem**, que o rótulo de fechamento chama de `SyntaxError`. O mesmo texto de erro
é o erro da tentativa 1 em 51 das 120 execuções da F e 259 de 346 dos seus registros
`SyntaxError` estáticos (verificado como cerca aberta só nas 51 travadas); nas runs E
e C é 9 de 117 e 11 de 126. **[a]** para as contagens, **[b]** para o mecanismo (a
cerca não fechada é verificada nas 51; a cadeia causal da repetição não). Dois efeitos:
o código truncado é devolvido ao gerador como "tentativa anterior"; e o que parecia
"o laço não muda a resposta" é, em dois terços, o mesmo modo de degeneração sob teto.
Isto é outra instância do padrão do parágrafo anterior: o rótulo de fechamento
absorve uma condição (truncagem) que o nome não descreve.

### Retrieval não entrega conhecimento negativo

No baseline de 19/09 (T102, Ollama 0.34.1, corpus 2.x, anterior à derivação de
correções de símbolo F25), das 112 execuções cuja última tentativa foi um
`ImportError`, **104 (92,9%)**
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
*framework*. **[a]** para a correspondência. Como hipótese, não medida, os
nomes vêm de transferência de vocabulário do pré-treino (o PennyLane não está
no corpus).

### O trace descartado era o que o diagnóstico precisava

Até as runs anteriores a C, o trace de cada execução (consulta enviada, número
de chunks, decisões do crítico) era acumulado e descartado ao fim: o registro persistia 24 campos,
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
