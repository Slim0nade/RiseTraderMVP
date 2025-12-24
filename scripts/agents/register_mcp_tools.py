#!/usr/bin/env python3
"""
Register MCP Tools in Database

Reads MCP tool contracts from contracts/mcp-tools.yaml and registers them
in the mcp_tools database table for agent access.

Uses REAL database connection - no mocks!
"""

import asyncio
import os
import sys
from pathlib import Path
from uuid import uuid4
import yaml

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker

from src.database.models.mcp_tool import MCPTool
from src.database.repositories.mcp_tool_repository import MCPToolRepository


# MCP tool implementation mappings
TOOL_IMPLEMENTATIONS = {
    "get_tcn_forecast": "src.ml.tools.forecasting_tools.get_tcn_forecast",
    "get_tft_prediction": "src.ml.tools.forecasting_tools.get_tft_prediction",
    "get_fedformer_regime": "src.ml.tools.forecasting_tools.get_fedformer_regime",
    "calculate_kelly": "src.ml.tools.calculation_tools.calculate_kelly",
    "calculate_atr": "src.ml.tools.calculation_tools.calculate_atr",
    "get_support_resistance": "src.ml.tools.market_structure_tools.get_support_resistance",
    "detect_liquidity_clusters": "src.ml.tools.market_structure_tools.detect_liquidity_clusters",
    "get_economic_events": "src.ml.tools.data_retrieval_tools.get_economic_events",
    "get_cot_data": "src.ml.tools.data_retrieval_tools.get_cot_data",
}


async def load_mcp_contracts(contracts_path: str) -> dict:
    """
    Load MCP tool contracts from YAML file.

    Args:
        contracts_path: Path to mcp-tools.yaml

    Returns:
        Dictionary of tool contracts
    """
    with open(contracts_path, 'r') as f:
        contracts = yaml.safe_load(f)

    print(f"✅ Loaded MCP contracts from {contracts_path}")
    return contracts


async def register_tool(
    repo: MCPToolRepository,
    tool_name: str,
    tool_spec: dict,
    category: str
) -> MCPTool:
    """
    Register a single MCP tool in the database.

    Args:
        repo: MCPToolRepository instance
        tool_name: Tool name (e.g., 'get_tcn_forecast')
        tool_spec: Tool specification from contract
        category: Tool category (e.g., 'ml_forecast')

    Returns:
        Created MCPTool instance
    """
    # Check if tool already exists
    existing = await repo.get_by_tool_name(tool_name)
    if existing:
        print(f"⚠️  Tool '{tool_name}' already registered (ID: {existing.id})")
        return existing

    # Extract schemas
    input_schema = tool_spec.get('input', {})
    output_schema = tool_spec.get('output', {})

    # Get implementation path
    implementation_path = TOOL_IMPLEMENTATIONS.get(
        tool_name,
        f"src.ml.tools.{category}.{tool_name}"
    )

    # Extract performance config
    performance = tool_spec.get('performance', {})
    timeout_ms = performance.get('timeout_ms', 5000)
    cache_ttl = performance.get('cache_ttl_seconds', 300)
    circuit_breaker_threshold = performance.get('circuit_breaker_threshold', 5)

    # Create tool instance
    tool = MCPTool(
        id=uuid4(),
        tool_name=tool_name,
        display_name=tool_spec.get('description', tool_name.replace('_', ' ').title()),
        tool_type=category,
        description=tool_spec.get('description', ''),
        input_schema=input_schema,
        output_schema=output_schema,
        implementation_path=implementation_path,
        version="1.0.0",
        allowed_agent_types=[],  # All agents can use by default
        requires_approval=False,
        is_active=True,
        is_beta=False,
        total_calls=0,
        successful_calls=0,
        error_count=0,
        config={
            'cache_ttl_seconds': cache_ttl,
            'circuit_breaker_threshold': circuit_breaker_threshold,
        },
        rate_limit_per_minute=None,  # No rate limit initially
        timeout_seconds=timeout_ms // 1000,  # Convert ms to seconds
        created_by='system',
        notes=f"Registered from contracts/mcp-tools.yaml",
        documentation_url=None
    )

    # Save to database
    repo.session.add(tool)
    await repo.session.commit()
    await repo.session.refresh(tool)
    print(f"✅ Registered tool: {tool_name} (ID: {tool.id})")

    return tool


async def register_all_tools():
    """
    Register all MCP tools from contracts file.
    """
    # Get database URL from environment
    database_url = os.getenv(
        'DATABASE_URL',
        'postgresql+asyncpg://postgres:risetrader2024@localhost:5433/risetrader'
    )

    print(f"🔌 Connecting to database: {database_url.split('@')[1]}")

    # Create async engine
    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(
        engine, class_=AsyncSession, expire_on_commit=False
    )

    # Load contracts
    contracts_path = Path(__file__).parent.parent.parent / 'specs' / '005-intelligent-agent-trading' / 'contracts' / 'mcp-tools.yaml'
    contracts = await load_mcp_contracts(str(contracts_path))

    # Start database session
    async with async_session() as session:
        repo = MCPToolRepository(session)

        registered_count = 0
        skipped_count = 0

        # Register ML forecast tools
        if 'ml_forecasts' in contracts:
            print("\n📊 Registering ML Forecast Tools...")
            for tool_name, tool_spec in contracts['ml_forecasts'].items():
                try:
                    tool = await register_tool(repo, tool_name, tool_spec, 'ml_forecast')
                    if tool:
                        registered_count += 1
                    else:
                        skipped_count += 1
                except Exception as e:
                    print(f"❌ Error registering {tool_name}: {e}")
                    skipped_count += 1

        # Register calculation tools
        if 'calculations' in contracts:
            print("\n🧮 Registering Calculation Tools...")
            for tool_name, tool_spec in contracts['calculations'].items():
                try:
                    tool = await register_tool(repo, tool_name, tool_spec, 'calculation')
                    if tool:
                        registered_count += 1
                    else:
                        skipped_count += 1
                except Exception as e:
                    print(f"❌ Error registering {tool_name}: {e}")
                    skipped_count += 1

        # Register market structure tools
        if 'market_structure' in contracts:
            print("\n📈 Registering Market Structure Tools...")
            for tool_name, tool_spec in contracts['market_structure'].items():
                try:
                    tool = await register_tool(repo, tool_name, tool_spec, 'market_structure')
                    if tool:
                        registered_count += 1
                    else:
                        skipped_count += 1
                except Exception as e:
                    print(f"❌ Error registering {tool_name}: {e}")
                    skipped_count += 1

        # Register data retrieval tools
        if 'data_retrieval' in contracts:
            print("\n📡 Registering Data Retrieval Tools...")
            for tool_name, tool_spec in contracts['data_retrieval'].items():
                try:
                    tool = await register_tool(repo, tool_name, tool_spec, 'data_retrieval')
                    if tool:
                        registered_count += 1
                    else:
                        skipped_count += 1
                except Exception as e:
                    print(f"❌ Error registering {tool_name}: {e}")
                    skipped_count += 1

        # Commit all changes
        await session.commit()

        print("\n" + "="*60)
        print(f"✅ MCP Tool Registration Complete!")
        print(f"   Registered: {registered_count} tools")
        print(f"   Skipped: {skipped_count} tools (already existed)")
        print("="*60)

    # Close engine
    await engine.dispose()


async def main():
    """Main entry point."""
    try:
        await register_all_tools()
    except Exception as e:
        print(f"\n❌ Registration failed: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
