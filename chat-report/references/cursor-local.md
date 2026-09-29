# Coleta no Cursor

Executar esta coleta antes de um relatório sobre uma sessão Cursor. O objetivo é comprovar o que existe na instalação correta, sem presumir que todos os dados estejam na transcrição. Acesso ao contexto da conversa não equivale a acesso à telemetria de cobrança.

## 1. Identificar máquina e conversa

Identificar se o terminal está na máquina da interface Cursor, em WSL, SSH ou ambiente remoto. Um banco ausente no servidor não demonstra ausência no computador que hospeda a interface. Identificar perfil, versão e diretório de dados personalizado quando houver; não substituir o diretório pessoal do usuário por um caminho inventado.

Obter o composer ID da conversa atual a partir de metadados disponíveis ou da transcrição correspondente e validar a associação ao projeto. Não escolher a conversa mais recente da conta nem um ID de outra tarefa. Se só houver o projeto, inspecionar os índices de metadados do workspace antes de pedir que o usuário procure manualmente.

## 2. Localizar as fontes

| Sistema | Candidato inicial ao banco de conversas |
|---|---|
| Windows | `%APPDATA%\Cursor\User\globalStorage\state.vscdb` |
| macOS | `~/Library/Application Support/Cursor/User/globalStorage/state.vscdb` |
| Linux | `~/.config/Cursor/User/globalStorage/state.vscdb`, respeitando `XDG_CONFIG_HOME` |

Resolver variáveis pelo ambiente real. Se houver diretório de dados personalizado ou outro perfil, usar seu caminho conhecido. Usar `User/workspaceStorage/<workspace>/workspace.json` e `state.vscdb` do workspace correspondente apenas quando necessário para associação ou esquema antigo. Não varrer todos os discos nem despejar outras conversas.

Tratar a transcrição como fonte de conteúdo. Tratar registros de atribuição de edições como evidência complementar de eventos de código, sem convertê-los em todas as requisições ou todas as horas da tarefa. A simples ausência de tokens nessas duas fontes não encerra a investigação.

## 3. Inspecionar em modo somente leitura

Executar o coletor incluído na skill, no computador que contém o banco:

```text
python <pasta-da-skill>/scripts/inspect_cursor.py --conversation <composer-id>
```

Para um caminho confirmado ou perfil personalizado:

```text
python <pasta-da-skill>/scripts/inspect_cursor.py --conversation <composer-id> --db "<caminho-completo>/state.vscdb"
```

No Windows, usar `py -3` se esse for o executável disponível. O script não exige bibliotecas externas e imprime JSON. Não precisa criar arquivo, acessar rede, ler credenciais, fechar o Cursor ou modificar o banco. Sem Python, executar consultas equivalentes com uma ferramenta SQLite já disponível; não abandonar a coleta só porque o script não pode rodar.

O coletor usa `mode=ro`, transação de leitura, filtros pelo ID e limites explícitos. Evitar `immutable=1` em banco ativo, pois pode ignorar WAL. Se precisar de snapshot, usar backup SQLite consistente ou mecanismo equivalente que preserve a visão do WAL; não copiar somente o arquivo principal em uso. Não executar migrações, limpeza, checkpoint ou `VACUUM`.

Detectar as tabelas existentes. Em esquemas observados por parsers independentes, `cursorDiskKV` guarda `composerData:<id>` e `bubbleId:<id>:<bubble-id>`. Versões recentes também podem ter `composerHeaders`, consultável por `composerId`. Versões antigas podem ter índices no `ItemTable` (`composer.composerData` ou `composer.composerHeaders`). Os formatos internos não são uma API estável; se houver outro esquema, inspecioná-lo sem afirmar que a sessão desapareceu.

O script cobre o KV e cabeçalhos recentes. Se retornar `conversation_not_found_in_supported_tables`, verificar associação de máquina/perfil/ID e índices antigos antes de concluir que não existem registros. Para localizar um índice antigo, ler apenas sua chave conhecida e filtrar o JSON pelo composer ID; não imprimir todo o índice. Sem possibilidade de acesso, registrar precisamente a limitação.

## 4. Interpretar os campos encontrados

- Considerar cada `candidate_fields` uma evidência bruta que ainda precisa de semântica, unidade e cobertura. O coletor não transforma candidatos em um relatório automaticamente.
- Verificar `tokenCount` e quaisquer campos de uso realmente presentes. **Contadores preenchidos com zero podem ser valores padrão**, especialmente quando toda a conversa está zerada. Não apresentar isso como consumo zero nem calcular custo zero.
- Não converter `contextUsagePercent`, ocupação de contexto ou limite em consumo acumulado. Um contador positivo por bubble ainda exige reconciliação por requisição; uma resposta pode conter vários segmentos.
- Preservar timestamps em seu formato de origem. Timestamps de cabeçalho podem estar em epoch ms; timestamps de mensagens podem estar em RFC3339. Validar datas, fuso e unidade. Não assumir que todo número chamado `time` seja relógio de calendário.
- Se houver início/fim de requisição no mesmo relógio, validar o significado, deduplicar, recortar no corte e unir intervalos. Não subtrair relógio monotônico de epoch. Chamar o resultado duração das requisições observadas, sem presumir cobertura de toda a execução do agente.
- Se só houver horários de mensagens, informar o período conhecido. Quando o usuário pedir aproximação de atividade, aplicar a regra de janelas do SKILL.md com rótulo de estimativa. Dedicação humana permanece dependente de marcações/atividade atribuída, não do banco de mensagens.
- Datas de arquivo e `lastUpdatedAt` não são duração ativa. Registros abertos, valores truncados, blobs grandes não lidos, timeouts e schemas desconhecidos tornam a inspeção parcial.

O coletor não imprime corpo de prompts, respostas ou resultados de ferramentas; registra somente uma lista restrita de campos conhecidos de métricas e tempo. Nomes de modelo em texto não são emitidos. Uma lista vazia não prova que um novo schema não tenha outros metadados: inspecionar a estrutura localmente quando houver divergência. Não colar um dump integral do banco em ferramentas externas. Se precisar ler conteúdo para desambiguar identidade, fazê-lo localmente e apenas para a conversa alvo.

## 5. Completar uso e cobrança quando possível

Se o SDK oficial já estiver disponível, a identidade do agente estiver comprovada e houver acesso autorizado, verificar a consulta de uso existente, como `Agent.getUsage()`. Não presumir que qualquer composer ID de IDE seja aceito pela API; confirmar o mapeamento e a superfície suportada. Não criar outro agente para consultar uso anterior e não procurar/expor tokens de autenticação.

O SDK distingue contagem ao vivo de uso faturado e pode devolver custo ainda ausente enquanto ele consolida. Preservar essas distinções. Alternativamente, usar exportação/painel de consumo ou Admin API já acessível. Vincular registros por ID verificável; coincidência de horário/modelo não basta para atribuição exata. Não exigir conta administrativa como primeira opção de um usuário individual.

Para dados não acessíveis do lado do agente, pedir somente o registro/exportação necessário à lacuna remanescente. Não prometer que o banco local tem o detalhamento de cache, custo ou atenção humana.

## 6. Diagnóstico obrigatório de lacunas

Registrar no relatório, de forma resumida:

| Fonte | Resultado da inspeção | Consequência |
|---|---|---|
| Banco de conversas | caminho, tabela, composer encontrado ou motivo de falha | identidade e abrangência verificadas ou pendentes |
| Mensagens | quantidade inspecionada, campos de tempo e uso disponíveis | períodos/contadores aproveitáveis ou ausentes |
| Uso/faturamento | origem consultada, vínculo por ID e disponibilidade | custo atribuído ou lacuna específica |

Distinguir **não coletado**, **inacessível neste ambiente**, **formato não suportado**, **campo ausente**, **contador padrão não confiável** e **medição disponível**. Não usar a frase absoluta “o Cursor não tem essas informações” com base em uma única transcrição ou instalação.

Só afirmar que a nova coleta resolveu o caso real após executá-la na máquina/sessão do usuário. Testes com bancos sintéticos validam o código, não a presença de métricas naquela instalação.

## Fontes e escopo das evidências

- [Cursor SDK — getUsage](https://cursor.com/docs/sdk/typescript): API oficial de uso por agente; confirmar versão, identificação e acesso.
- [Cursor — Admin API](https://cursor.com/docs/account/teams/admin-api): uso por evento, quando disponível para a conta.
- [txcript — formato Cursor Desktop](https://github.com/skillsynchq/txcript/blob/main/docs/formats/cursor-desktop.md): documentação do autor de um parser sobre schema, timestamps e `tokenCount`; evidência de implementação independente, não contrato oficial do Cursor.
- [cursaves — armazenamento](https://github.com/Callum-Ward/cursaves/blob/main/docs/how-cursor-stores-chats.md): investigação do autor sobre armazenamento/índices de versões anteriores; mesma ressalva de compatibilidade.

Verificado em 29/09/2026. Revalidar formatos na instalação alvo antes de calcular.
