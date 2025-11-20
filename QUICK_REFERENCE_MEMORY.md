# Serena Memory vs Hooks vs CLAUDE.md - Quick Reference

## 🤔 Which Approach to Use?

### Use **Serena Automatic Memories** when:
✅ You need project structure understanding
✅ Claude needs to know your tech stack
✅ You want pattern recognition across codebase
✅ You need symbol-level code navigation

**Setup**: One-time onboarding
**Location**: `.serena/memories/` (auto-created)
**How**: Let Serena do it automatically

---

### Use **Serena Manual Memories** when:
✅ Building multi-day features
✅ Need to track progress between sessions
✅ Want to save "checkpoint" states
✅ Need to resume complex work later

**Setup**: Create on demand via memory-manager
**Location**: `.serena/memories/[feature]-progress.md`
**How**: 
```
"Use memory-manager to save progress on SignalGeneratorAgent"
```

---

### Use **CLAUDE.md** when:
✅ You have static, unchanging rules
✅ Setting coding standards/conventions
✅ Documenting architecture principles
✅ Providing project overview for ALL sessions

**Setup**: Create once, rarely update
**Location**: `.claude/CLAUDE.md`
**How**: Write markdown documentation

---

### Use **Hooks** when:
✅ You want automated actions (format, lint, test)
✅ Need validation before changes
✅ Want to log activity automatically
✅ Need to enforce quality gates

**Setup**: Configure in settings.json
**Location**: `.claude/settings.json`
**How**: Define shell commands or prompts

---

### Use **memory-manager Subagent** when:
✅ Starting a work session (load context)
✅ Ending a work session (save progress)
✅ Need to organize/consolidate memories
✅ Want status of all 10 agents

**Setup**: Add to `.claude/agents/`
**Location**: `.claude/agents/memory-manager.md`
**How**:
```
"Use memory-manager to load context"
"Use memory-manager to save progress"
```

---

## 📊 Comparison Table

| Feature | Serena Auto | Serena Manual | CLAUDE.md | Hooks | Memory-Manager |
|---------|-------------|---------------|-----------|-------|----------------|
| **Persistence** | Across sessions | Across sessions | Forever | Per session | Manages both |
| **Updates** | Automatic | Manual | Rarely | Never | On demand |
| **Use Case** | Code understanding | Progress tracking | Static rules | Automation | Session continuity |
| **Created By** | Serena | You/Agent | You | You | Subagent |
| **Token Cost** | High (onboarding) | Low | Free | Free | Low |
| **Best For** | Large codebases | Multi-day work | Standards | Quality gates | Organization |

---

## 🎯 RiseTrader Recommended Stack

### The Winning Combination:

```
┌─────────────────────────────────────────────┐
│  CLAUDE.md (Static Rules)                   │
│  ├─ Architecture principles                 │
│  ├─ Coding standards                        │
│  └─ Subagent delegation guidelines          │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Serena Automatic Memories                  │
│  ├─ .serena/memories/project-overview.md    │
│  ├─ .serena/memories/tech-stack.md          │
│  └─ .serena/cache/ (symbol index)           │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Hooks (Automation)                         │
│  ├─ Pre-edit: Backup                        │
│  ├─ Post-edit: Format, lint                 │
│  └─ On-stop: Prompt memory save             │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  memory-manager (Session Management)        │
│  ├─ Session start: Load context             │
│  ├─ Session end: Save progress              │
│  └─ Organize feature memories               │
└─────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────┐
│  Serena Manual Memories                     │
│  ├─ .serena/memories/signal-agent.md        │
│  ├─ .serena/memories/day-2025-11-16.md      │
│  └─ .serena/memories/mcp-architecture.md    │
└─────────────────────────────────────────────┘
```

---

## 🚀 Quick Start Checklist

### One-Time Setup
- [ ] Add Serena to Claude Code: `claude mcp add-json "serena" {...}`
- [ ] Run onboarding: `"Serena, run onboarding"`
- [ ] Create `.claude/CLAUDE.md` with RiseTrader rules
- [ ] Add hooks to `.claude/settings.json`
- [ ] Add `memory-manager.md` to `.claude/agents/`
- [ ] Add `.serena/` to `.gitignore`

### Daily Workflow
- [ ] **Morning**: `"Use memory-manager to load context"`
- [ ] **During**: Let Serena auto-use its memories
- [ ] **Progress**: `"Use memory-manager to checkpoint progress"`
- [ ] **Evening**: `"Use memory-manager to save progress"`

---

## 💡 Pro Tips

### Tip 1: Combine Them!
```
# In CLAUDE.md (static rule):
"Always delegate agent work to agent-developer subagent"

# Hook (automation):
After agent-developer edits, run tests

# Serena memory (tracking):
memory-manager tracks which agents are complete

# Result: Automated, tracked, consistent development!
```

### Tip 2: Use Hooks to Prompt Memory Saves
```json
{
  "hooks": {
    "Stop": [{
      "matcher": "*",
      "hooks": [{
        "type": "prompt",
        "prompt": "If we made significant progress, use memory-manager to save it"
      }]
    }]
  }
}
```

### Tip 3: CLAUDE.md → memory-manager Integration
```markdown
# In CLAUDE.md:

## Session Management
At start of every session:
1. Use memory-manager to load yesterday's context
2. Review active feature status
3. Identify today's priorities

At end of every session:
1. Use memory-manager to save progress
2. Note any blockers
3. Set priorities for next session
```

### Tip 4: Memory-Manager as Your "Project Manager"
```
"Use memory-manager to show status dashboard"

Outputs:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
📊 RiseTrader Development Status

Agents Completed: 4/10 (40%)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ MarketDataAgent
✅ MLPredictionAgent  
✅ RegimeDetectionAgent
✅ SignalGeneratorAgent
🔨 RiskManagerAgent (60%)
📋 ExecutionAgent
📋 PerformanceMonitor
📋 RiskOverseerAgent
📋 StrategyOptimizer
📋 DataQualityAgent
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Current Focus: RiskManagerAgent
Blockers: None
Next Up: ExecutionAgent
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

---

## 🎬 Real Example: Building SignalGeneratorAgent

### Monday (Setup)
```
# CLAUDE.md says: "All agents must follow event-driven pattern"
# Serena onboarding created: tech-stack.md, project-overview.md

"Use agent-developer to start SignalGeneratorAgent"
# Serena auto-uses its memories to understand the codebase

"Use memory-manager to save progress"
# Creates: signal-agent-progress.md, day-2025-11-18.md
```

### Tuesday (Continue)
```
"Use memory-manager to load context"
# Reads: signal-agent-progress.md, day-2025-11-18.md
# Shows: "Yesterday: Started SignalGeneratorAgent, 30% done"

"Continue SignalGeneratorAgent implementation"
# Serena uses cached symbols, project patterns

# Hook auto-runs after edits: Format, lint

"Use memory-manager to save progress"
# Updates: signal-agent-progress.md (now 70%)
# Creates: day-2025-11-19.md
```

### Wednesday (Complete)
```
"Use memory-manager to load context"
# Shows: SignalGeneratorAgent 70% complete, tests pending

"Complete SignalGeneratorAgent tests"

# Hook on-stop: "Did we finish a major feature?"
"Use memory-manager to mark SignalGeneratorAgent COMPLETE"

# Creates final memory: signal-agent-complete.md
```

---

## ❓ FAQ

**Q: Do I need ALL of these?**
A: No! Start with CLAUDE.md + Serena automatic. Add manual memories for long features. Add hooks when you want automation.

**Q: Which is most important?**
A: For RiseTrader's complexity: memory-manager + Serena automatic

**Q: Can I use Serena without memory-manager?**
A: Yes! memory-manager just makes it easier to organize.

**Q: Do hooks work without Serena?**
A: Yes! Hooks are independent. They can work with or without Serena.

**Q: Is CLAUDE.md required?**
A: No, but highly recommended for consistent behavior.

---

## 📚 Further Reading

- [SERENA_MEMORY_GUIDE.md](./SERENA_MEMORY_GUIDE.md) - Complete guide
- [memory-manager.md](./memory-manager.md) - Subagent details
- [README.md](./README.md) - Subagent overview

---

**TL;DR**: Use **CLAUDE.md** for rules, **Serena** for code understanding, **memory-manager** for progress tracking, and **hooks** for automation. Together they create an unstoppable development system! 🚀
