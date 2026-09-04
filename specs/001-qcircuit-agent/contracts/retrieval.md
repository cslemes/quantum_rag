# Contract: Retrieval

**Feature**: `001-qcircuit-agent` | **Data**: 2026-08-11
**Módulos**: `src/qcagent/retrieval/index.py`, `src/qcagent/retrieval/hybrid.py`
**Tarefas**: T034, T035, T035b, T036, T036b, T037, T038
**Requisitos cobertos**: FR-011, FR-012, FR-013, FR-014, FR-015

Este contrato é normativo. Assinaturas e nomes de campo são fixos; a
implementação pode variar internamente, mas não a interface.

---

## Constantes de coleção

```python
# src/qcagent/retrieval/index.py
COLLECTION = "qdocs"
DENSE_VECTOR = "dense"
SPARSE_VECTOR = "sparse"

PAYLOAD_INDEXED_FIELDS = ("library_version", "deprecated", "source")
```

---

## `index.py`

### `ensure_collection`

```python
def ensure_collection(
    client: QdrantClient,
    dense_dim: int,
    *,
    recreate: bool = False,
) -> None:
    """
    Cria a coleção `qdocs` com dois vetores nomeados e os índices de payload.
    Idempotente: se a coleção já existe e `recreate=False`, não faz nada.

    Config obrigatória:
      vectors_config = {
          DENSE_VECTOR: VectorParams(size=dense_dim, distance=Distance.COSINE)
      }
      sparse_vectors_config = {
          SPARSE_VECTOR: SparseVectorParams(modifier=Modifier.IDF)
      }

    O modifier IDF é OBRIGATÓRIO. Sem ele o vetor esparso vira contagem de termo
    bruta e perde a ponderação por raridade — que é exatamente o que faz
    `SparsePauliOp` ganhar de palavras comuns numa consulta. Se o fastembed já
    aplicar IDF do lado do cliente, NÃO habilitar aqui: aplicar duas vezes
    distorce o ranking. Decidir e registrar em research.md.

    Após criar, chamar `_create_payload_indexes` — ver T035.
    """
```

### `_create_payload_indexes`

```python
def _create_payload_indexes(client: QdrantClient) -> None:
    """
    Cria índice de payload para cada campo em PAYLOAD_INDEXED_FIELDS.

      library_version -> PayloadSchemaType.KEYWORD
      deprecated      -> PayloadSchemaType.BOOL
      source          -> PayloadSchemaType.KEYWORD

    CRÍTICO (T035): sem estes índices o Qdrant não consegue aplicar o filtro
    durante a travessia do HNSW e cai para pós-filtragem. Como material
    obsoleto é abundante neste corpus, o top-k pré-filtro pode ser descartado
    por inteiro e a consulta devolve vazio para uma pergunta que tinha
    resposta. É o modo de falha que mais ameaça o portão M1.

    Idempotente: recriar índice existente é no-op.
    """
```

### `point_id`

```python
def point_id(doc_id: str) -> str:
    """
    ID determinístico: str(uuid5(NAMESPACE_URL, doc_id)).

    Garante que reingerir o corpus sobrescreve em vez de duplicar (T035b).
    Não usar UUID aleatório nem contador incremental.
    """
```

### `upsert_chunks`

```python
def upsert_chunks(
    client: QdrantClient,
    chunks: Sequence[Chunk],
    dense_vectors: Sequence[list[float]],
    sparse_vectors: Sequence[SparseVector],
    *,
    batch_size: int = 256,
    wait: bool = True,
) -> int:
    """
    Insere ou atualiza chunks em lote. Retorna a quantidade de pontos gravados.

    Payload gravado por ponto (schema fixo — ver data-model.md):
        text, source, library_version, deprecated, replacement, symbol

    Pré-condições:
      - len(chunks) == len(dense_vectors) == len(sparse_vectors)
      - todo chunk.doc_id é único no lote

    `wait=True` por padrão: a ingestão é offline e a consistência importa mais
    que a vazão. A avaliação de recall (T041) logo depois da ingestão daria
    resultado errado com escrita assíncrona.

    Levanta `ValueError` se as sequências divergirem em tamanho.
    """
```

### `snapshot`

```python
def snapshot(client: QdrantClient, out_dir: Path) -> SnapshotInfo:
    """
    Cria snapshot da coleção e o baixa para `out_dir`. Retorna nome, caminho
    local e sha256 do arquivo.

    T036b / Princípio II: o hash retornado entra no `run_id`. Permite
    reconstruir na semana 11 exatamente o corpus recuperável na semana 4,
    mesmo que a documentação upstream tenha mudado no intervalo.

    Chamar ao fim da ingestão e antes de cada rodada experimental.
    """
```

```python
class SnapshotInfo(BaseModel):
    name: str
    local_path: Path
    sha256: str
    point_count: int
    created_at: str
```

---

## `hybrid.py`

### `RetrievalQuery`

```python
class RetrievalQuery(BaseModel):
    """Entrada de uma consulta. Construída pelo nó retriever."""
    text: str
    target_version: str                      # ex.: "1.2.4" — FR-011
    sources: list[str] | None = None         # None = todas as fontes
    include_deprecated: bool = True          # FR-014: rotular, não omitir
    limit: int = 8
    prefetch_limit: int = 40                 # candidatos por ramo antes da fusão
```

### `search`

```python
def search(
    client: QdrantClient,
    query: RetrievalQuery,
    embedder: Embedder,
) -> list[Chunk]:
    """
    Consulta híbrida em UM round-trip usando a Query API.

    Estrutura obrigatória:
        prefetch = [
            Prefetch(query=dense_vec,  using=DENSE_VECTOR,  limit=prefetch_limit,
                     filter=build_filter(query)),
            Prefetch(query=sparse_vec, using=SPARSE_VECTOR, limit=prefetch_limit,
                     filter=build_filter(query)),
        ]
        query = FusionQuery(fusion=Fusion.RRF)
        limit = query.limit

    O filtro vai em CADA ramo do prefetch, não só no nível externo — filtrar
    depois da fusão desperdiça candidatos e reintroduz o problema de
    pós-filtragem que T035 existe para evitar.

    Não implementar RRF em código próprio: a fusão nativa é um round-trip e
    menos superfície de teste.

    Retorna Chunks ordenados por score decrescente, com `deprecated` e
    `replacement` preenchidos a partir do payload.
    """
```

### `build_filter`

```python
def build_filter(query: RetrievalQuery) -> Filter:
    """
    Monta o filtro Qdrant a partir da consulta.

      must:   library_version == query.target_version
              source IN query.sources          (se não for None)
      must_not: deprecated == True             (se include_deprecated=False)

    Nota sobre FR-014: o padrão é include_deprecated=True. Material obsoleto
    DEVE chegar ao gerador rotulado como não utilizável, não ser filtrado fora
    — ver D7 em research.md. O parâmetro existe para o braço de ablação e para
    a avaliação isolada do retriever, não para o caminho normal.
    """
```

### `split_by_register`

```python
def split_by_register(chunks: Sequence[Chunk]) -> RetrievalBundle:
    """
    Separa material de referência de API de material descritivo de algoritmo.
    FR-015: os dois registros respondem a perguntas diferentes e chegam ao
    gerador em blocos distinguíveis.

      api_chunks:   source in {qiskit_api, pennylane_api, migration_guide}
      paper_chunks: source == arxiv
    """
```

```python
class RetrievalBundle(BaseModel):
    api_chunks: list[Chunk]
    paper_chunks: list[Chunk]

    def to_prompt_context(self) -> str:
        """
        Renderiza para o prompt do generator. Contrato de formatação:

        - Bloco de API primeiro, bloco de papers depois, cada um com cabeçalho.
        - Chunk com deprecated=True renderizado com marcação explícita de
          proibição e o campo `replacement` visível, ex.:

              [OBSOLETO — NÃO USAR] execute()
              Substituir por: backend.run() / Sampler / Estimator
              <texto>

        - Chunk vigente renderizado sem marcação.

        O contraste explícito é o mecanismo (D7): omitir não desfaz a memória
        do modelo; declarar a proibição corrige ativamente.
        """
```

---

## Interface do embedder

```python
class Embedder(Protocol):
    """Implementada em src/qcagent/retrieval/embedding.py. Modelo escolhido
    em D4 após o piloto de recall — o contrato não depende dessa escolha."""

    @property
    def dense_dim(self) -> int: ...

    def embed_documents(self, texts: Sequence[str]) -> list[list[float]]: ...
    def embed_query(self, text: str) -> list[float]: ...
    def embed_sparse_documents(self, texts: Sequence[str]) -> list[SparseVector]: ...
    def embed_sparse_query(self, text: str) -> SparseVector: ...
```

**Assimetria proposital**: documento e consulta têm métodos separados porque
vários modelos exigem prefixos distintos (`passage:` / `query:`). Usar o método
errado degrada recall de forma silenciosa — não há erro, só resultado pior.

---

## Contrato de erros

| Condição | Comportamento |
|---|---|
| Coleção inexistente na consulta | Levantar `CollectionNotFound`; NÃO criar sob demanda |
| Qdrant indisponível | Retry com backoff exponencial, 3 tentativas, depois propagar |
| Consulta devolve vazio | Retornar `[]`; o nó retriever registra e o critic decide — nunca simular resultado |
| Dimensão do embedding difere da coleção | Levantar `DimensionMismatch` na inicialização, não na primeira consulta |

---

## Testes exigidos

| Teste | Arquivo | Verifica |
|---|---|---|
| Índices de payload existem após `ensure_collection` | `tests/unit/test_index.py` | T035 |
| Reingestão do mesmo corpus não altera `point_count` | `tests/unit/test_index.py` | T035b, idempotência |
| Filtro por versão exclui a versão errada | `tests/unit/test_hybrid.py` | FR-011 |
| Consulta por identificador exato recupera o símbolo no top-3 | `tests/unit/test_hybrid.py` | FR-013, caso `RZGate` vs `RXGate` |
| `to_prompt_context` marca chunk obsoleto e mostra `replacement` | `tests/unit/test_hybrid.py` | FR-014 |
| `split_by_register` separa arxiv de docs de API | `tests/unit/test_hybrid.py` | FR-015 |
| `recall@8 ≥ 0.85` nas 50 consultas sintéticas | `analysis/eval_retrieval.py` | portão M1 |

**Teste de caso crítico** (o que justifica o híbrido existir): consulta contendo
`RZGate` DEVE trazer o chunk de `RZGate` acima do de `RXGate`. Se falhar, o ramo
esparso não está contribuindo — verificar o modifier IDF antes de mexer no
modelo denso.

---

## Nota de verificação

As chamadas descritas acima (`query_points` com `prefetch` + `FusionQuery`,
`SparseVectorParams(modifier=Modifier.IDF)`, `create_payload_index`)
correspondem à API do `qdrant-client` conforme conhecida na redação deste
contrato. Confirmar contra a documentação da versão fixada em T003 antes de
implementar T034 — nomes de parâmetro em torno da Query API mudaram entre
versões menores. Divergência encontrada: corrigir aqui primeiro, depois no
código.
