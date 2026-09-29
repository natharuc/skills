# Relatório HTML compilado

Sumário: [entrega visual](#entrega-visual), [execução](#execução),
[contrato de apresentação](#contrato-de-apresentação),
[exemplo fictício](#exemplo-fictício), [garantias e limites](#garantias-e-limites).

## Entrega visual

O resultado padrão é um documento HTML **já preenchido**, bonito, responsivo e
auditável. Produzir o arquivo final e abri-lo na visualização nativa de HTML,
artefato ou navegador disponibilizada pelo host. Mostrar apenas o código-fonte ou
um link de download não substitui a visualização quando ela estiver disponível.
Salvar o documento completo no destino autorizado pelo host, mesmo quando a
visualização usar um fragmento. Nome sugerido: `chat-report-<sessao>-<corte>.html`.

Usar `--fragment` somente para hosts que aceitam CSS e HTML estático em uma
superfície visual nativa. Ele contém `<style>` e `<main>`, sem `doctype`, `html`,
`head`, `body` ou JavaScript. O CSS fica restrito a `.chat-report`. Não injetar o
documento completo em uma API que aceita apenas fragmentos. Se a superfície
remover estilos, preferir a visualização do arquivo completo. Se não existir
capacidade visual, entregar o HTML e informar essa limitação sem fingir preview.

O layout traz quatro indicadores, tabela de métricas com fontes, detalhamento
opcional por modelo/agente, eventos comprovados, entregas e limites. Não criar
gráficos, barras de progresso, cronogramas ou distribuições sem dados que os
sustentem. O HTML fica legível sem JavaScript, sem internet e na impressão.

## Execução

O renderizador usa apenas Python 3 stdlib. A partir da pasta da skill:

```sh
python3 scripts/render_report.py presentation.json --output chat-report.html
python3 scripts/render_report.py presentation.json --output chat-report-fragment.html --fragment
```

`--overwrite` autoriza substituir explicitamente um arquivo existente. Sem ele,
o arquivo é preservado e a execução falha. O renderizador cria os diretórios
necessários, rejeita saída igual à entrada e imprime em stdout um objeto JSON
com `output` e `format` (`standalone` ou `fragment`). Erros produzem um objeto
`error` em stderr e código de saída 2; sucesso retorna 0.

O script valida **dados de apresentação**, não recebe diretamente a saída de
`calculate.py` nem recalcula tokens, durações, moedas ou custos. Preparar o JSON
após conferir as evidências e os cálculos. O mesmo JSON gera ambas as formas.

## Contrato de apresentação

Campos desconhecidos, chaves JSON repetidas, `NaN`, tipos incorretos, strings
vazias, IDs repetidos e referências a fontes inexistentes são rejeitados.
Objetos/listas opcionais devem ser omitidos; `null` só é permitido nos campos de
texto descritos como opcionais. Textos são literais, não HTML nem Markdown.

| Campo raiz | Tipo e regra |
|---|---|
| `version` | Obrigatório: inteiro `1`. |
| `task` | Obrigatório: texto não vazio, título breve da tarefa. |
| `scope` | Texto opcional ou `null`, escopo atribuído. |
| `period` | Objeto opcional com `start`, `cutoff`, `timezone`; cada campo é texto de apresentação ou `null`. Não há parsing de datas nem inferência de fuso. |
| `summary` | Texto opcional ou `null`, síntese baseada em evidências. |
| `metrics` | Lista opcional de métricas, no formato abaixo. |
| `breakdowns` | Lista opcional de objetos `{ "title": texto, "metrics": [métrica, ...] }`; cada grupo exige ao menos uma métrica. Usar para modelos ou agentes identificados. |
| `timeline` | Lista opcional de eventos `{ "time": texto, "title": texto, "detail": texto ou null, "source_ids": [id, ...] }`. `time`, `title` e ao menos uma fonte são obrigatórios. A ordem fornecida é preservada. |
| `deliverables` | Lista opcional de objetos `{ "label": texto, "detail": texto ou null, "source_ids": [id, ...] }`; rótulo e ao menos uma fonte são obrigatórios. Apenas resultados confirmados. |
| `sources` | Lista opcional de fontes no formato abaixo. |
| `limitations` | Lista opcional de textos não vazios sobre lacunas, atribuição, cobertura, premissas e precisão. |

Cada **métrica** aceita exatamente:

| Campo | Tipo e regra |
|---|---|
| `id` | Texto obrigatório, único dentro da respectiva lista. |
| `label` | Texto obrigatório: o nome preciso da medida. |
| `value` | Texto já formatado ou `null`; omitir equivale a `null`. Números JSON são rejeitados. |
| `status` | `measured`, `declared`, `calculated`, `estimated` ou `unavailable`; padrão `unavailable`. |
| `coverage` | `complete`, `partial` ou `unavailable`; padrão `unavailable`. |
| `source_ids` | Lista de IDs de fontes existentes; ao menos uma fonte se `value` não for `null`. IDs repetidos são rejeitados. |
| `note` | Texto opcional ou `null`: método, qualificação, premissa ou lacuna. |

Os rótulos visuais de status são **Medido**, **Informado**, **Calculado**,
**Estimado** e **Indisponível**. Um valor conhecido exige status diferente de
`unavailable`, cobertura `complete` ou `partial` e fonte. Um valor `null` exige
status e cobertura `unavailable`. Zero só deve entrar como texto formatado quando
for comprovado. O validador confere consistência estrutural, não autenticidade.

Na lista raiz `metrics`, quatro IDs selecionam os cartões principais:

| ID | Uso |
|---|---|
| `human_time` | Dedicação humana; não usar duração da IA ou resposta entre mensagens. |
| `agent_time` | Execução do agente, ou duração bruta explicitamente identificada no `label`. |
| `tokens` | Consumo observado; para cobertura parcial usar, por exemplo, `"Subtotal: 3.600"`, além da cobertura parcial visível. |
| `cost` | Uma categoria específica de custo. Preservar moeda e nome exato no `label`, como “Referência API” ou “Cobrança atribuída”. Nunca somar essas duas categorias. |

O nome, valor e qualificação fornecidos são preservados também no cartão. IDs
principais ausentes geram cartões e linhas **Indisponível**, sem números. Outras
métricas aparecem na tabela, na ordem fornecida. Mostrar custos adicionais em
linhas separadas com IDs próprios. Não criar total entre moedas. Se o custo não
for conhecido, o cartão informa indisponibilidade.

Cada **fonte** aceita `id` e `label` obrigatórios, `detail` opcional ou `null`, e
`url` opcional ou `null`. Os IDs são usados internamente para ligar evidências e
não são impressos; a UI usa numeração local. URLs só aceitam `http` ou `https`,
sem credenciais, e viram links convencionais sem busca automática. Preferir
rótulos saneados: “Exportação de consumo da sessão”, sem transcrição, tokens de
acesso, caminho sensível, credencial ou identificadores internos desnecessários.
O renderer **não faz redação automática** de texto: preparar dados seguros antes.

## Exemplo fictício

Este JSON é **FICTIONAL / FICTÍCIO**, apenas para exercitar o layout. Não usar os
números, datas, preço ou entregas deste exemplo em um relatório real.

```json
{
  "version": 1,
  "task": "FICTIONAL — Demonstração de relatório",
  "scope": "Sessão fictícia e agentes vinculados",
  "period": {
    "start": "29 set 2026 · 10:00",
    "cutoff": "29 set 2026 · 10:10",
    "timezone": "UTC"
  },
  "summary": "Demonstração fictícia de uma entrega e seu consumo conhecido.",
  "metrics": [
    {
      "id": "human_time", "label": "Dedicação humana", "value": null,
      "note": "Não há timer nem declaração de dedicação humana."
    },
    {
      "id": "agent_time", "label": "Execução do agente", "value": "6 min",
      "status": "calculated", "coverage": "complete", "source_ids": ["demo"],
      "note": "União dos intervalos observados."
    },
    {
      "id": "tokens", "label": "Tokens consumidos", "value": "Subtotal: 3.600",
      "status": "measured", "coverage": "partial", "source_ids": ["demo"],
      "note": "Um agente não possui telemetria."
    },
    {
      "id": "cost", "label": "Referência API", "value": "US$ 0,00665",
      "status": "estimated", "coverage": "partial", "source_ids": ["demo"],
      "note": "Subtotal de referência; tarifa fictícia."
    }
  ],
  "timeline": [{
    "time": "10:06 UTC", "title": "Validação concluída",
    "detail": "Evento fictício documentado para demonstração.", "source_ids": ["demo"]
  }],
  "deliverables": [{
    "label": "Relatório de demonstração", "source_ids": ["demo"]
  }],
  "sources": [{
    "id": "demo", "label": "Dados fictícios",
    "detail": "Exemplo de documentação; não corresponde a uma sessão real."
  }],
  "limitations": ["Todos os dados deste exemplo são fictícios."]
}
```

Entrada mínima válida: `{"version": 1, "task": "Nome da tarefa"}`. Ela produz
um relatório sem números inventados, fontes ausentes e indicadores indisponíveis.
Não adicionar eventos ou entregas só para preencher espaços vazios.

## Garantias e limites

- O HTML final contém os valores renderizados no servidor. Não depende de scripts
  para preencher a tela; não há CDN, fonte externa, biblioteca ou rede.
- `html.escape(..., quote=True)` protege todos os textos e atributos fornecidos.
  Classes CSS vêm apenas de enums validados. Strings com tags aparecem como texto.
- Links de fontes só são acessados por ação do usuário; o renderer não consulta
  serviços, variáveis de ambiente, logs, preços ou telemetria.
- O template contém apenas estrutura e estilos, sem métricas ou eventos de exemplo.
  Não enviar o template com placeholders como se fosse o relatório final.
- O contrato preserva os textos fornecidos. Cabe ao agente distinguir subtotal,
  total, cobrança real, referência, estimativa, declaração e ausência de dado;
  confirmar eventos e entregas; e evitar precisão indevida.
- A impressão usa CSS próprio. Conferir o relatório final no host disponível,
  especialmente em telas estreitas ou com textos longos. O fragmento isolado usa
  estilos com prefixo, mas a aparência também pode depender das regras do host.
