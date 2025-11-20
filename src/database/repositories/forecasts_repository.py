"""
Forecasts repository for ML predictions.
"""
from datetime import datetime
from decimal import Decimal
from typing import Dict, List, Optional

from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..models.forecasts import Forecast
from .base import BaseRepository


class ForecastsRepository(BaseRepository[Forecast]):
    """
    Repository for ML forecasts and predictions.

    Manages model predictions with validation tracking.
    """

    def __init__(self, session: AsyncSession):
        super().__init__(Forecast, session)

    async def get_latest_forecast(
        self,
        symbol: str,
        horizon: str,
        model_type: Optional[str] = None,
    ) -> Optional[Forecast]:
        """
        Get the latest forecast for a symbol and horizon.

        Args:
            symbol: Trading symbol
            horizon: Forecast horizon (e.g., '1h', '4h', '1d')
            model_type: Optional model type filter

        Returns:
            Latest Forecast instance or None
        """
        query = (
            select(Forecast)
            .where(
                and_(
                    Forecast.symbol == symbol,
                    Forecast.forecast_horizon == horizon,
                )
            )
            .order_by(desc(Forecast.prediction_timestamp))
            .limit(1)
        )

        if model_type:
            query = query.where(Forecast.model_type == model_type)

        result = await self.session.execute(query)
        return result.scalar_one_or_none()

    async def get_forecasts_for_target_time(
        self,
        symbol: str,
        target_timestamp: datetime,
        horizon: Optional[str] = None,
    ) -> List[Forecast]:
        """
        Get all forecasts for a specific target timestamp.

        Useful for ensemble predictions.

        Args:
            symbol: Trading symbol
            target_timestamp: Target prediction time
            horizon: Optional horizon filter

        Returns:
            List of Forecast instances from different models
        """
        query = select(Forecast).where(
            and_(
                Forecast.symbol == symbol,
                Forecast.target_timestamp == target_timestamp,
            )
        )

        if horizon:
            query = query.where(Forecast.forecast_horizon == horizon)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def save_forecast(self, forecast_data: Dict) -> Forecast:
        """
        Save a new forecast.

        Args:
            forecast_data: Dictionary with forecast attributes

        Returns:
            Created Forecast instance
        """
        return await self.create(forecast_data)

    async def validate_forecast(
        self,
        forecast_id: int,
        actual_price: Decimal,
    ) -> Optional[Forecast]:
        """
        Validate a forecast with actual price.

        Args:
            forecast_id: Forecast ID
            actual_price: Actual observed price

        Returns:
            Updated Forecast instance or None if not found
        """
        forecast = await self.get(forecast_id)
        if not forecast:
            return None

        forecast.validate_prediction(actual_price)
        await self.session.flush()
        await self.session.refresh(forecast)
        return forecast

    async def get_unvalidated_forecasts(
        self,
        symbol: Optional[str] = None,
        before_time: Optional[datetime] = None,
    ) -> List[Forecast]:
        """
        Get forecasts that haven't been validated yet.

        Args:
            symbol: Optional symbol filter
            before_time: Only get forecasts with target_timestamp before this time

        Returns:
            List of unvalidated Forecast instances
        """
        query = select(Forecast).where(
            (Forecast.is_validated.is_(None)) | (Forecast.is_validated == False)
        )

        if symbol:
            query = query.where(Forecast.symbol == symbol)

        if before_time:
            query = query.where(Forecast.target_timestamp <= before_time)

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_model_forecast_history(
        self,
        model_type: str,
        model_version: str,
        symbol: str,
        limit: int = 100,
    ) -> List[Forecast]:
        """
        Get forecast history for a specific model.

        Args:
            model_type: Model type
            model_version: Model version
            symbol: Trading symbol
            limit: Maximum number of records

        Returns:
            List of Forecast instances ordered by prediction time
        """
        query = (
            select(Forecast)
            .where(
                and_(
                    Forecast.model_type == model_type,
                    Forecast.model_version == model_version,
                    Forecast.symbol == symbol,
                )
            )
            .order_by(desc(Forecast.prediction_timestamp))
            .limit(limit)
        )

        result = await self.session.execute(query)
        return list(result.scalars().all())

    async def get_forecast_accuracy_stats(
        self,
        model_type: str,
        symbol: str,
        horizon: Optional[str] = None,
    ) -> Optional[Dict[str, float]]:
        """
        Calculate accuracy statistics for a model.

        Args:
            model_type: Model type
            symbol: Trading symbol
            horizon: Optional horizon filter

        Returns:
            Dictionary with accuracy metrics or None if no validated forecasts
        """
        query = select(
            func.count(Forecast.id).label("total"),
            func.avg(Forecast.absolute_error).label("mae"),
            func.avg(Forecast.percentage_error).label("mpe"),
            func.stddev(Forecast.prediction_error).label("std_error"),
        ).where(
            and_(
                Forecast.model_type == model_type,
                Forecast.symbol == symbol,
                Forecast.is_validated == True,
            )
        )

        if horizon:
            query = query.where(Forecast.forecast_horizon == horizon)

        result = await self.session.execute(query)
        stats = result.one()

        if not stats.total or stats.total == 0:
            return None

        return {
            "total_validated": stats.total,
            "mean_absolute_error": float(stats.mae) if stats.mae else 0.0,
            "mean_percentage_error": float(stats.mpe) if stats.mpe else 0.0,
            "std_error": float(stats.std_error) if stats.std_error else 0.0,
        }

    async def get_ensemble_prediction(
        self,
        symbol: str,
        target_timestamp: datetime,
        horizon: str,
    ) -> Optional[Dict[str, any]]:
        """
        Get ensemble prediction from multiple models.

        Args:
            symbol: Trading symbol
            target_timestamp: Target prediction time
            horizon: Forecast horizon

        Returns:
            Dictionary with ensemble prediction or None
        """
        forecasts = await self.get_forecasts_for_target_time(
            symbol, target_timestamp, horizon
        )

        if not forecasts:
            return None

        # Calculate weighted average based on model confidence
        total_weight = Decimal(0)
        weighted_sum = Decimal(0)

        for forecast in forecasts:
            weight = forecast.model_confidence or Decimal(1)
            weighted_sum += forecast.predicted_price * weight
            total_weight += weight

        if total_weight == 0:
            # Fallback to simple average
            avg_price = sum(f.predicted_price for f in forecasts) / len(forecasts)
        else:
            avg_price = weighted_sum / total_weight

        return {
            "symbol": symbol,
            "target_timestamp": target_timestamp,
            "horizon": horizon,
            "ensemble_prediction": float(avg_price),
            "num_models": len(forecasts),
            "model_types": [f.model_type for f in forecasts],
        }

    async def get_recent_forecasts(
        self,
        symbol: str,
        hours: int = 24,
        model_type: Optional[str] = None,
    ) -> List[Forecast]:
        """
        Get recent forecasts within the last N hours.

        Args:
            symbol: Trading symbol
            hours: Number of hours to look back
            model_type: Optional model type filter

        Returns:
            List of Forecast instances
        """
        from datetime import timedelta

        cutoff_time = datetime.utcnow() - timedelta(hours=hours)

        query = select(Forecast).where(
            and_(
                Forecast.symbol == symbol,
                Forecast.prediction_timestamp >= cutoff_time,
            )
        )

        if model_type:
            query = query.where(Forecast.model_type == model_type)

        query = query.order_by(desc(Forecast.prediction_timestamp))

        result = await self.session.execute(query)
        return list(result.scalars().all())
