# Dandelionz Backend — Claude Code Guidelines

## Agent & Tool Usage
- Use direct tools (Grep, Read, Glob, Edit) for all exploration and file work. Do NOT spawn Agent subagents unless the task genuinely requires parallelism across many files or the user explicitly asks.
- Never use `isolation: "worktree"` on Agent calls unless branch isolation is explicitly needed.
- For multi-file searches, prefer chained Grep/Glob calls over spawning an Explore agent.
