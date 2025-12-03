"""
ModelConfiguration repository for versioned agent configurations.
"""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.model_configuration import ModelConfiguration
from .base import BaseRepository


class ModelConfigurationRepository(BaseRepository[ModelConfiguration]):
    """Repository for ModelConfiguration model operations."""

    def __init__(self, session: AsyncSession):
        """Initialize ModelConfigurationRepository."""
        super().__init__(ModelConfiguration, session)

    async def get_by_id(self, config_id: UUID) -> Optional[ModelConfiguration]:
        """Get configuration by UUID."""
        query = select(ModelConfiguration).where(ModelConfiguration.id == config_id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_name(self, config_name: str) -> Optional[ModelConfiguration]:
        """Get configuration by name."""
        query = select(ModelConfiguration).where(ModelConfiguration.config_name == config_name)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_agent_type(
        self,
        agent_type: str,
        config_type: Optional[str] = None,
        is_active: Optional[bool] = None
    ) -> List[ModelConfiguration]:
        """Get configurations for an agent type."""
        query = select(ModelConfiguration).where(ModelConfiguration.agent_type == agent_type)

        if config_type:
            query = query.where(ModelConfiguration.config_type == config_type)
        if is_active is not None:
            query = query.where(ModelConfiguration.is_active == is_active)

        query = query.order_by(ModelConfiguration.version.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_default_config(self, agent_type: str, config_type: str) -> Optional[ModelConfiguration]:
        """Get default configuration for an agent type."""
        query = select(ModelConfiguration).where(
            and_(
                ModelConfiguration.agent_type == agent_type,
                ModelConfiguration.config_type == config_type,
                ModelConfiguration.is_default == True
            )
        )
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_active_configs(
        self,
        agent_type: Optional[str] = None,
        config_type: Optional[str] = None
    ) -> List[ModelConfiguration]:
        """Get all active configurations."""
        query = select(ModelConfiguration).where(ModelConfiguration.is_active == True)

        if agent_type:
            query = query.where(ModelConfiguration.agent_type == agent_type)
        if config_type:
            query = query.where(ModelConfiguration.config_type == config_type)

        query = query.order_by(ModelConfiguration.agent_type, ModelConfiguration.version.desc())
        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, **kwargs) -> ModelConfiguration:
        """Create a new configuration."""
        config = ModelConfiguration(**kwargs)
        self.session.add(config)
        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def activate(self, config_id: UUID) -> Optional[ModelConfiguration]:
        """Activate a configuration."""
        config = await self.get_by_id(config_id)
        if not config:
            return None

        config.is_active = True
        await self.session.commit()
        await self.session.refresh(config)
        return config

    async def deactivate(self, config_id: UUID) -> Optional[ModelConfiguration]:
        """Deactivate a configuration."""
        config = await self.get_by_id(config_id)
        if not config:
            return None

        config.is_active = False
        await self.session.commit()
        await self.session.refresh(config)
        return config
