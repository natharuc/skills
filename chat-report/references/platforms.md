# Fontes e integração por agente

Usar como mapa de descoberta, não como garantia de acesso. Verificado em 29/09/2026. Confirmar a versão instalada e a documentação vigente quando o esquema divergir. Não criar integração administrativa nem habilitar telemetria como efeito colateral de um relatório.

## Instalação local e invocação

Copiar a pasta completa com nome `chat-report`, preservando `SKILL.md` e `references/`; manter `scripts/` para cálculo opcional. Usar somente uma localização por instalação para evitar duplicatas. Resolver `~` como o diretório pessoal do sistema; não assumir Bash no Windows. Se distribuir apenas `SKILL.md`, conservar as regras nele e omitir recursos indisponíveis sem alegar tê-los executado.

| Host | Pasta no projeto | Alternativa pessoal | Invocação |
|---|---|---|---|
| Cursor | `.cursor/skills/chat-report/` ou `.agents/skills/chat-report/` | `~/.cursor/skills/chat-report/` | `/chat-report` |
| Claude Code | `.claude/skills/chat-report/` | `~/.claude/skills/chat-report/` | `/chat-report` |
| Codex CLI/IDE | `.agents/skills/chat-report/` | `~/.agents/skills/chat-report/` | `$chat-report` ou seleção por `/skills` |
| Copilot CLI | `.github/skills/chat-report/` ou `.agents/skills/chat-report/` | `~/.copilot/skills/chat-report/` | `/chat-report` |
| ChatGPT com skill instalada | Diretório de skills do próprio host | Gerenciado pelo host | Selecionar `@chat-report` |
| Outro agente | Localização documentada pelo host | Conforme suporte | Carregar o SKILL.md como skill, comando ou instruções |

Não afirmar instalação no computador do usuário por ter salvo a skill em outro ambiente. Skills locais do Cursor não chegam automaticamente a sessões remotas. Não extrapolar suporte do Copilot CLI para todas as IDEs. Conferir a descoberta no host antes de prometer o comando. O arquivo `agents/openai.yaml` é metadado opcional; os outros agentes podem ignorá-lo.

Fontes de instalação:
- [Cursor — Skills](https://cursor.com/docs/skills)
- [Claude Code — Skills](https://code.claude.com/docs/en/skills)
- [OpenAI — Build skills](https://learn.chatgpt.com/docs/build-skills)
- [GitHub — Copilot CLI skills](https://docs.github.com/en/copilot/how-tos/copilot-cli/customize-copilot/add-skills)

## Cursor

Executar [cursor-local.md](cursor-local.md) antes de concluir indisponibilidade. Usar `scripts/inspect_cursor.py` para ler somente metadados do composer correto em `state.vscdb`, com detecção de schema. A transcrição e `ai-code-tracking.db` sozinhos não esgotam as fontes locais. O coletor retorna candidatos, não totais faturados, e não garante que a versão instalada tenha contadores preenchidos.

Priorizar exportação de consumo e logs da sessão efetivamente disponíveis. Quando houver acesso autorizado à Admin API, verificar `conversationId`, que pode estar ausente; sem vínculo de conversa, não atribuir precisamente os eventos a este chat. A presença de tokens também é opcional. Distinguir `chargedCents` (valor atribuído, incluindo taxa aplicável) de custo do modelo em `tokenUsage.totalCents`. Conferir tipo de uso e faturamento: consumo incluído no plano não demonstra pagamento adicional. Respeitar atraso e limites de atualização da fonte; não tratar ausência recente como zero.

Não pressupor que todo usuário/plano tenha Admin API. No CLI, inspecionar a saída estruturada disponível; não usar `duration_api_ms` como medição independente de `duration_ms` quando a implementação os iguala. Sem campos de uso, não reconstruir tokens a partir da duração.

Fontes:
- [Cursor — Admin API](https://cursor.com/docs/account/teams/admin-api)
- [Cursor CLI — Output format](https://cursor.com/docs/cli/reference/output-format)

## Claude Code

Consultar o resumo de uso disponível na versão, como `/usage` nas versões documentadas atualmente, ou dados que o usuário tenha exportado. Preservar custo estimado como estimativa, inclusive em assinaturas. Verificar limites da sessão, retomadas e resets antes de usar totais; não tratar nomes de comandos antigos como interface universal.

Quando já houver OpenTelemetry, procurar métricas/eventos de tokens, custo, duração e IDs para associar sessão e subagentes. Inspecionar a semântica de `claude_code.active_time.total` e sua dimensão `type`; atividade registrada pelo CLI não comprova atenção humana exclusiva à tarefa. Contador `total_tokens` em evento de conclusão de subagente pode representar somente sua última requisição, não toda a execução.

Na statusline, não interpretar `context_window.total_input_tokens` e `total_output_tokens` como acumulado faturado sem conferir o esquema: a documentação atual os descreve em relação ao contexto/última resposta. Separar duração de sessão e duração API.

Fontes:
- [Claude Code — Costs](https://code.claude.com/docs/en/costs)
- [Claude Code — Monitoring](https://code.claude.com/docs/en/monitoring-usage)
- [Claude Code — Statusline](https://code.claude.com/docs/en/statusline)

## Codex e ChatGPT

Usar os dados de uso/rollout que o host realmente exponha para a thread correta. No app-server, `thread/tokenUsage/updated` fornece atualizações de uso; eventos `turn/started`, `turn/completed` e itens possuem IDs úteis para reconstrução. Inspecionar schema e distinguir acumulado de último turno; não somar os dois.

Uma tool com `durationMs` não demonstra a duração completa da sessão. Associar sessões filhas pelos vínculos de colaboração. Não presumir que a interface ChatGPT exponha rollouts, métricas privadas ou arquivos locais. Percentuais de limites de assinatura não são tokens ou dinheiro. Se só houver conversa visível, gerar relatório parcial.

Fontes:
- [OpenAI — App server](https://learn.chatgpt.com/docs/app-server)
- [OpenAI — Codex pricing](https://developers.openai.com/codex/pricing)

## GitHub Copilot

Identificar a superfície: CLI, SDK ou chat de IDE. No CLI, consultar `/usage` quando disponível, preservando tokens por modelo e créditos na unidade original. Se utilizar OpenTelemetry já habilitado, não interpretar `github.copilot.cost` como dinheiro: a documentação do CLI o descreve como multiplicador de cobrança.

No SDK, verificar a versão: eventos `assistant.usage` podem ser efêmeros e não reaparecer ao retomar a sessão. Totais por `session.usage.getMetrics` dependem de suporte experimental. Não interpretar `session.usage_info.currentTokens` como consumo acumulado. Sem histórico completo, declarar cobertura parcial mesmo se a sessão puder ser retomada normalmente.

Fontes:
- [GitHub — Copilot CLI reference](https://docs.github.com/en/copilot/reference/copilot-cli-reference/cli-command-reference)
- [GitHub — SDK usage and billing](https://docs.github.com/en/copilot/how-tos/copilot-sdk/features/usage-and-billing)

## Agente não listado ou ambiente restrito

Inspecionar recursos disponíveis sem presumir caminhos/nomes de bancos. Se houver fonte oficial de uso, adaptar para as categorias do SKILL.md e registrar o mapeamento. Se não houver terminal, calcular com recurso nativo disponível ou apresentar contadores confiáveis sem agregação não verificável. Sem telemetria/timestamps, relatar entregas comprovadas e marcar as métricas ausentes como indisponíveis.

Para tarifas e câmbio, consultar fontes atuais somente quando o cálculo exigir. Não usar estas páginas de integração como prova de uma tarifa específica. Para acompanhamento futuro, usar as marcações manuais do SKILL.md ou propor instrumentação separada quando solicitada; não prometer recuperar dados que nunca foram registrados.
