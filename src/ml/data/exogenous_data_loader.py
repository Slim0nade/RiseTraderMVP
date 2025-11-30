"""Exogenous Data Loader - Fetch DXY, VIX, news events for model features."""

import yfinance as yf
import pandas as pd
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from src.database.repositories.exogenous_variable_repository import ExogenousVariableRepository


class ExogenousDataLoader:
    """Load external market indicators (DXY, VIX, news events)."""
    
    def __init__(self, db_session: AsyncSession):
        self.db = db_session
        self.repo = ExogenousVariableRepository(db_session)
    
    async def fetch_dxy_vix(self, start_date: datetime, end_date: datetime):
        """Fetch DXY and VIX data from Yahoo Finance."""
        # Fetch DXY (Dollar Index)
        dxy = yf.Ticker("DX-Y.NYB")
        dxy_data = dxy.history(start=start_date, end=end_date, interval="1h")
        
        for timestamp, row in dxy_data.iterrows():
            await self.repo.create_or_update(
                variable_name="DXY",
                timestamp=timestamp,
                value=float(row['Close']),
                source="yahoo_finance"
            )
        
        # Fetch VIX (Volatility Index)
        vix = yf.Ticker("^VIX")
        vix_data = vix.history(start=start_date, end=end_date, interval="1h")
        
        for timestamp, row in vix_data.iterrows():
            await self.repo.create_or_update(
                variable_name="VIX",
                timestamp=timestamp,
                value=float(row['Close']),
                source="yahoo_finance"
            )
        
        return {"dxy_records": len(dxy_data), "vix_records": len(vix_data)}
    
    async def mark_news_event(self, event_name: str, event_time: datetime):
        """Mark economic calendar event as binary flag."""
        await self.repo.create_or_update(
            variable_name="NEWS_EVENT",
            timestamp=event_time,
            value=None,
            is_event=True,
            source="economic_calendar"
        )
