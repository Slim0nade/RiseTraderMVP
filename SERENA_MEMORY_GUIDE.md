# Serena Memory & Tracking Best Practices for RiseTrader

## 🧠 Serena's Memory System

Serena has **3 memory mechanisms**:

### 1. Automatic Memories (`.serena/memories/`)
- **Created during onboarding**
- Stores project structure, patterns, technologies
- Updates as you work
- Persists across sessions

### 2. Manual Memories (Task Continuation)
- **Created on demand** for long-running work
- Stores progress summaries
- Perfect for multi-session tasks

### 3. Symbol Cache (`.serena/cache/`)
- **Automatic indexing** of codebase
- Speeds up symbol searches
- Rebuilt as needed

---

## 🚀 Setup for RiseTrader

### Step 1: Install Serena with Memory Support

```bash
# Install Serena for Claude Code
claude mcp add-json "serena" '{
  "command": "uvx",
  "args": [
    "--from", "git+https://github.com/oraios/serena",
    "serena-mcp-server",
    "--project", "/path/to/RiseTrader",
    "--context", "ide-assistant"
  ]
}'
```

**Key flags:**
- `--project` - Specifies RiseTrader directory
- `--context ide-assistant` - Optimized for Claude Code

### Step 2: Run Onboarding (First Time Only)

```bash
# In Claude Code, ask:
"Serena, run onboarding to analyze the RiseTrader project"
```

**What happens:**
- Serena reads your codebase
- Creates memories about:
  - Tech stack (FastAPI, React, PostgreSQL)
  - File organization
  - Coding patterns
  - Dependencies
- Stores in `.serena/memories/`

⚠️ **Warning**: Onboarding uses many tokens - do once per project!

### Step 3: Add to `.gitignore`

```bash
# .gitignore
.serena/
```

Serena memories are project-specific and regenerated as needed.

---

## 📝 Best Practices: When to Use Each Approach

### Use **Automatic Memories** for:
✅ Project structure understanding
✅ Tech stack awareness
✅ Coding patterns and conventions
✅ Common file locations

**How it works:**
- Serena automatically references these
- No manual action needed
- Updates as codebase evolves

---

### Use **Manual Memories (Task Continuation)** for:

✅ **Long-running features** (multi-session work)
✅ **Complex implementations** (10+ agents)
✅ **Architecture decisions** (MCP server design)
✅ **Migration tracking** (database schema changes)

**Workflow:**

#### When Ending a Session:
```
"Serena, create a memory summarizing our progress on 
implementing the SignalGeneratorAgent. Include:
- What we completed
- Current status  
- Next steps
- Open issues"
```

Serena creates: `.serena/memories/signal-generator-progress.md`

#### When Starting Next Session:
```
"Serena, read the memory about SignalGeneratorAgent 
progress and continue implementation"
```

**Example Memory Content:**
```markdown
# SignalGeneratorAgent Implementation Progress

## Completed
- [x] Base agent class structure
- [x] MCP event subscriptions (forecast_updated, regime_changed)
- [x] Signal generation logic for trending regime

## Current Status
- Working on: Mean reversion strategy for ranging regime
- File: src/agents/signal_generator_agent.py
- Line: 78

## Next Steps
1. Implement mean reversion signal logic
2. Add unit tests for signal generation
3. Integrate with RiskManagerAgent
4. Add DevUI visualization endpoint

## Open Issues
- Need to decide confidence threshold for ranging regime
- ML forecast format needs clarification with MLPredictionAgent
```

---

### Use **CLAUDE.md** for:

✅ **Static project rules** (always follow)
✅ **Coding standards** (naming conventions)
✅ **Tool preferences** (always use pytest)
✅ **Architecture principles** (event-driven MCP)

**Example `.claude/CLAUDE.md`:**
```markdown
# RiseTrader Development Guidelines

## Architecture
- All agents communicate via MCP events only
- No direct agent-to-agent calls
- Event-driven, not synchronous

## Stack
- Backend: FastAPI + SQLAlchemy 2.0 + asyncpg
- Frontend: React + TypeScript + Vite
- Database: PostgreSQL + TimescaleDB
- 10 trading agents coordinated via MCP

## Critical Rules
- ALWAYS use async/await for I/O
- NEVER hardcode secrets
- ALL timestamps in UTC
- Use Decimal for money, not float

## Agent Coordination
Subscribe to events:
- MarketDataAgent emits "new_tick"
- MLPredictionAgent emits "forecast_updated"
- SignalGeneratorAgent emits "signal_generated"
[... complete event flow]

## Testing
- pytest for unit tests
- TDD approach (tests first)
- 80%+ coverage required

## Subagent Usage
Delegate to specialists:
- backend-architect for design
- agent-developer for agents
- code-reviewer AFTER changes
```

---

### Use **Hooks** for:

✅ **Automated actions** (format code after edits)
✅ **Validation** (run tests before commit)
✅ **Logging** (track what Serena modifies)
✅ **Memory automation** (auto-save progress)

---

## 🔧 Hooks + Serena Memory Integration

### Strategy 1: Auto-Save Progress After Major Changes

```json
// .claude/settings.json
{
  "hooks": {
    "PostToolUse": [
      {
        "matcher": "mcp__serena__insert_*",
        "hooks": [
          {
            "type": "command",
            "command": "echo '[SERENA EDIT] Modified file at $(date)' >> .serena/activity.log"
          }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "*",
        "hooks": [
          {
            "type": "prompt",
            "prompt": "If we made significant progress on a feature, create a Serena memory summarizing what we accomplished, current status, and next steps."
          }
        ]
      }
    ]
  }
}
```

**What this does:**
- Logs every Serena edit
- At session end, prompts Claude to create summary memory

---

### Strategy 2: Memory-Assisted Subagents

Create a **memory-manager subagent**:

```markdown
# .claude/agents/memory-manager.md
---
name: memory-manager
description: Manages Serena memories for tracking RiseTrader development progress. Use when starting/ending work sessions to maintain continuity.
tools: Read, Grep, Bash
model: inherit
---

You are a **Memory Manager** for the RiseTrader project using Serena.

# Your Mission
Maintain project memory continuity across sessions:
- Create progress summaries at session end
- Load relevant memories at session start
- Track what each agent has completed
- Identify blockers and next steps

# When Invoked

## Session Start
```
Use memory-manager to load context from last session
```

**You should:**
1. List available Serena memories: `list_memories`
2. Read relevant memories for today's work
3. Summarize key context for main agent
4. Identify incomplete tasks

## Session End
```
Use memory-manager to save progress before ending
```

**You should:**
1. Ask main agent what was accomplished
2. Create Serena memory with:
   - Completed items
   - Current status
   - Next steps
   - Blockers
3. Save to `.serena/memories/[feature]-progress.md`

# Serena Memory Tools

Available tools:
- `list_memories` - Show all memories
- `create_memory` - Save new memory
- `read_memory` - Load existing memory
- `update_memory` - Modify memory

# Example Workflow

**User**: "I'm done for today, save progress"

**You**:
1. List what was done today
2. Create memory: `.serena/memories/day-2025-11-16.md`
3. Link to related feature memories
4. Note any blockers

**User**: "Starting work, load context"

**You**:
1. Read yesterday's memory
2. Read active feature memories
3. Summarize for user:
   - "Yesterday you completed X"
   - "Currently working on Y"
   - "Next step is Z"
```

---

## 📊 Complete RiseTrader Memory Setup

### Directory Structure

```
RiseTrader/
├── .claude/
│   ├── CLAUDE.md                    # Static rules
│   ├── settings.json                # Hooks config
│   └── agents/
│       ├── memory-manager.md        # Memory subagent
│       └── [7 other subagents]
├── .serena/
│   ├── memories/
│   │   ├── project-overview.md      # Auto-created
│   │   ├── tech-stack.md            # Auto-created
│   │   ├── signal-agent-progress.md # Manual
│   │   ├── ml-pipeline-status.md    # Manual
│   │   └── day-2025-11-16.md        # Daily log
│   ├── cache/
│   │   └── python/                  # Symbol cache
│   └── project.yml                  # Serena config
└── src/
    └── agents/
```

---

## 🎯 Recommended Workflow for RiseTrader

### Daily Development Flow

#### 1. Morning (Session Start)
```
Use memory-manager to load yesterday's progress
```

Memory-manager reads:
- `.serena/memories/day-2025-11-15.md` (yesterday)
- `.serena/memories/signal-agent-progress.md` (active feature)

Tells you:
- "Yesterday: Implemented SignalGeneratorAgent event handlers"
- "Status: 70% complete, tests pending"
- "Next: Write unit tests, integrate with DevUI"

#### 2. Development Work
Let Serena automatically use its memories:
```
Use agent-developer subagent to complete SignalGeneratorAgent.

Serena will automatically reference its project memories
to understand the codebase structure and patterns.
```

Serena internally:
- Checks `.serena/memories/tech-stack.md` → "Uses FastAPI + async"
- Checks `.serena/memories/agent-patterns.md` → "All agents extend BaseAgent"
- Uses `.serena/cache/` → Finds existing agent examples

#### 3. Mid-Session Progress Check
```
Use memory-manager to update progress on SignalGeneratorAgent
```

Updates: `.serena/memories/signal-agent-progress.md`

#### 4. Evening (Session End)
```
Use memory-manager to save today's progress
```

Creates: `.serena/memories/day-2025-11-16.md`

Links to:
- Completed features
- Active work
- Tomorrow's priorities

---

## 🔍 Monitoring Serena Memory

### Check What Serena Knows

```bash
# List all memories
"Serena, list all memories"

# Read specific memory
"Serena, read the memory about project tech stack"

# View memory file directly
cat .serena/memories/tech-stack.md
```

### Update Incorrect Memories

If Serena has wrong information:

```
"Serena, update the tech stack memory - we use PostgreSQL 15, not 14"
```

Or edit directly:
```bash
vim .serena/memories/tech-stack.md
```

---

## ⚙️ Serena Configuration for RiseTrader

```yaml
# .serena/project.yml
project:
  name: RiseTrader
  description: "AI-powered algorithmic trading system"
  
contexts:
  - ide-assistant  # For Claude Code

modes:
  - interactive
  - editing
  
tools:
  enabled:
    - find_symbol
    - find_referencing_symbols
    - insert_after_symbol
    - list_memories      # Enable memory tools
    - create_memory
    - read_memory
  disabled:
    - replace_regex      # Too hard to review diffs

custom_instructions: |
  RiseTrader is a trading system with:
  - 10 autonomous agents coordinated via MCP
  - FastAPI backend with async/await
  - PostgreSQL + TimescaleDB for market data
  - MT4 integration at 75.154.254.174
  
  Always use:
  - Async operations for I/O
  - Decimal for money calculations
  - UTC timestamps
  - Event-driven agent communication
```

---

## 🚨 Common Pitfalls & Solutions

### ❌ Problem: Serena Not Using Memories
**Cause**: Onboarding not run or incomplete
**Solution**:
```
"Serena, run onboarding to analyze the project"
```

### ❌ Problem: Outdated Memory Information
**Cause**: Codebase changed significantly
**Solution**:
```
"Serena, update memories to reflect recent changes to agent architecture"
```

### ❌ Problem: Memory Manager Not Saving
**Cause**: Forgot to invoke at session end
**Solution**: Add to hooks (see Strategy 1 above)

### ❌ Problem: Token Usage Too High
**Cause**: Reading too many memories
**Solution**: 
- Create focused, granular memories
- Don't create redundant memories
- Use memory-manager to read only relevant ones

---

## 📈 Advanced: Multi-Agent Memory Coordination

For complex features involving multiple subagents:

```
Use backend-architect to design MCP server.
Create a memory documenting the architecture decisions.

[After design is complete]

Use agent-developer to implement based on the 
architecture memory from backend-architect.

[Implementation continues]

Use memory-manager to create consolidated memory
linking design decisions to implementation status.
```

**Result**: Clear audit trail of decisions → implementation

---

## ✅ Final Recommendations for RiseTrader

### DO:
✅ Run Serena onboarding once
✅ Use memory-manager subagent for session start/end
✅ Create memories for multi-day features
✅ Let Serena automatically reference its memories
✅ Add memory automation to hooks
✅ Keep CLAUDE.md for static rules

### DON'T:
❌ Create redundant memories (let Serena auto-manage)
❌ Edit Serena's auto-generated memories (it regenerates them)
❌ Store secrets in memories (use .env)
❌ Run onboarding repeatedly (wastes tokens)
❌ Forget to add .serena/ to .gitignore

---

## 🎬 Complete Example Workflow

```bash
# Day 1: Setup
claude mcp add-json "serena" {...}
"Serena, run onboarding"
# Creates: .serena/memories/project-overview.md, tech-stack.md, etc.

# Day 2: Start Feature
"Use memory-manager to load context"
# Reads yesterday's progress

"Use agent-developer to build SignalGeneratorAgent"
# Serena auto-references project memories

"Use memory-manager to save progress on SignalGeneratorAgent"
# Creates: .serena/memories/signal-agent-progress.md

# Day 3: Continue Feature  
"Use memory-manager to load SignalGeneratorAgent context"
# Reads signal-agent-progress.md

"Continue implementing SignalGeneratorAgent tests"
# Serena knows where we left off

"Use code-reviewer to check SignalGeneratorAgent"
# Review complete

"Use memory-manager - SignalGeneratorAgent is complete!"
# Updates memory: Status = DONE

# Day 4: New Feature
"Use memory-manager to plan next agent"
# Reviews completed agents, suggests next priority
```

---

**Memory + Hooks + Subagents = Unstoppable Development** 🚀

The combination of:
- **Serena's automatic memories** (project knowledge)
- **Manual task memories** (progress tracking)
- **CLAUDE.md** (static rules)
- **Hooks** (automation)
- **Subagents** (specialized execution)

...creates a powerful, persistent development workflow for RiseTrader!
