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


# ============================================================================
# MT4 POSITION MODEL TESTS (T036 - User Story 2)
# ============================================================================

class TestMT4PositionModel:
    """Test MT4Position model P&L calculations and helper methods."""

    def test_create_mt4_position(self):
        """Test creating MT4 position"""
        from src.database.models.mt4_positions import MT4Position

        position = MT4Position(
            ticket_number=12345,
            magic_number=100001,
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            open_price=Decimal("75.50"),
            current_price=Decimal("75.75"),
            unrealized_pnl=Decimal("25.00"),
            open_time=datetime(2025, 11, 22, 10, 0, 0),
            last_updated=datetime(2025, 11, 22, 10, 5, 0)
        )

        assert position.ticket_number == 12345
        assert position.symbol == "CrudeOIL"
        assert position.direction == "BUY"
        assert position.unrealized_pnl == Decimal("25.00")

    def test_calculate_pnl_for_buy_position(self):
        """Test P&L calculation for BUY position (long)."""
        from src.database.models.mt4_positions import MT4Position

        position = MT4Position(
            ticket_number=12345,
            magic_number=100001,
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),  # 0.1 lots
            open_price=Decimal("75.00"),
            current_price=Decimal("76.00"),  # +$1.00
            unrealized_pnl=Decimal("0.00"),
            open_time=datetime.now(),
            last_updated=datetime.now()
        )

        # For CrudeOIL: contract_size = 1000 barrels
        # P&L = (current_price - open_price) * volume * contract_size
        # P&L = (76.00 - 75.00) * 0.1 * 1000 = $100.00
        pnl = position.calculate_pnl(contract_size=Decimal("1000"))

        assert pnl == Decimal("100.00")

    def test_calculate_pnl_for_sell_position(self):
        """Test P&L calculation for SELL position (short)."""
        from src.database.models.mt4_positions import MT4Position

        position = MT4Position(
            ticket_number=12346,
            magic_number=100001,
            symbol="CrudeOIL",
            direction="SELL",
            volume=Decimal("0.1"),
            open_price=Decimal("76.00"),
            current_price=Decimal("75.00"),  # -$1.00 (profit for short)
            unrealized_pnl=Decimal("0.00"),
            open_time=datetime.now(),
            last_updated=datetime.now()
        )

        # For SELL position, price going down is profit
        # P&L = -(current_price - open_price) * volume * contract_size
        # P&L = -(75.00 - 76.00) * 0.1 * 1000 = $100.00
        pnl = position.calculate_pnl(contract_size=Decimal("1000"))

        assert pnl == Decimal("100.00")

    def test_calculate_pnl_negative(self):
        """Test P&L calculation for losing position."""
        from src.database.models.mt4_positions import MT4Position

        position = MT4Position(
            ticket_number=12347,
            magic_number=100001,
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.2"),
            open_price=Decimal("76.00"),
            current_price=Decimal("75.00"),  # -$1.00 (loss)
            unrealized_pnl=Decimal("0.00"),
            open_time=datetime.now(),
            last_updated=datetime.now()
        )

        # P&L = (75.00 - 76.00) * 0.2 * 1000 = -$200.00
        pnl = position.calculate_pnl(contract_size=Decimal("1000"))

        assert pnl == Decimal("-200.00")

    def test_is_profitable(self):
        """Test is_profitable() helper method."""
        from src.database.models.mt4_positions import MT4Position

        # Profitable position
        profitable_position = MT4Position(
            ticket_number=12348,
            magic_number=100001,
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            open_price=Decimal("75.00"),
            current_price=Decimal("76.00"),
            unrealized_pnl=Decimal("100.00"),
            open_time=datetime.now(),
            last_updated=datetime.now()
        )

        assert profitable_position.is_profitable() is True

        # Losing position
        losing_position = MT4Position(
            ticket_number=12349,
            magic_number=100001,
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            open_price=Decimal("76.00"),
            current_price=Decimal("75.00"),
            unrealized_pnl=Decimal("-100.00"),
            open_time=datetime.now(),
            last_updated=datetime.now()
        )

        assert losing_position.is_profitable() is False

    def test_get_duration_seconds(self):
        """Test get_duration_seconds() method."""
        from src.database.models.mt4_positions import MT4Position

        open_time = datetime(2025, 11, 22, 10, 0, 0)

        position = MT4Position(
            ticket_number=12350,
            magic_number=100001,
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            open_price=Decimal("75.00"),
            current_price=Decimal("75.50"),
            unrealized_pnl=Decimal("50.00"),
            open_time=open_time,
            last_updated=datetime.now()
        )

        duration = position.get_duration_seconds()

        # Should be positive (current time - open time)
        assert duration > 0

    def test_is_at_stop_loss(self):
        """Test is_at_stop_loss() method."""
        from src.database.models.mt4_positions import MT4Position

        position = MT4Position(
            ticket_number=12351,
            magic_number=100001,
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            open_price=Decimal("75.00"),
            current_price=Decimal("74.00"),  # At stop loss
            unrealized_pnl=Decimal("-100.00"),
            stop_loss=Decimal("74.00"),
            take_profit=Decimal("77.00"),
            open_time=datetime.now(),
            last_updated=datetime.now()
        )

        assert position.is_at_stop_loss() is True

        # Update price away from stop loss
        position.current_price = Decimal("75.50")
        assert position.is_at_stop_loss() is False

    def test_is_at_take_profit(self):
        """Test is_at_take_profit() method."""
        from src.database.models.mt4_positions import MT4Position

        position = MT4Position(
            ticket_number=12352,
            magic_number=100001,
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            open_price=Decimal("75.00"),
            current_price=Decimal("77.00"),  # At take profit
            unrealized_pnl=Decimal("200.00"),
            stop_loss=Decimal("74.00"),
            take_profit=Decimal("77.00"),
            open_time=datetime.now(),
            last_updated=datetime.now()
        )

        assert position.is_at_take_profit() is True

        # Update price away from take profit
        position.current_price = Decimal("76.50")
        assert position.is_at_take_profit() is False

    def test_pnl_with_different_contract_sizes(self):
        """Test P&L calculation with various contract sizes."""
        from src.database.models.mt4_positions import MT4Position

        position = MT4Position(
            ticket_number=12353,
            magic_number=100001,
            symbol="EURUSD",
            direction="BUY",
            volume=Decimal("1.0"),  # 1 lot
            open_price=Decimal("1.1000"),
            current_price=Decimal("1.1100"),  # +100 pips
            unrealized_pnl=Decimal("0.00"),
            open_time=datetime.now(),
            last_updated=datetime.now()
        )

        # For EURUSD: contract_size = 100,000 units
        # P&L = (1.1100 - 1.1000) * 1.0 * 100000 = $1,000.00
        pnl = position.calculate_pnl(contract_size=Decimal("100000"))

        assert pnl == Decimal("10000.00")

    def test_validate_volume_positive(self):
        """Test volume validation (must be positive)."""
        from src.database.models.mt4_positions import MT4Position

        with pytest.raises(ValueError, match="volume must be positive"):
            position = MT4Position(
                ticket_number=12354,
                magic_number=100001,
                symbol="CrudeOIL",
                direction="BUY",
                volume=Decimal("-0.1"),  # Invalid: negative
                open_price=Decimal("75.00"),
                current_price=Decimal("75.50"),
                unrealized_pnl=Decimal("0.00"),
                open_time=datetime.now(),
                last_updated=datetime.now()
            )

    def test_validate_direction(self):
        """Test direction validation (must be BUY or SELL)."""
        from src.database.models.mt4_positions import MT4Position

        with pytest.raises(ValueError, match="Direction must be BUY or SELL"):
            position = MT4Position(
                ticket_number=12355,
                magic_number=100001,
                symbol="CrudeOIL",
                direction="INVALID",  # Invalid direction
                volume=Decimal("0.1"),
                open_price=Decimal("75.00"),
                current_price=Decimal("75.50"),
                unrealized_pnl=Decimal("0.00"),
                open_time=datetime.now(),
                last_updated=datetime.now()
            )

    def test_position_repr(self):
        """Test __repr__() method."""
        from src.database.models.mt4_positions import MT4Position

        position = MT4Position(
            ticket_number=12356,
            magic_number=100001,
            symbol="CrudeOIL",
            direction="BUY",
            volume=Decimal("0.1"),
            open_price=Decimal("75.00"),
            current_price=Decimal("75.50"),
            unrealized_pnl=Decimal("50.00"),
            open_time=datetime.now(),
            last_updated=datetime.now()
        )

        repr_str = repr(position)

        assert "MT4Position" in repr_str
        assert "ticket=12356" in repr_str
        assert "symbol='CrudeOIL'" in repr_str
        assert "direction='BUY'" in repr_str
        assert "volume=0.1" in repr_str
        assert "pnl=50.00" in repr_str
