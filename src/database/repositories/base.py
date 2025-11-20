"""
Base repository with common CRUD operations.
"""
from typing import Any, Dict, Generic, List, Optional, Type, TypeVar

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.base import Base

ModelType = TypeVar("ModelType", bound=Base)


class BaseRepository(Generic[ModelType]):
    """
    Base repository providing common CRUD operations for all models.

    Uses SQLAlchemy 2.0 async syntax with type hints.
    """

    def __init__(self, model: Type[ModelType], session: AsyncSession):
        """
        Initialize repository.

        Args:
            model: SQLAlchemy model class
            session: Async database session
        """
        self.model = model
        self.session = session

    async def get(self, id: int) -> Optional[ModelType]:
        """
        Get a single record by ID.

        Args:
            id: Primary key ID

        Returns:
            Model instance or None if not found
        """
        query = select(self.model).where(self.model.id == id)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_all(
        self,
        limit: int = 100,
        offset: int = 0,
        order_by: Optional[str] = None,
        **filters: Any,
    ) -> List[ModelType]:
        """
        Get all records with pagination and optional filtering.

        Args:
            limit: Maximum number of records to return
            offset: Number of records to skip
            order_by: Column name to order by (defaults to id)
            **filters: Additional filter criteria

        Returns:
            List of model instances
        """
        query = select(self.model)

        # Apply filters
        for key, value in filters.items():
            if hasattr(self.model, key):
                query = query.where(getattr(self.model, key) == value)

        # Apply ordering
        if order_by and hasattr(self.model, order_by):
            query = query.order_by(getattr(self.model, order_by))
        elif hasattr(self.model, "id"):
            query = query.order_by(self.model.id)

        # Apply pagination
        query = query.limit(limit).offset(offset)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def create(self, data: Dict[str, Any]) -> ModelType:
        """
        Create a new record.

        Args:
            data: Dictionary of model attributes

        Returns:
            Created model instance
        """
        instance = self.model(**data)
        self.session.add(instance)
        await self.session.flush()
        await self.session.refresh(instance)
        return instance

    async def update(self, id: int, data: Dict[str, Any]) -> Optional[ModelType]:
        """
        Update an existing record.

        Args:
            id: Primary key ID
            data: Dictionary of attributes to update

        Returns:
            Updated model instance or None if not found
        """
        query = (
            update(self.model)
            .where(self.model.id == id)
            .values(**data)
            .returning(self.model)
        )
        result = await self.session.execute(query)
        await self.session.flush()
        return result.scalar_one_or_none()

    async def delete(self, id: int) -> bool:
        """
        Delete a record by ID.

        Args:
            id: Primary key ID

        Returns:
            True if deleted, False if not found
        """
        query = delete(self.model).where(self.model.id == id)
        result = await self.session.execute(query)
        await self.session.flush()
        return result.rowcount > 0

    async def bulk_insert(self, records: List[Dict[str, Any]]) -> int:
        """
        Bulk insert multiple records.

        Args:
            records: List of dictionaries containing model attributes

        Returns:
            Number of records inserted
        """
        instances = [self.model(**record) for record in records]
        self.session.add_all(instances)
        await self.session.flush()
        return len(instances)

    async def count(self, **filters: Any) -> int:
        """
        Count records matching filters.

        Args:
            **filters: Filter criteria

        Returns:
            Number of matching records
        """
        from sqlalchemy import func

        query = select(func.count()).select_from(self.model)

        # Apply filters
        for key, value in filters.items():
            if hasattr(self.model, key):
                query = query.where(getattr(self.model, key) == value)

        result = await self.session.execute(query)
        return result.scalar() or 0

    async def exists(self, id: int) -> bool:
        """
        Check if a record exists.

        Args:
            id: Primary key ID

        Returns:
            True if record exists, False otherwise
        """
        query = select(self.model.id).where(self.model.id == id).limit(1)
        result = await self.session.execute(query)
        return result.scalar_one_or_none() is not None

    async def get_by(self, **filters: Any) -> Optional[ModelType]:
        """
        Get a single record by filters.

        Args:
            **filters: Filter criteria

        Returns:
            Model instance or None if not found
        """
        query = select(self.model)

        for key, value in filters.items():
            if hasattr(self.model, key):
                query = query.where(getattr(self.model, key) == value)

        query = query.limit(1)
        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_many_by(self, **filters: Any) -> List[ModelType]:
        """
        Get multiple records by filters.

        Args:
            **filters: Filter criteria

        Returns:
            List of model instances
        """
        query = select(self.model)

        for key, value in filters.items():
            if hasattr(self.model, key):
                query = query.where(getattr(self.model, key) == value)

        result = await self.session.execute(query)
        return list(result.scalars().all())
