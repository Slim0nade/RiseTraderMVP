"""
Unit tests for TrainingRun SQLAlchemy model
Tests model structure, status transitions, and JSONB fields
"""

import pytest
from datetime import datetime
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.exc import IntegrityError

from src.database.models.training_runs import TrainingRun, TrainingStatus, Base


@pytest.fixture(scope="function")
def db_session():
    """Create an in-memory SQLite database for testing"""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    yield session
    session.close()


class TestTrainingRunModel:
    """Test suite for TrainingRun model"""

    def test_training_run_creation_with_required_fields(self, db_session):
        """Test creating training run with all required fields"""
        training_run = TrainingRun(
            run_name="lstm_crudeOIL_1h_v1",
            symbol="CrudeOIL",
            model_type="lstm",
            hyperparameters={"learning_rate": 0.001, "batch_size": 64},
            feature_config={"lookback_window": 60},
            training_config={"max_epochs": 100},
        )
        db_session.add(training_run)
        db_session.commit()

        assert training_run.id is not None
        assert training_run.run_name == "lstm_crudeOIL_1h_v1"
        assert training_run.status == TrainingStatus.PENDING

    def test_training_status_enum_values(self, db_session):
        """Test all training status enum values"""
        statuses = [
            TrainingStatus.PENDING,
            TrainingStatus.RUNNING,
            TrainingStatus.COMPLETED,
            TrainingStatus.FAILED,
            TrainingStatus.CANCELLED,
        ]

        for status in statuses:
            training_run = TrainingRun(
                run_name=f"test_run_{status.value}",
                symbol="CrudeOIL",
                model_type="lstm",
                hyperparameters={},
                feature_config={},
                training_config={},
                status=status,
            )
            db_session.add(training_run)
            db_session.commit()
            assert training_run.status == status
            db_session.rollback()

    def test_training_run_with_mlflow_run_id(self, db_session):
        """Test training run with MLflow run ID"""
        training_run = TrainingRun(
            run_name="lstm_crudeOIL_1h_v1",
            symbol="CrudeOIL",
            model_type="lstm",
            hyperparameters={},
            feature_config={},
            training_config={},
            mlflow_run_id="a1b2c3d4e5f6g7h8i9j0",
        )
        db_session.add(training_run)
        db_session.commit()

        assert training_run.mlflow_run_id == "a1b2c3d4e5f6g7h8i9j0"

    def test_training_run_timestamps(self, db_session):
        """Test training run timestamps"""
        training_run = TrainingRun(
            run_name="lstm_crudeOIL_1h_v1",
            symbol="CrudeOIL",
            model_type="lstm",
            hyperparameters={},
            feature_config={},
            training_config={},
            started_at=datetime(2025, 11, 29, 10, 0, 0),
            completed_at=datetime(2025, 11, 29, 10, 28, 35),
        )
        db_session.add(training_run)
        db_session.commit()

        assert training_run.started_at is not None
        assert training_run.completed_at is not None

    def test_training_run_duration_calculation(self, db_session):
        """Test training run duration in seconds"""
        training_run = TrainingRun(
            run_name="lstm_crudeOIL_1h_v1",
            symbol="CrudeOIL",
            model_type="lstm",
            hyperparameters={},
            feature_config={},
            training_config={},
            duration_seconds=1715,
        )
        db_session.add(training_run)
        db_session.commit()

        assert training_run.duration_seconds == 1715

    def test_training_run_final_metrics(self, db_session):
        """Test storing final metrics as JSONB"""
        final_metrics = {
            "mpe": -0.52,
            "rmse": 0.38,
            "mae": 0.29,
            "mape": 2.1,
            "directional_accuracy": 61.5,
        }

        training_run = TrainingRun(
            run_name="lstm_crudeOIL_1h_v1",
            symbol="CrudeOIL",
            model_type="lstm",
            hyperparameters={},
            feature_config={},
            training_config={},
            final_metrics=final_metrics,
        )
        db_session.add(training_run)
        db_session.commit()

        assert training_run.final_metrics["mpe"] == -0.52
        assert training_run.final_metrics["rmse"] == 0.38

    def test_training_run_model_version(self, db_session):
        """Test storing resulting model version"""
        training_run = TrainingRun(
            run_name="lstm_crudeOIL_1h_v1",
            symbol="CrudeOIL",
            model_type="lstm",
            hyperparameters={},
            feature_config={},
            training_config={},
            model_version="v1.0.0",
        )
        db_session.add(training_run)
        db_session.commit()

        assert training_run.model_version == "v1.0.0"

    def test_training_run_error_message(self, db_session):
        """Test storing error message for failed runs"""
        training_run = TrainingRun(
            run_name="lstm_crudeOIL_1h_v1",
            symbol="CrudeOIL",
            model_type="lstm",
            hyperparameters={},
            feature_config={},
            training_config={},
            status=TrainingStatus.FAILED,
            error_message="CUDA out of memory",
        )
        db_session.add(training_run)
        db_session.commit()

        assert training_run.error_message == "CUDA out of memory"

    def test_training_run_created_by_tracking(self, db_session):
        """Test tracking who created the training run"""
        training_run = TrainingRun(
            run_name="lstm_crudeOIL_1h_v1",
            symbol="CrudeOIL",
            model_type="lstm",
            hyperparameters={},
            feature_config={},
            training_config={},
            created_by="data_scientist@risetrader.com",
        )
        db_session.add(training_run)
        db_session.commit()

        assert training_run.created_by == "data_scientist@risetrader.com"

    def test_training_run_query_by_symbol_and_status(self, db_session):
        """Test querying training runs by symbol and status"""
        # Create multiple training runs
        for i in range(3):
            training_run = TrainingRun(
                run_name=f"lstm_crudeOIL_1h_v{i}",
                symbol="CrudeOIL",
                model_type="lstm",
                hyperparameters={},
                feature_config={},
                training_config={},
                status=TrainingStatus.COMPLETED,
            )
            db_session.add(training_run)
        db_session.commit()

        # Query training runs
        training_runs = (
            db_session.query(TrainingRun)
            .filter_by(symbol="CrudeOIL", status=TrainingStatus.COMPLETED)
            .all()
        )

        assert len(training_runs) == 3

    def test_training_run_hyperparameters_storage(self, db_session):
        """Test storing complex hyperparameters as JSONB"""
        hyperparameters = {
            "model": {"num_layers": 2, "hidden_size": 128, "dropout": 0.2},
            "training": {"learning_rate": 0.001, "batch_size": 64},
        }

        training_run = TrainingRun(
            run_name="lstm_crudeOIL_1h_v1",
            symbol="CrudeOIL",
            model_type="lstm",
            hyperparameters=hyperparameters,
            feature_config={},
            training_config={},
        )
        db_session.add(training_run)
        db_session.commit()

        assert training_run.hyperparameters["model"]["num_layers"] == 2
        assert training_run.hyperparameters["training"]["learning_rate"] == 0.001
