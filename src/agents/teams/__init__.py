"""
AutoGen Team Orchestration for RiseTrader Multi-Agent System.

Provides team coordination patterns using AutoGen 0.4:
- Analysis Team: RoundRobinGroupChat for sequential analyst collaboration
- Debate Team: SelectorGroupChat for bull/bear adversarial reasoning
- Trading Pipeline: Swarm for multi-stage decision workflow

Teams coordinate multiple agents to make better trading decisions through
structured collaboration patterns.
"""

from src.agents.teams.analysis_team import create_analysis_team
from src.agents.teams.debate_team import create_debate_team
from src.agents.teams.trading_pipeline import create_trading_pipeline
from src.agents.teams.team_factory import AgentTeamFactory

__all__ = [
    "create_analysis_team",
    "create_debate_team",
    "create_trading_pipeline",
    "AgentTeamFactory",
]
