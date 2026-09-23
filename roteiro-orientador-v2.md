# Roteiro — reunião de orientação (escopo v2)

**Atualizado**: 20/09/2026 — semana 6 de 12
**Objetivo**: validar o recorte de produto, apresentar o baseline medido e
resolver quatro decisões em aberto.
**Duração alvo**: 45 minutos, com 15 de discussão.

Leve: o sistema rodando, o `report-notes.md` e este roteiro.

---

## 1. Abertura (2 min)

> "É uma ferramenta que gera circuitos quânticos a partir de descrição em
> linguagem natural, verifica o que consegue verificar, e é explícita sobre o
> que não verificou."

Se ele perguntar o problema:

> "LLMs escrevem código Qiskit mal — alucinam APIs removidas e erram detalhes
> que parecem certos. E quem pede o circuito muitas vezes não sabe conferir.
> Código plausível e errado é o pior resultado possível."

---

## 2. O que torna o domínio tratável (3 min)

Não pule. É o que sustenta o produto existir.

> "Em geração de código comum, para saber se está certo alguém precisa escrever
> testes. Em circuito quântico existe oráculo matemático — dá para comparar a
> unitária, ou compor com a inversa e testar se dá identidade. Isso permite
> verificar de verdade, não pedir opinião a outro modelo."

Se ele vier de engenharia de software:

> "É o *oracle problem* clássico. Este domínio o resolve parcialmente, de
> graça."

---

## 3. Demonstração (8 min)

Rode ao vivo. Mostre, comentando enquanto roda.

O que apontar:

- o circuito falhou, o sistema diagnosticou, corrigiu, convergiu
- as camadas de verificação, cada uma com veredito próprio
- **o relatório de garantia** — é o diferencial, e é onde parar mais tempo

Mostre especificamente o caso sem asserção:

> "Repare que ele diz, em maiúsculas, que a corretude funcional NÃO foi
> verificada. O circuito executa, transpila, respeita as restrições — e o
> sistema se recusa a chamar isso de correto."

Se falhar ao vivo, **não é problema**. Aponte que reporta falha explícita em
vez de entregar algo não verificado.

---

## 4. A mudança de escopo (4 min)

Diga você, cedo, sem rodeios.

> "Comecei especificando um experimento controlado — cinco condições
> comparativas, ablação, teste de hipóteses. Ao confirmar que o entregável é
> produto, reduzi o escopo: saiu a matriz experimental, ficou o sistema mais
> uma suíte de regressão. As 120 tarefas que eu tinha construído mudaram de
> função — eram instrumento de medida, viraram garantia de que mudanças não
> degradam o sistema."

Se ele perguntar se foi desperdício:

> "Não. O dataset é o mesmo, a disciplina de verificação é a mesma. O que saiu
> foi o aparato de inferência estatística, que não faz sentido num produto."

---

## 5. O que está pronto (5 min)

- geração com loop de correção diagnóstica
- recuperação de documentação versionada, `recall@8` de 0,95
- verificação sem referência: asserções declaradas pelo usuário
- relatório de garantia explícito sobre o não verificado
- 120 tarefas com referências verificadas por construção independente
- suíte de regressão completa, rodando em 108 minutos

Falta: interface, execução em hardware real.

---

## 6. O baseline, com honestidade (6 min)

Este é o momento que distingue um trabalho sério. Não suavize.

> "Rodei a suíte completa. A taxa de sucesso é baixa — 1,8% — mas o número
> importante é outro: 84% das execuções param antes de chegar à verificação
> funcional, porque o código não roda. E 331 de 335 falhas esgotam as cinco
> tentativas do loop de correção."

O que isso diz:

> "O gargalo não é o modelo errar a física. É que ele raramente chega lá. E o
> loop de correção, quando engaja, praticamente nunca converge — gasta cinco
> chamadas para chegar onde começou."

E o achado que veio daí:

> "Encontrei um defeito no roteamento: 39% das falhas eram import faltando,
> classificadas como se fossem API inexistente e roteadas para reconsultar
> documentação. Nenhuma documentação adiciona uma linha de import. Corrigi,
> escrevi a previsão de melhora antes de testar — e a previsão foi refutada.
> O roteamento correto não bastou."

---

## 7. O achado metodológico mais forte (5 min)

Se houver um momento para impressionar, é este.

> "Ao medir a correção, incluí um controle: uma métrica que, por construção,
> não poderia mudar — ela mede a primeira tentativa, antes de o roteamento
> existir. Ela mudou 43%. Isso revelou que o cliente do modelo não fixava
> temperatura, e 26% das execuções divergiam entre rodadas idênticas."

O ponto:

> "Sem o controle, 'a métrica subiu 43%' teria sido o resultado reportado.
> Plausível, quotável e falso. Revisão de código não pegaria, porque não há
> bug. Mais amostras não pegariam, porque estimariam melhor o número errado. O
> que separou ruído de resultado foi nomear antes qual número não poderia se
> mover."

Se ele quiser mais, há outros: oráculos mais estreitos que os enunciados,
cegueira de fase em verificação por medição, diagnóstico incorreto pior que
nenhum. Todos documentados no `report-notes.md`.

---

## 8. A limitação, dita por você (4 min)

Antes que ele pergunte.

> "Executabilidade e transpilação eu verifico para qualquer circuito. Corretude
> funcional precisa de algo contra o que comparar — e se o usuário já tem a
> referência, por que pediria para gerar?"

A solução:

> "O usuário declara a propriedade esperada em vez do circuito. 'Amplitude
> igual em |000⟩ e |111⟩' é muito mais fácil de escrever que a implementação, e
> é verificável por simulação."

E o limite honesto da solução:

> "Testei a linguagem contra tarefas reais e ela não cobre tudo. Para
> transformação geral, como a QFT, asserções sobre o estado inicial não dizem
> nada. Para tarefas cuja corretude é uma derivação numérica, escrever a
> asserção dá o mesmo trabalho que construir o circuito. Isso está registrado
> como limitação, não escondido."

---

## 9. Perguntas para ele (15 min)

Leve escritas.

**1. O recorte de produto atende ao que o programa espera?**
> "É IA aplicada a computação quântica. Não busca vantagem quântica. A entrega
> é a ferramenta mais o relatório."

**2. O que ele espera do relatório?**
Extensão, estrutura, se há template. Isso determina o que priorizar nas seis
semanas restantes.

**3. Baseline baixo é problema?**
> "1,8% de sucesso pode soar mal fora de contexto. Meu argumento é que o número
> é diagnóstico, não resultado — e que a honestidade sobre ele é parte do que o
> trabalho defende. Você vê risco nisso na avaliação?"

**4. Onde investir as seis semanas restantes?**
Três candidatos, e ele deve escolher:
- **interface** — torna demonstrável, é o que uma banca vê
- **reparo incremental** — a hipótese aberta; pode mover o baseline de verdade
- **execução em hardware real** — fecha o ciclo, depende de fila externa

Minha inclinação é interface primeiro, mas a pergunta é dele.

**5. Vale publicar algo?**
O dataset de 120 tarefas com referências verificadas não tem equivalente
público, e há seis achados metodológicos. Pergunte se vê espaço em evento, e se
seria coorientado.

---

## Se ele achar que falta experimento

> "A infraestrutura está toda pronta — dataset, runner, comparação entre
> execuções, controle de determinismo. Reintroduzir uma comparação reduzida,
> dois geradores e duas condições, custaria uma semana."

**Ouça de verdade.** Não defenda a decisão de escopo como irreversível.

---

## Se ele perguntar da aplicação no seu trabalho

> "A conexão não é o domínio, é o método: um agente que verifica o próprio
> resultado antes de entregar. Circuito quântico é onde o oráculo é barato, o
> que torna o problema tratável num trabalho de conclusão."

---

## Depois

Registre no `report-notes.md`, na mesma sessão: o que ele pediu, o que vetou, o
que ficou combinado. E, se a pergunta 4 tiver resposta, reorganize o
`tasks.md` antes de retomar.
