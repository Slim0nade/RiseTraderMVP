"""
ExogenousVariable model - External market indicators (DXY, VIX, news events)
Based on spec: 003-ml-forecasting-pipeline/data-model.md
"""
from datetime import datetime

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Index
from sqlalchemy.ext.declarative import declarative_base

Base = declarative_base()


class ExogenousVariable(Base):
    """
    External market indicators

    Stores DXY (Dollar Index), VIX (Volatility Index), and economic news events
    for use as exogenous features in ML models to improve forecast accuracy.
    """

    __tablename__ = "exogenous_variables"

    # Primary key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # Identification
    variable_name = Column(String(50), nullable=False, index=True)  # "DXY", "VIX", "NFP_EVENT"
    timestamp = Column(DateTime, nullable=False, index=True)

    # Value
    value = Column(Float)  # Continuous variables (DXY, VIX)
    is_event = Column(Boolean, default=False)  # Binary flag for news events

    # Metadata
    source = Column(String(100))  # Data source (e.g., "yahoo_finance", "alpha_vantage")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    __table_args__ = (
        Index('idx_exogenous_lookup', 'variable_name', 'timestamp'),
    )

    def __repr__(self) -> str:
        return (
            f"<ExogenousVariable(id={self.id}, name='{self.variable_name}', "
            f"timestamp='{self.timestamp}', value={self.value})>"
        )
