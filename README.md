# Skills

Skills portáveis para agentes de programação.

## chat-report

Gera um relatório **HTML completo, responsivo e offline** sobre uma conversa ou tarefa, com:

- tokens de entrada, saída e cache, conforme a telemetria disponível;
- dedicação humana, execução dos agentes e tempo decorrido separados;
- cobrança atribuída, referência de API e valor-hora, sem misturar seus significados;
- fontes, cobertura, entregas e limitações;
- coleta local de metadados do Cursor em modo somente leitura.

A skill deve abrir o relatório na visualização nativa do agente. Quando a interface não suporta HTML, entrega o arquivo pronto e informa essa limitação.

### Instalação

Copie a pasta completa [chat-report](./chat-report), incluindo seus recursos, para a localização do seu agente:

| Agente | Pasta no projeto |
|---|---|
| Cursor | `.cursor/skills/chat-report/` |
| Claude Code | `.claude/skills/chat-report/` |
| Codex CLI/IDE | `.agents/skills/chat-report/` |
| Copilot CLI | `.github/skills/chat-report/` |

Consulte [integrações e alternativas](./chat-report/references/platforms.md).

### Uso

```text
/chat-report
/chat-report detalhado
/chat-report diagnosticar
```

No Codex CLI, invoque como `$chat-report`. Para marcar dedicação humana manualmente, use `iniciar`, `pausar`, `retomar` e `encerrar` após o nome da skill.

### Recursos

- [Instruções completas](./chat-report/SKILL.md)
- [Coleta no Cursor](./chat-report/references/cursor-local.md)
- [Cálculo auditável](./chat-report/references/calculation.md)
- [Geração e visualização HTML](./chat-report/references/html-report.md)

Os scripts opcionais usam Python 3, sem dependências externas. O agente pode executar um fluxo equivalente quando Python não estiver disponível.

A skill não recupera dados que nunca foram registrados. Contadores locais zerados, contexto ocupado e tempo de chat aberto não comprovam consumo zero, tokens faturados ou horas humanas. A coleta precisa ser verificada na instalação real.
