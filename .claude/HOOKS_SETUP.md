# Hooks Setup for RiseTrader Memory Management

## What Are Hooks?

Hooks are shell commands that execute automatically in response to Claude Code events. They're perfect for automating memory saves and context management.

## Recommended Hooks for RiseTrader

### 1. Session End Hook (Prompts to Save Progress)

When you're wrapping up work, this hook will remind you to save progress using the memory-manager subagent.

**To configure:**
1. Open Claude Code settings (File → Preferences → Settings)
2. Search for "hooks"
3. Add a custom hook for session management

**Example Hook Configuration:**

```json
{
  "claude.hooks.userPromptSubmit": "echo '\n💾 Tip: Use memory-manager to save progress before ending session'"
}
```

### 2. Project Switch Hook (Loads Context)

When starting a session, automatically remind to load context.

```json
{
  "claude.hooks.projectOpen": "echo '🚀 RiseTrader Session Started\n📖 Use: memory-manager to load context'"
}
```

## Manual Setup (Alternative)

If hooks aren't available in your Claude Code version, you can:

### Morning Routine (Session Start):
```bash
# In Claude Code chat:
"Use memory-manager to load context"
```

### Evening Routine (Session End):
```bash
# In Claude Code chat:
"Use memory-manager to save progress"
```

## Hook Best Practices

1. **Keep hooks simple** - Just echo reminders, don't run complex commands
2. **Use memory-manager subagent** - Let it handle the actual memory operations
3. **Be consistent** - Run load/save at predictable times
4. **Review periodically** - Check `.serena/memories/` weekly to clean up

## Testing Your Setup

After configuring hooks, test them:

```bash
# 1. Start a new Claude Code session
# 2. Look for the "load context" reminder
# 3. Do some work (e.g., implement an agent)
# 4. Before closing, look for the "save progress" reminder
```

## Integration with Serena

Hooks work perfectly with Serena's automatic memory:

- **Serena automatic** = Understands codebase structure (passive)
- **memory-manager** = Tracks implementation progress (active)
- **Hooks** = Reminds you to use memory-manager (automation)

## Example Workflow

```
Session Start:
  → Hook reminds: "Use memory-manager to load context"
  → You: "Use memory-manager to load context"
  → Memory-manager loads last session's progress
  → Continue where you left off

During Work:
  → Use subagents: backend-architect, agent-developer, etc.
  → Make progress on agents

Session End:
  → Hook reminds: "Use memory-manager to save progress"
  → You: "Use memory-manager to save progress"
  → Memory-manager saves current state
  → Next session picks up seamlessly
```

## Troubleshooting

**Hooks not firing?**
- Check Claude Code settings are saved
- Restart Claude Code
- Verify hook syntax in settings

**Memory not persisting?**
- Ensure Serena is installed: `claude mcp list`
- Check `.serena/memories/` exists
- Run onboarding if needed

## Next Steps

After setting up hooks:

1. Run Serena onboarding (see SETUP_COMPLETE.md)
2. Test memory-manager subagent
3. Start building with the 7 specialist subagents
4. Enjoy persistent memory across sessions! 🎉
