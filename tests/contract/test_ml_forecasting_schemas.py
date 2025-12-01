"""
Contract tests for ML Forecasting API schemas.
Validates request/response models against OpenAPI specification.
"""

import pytest
from pydantic import ValidationError
from datetime import datetime

from src.api.models.ml_models import (
    InferenceRequest,
    InferenceResponse,
    ForecastResponse,
    TrainingRequest,
    TrainingResponse
)


class TestInferenceRequestSchema:
    """Test InferenceRequest schema validation."""

    def test_valid_inference_request(self):
        """Test valid inference request."""
        data = {
            "symbol": "CrudeOIL",
            "forecast_horizons": ["1h", "4h", "24h"],
            "model_type": "ensemble",
            "include_confidence_intervals": True
        }

        request = InferenceRequest(**data)

        assert request.symbol == "CrudeOIL"
        assert request.forecast_horizons == ["1h", "4h", "24h"]
        assert request.model_type == "ensemble"
        assert request.include_confidence_intervals is True

    def test_inference_request_with_timestamp(self):
        """Test inference request with custom timestamp."""
        data = {
            "symbol": "EURUSD",
            "timestamp": datetime(2024, 1, 15, 10, 0, 0),
            "forecast_horizons": ["1h"],
            "model_type": "lstm"
        }

        request = InferenceRequest(**data)

        assert request.timestamp == datetime(2024, 1, 15, 10, 0, 0)

    def test_inference_request_defaults(self):
        """Test inference request with default values."""
        data = {
            "symbol": "GOLD",
            "forecast_horizons": ["30d"]
        }

        request = InferenceRequest(**data)

        assert request.model_type == "ensemble"  # Default
        assert request.include_confidence_intervals is True  # Default
        assert request.timestamp is None  # Optional

    def test_inference_request_missing_required_fields(self):
        """Test validation fails when required fields missing."""
        data = {
            "symbol": "CrudeOIL"
            # Missing forecast_horizons
        }

        with pytest.raises(ValidationError):
            InferenceRequest(**data)

    def test_inference_request_empty_symbol(self):
        """Test validation fails with empty symbol."""
        data = {
            "symbol": "",
            "forecast_horizons": ["1h"]
        }

        with pytest.raises(ValidationError):
            InferenceRequest(**data)

    def test_inference_request_symbol_too_long(self):
        """Test validation fails when symbol exceeds max length."""
        data = {
            "symbol": "A" * 21,  # Max 20 characters
            "forecast_horizons": ["1h"]
        }

        with pytest.raises(ValidationError):
            InferenceRequest(**data)

    def test_inference_request_empty_horizons(self):
        """Test validation fails with empty horizons list."""
        data = {
            "symbol": "CrudeOIL",
            "forecast_horizons": []
        }

        with pytest.raises(ValidationError):
            InferenceRequest(**data)

    def test_inference_request_invalid_model_type(self):
        """Test validation fails with invalid model type."""
        data = {
            "symbol": "CrudeOIL",
            "forecast_horizons": ["1h"],
            "model_type": "invalid_model"
        }

        with pytest.raises(ValidationError):
            InferenceRequest(**data)

    def test_inference_request_valid_model_types(self):
        """Test all valid model types."""
        valid_types = ["lstm", "xgboost", "ensemble"]

        for model_type in valid_types:
            data = {
                "symbol": "CrudeOIL",
                "forecast_horizons": ["1h"],
                "model_type": model_type
            }

            request = InferenceRequest(**data)
            assert request.model_type == model_type


class TestForecastResponseSchema:
    """Test ForecastResponse schema."""

    def test_valid_forecast_response(self):
        """Test valid forecast response."""
        data = {
            "id": 12345,
            "symbol": "CrudeOIL",
            "timestamp": datetime(2024, 1, 15, 14, 0, 0),
            "forecast_horizon": "1h",
            "model_type": "ensemble",
            "model_version": "v1.0.0",
            "predicted_value": 78.45,
            "lower_bound": 77.80,
            "upper_bound": 79.10,
            "confidence_score": 0.87,
            "created_at": datetime(2024, 1, 15, 13, 59, 55),
            "inference_time_ms": 42.5
        }

        response = ForecastResponse(**data)

        assert response.id == 12345
        assert response.predicted_value == 78.45
        assert response.confidence_score == 0.87

    def test_forecast_response_without_confidence_intervals(self):
        """Test forecast response without confidence intervals."""
        data = {
            "id": 1,
            "symbol": "BTCUSD",
            "timestamp": datetime.utcnow(),
            "forecast_horizon": "1h",
            "model_type": "xgboost",
            "model_version": "v2.0.0",
            "predicted_value": 45000.0,
            "lower_bound": None,
            "upper_bound": None,
            "confidence_score": None,
            "created_at": datetime.utcnow(),
            "inference_time_ms": None
        }

        response = ForecastResponse(**data)

        assert response.lower_bound is None
        assert response.upper_bound is None

    def test_forecast_response_required_fields(self):
        """Test forecast response requires core fields."""
        data = {
            "id": 1,
            "symbol": "TEST",
            "timestamp": datetime.utcnow(),
            "forecast_horizon": "1h",
            "model_type": "lstm",
            "model_version": "v1.0.0",
            "predicted_value": 100.0,
            "created_at": datetime.utcnow()
        }

        response = ForecastResponse(**data)

        assert response.id == 1
        assert response.predicted_value == 100.0


class TestInferenceResponseSchema:
    """Test InferenceResponse schema."""

    def test_valid_inference_response(self):
        """Test valid inference response with multiple forecasts."""
        forecasts_data = [
            {
                "id": 1,
                "symbol": "CrudeOIL",
                "timestamp": datetime.utcnow(),
                "forecast_horizon": "1h",
                "model_type": "ensemble",
                "model_version": "v1.0.0",
                "predicted_value": 78.45,
                "lower_bound": 77.80,
                "upper_bound": 79.10,
                "confidence_score": 0.87,
                "created_at": datetime.utcnow(),
                "inference_time_ms": 42.5
            },
            {
                "id": 2,
                "symbol": "CrudeOIL",
                "timestamp": datetime.utcnow(),
                "forecast_horizon": "4h",
                "model_type": "ensemble",
                "model_version": "v1.0.0",
                "predicted_value": 78.90,
                "lower_bound": 77.95,
                "upper_bound": 79.85,
                "confidence_score": 0.79,
                "created_at": datetime.utcnow(),
                "inference_time_ms": 45.2
            }
        ]

        forecasts = [ForecastResponse(**f) for f in forecasts_data]

        data = {
            "symbol": "CrudeOIL",
            "timestamp": datetime.utcnow(),
            "forecasts": forecasts,
            "inference_time_ms": 48.2,
            "cache_hit": False
        }

        response = InferenceResponse(**data)

        assert response.symbol == "CrudeOIL"
        assert len(response.forecasts) == 2
        assert response.cache_hit is False

    def test_inference_response_cache_hit(self):
        """Test inference response with cache hit."""
        forecast_data = {
            "id": 1,
            "symbol": "GOLD",
            "timestamp": datetime.utcnow(),
            "forecast_horizon": "30d",
            "model_type": "lstm",
            "model_version": "v1.0.0",
            "predicted_value": 1850.5,
            "created_at": datetime.utcnow()
        }

        data = {
            "symbol": "GOLD",
            "timestamp": datetime.utcnow(),
            "forecasts": [ForecastResponse(**forecast_data)],
            "inference_time_ms": 2.1,
            "cache_hit": True
        }

        response = InferenceResponse(**data)

        assert response.cache_hit is True
        assert response.inference_time_ms == 2.1


class TestTrainingRequestSchema:
    """Test TrainingRequest schema."""

    def test_valid_training_request(self):
        """Test valid training request."""
        data = {
            "run_name": "lstm_crudeOIL_1h_production_v1",
            "symbol": "CrudeOIL",
            "model_type": "lstm",
            "async_training": True
        }

        request = TrainingRequest(**data)

        assert request.run_name == "lstm_crudeOIL_1h_production_v1"
        assert request.symbol == "CrudeOIL"
        assert request.model_type == "lstm"
        assert request.async_training is True

    def test_training_request_with_config_override(self):
        """Test training request with config override."""
        data = {
            "run_name": "test_run",
            "symbol": "EURUSD",
            "model_type": "xgboost",
            "config_override": {
                "training": {"epochs": 50, "learning_rate": 0.01}
            }
        }

        request = TrainingRequest(**data)

        assert request.config_override is not None
        assert request.config_override["training"]["epochs"] == 50

    def test_training_request_defaults(self):
        """Test training request defaults."""
        data = {
            "run_name": "test",
            "symbol": "TEST",
            "model_type": "lstm"
        }

        request = TrainingRequest(**data)

        assert request.async_training is True  # Default
        assert request.config_override is None  # Optional

    def test_training_request_invalid_model_type(self):
        """Test validation fails with invalid model type."""
        data = {
            "run_name": "test",
            "symbol": "TEST",
            "model_type": "ensemble"  # Not allowed for training
        }

        with pytest.raises(ValidationError):
            TrainingRequest(**data)

    def test_training_request_valid_model_types(self):
        """Test valid model types for training."""
        valid_types = ["lstm", "xgboost"]

        for model_type in valid_types:
            data = {
                "run_name": "test",
                "symbol": "TEST",
                "model_type": model_type
            }

            request = TrainingRequest(**data)
            assert request.model_type == model_type


class TestTrainingResponseSchema:
    """Test TrainingResponse schema."""

    def test_valid_training_response(self):
        """Test valid training response."""
        data = {
            "training_run_id": 101,
            "run_name": "lstm_crudeOIL_1h_production_v1",
            "status": "running",
            "mlflow_run_id": "a1b2c3d4e5f6g7h8",
            "estimated_duration_minutes": 28,
            "message": "Training started successfully"
        }

        response = TrainingResponse(**data)

        assert response.training_run_id == 101
        assert response.status == "running"
        assert response.mlflow_run_id == "a1b2c3d4e5f6g7h8"

    def test_training_response_without_optional_fields(self):
        """Test training response without optional fields."""
        data = {
            "training_run_id": 102,
            "run_name": "test_run",
            "status": "pending",
            "mlflow_run_id": None,
            "estimated_duration_minutes": None,
            "message": "Training queued"
        }

        response = TrainingResponse(**data)

        assert response.mlflow_run_id is None
        assert response.estimated_duration_minutes is None


class TestSchemaIntegration:
    """Test schema integration scenarios."""

    def test_full_inference_workflow_schemas(self):
        """Test complete inference request -> response workflow."""
        # Create request
        request = InferenceRequest(
            symbol="CrudeOIL",
            forecast_horizons=["1h", "4h"],
            model_type="ensemble",
            include_confidence_intervals=True
        )

        # Simulate response
        forecasts = [
            ForecastResponse(
                id=1,
                symbol="CrudeOIL",
                timestamp=datetime.utcnow(),
                forecast_horizon="1h",
                model_type="ensemble",
                model_version="v1.0.0",
                predicted_value=78.45,
                lower_bound=77.80,
                upper_bound=79.10,
                confidence_score=0.87,
                created_at=datetime.utcnow(),
                inference_time_ms=42.5
            ),
            ForecastResponse(
                id=2,
                symbol="CrudeOIL",
                timestamp=datetime.utcnow(),
                forecast_horizon="4h",
                model_type="ensemble",
                model_version="v1.0.0",
                predicted_value=78.90,
                created_at=datetime.utcnow()
            )
        ]

        response = InferenceResponse(
            symbol=request.symbol,
            timestamp=datetime.utcnow(),
            forecasts=forecasts,
            inference_time_ms=48.2,
            cache_hit=False
        )

        # Verify workflow
        assert response.symbol == request.symbol
        assert len(response.forecasts) == len(request.forecast_horizons)

    def test_full_training_workflow_schemas(self):
        """Test complete training request -> response workflow."""
        # Create request
        request = TrainingRequest(
            run_name="lstm_test_v1",
            symbol="GOLD",
            model_type="lstm",
            async_training=True
        )

        # Simulate response
        response = TrainingResponse(
            training_run_id=201,
            run_name=request.run_name,
            status="running",
            mlflow_run_id="xyz789",
            estimated_duration_minutes=25,
            message="Training started"
        )

        # Verify workflow
        assert response.run_name == request.run_name
        assert response.status == "running"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
