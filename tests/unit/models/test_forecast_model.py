"""
Unit tests for Forecast SQLAlchemy model
Tests model structure, validation, and constraints
"""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from src.database.models.forecasts import Forecast, Base


@pytest.fixture(scope="function")
def db_session():
    """Create an in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestForecastModel:
    """Test suite for Forecast model"""

    def test_forecast_creation_with_required_fields(self, db_session):
        """Test creating forecast with all required fields"""
        forecast = Forecast(
            symbol="CrudeOIL",
            timestamp=datetime(2025, 11, 29, 14, 0, 0),
            forecast_horizon="1h",
            model_type="lstm",
            model_version="v1.0.0",
            predicted_value=78.45,
        )
        db_session.add(forecast)
        db_session.commit()

        assert forecast.id is not None
        assert forecast.symbol == "CrudeOIL"
        assert forecast.predicted_value == 78.45

    def test_forecast_with_confidence_intervals(self, db_session):
        """Test forecast with confidence intervals"""
        forecast = Forecast(
            symbol="CrudeOIL",
            timestamp=datetime(2025, 11, 29, 14, 0, 0),
            forecast_horizon="1h",
            model_type="lstm",
            model_version="v1.0.0",
            predicted_value=78.45,
            lower_bound=77.80,
            upper_bound=79.10,
            confidence_score=0.87,
        )
        db_session.add(forecast)
        db_session.commit()

        assert forecast.lower_bound == 77.80
        assert forecast.upper_bound == 79.10
        assert forecast.confidence_score == 0.87

    def test_forecast_missing_required_field_raises_error(self, db_session):
        """Test that missing required fields raise IntegrityError"""
        forecast = Forecast(
            symbol="CrudeOIL",
            # Missing timestamp
            forecast_horizon="1h",
            model_type="lstm",
            model_version="v1.0.0",
            predicted_value=78.45,
        )
        db_session.add(forecast)

        with pytest.raises(IntegrityError):
            db_session.commit()

    def test_forecast_horizon_values(self, db_session):
        """Test different forecast horizon values"""
        horizons = ["1h", "4h", "24h"]

        for horizon in horizons:
            forecast = Forecast(
                symbol="CrudeOIL",
                timestamp=datetime(2025, 11, 29, 14, 0, 0),
                forecast_horizon=horizon,
                model_type="lstm",
                model_version="v1.0.0",
                predicted_value=78.45,
            )
            db_session.add(forecast)
            db_session.commit()
            assert forecast.forecast_horizon == horizon
            db_session.rollback()

    def test_model_type_values(self, db_session):
        """Test different model type values"""
        model_types = ["lstm", "xgboost", "ensemble"]

        for model_type in model_types:
            forecast = Forecast(
                symbol="CrudeOIL",
                timestamp=datetime(2025, 11, 29, 14, 0, 0),
                forecast_horizon="1h",
                model_type=model_type,
                model_version="v1.0.0",
                predicted_value=78.45,
            )
            db_session.add(forecast)
            db_session.commit()
            assert forecast.model_type == model_type
            db_session.rollback()

    def test_forecast_with_mlflow_run_id(self, db_session):
        """Test forecast with MLflow run ID"""
        forecast = Forecast(
            symbol="CrudeOIL",
            timestamp=datetime(2025, 11, 29, 14, 0, 0),
            forecast_horizon="1h",
            model_type="lstm",
            model_version="v1.0.0",
            predicted_value=78.45,
            mlflow_run_id="a1b2c3d4e5f6g7h8i9j0",
        )
        db_session.add(forecast)
        db_session.commit()

        assert forecast.mlflow_run_id == "a1b2c3d4e5f6g7h8i9j0"

    def test_forecast_created_at_auto_populated(self, db_session):
        """Test that created_at is automatically populated"""
        forecast = Forecast(
            symbol="CrudeOIL",
            timestamp=datetime(2025, 11, 29, 14, 0, 0),
            forecast_horizon="1h",
            model_type="lstm",
            model_version="v1.0.0",
            predicted_value=78.45,
        )
        db_session.add(forecast)
        db_session.commit()

        assert forecast.created_at is not None
        assert isinstance(forecast.created_at, datetime)

    def test_forecast_inference_time_tracking(self, db_session):
        """Test inference time tracking in milliseconds"""
        forecast = Forecast(
            symbol="CrudeOIL",
            timestamp=datetime(2025, 11, 29, 14, 0, 0),
            forecast_horizon="1h",
            model_type="lstm",
            model_version="v1.0.0",
            predicted_value=78.45,
            inference_time_ms=42.5,
        )
        db_session.add(forecast)
        db_session.commit()

        assert forecast.inference_time_ms == 42.5

    def test_forecast_query_by_symbol_and_horizon(self, db_session):
        """Test querying forecasts by symbol and horizon"""
        # Create multiple forecasts
        for i in range(3):
            forecast = Forecast(
                symbol="CrudeOIL",
                timestamp=datetime(2025, 11, 29, 14 + i, 0, 0),
                forecast_horizon="1h",
                model_type="lstm",
                model_version="v1.0.0",
                predicted_value=78.45 + i,
            )
            db_session.add(forecast)
        db_session.commit()

        # Query forecasts
        forecasts = (
            db_session.query(Forecast)
            .filter_by(symbol="CrudeOIL", forecast_horizon="1h")
            .all()
        )

        assert len(forecasts) == 3

    def test_forecast_confidence_score_range(self, db_session):
        """Test confidence score must be between 0 and 1"""
        # Valid confidence score
        forecast = Forecast(
            symbol="CrudeOIL",
            timestamp=datetime(2025, 11, 29, 14, 0, 0),
            forecast_horizon="1h",
            model_type="lstm",
            model_version="v1.0.0",
            predicted_value=78.45,
            confidence_score=0.5,
        )
        db_session.add(forecast)
        db_session.commit()

        assert 0.0 <= forecast.confidence_score <= 1.0
