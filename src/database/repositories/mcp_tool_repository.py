"""
MCPTool repository for MCP tool registry management.
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.mcp_tool import MCPTool
from .base import BaseRepository


class MCPToolRepository(BaseRepository[MCPTool]):
    """Repository for MCPTool model operations."""

    def __init__(self, session: AsyncSession):
        """Initialize MCPToolRepository."""
        super().__init__(MCPTool, session)

    async def get_by_id(self, tool_id: UUID) -> Optional[MCPTool]:
        """Get tool by UUID."""
        query = select(MCPTool).where(MCPTool.id == tool_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_tool_name(self, tool_name: str) -> Optional[MCPTool]:
        """Get tool by unique tool name."""
        query = select(MCPTool).where(MCPTool.tool_name == tool_name)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_tool_type(
        self,
        tool_type: str,
        is_active: Optional[bool] = True
    ) -> List[MCPTool]:
        """Get tools by type."""
        query = select(MCPTool).where(MCPTool.tool_type == tool_type)

        if is_active is not None:
            query = query.where(MCPTool.is_active == is_active)

        query = query.order_by(MCPTool.tool_name)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_active_tools(self, is_beta: Optional[bool] = None) -> List[MCPTool]:
        """Get all active tools."""
        query = select(MCPTool).where(MCPTool.is_active == True)

        if is_beta is not None:
            query = query.where(MCPTool.is_beta == is_beta)

        query = query.order_by(MCPTool.tool_type, MCPTool.tool_name)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_tools_for_agent_type(
        self,
        agent_type: str,
        is_active: Optional[bool] = True
    ) -> List[MCPTool]:
        """Get tools available to a specific agent type."""
        query = select(MCPTool)

        if is_active is not None:
            query = query.where(MCPTool.is_active == is_active)

        # Filter by allowed_agent_types (JSON array contains agent_type or is empty)
        query = query.where(
            (func.jsonb_array_length(MCPTool.allowed_agent_types) == 0) |
            (MCPTool.allowed_agent_types.contains([agent_type]))
        )

        query = query.order_by(MCPTool.tool_name)
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, **kwargs) -> MCPTool:
        """Create a new tool."""
        tool = MCPTool(**kwargs)
        self.session.add(tool)
        await self.session.commit()
        await self.session.refresh(tool)
        return tool

    async def increment_calls(
        self,
        tool_id: UUID,
        success: bool,
        execution_time_ms: Optional[float] = None
    ) -> Optional[MCPTool]:
        """Increment tool call counters."""
        tool = await self.get_by_id(tool_id)
        if not tool:
            return None

        tool.total_calls += 1
        if success:
            tool.successful_calls += 1
        else:
            tool.error_count += 1

        # Update average execution time
        if execution_time_ms is not None and success:
            if tool.avg_execution_time_ms is None:
                tool.avg_execution_time_ms = execution_time_ms
            else:
                # Running average
                total_time = tool.avg_execution_time_ms * (tool.successful_calls - 1)
                tool.avg_execution_time_ms = (total_time + execution_time_ms) / tool.successful_calls

        tool.last_called_at = func.now()

        await self.session.commit()
        await self.session.refresh(tool)
        return tool

    async def record_error(
        self,
        tool_id: UUID,
        error_message: str
    ) -> Optional[MCPTool]:
        """Record a tool error."""
        tool = await self.get_by_id(tool_id)
        if not tool:
            return None

        tool.error_count += 1
        tool.last_error_message = error_message

        await self.session.commit()
        await self.session.refresh(tool)
        return tool

    async def activate(self, tool_id: UUID) -> Optional[MCPTool]:
        """Activate a tool."""
        tool = await self.get_by_id(tool_id)
        if not tool:
            return None

        tool.is_active = True
        await self.session.commit()
        await self.session.refresh(tool)
        return tool

    async def deactivate(self, tool_id: UUID) -> Optional[MCPTool]:
        """Deactivate a tool."""
        tool = await self.get_by_id(tool_id)
        if not tool:
            return None

        tool.is_active = False
        await self.session.commit()
        await self.session.refresh(tool)
        return tool
