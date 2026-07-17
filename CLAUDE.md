## AI entry point — read first

`AI_PROJECT_INDEX.md` is the **single source of truth** for any AI working on this project.
Read it first to orient. It must always reflect the latest project structure, documentation,
workflows, and development/deployment guidelines.

**Keep it in sync:** whenever the **architecture, workflow, deployment process/topology, or
documentation** changes, update `AI_PROJECT_INDEX.md` in the **same change** (never let it
drift). This includes new/moved components or services, added/removed/repurposed docs, and any
change to how the project is developed or deployed.

**Development & deployment workflow (assume this unless explicitly changed):**
1. Develop on the local machine (the git worktree is the source of truth).
2. Test locally (`pytest tests/unit`, plus integration/e2e where relevant; `mypy` + `ruff`).
3. Deploy to production (upload changed files to `/opt/telegram-bot`, rebuild affected images,
   `docker compose --profile bot-api -f docker-compose.prod.yml up -d`).

**Topology:** Local machine = development; **Production Server #1** = main Telegram Bot (app
stack); **Production Server #2** = self-hosted Telegram Bot API server. See the
"Development Workflow & Deployment Topology" section of `AI_PROJECT_INDEX.md` for details.

## graphify

This project has a knowledge graph at graphify-out/ with god nodes, community structure, and cross-file relationships.

Rules:
- For codebase questions, first run `graphify query "<question>"` when graphify-out/graph.json exists. Use `graphify path "<A>" "<B>"` for relationships and `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph, usually much smaller than GRAPH_REPORT.md or raw grep output.
- If graphify-out/wiki/index.md exists, use it for broad navigation instead of raw source browsing.
- Read graphify-out/GRAPH_REPORT.md only for broad architecture review or when query/path/explain do not surface enough context.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API cost).
