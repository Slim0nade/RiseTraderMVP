# ✅ RiseTrader Subagent & Memory System - Setup Complete!

## What's Been Installed

### 1. ✅ Claude Code Subagents (8 specialists)

Located in `.claude/agents/`:

- **backend-architect.md** - FastAPI/MCP architecture expert
- **ml-engineer.md** - PPO-LSTM & forecasting specialist
- **agent-developer.md** - Builds your 10 trading agents
- **database-specialist.md** - PostgreSQL/TimescaleDB expert
- **frontend-developer.md** - React/DevUI visualization
- **devops-engineer.md** - Docker/K8s/monitoring
- **code-reviewer.md** - Security & quality guardian
- **memory-manager.md** - Session continuity & progress tracking

### 2. ✅ Serena MCP Server

Installed and configured with:
- Project context: RiseTraderMVP
- Context mode: `ide-assistant`
- Memory location: `.serena/memories/`

### 3. 📋 Documentation Created

- **HOOKS_SETUP.md** - Guide for configuring automatic memory prompts
- **SETUP_COMPLETE.md** - This file (quick reference)

## 🚀 Next Steps (In Order)

### Step 1: Run Serena Onboarding (First Time Only)

This creates automatic project understanding:

```bash
# In Claude Code chat:
"Serena, run onboarding"
```

This will:
- Analyze your project structure
- Create baseline memories
- Set up automatic context awareness
- Takes ~2-3 minutes

### Step 2: Configure Hooks (Optional but Recommended)

See `.claude/HOOKS_SETUP.md` for detailed instructions.

**Quick version:**
1. Open Claude Code Settings
2. Search for "hooks"
3. Add reminder hooks for memory saves

### Step 3: Test the System

Try using a subagent:

```bash
# In Claude Code chat:
"Use backend-architect to design the MCP server architecture"
```

### Step 4: Start Building!

Use the full subagent team to build RiseTrader:

```bash
# Example workflow:
1. "Use memory-manager to load context"  # Session start
2. "Use backend-architect to design the agent base class"
3. "Use agent-developer to implement SignalGeneratorAgent"
4. "Use database-specialist to optimize the forecasts table"
5. "Use code-reviewer to check my implementation"
6. "Use memory-manager to save progress"  # Session end
```

## 📖 How to Use Subagents

### Syntax:

```bash
"Use [subagent-name] to [task]"
```

### Examples:

```bash
# Architecture & Design
"Use backend-architect to design the MCP event system"
"Use database-specialist to design the time-series schema"

# Implementation
"Use agent-developer to implement RiskManagerAgent"
"Use ml-engineer to build the PPO-LSTM forecasting model"
"Use frontend-developer to create the DevUI dashboard"

# DevOps & Deployment
"Use devops-engineer to create Docker Compose configuration"
"Use devops-engineer to set up Prometheus monitoring"

# Quality & Review
"Use code-reviewer to review the agent implementation"
"Use code-reviewer to check for security vulnerabilities"

# Memory Management
"Use memory-manager to load context"  # Start of session
"Use memory-manager to save progress"  # End of session
"Use memory-manager to summarize what we've built"
```

## 🎯 Recommended Daily Workflow

### Morning (Start of Session):
1. Open Claude Code in RiseTraderMVP project
2. "Use memory-manager to load context"
3. Review what was completed last session
4. Continue building

### During Work:
- Use specialist subagents for specific tasks
- backend-architect for design decisions
- agent-developer for agent implementation
- code-reviewer after each major component

### Evening (End of Session):
1. "Use memory-manager to save progress"
2. Memory-manager will record:
   - What was completed today
   - What's in progress
   - Next steps for tomorrow

## 🧠 Memory System Overview

**Three-Layer Memory:**

1. **Serena Automatic** (Passive)
   - Always running
   - Understands project structure
   - No manual effort

2. **memory-manager** (Active)
   - Tracks multi-day progress
   - You control when to save/load
   - Organized by session

3. **Hooks** (Automation)
   - Reminds you to save
   - Optional but helpful
   - See HOOKS_SETUP.md

## 🔍 Verify Installation

Run these checks:

```bash
# 1. Check subagents are installed
ls -la .claude/agents/
# Should show 8 .md files

# 2. Check Serena is installed
# In Claude Code chat:
"Serena, check status"

# 3. Test a subagent
"Use backend-architect to explain the MCP pattern"
```

## 📊 Project Context (Pre-loaded in Subagents)

All subagents know about:
- ✅ 10 RiseTrader agents (Signal, Risk, Execution, etc.)
- ✅ MT4 connection at 75.154.254.174
- ✅ PostgreSQL + Redis stack
- ✅ FastAPI + React architecture
- ✅ MLflow for experiment tracking
- ✅ Security requirements (encryption, auth)
- ✅ 11-week implementation timeline

## 🎓 Learning Resources

**Inside Subagents:**
- Each subagent includes examples and patterns
- Read them directly: `cat .claude/agents/backend-architect.md`

**Project Documentation:**
- CLAUDE.md - Project overview and architecture
- PROJECT_REBUILD_SPECIFICATION.md - Complete technical spec
- RiseTrader_FINAL_BUILD_PLAN.md - Implementation timeline

## 💡 Pro Tips

1. **Chain subagents** for complex tasks:
   ```
   "Use backend-architect to design the agent system, then use
   agent-developer to implement SignalGeneratorAgent, then use
   code-reviewer to review it"
   ```

2. **Save often** with memory-manager:
   - After completing each agent
   - Before switching to a different feature area
   - At natural breakpoints

3. **Use code-reviewer** before moving on:
   - Catches bugs early
   - Validates security
   - Ensures consistency

4. **Let subagents collaborate**:
   - backend-architect designs
   - agent-developer implements
   - database-specialist optimizes queries
   - code-reviewer validates
   - devops-engineer deploys

## 🚨 Important Reminders

1. **Serena runs automatically** - No need to explicitly call it (except for onboarding)
2. **memory-manager is manual** - You control when to load/save
3. **Hooks are optional** - But they make life easier
4. **Subagents complement each other** - Use the right specialist for each task

## 🎉 You're Ready!

Your development environment is fully configured with:
- ✅ 8 specialized AI subagents
- ✅ Persistent memory across sessions
- ✅ Complete project context
- ✅ Best practices and patterns

Start building RiseTrader's agent system! 🚀

## First Command to Try

```bash
"Use memory-manager to initialize project tracking, then use
backend-architect to explain the MCP server architecture we need to build"
```

---

**Questions or issues?** All subagent files are in `.claude/agents/` and can be modified as needed.
