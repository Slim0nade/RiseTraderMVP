"""
Unit tests for ModelMetrics SQLAlchemy model
Tests model performance metrics storage and retrieval
"""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.database.models.model_metrics import ModelMetrics, Base


@pytest.fixture(scope="function")
def db_session():
    """Create an in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestModelMetricsModel:
    """Test suite for ModelMetrics model"""

    def test_model_metrics_creation_with_required_fields(self, db_session):
        """Test creating model metrics with all required fields"""
        metrics = ModelMetrics(
            model_type="lstm",
            model_version="v1.0.0",
            symbol="CrudeOIL",
            forecast_horizon="1h",
            mpe=-0.52,
            rmse=0.38,
            mae=0.29,
            mape=2.1,
        )
        db_session.add(metrics)
        db_session.commit()

        assert metrics.id is not None
        assert metrics.model_type == "lstm"
        assert metrics.mpe == -0.52

    def test_model_metrics_all_metrics(self, db_session):
        """Test storing all evaluation metrics"""
        metrics = ModelMetrics(
            model_type="lstm",
            model_version="v1.0.0",
            symbol="CrudeOIL",
            forecast_horizon="1h",
            mpe=-0.52,
            rmse=0.38,
            mae=0.29,
            mape=2.1,
            directional_accuracy=61.5,
        )
        db_session.add(metrics)
        db_session.commit()

        assert metrics.mpe == -0.52
        assert metrics.rmse == 0.38
        assert metrics.mae == 0.29
        assert metrics.mape == 2.1
        assert metrics.directional_accuracy == 61.5

    def test_model_metrics_evaluation_date_auto_populated(self, db_session):
        """Test that evaluation_date is automatically populated"""
        metrics = ModelMetrics(
            model_type="lstm",
            model_version="v1.0.0",
            symbol="CrudeOIL",
            forecast_horizon="1h",
            mpe=-0.52,
            rmse=0.38,
            mae=0.29,
            mape=2.1,
        )
        db_session.add(metrics)
        db_session.commit()

        assert metrics.evaluation_date is not None
        assert isinstance(metrics.evaluation_date, datetime)

    def test_model_metrics_sample_size(self, db_session):
        """Test storing sample size for metrics calculation"""
        metrics = ModelMetrics(
            model_type="lstm",
            model_version="v1.0.0",
            symbol="CrudeOIL",
            forecast_horizon="1h",
            mpe=-0.52,
            rmse=0.38,
            mae=0.29,
            mape=2.1,
            sample_size=720,
        )
        db_session.add(metrics)
        db_session.commit()

        assert metrics.sample_size == 720

    def test_model_metrics_mlflow_run_id(self, db_session):
        """Test linking metrics to MLflow run"""
        metrics = ModelMetrics(
            model_type="lstm",
            model_version="v1.0.0",
            symbol="CrudeOIL",
            forecast_horizon="1h",
            mpe=-0.52,
            rmse=0.38,
            mae=0.29,
            mape=2.1,
            mlflow_run_id="a1b2c3d4e5f6g7h8i9j0",
        )
        db_session.add(metrics)
        db_session.commit()

        assert metrics.mlflow_run_id == "a1b2c3d4e5f6g7h8i9j0"

    def test_model_metrics_query_by_version_and_horizon(self, db_session):
        """Test querying metrics by model version and horizon"""
        # Create metrics for different horizons
        horizons = ["1h", "4h", "24h"]
        for horizon in horizons:
            metrics = ModelMetrics(
                model_type="lstm",
                model_version="v1.0.0",
                symbol="CrudeOIL",
                forecast_horizon=horizon,
                mpe=-0.52,
                rmse=0.38,
                mae=0.29,
                mape=2.1,
            )
            db_session.add(metrics)
        db_session.commit()

        # Query specific metrics
        result = (
            db_session.query(ModelMetrics)
            .filter_by(model_version="v1.0.0", forecast_horizon="1h")
            .first()
        )

        assert result is not None
        assert result.forecast_horizon == "1h"

    def test_model_metrics_comparison_across_versions(self, db_session):
        """Test comparing metrics across different model versions"""
        versions = ["v1.0.0", "v1.1.0", "v1.2.0"]
        rmse_values = [0.38, 0.35, 0.32]

        for version, rmse in zip(versions, rmse_values):
            metrics = ModelMetrics(
                model_type="lstm",
                model_version=version,
                symbol="CrudeOIL",
                forecast_horizon="1h",
                mpe=-0.52,
                rmse=rmse,
                mae=0.29,
                mape=2.1,
            )
            db_session.add(metrics)
        db_session.commit()

        # Query all versions
        results = (
            db_session.query(ModelMetrics)
            .filter_by(symbol="CrudeOIL", forecast_horizon="1h")
            .order_by(ModelMetrics.rmse)
            .all()
        )

        assert len(results) == 3
        assert results[0].rmse < results[1].rmse < results[2].rmse

    def test_model_metrics_negative_mpe_values(self, db_session):
        """Test that MPE can be negative (over-prediction)"""
        metrics = ModelMetrics(
            model_type="lstm",
            model_version="v1.0.0",
            symbol="CrudeOIL",
            forecast_horizon="1h",
            mpe=-2.5,  # Negative = over-prediction
            rmse=0.38,
            mae=0.29,
            mape=2.1,
        )
        db_session.add(metrics)
        db_session.commit()

        assert metrics.mpe == -2.5

    def test_model_metrics_different_model_types(self, db_session):
        """Test storing metrics for different model types"""
        model_types = ["lstm", "xgboost", "ensemble"]

        for model_type in model_types:
            metrics = ModelMetrics(
                model_type=model_type,
                model_version="v1.0.0",
                symbol="CrudeOIL",
                forecast_horizon="1h",
                mpe=-0.52,
                rmse=0.38,
                mae=0.29,
                mape=2.1,
            )
            db_session.add(metrics)
            db_session.commit()
            assert metrics.model_type == model_type
            db_session.rollback()

    def test_model_metrics_directional_accuracy_percentage(self, db_session):
        """Test directional accuracy as percentage (0-100)"""
        metrics = ModelMetrics(
            model_type="lstm",
            model_version="v1.0.0",
            symbol="CrudeOIL",
            forecast_horizon="1h",
            mpe=-0.52,
            rmse=0.38,
            mae=0.29,
            mape=2.1,
            directional_accuracy=65.7,
        )
        db_session.add(metrics)
        db_session.commit()

        assert 0.0 <= metrics.directional_accuracy <= 100.0
