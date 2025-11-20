# Serena Memory Directory

This directory contains session memory and quick reference files for RiseTraderMVP.

## Files:

### 1. `QUICK_START.md`
Quick reference guide for starting new Claude Code sessions:
- Infrastructure status checks
- Available subagents
- Database connection info
- First development tasks
- Security reminders

**USE THIS:** At the start of every new session to orient yourself.

### 2. `SESSION_PROGRESS_2025-11-16.md`
Detailed session notes from November 16, 2025:
- Complete list of what was accomplished
- Infrastructure setup details
- Database restoration summary
- Files created/modified
- Architecture overview
- Next steps planning

**USE THIS:** To understand what was done in previous sessions.

### 3. `project.yml`
Serena configuration file (auto-generated):
- Project name and location
- Language settings
- Serena integration config

**DO NOT EDIT** unless you know what you're doing.

## How Serena Memory Works:

Serena is an MCP (Model Context Protocol) server that provides:
- Long-term project memory across sessions
- Code intelligence and navigation
- Project-aware tool execution

**Configuration Files:**
- Global: `~/.serena/serena_config.yml`
- Project-specific: `.serena/project.yml` (this directory)

**Registered Projects:**
- RiseBackendMVP (port 5432)
- RiseTraderMVP (port 5433) ← You are here

## Creating New Session Progress Files:

When a session ends, create a new file:
```
SESSION_PROGRESS_YYYY-MM-DD.md
```

Follow the same format as SESSION_PROGRESS_2025-11-16.md:
1. Completed tasks (with checkmarks)
2. Current infrastructure status
3. Next session tasks
4. Key decisions made
5. Files modified/created

## Quick Commands:

```bash
# View all session progress files
ls -lh /Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP/.serena/SESSION_PROGRESS_*.md

# Read the latest session
cat /Users/slimrouissi/Documents/VSCode/Rise/RiseTraderMVP/.serena/QUICK_START.md

# Check Serena is running
curl http://127.0.0.1:24283/ 2>/dev/null | head -1
```

## Integration with Claude Code:

These files are designed to be read by Claude Code at the start of each session to:
1. Understand what was done previously
2. Know what infrastructure is available
3. Identify the next priority tasks
4. Access key configuration info quickly

**Best Practice:** Always reference these files when starting work on RiseTraderMVP.

---

Last Updated: November 16, 2025
