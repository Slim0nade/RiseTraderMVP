"""
Unit tests for ExogenousVariable SQLAlchemy model
Tests external market indicator storage (DXY, VIX, news events)
"""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models.exogenous_variables import ExogenousVariable, Base


@pytest.fixture(scope="function")
def db_session():
    """Create an in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestExogenousVariableModel:
    """Test suite for ExogenousVariable model"""

    def test_exogenous_variable_continuous_value(self, db_session):
        """Test storing continuous exogenous variable (DXY, VIX)"""
        exogenous = ExogenousVariable(
            variable_name="DXY",
            timestamp=datetime(2025, 11, 29, 14, 0, 0),
            value=104.5,
            is_event=False,
            source="yahoo_finance",
        )
        db_session.add(exogenous)
        db_session.commit()

        assert exogenous.id is not None
        assert exogenous.variable_name == "DXY"
        assert exogenous.value == 104.5
        assert exogenous.is_event is False

    def test_exogenous_variable_news_event(self, db_session):
        """Test storing news event as binary flag"""
        exogenous = ExogenousVariable(
            variable_name="NEWS_EVENT",
            timestamp=datetime(2025, 11, 29, 13, 30, 0),
            value=None,  # Binary flag, no value needed
            is_event=True,
            source="economic_calendar",
        )
        db_session.add(exogenous)
        db_session.commit()

        assert exogenous.variable_name == "NEWS_EVENT"
        assert exogenous.is_event is True
        assert exogenous.value is None

    def test_exogenous_variable_dxy_storage(self, db_session):
        """Test storing Dollar Index (DXY) values"""
        exogenous = ExogenousVariable(
            variable_name="DXY",
            timestamp=datetime(2025, 11, 29, 14, 0, 0),
            value=104.5,
            source="yahoo_finance",
        )
        db_session.add(exogenous)
        db_session.commit()

        assert exogenous.variable_name == "DXY"
        assert exogenous.value == 104.5

    def test_exogenous_variable_vix_storage(self, db_session):
        """Test storing Volatility Index (VIX) values"""
        exogenous = ExogenousVariable(
            variable_name="VIX",
            timestamp=datetime(2025, 11, 29, 14, 0, 0),
            value=18.5,
            source="yahoo_finance",
        )
        db_session.add(exogenous)
        db_session.commit()

        assert exogenous.variable_name == "VIX"
        assert exogenous.value == 18.5

    def test_exogenous_variable_created_at_auto_populated(self, db_session):
        """Test that created_at is automatically populated"""
        exogenous = ExogenousVariable(
            variable_name="DXY",
            timestamp=datetime(2025, 11, 29, 14, 0, 0),
            value=104.5,
        )
        db_session.add(exogenous)
        db_session.commit()

        assert exogenous.created_at is not None
        assert isinstance(exogenous.created_at, datetime)

    def test_exogenous_variable_time_series_data(self, db_session):
        """Test storing time series data for DXY"""
        # Create hourly DXY data
        for hour in range(3):
            exogenous = ExogenousVariable(
                variable_name="DXY",
                timestamp=datetime(2025, 11, 29, 14 + hour, 0, 0),
                value=104.5 + (hour * 0.1),
                source="yahoo_finance",
            )
            db_session.add(exogenous)
        db_session.commit()

        # Query time series
        dxy_series = (
            db_session.query(ExogenousVariable)
            .filter_by(variable_name="DXY")
            .order_by(ExogenousVariable.timestamp)
            .all()
        )

        assert len(dxy_series) == 3
        assert dxy_series[0].value == 104.5
        assert dxy_series[1].value == 104.6

    def test_exogenous_variable_query_by_name_and_timestamp(self, db_session):
        """Test querying exogenous variable by name and timestamp"""
        target_time = datetime(2025, 11, 29, 14, 0, 0)

        exogenous = ExogenousVariable(
            variable_name="DXY",
            timestamp=target_time,
            value=104.5,
        )
        db_session.add(exogenous)
        db_session.commit()

        # Query specific data point
        result = (
            db_session.query(ExogenousVariable)
            .filter_by(variable_name="DXY", timestamp=target_time)
            .first()
        )

        assert result is not None
        assert result.value == 104.5

    def test_exogenous_variable_multiple_sources(self, db_session):
        """Test tracking data from multiple sources"""
        sources = ["yahoo_finance", "alpha_vantage", "economic_calendar"]

        for source in sources:
            exogenous = ExogenousVariable(
                variable_name="DXY",
                timestamp=datetime(2025, 11, 29, 14, 0, 0),
                value=104.5,
                source=source,
            )
            db_session.add(exogenous)
            db_session.commit()
            assert exogenous.source == source
            db_session.rollback()

    def test_exogenous_variable_nfp_event(self, db_session):
        """Test storing NFP (Non-Farm Payrolls) event"""
        exogenous = ExogenousVariable(
            variable_name="NFP_EVENT",
            timestamp=datetime(2025, 11, 29, 13, 30, 0),
            value=None,
            is_event=True,
            source="economic_calendar",
        )
        db_session.add(exogenous)
        db_session.commit()

        assert exogenous.variable_name == "NFP_EVENT"
        assert exogenous.is_event is True

    def test_exogenous_variable_fomc_event(self, db_session):
        """Test storing FOMC (Federal Open Market Committee) event"""
        exogenous = ExogenousVariable(
            variable_name="FOMC_EVENT",
            timestamp=datetime(2025, 11, 29, 14, 0, 0),
            value=None,
            is_event=True,
            source="economic_calendar",
        )
        db_session.add(exogenous)
        db_session.commit()

        assert exogenous.variable_name == "FOMC_EVENT"
        assert exogenous.is_event is True

    def test_exogenous_variable_query_events_only(self, db_session):
        """Test querying only event flags"""
        # Add continuous variables
        db_session.add(
            ExogenousVariable(
                variable_name="DXY",
                timestamp=datetime(2025, 11, 29, 14, 0, 0),
                value=104.5,
                is_event=False,
            )
        )

        # Add events
        db_session.add(
            ExogenousVariable(
                variable_name="NFP_EVENT",
                timestamp=datetime(2025, 11, 29, 13, 30, 0),
                value=None,
                is_event=True,
            )
        )
        db_session.commit()

        # Query only events
        events = db_session.query(ExogenousVariable).filter_by(is_event=True).all()

        assert len(events) == 1
        assert events[0].variable_name == "NFP_EVENT"
