# Skills in this pack

Copy **each subdirectory** (the folder that contains `SKILL.md`) into the client environment:

| Destination | Scope |
|---|---|
| `~/.cursor/skills/` | All Cursor projects for this user |
| `{other-repo}/.cursor/skills/` | One repo only |
| Claude / Codex skill dirs | Follow that product's skill layout |

Copy the folders themselves, not only `SKILL.md`:

```
paperfect-pipeline/
paperfect-reading/
paperfect-library/
paperfect-prompts/
```

Skills tell the agent **when and in what order** to call MCP tools. They do not run Python. The MCP server in the parent folder must also be registered, or the agent cannot process PDFs.
