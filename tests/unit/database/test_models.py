"""
Unit Tests for Database Models

Tests:
- Model creation and validation
- Relationships
- Properties and methods
- Serialization (to_dict)
"""

import pytest
from datetime import datetime, timezone
from decimal import Decimal

from src.database.models.positions import OpenPosition


# ============================================================================
# OPEN POSITION MODEL TESTS
# ============================================================================

class TestOpenPositionModel:
    """Test OpenPosition model"""
    
    def test_create_position(self):
        """Test creating open position"""
        position = OpenPosition(
            number="ORD123456",
            type="BUY",
            size=Decimal("1.5"),
            symbol="CrudeOIL",
            price=Decimal("1850.50"),
            stop_loss=Decimal("1840.00"),
            take_profit=Decimal("1870.00"),
            commission=Decimal("5.00"),
            last_profit=Decimal("0.00"),
            last_update=datetime.now(timezone.utc),
            last_strategy="momentum",
            simulation=False,
        )
        
        assert position.number == "ORD123456"
        assert position.type == "BUY"
        assert position.size == Decimal("1.5")
        assert position.symbol == "CrudeOIL"
    
    def test_position_is_long(self):
        """Test is_long property"""
        position = OpenPosition(
            number="ORD123",
            type="BUY",
            size=Decimal("1.0"),
            symbol="CrudeOIL",
            price=Decimal("1850.00"),
            commission=Decimal("5.00"),
            last_update=datetime.now(timezone.utc),
            last_strategy="test",
        )
        
        assert position.is_long is True
        assert position.is_short is False
    
    @pytest.mark.database
    @pytest.mark.asyncio
    async def test_insert_position(self, db_session):
        """Test inserting position into database"""
        position = OpenPosition(
            number="ORD123456",
            type="BUY",
            size=Decimal("1.0"),
            symbol="CrudeOIL",
            price=Decimal("1850.50"),
            commission=Decimal("5.00"),
            last_update=datetime.now(timezone.utc),
            last_strategy="momentum",
        )
        
        db_session.add(position)
        await db_session.commit()
        
        assert position.id is not None
