# Cálculo offline opcional

Sumário: [contrato de entrada](#contrato-de-entrada),
[saída e interpretação](#saída-e-interpretação),
[exemplo executável](#exemplo-executável).

`scripts/calculate.py` recebe um arquivo JSON normalizado, usa apenas Python 3
stdlib e imprime JSON em stdout. Não coleta logs, consulta preços, acessa rede,
altera arquivos nem infere tempo a partir de mensagens. Erros saem em JSON em
stderr com código 2. Execute com `python` (ou `python3`, conforme a instalação):

```sh
python scripts/calculate.py normalized.json
```

## Contrato de entrada

- `scope`: `label` não vazio, `cutoff` obrigatório e `start` opcional. Datas e
  horas seguem `YYYY-MM-DDTHH:MM:SS[.ffffff]Z` ou offset `±HH:MM`; timezone é
  obrigatório. O adaptador deve selecionar apenas requisições do escopo até o
  cutoff; o script não recebe timestamps de requisições nem verifica essa seleção.
- `coverage`: `complete` ou `partial`, aplicado ao conjunto de dados do escopo.
  Use `complete` somente com evidência de cobertura completa das fontes relevantes.
- `coverage_by_metric`: objeto opcional com chaves opcionais `tokens`, `agent` e
  `human`, cada qual `complete` ou `partial`. Cada chave substitui a cobertura
  global apenas para sua métrica; chaves omitidas herdam `coverage`. A cobertura
  de `tokens` também governa custos. Por exemplo, tokens parciais e observação
  humana completa: `"coverage": "partial", "coverage_by_metric": {"human": "complete"}`.
- `requests`: lista opcional. Cada objeto contém `id` com strings não vazias
  `provider`, `session`, `request`, e `tokens` com **todas** as cinco categorias:
  `input_uncached`, `cache_read`, `cache_write_short`, `cache_write_long`, `output`.
  Cada quantidade é inteiro ≥ 0 ou `null`. As categorias precisam ser **disjuntas**;
  normalize contadores inclusivos do provedor antes de chamar o script. Cache lido
  e cache escrito não podem permanecer incluídos em `input_uncached`. Reasoning
  já incluído no output não deve ser adicionado novamente. O script não aceita
  uma categoria separada de reasoning.
- Zero significa ausência confirmada naquela categoria. Use `null` se o valor
  não estiver disponível; não presuma zero para um campo ausente no log.
- `pricing` é opcional por requisição; omita o objeto quando não houver preços.
  Quando presente, exige `currency` (três letras maiúsculas), `source` (referência
  não vazia), `as_of` (`YYYY-MM-DD`, data da tabela aplicável) e `per_million` com
  as mesmas cinco categorias. Taxas são strings decimais não negativas, sem
  expoente, ou `null`; por exemplo `"2.50"`. Registre preços aplicáveis ao modelo,
  tier, janela de contexto, operação e data escolhidos. Uma URL em `source` é
  apenas metadado: o script não a visita nem verifica a tabela.
- `agent_intervals`: lista opcional de objetos `start`/`end` e `agent_id` (string
  não vazia e estável para o agente observado). Cada intervalo representa execução
  fechada e observada. Sobreposições e duplicatas do mesmo agente são unidas antes
  de somar esforço; IDs diferentes preservam paralelismo entre agentes.
- `human_intervals`: lista opcional de `start`/`end` e `basis`, obrigatoriamente
  `measured` ou `declared`. Só inclua tempo humano explicitamente medido ou
  declarado. Datas de mensagens, execução de ferramentas e silêncio não medem
  atenção humana. Intervalos declarados continuam sendo declarações, não medições.
- Intervalos precisam ter `start ≤ end ≤ cutoff`; quando `scope.start` existe,
  nenhum intervalo pode começar antes dele. Não há clipping automático. Finais
  ausentes ou `null` são rejeitados: reporte atividades abertas fora do cálculo.
  Uma duração zero só deve entrar se observada ou explicitamente declarada.
- Campos desconhecidos, categorias omitidas, tipos incorretos e chaves JSON
  repetidas são rejeitados. Listas omitidas e listas vazias produzem métricas
  indisponíveis (`null`), não evidência de consumo ou duração zero.

## Saída e interpretação

`known_subtotal` soma apenas valores conhecidos; `total` só é preenchido se há
evidência, nenhum componente está ausente e a cobertura efetiva daquela métrica
é `complete`. Com cobertura efetiva `partial`, seu `total` permanece `null`, mesmo
quando o subtotal é calculável. A saída repete a cobertura global e as coberturas
efetivas em `coverage_by_metric`. `coverage` de cada resultado calculado é
`complete`, `partial` ou `unavailable`;
`known_values`/`missing_values` contam componentes, não tokens. Para tempo calendário,
componentes são os intervalos já unidos; não representam atividades individuais.
Nenhum subtotal deve ser apresentado como total completo do escopo.

Requisições com o mesmo trio `provider/session/request` e conteúdo igual são
contadas uma vez. Mesmo ID com conteúdo diferente causa erro, inclusive preços
ou metadados divergentes. Reconcilie a origem antes de calcular; não escolha uma
versão silenciosamente.

Custos são **referência de API**, calculados com `Decimal` por requisição/categoria
como `tokens × taxa / 1.000.000`, preservados como strings decimais sem arredondar
para centavos. Não são custo cobrado, fatura, preço de assinatura nem economia
financeira observada. Não há total entre moedas: veja `currency_buckets` e as
linhas em `reference_api_cost.requests`. Uma categoria com zero tokens confirmado
tem custo zero mesmo com taxa desconhecida, desde que a moeda esteja identificada;
tokens desconhecidos continuam indisponíveis. Requisições sem `pricing` aparecem
em `unassigned_currency_requests` e impedem totais completos dos buckets, pois
sua moeda também é desconhecida. Taxas diferentes por requisição são preservadas.
O calculador suporta apenas essas cinco categorias: se uma mesma requisição tiver
modalidades ou faixas com tarifas diferentes dentro de uma categoria, calcule
separadamente fora do script com evidência, sem inventar tarifa média ou número
de requisições.

`time.agent.calendar_seconds` é a duração da **união** dos intervalos: paralelismo
não duplica tempo calendário. `aggregate_agent_seconds` soma as durações da união
dos intervalos **por agente** e pode ser maior quando agentes distintos trabalham
em paralelo. Repetições ou sobreposições do mesmo `agent_id` não aumentam esse
esforço. `time.human.calendar_seconds`
também usa união, exclusivamente dos intervalos humanos fornecidos.
`elapsed_scope_seconds` é simplesmente `cutoff − scope.start`, ou `null` sem start;
não mede execução, esforço do agente, atenção humana ou tempo manual evitado.
Durações são strings decimais em segundos, com precisão de microssegundos.

## Exemplo executável

Salve como `normalized.json` e execute o comando acima a partir da pasta da skill.
Os preços abaixo são **fictícios**, apenas para conferir a aritmética.

```json
{
  "scope": {
    "label": "Demonstração local",
    "start": "2026-09-29T10:00:00Z",
    "cutoff": "2026-09-29T10:10:00Z"
  },
  "coverage": "complete",
  "requests": [{
    "id": {"provider": "demo", "session": "s1", "request": "r1"},
    "tokens": {
      "input_uncached": 1000,
      "cache_read": 2000,
      "cache_write_short": 100,
      "cache_write_long": 0,
      "output": 500
    },
    "pricing": {
      "currency": "USD",
      "source": "Tabela fictícia para demonstração",
      "as_of": "2026-09-29",
      "per_million": {
        "input_uncached": "2",
        "cache_read": "0.2",
        "cache_write_short": "2.5",
        "cache_write_long": "4",
        "output": "8"
      }
    }
  }],
  "agent_intervals": [
    {"agent_id": "a1", "start": "2026-09-29T10:00:00Z", "end": "2026-09-29T10:04:00Z"},
    {"agent_id": "a2", "start": "2026-09-29T10:02:00Z", "end": "2026-09-29T10:06:00Z"}
  ],
  "human_intervals": [
    {"start": "2026-09-29T10:07:00Z", "end": "2026-09-29T10:08:00Z", "basis": "declared"}
  ]
}
```

Resultados: 3.600 tokens; referência API de `"0.00665"` USD; tempo calendário de
agente `"360"` s; esforço agregado `"480"` s; tempo humano declarado `"60"` s;
escopo decorrido `"600"` s. Remover os intervalos humanos torna seu tempo `null`;
trocar `coverage` para `partial` preserva os subtotais, mas torna os totais `null`.
