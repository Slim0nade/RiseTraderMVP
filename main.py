"""
RiseTrader Main Entry Point

Starts the FastAPI server with all agents and services.

Usage:
    python main.py

Environment Variables:
    HOST: Server host (default: 0.0.0.0)
    PORT: Server port (default: 8003)
    LOG_LEVEL: Logging level (default: INFO)
    RELOAD: Enable auto-reload for development (default: False)
"""
import os
import sys

# Add project root to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import uvicorn
from src.api.config import settings


def main():
    """
    Main entry point for RiseTrader API server.
    """
    print(f"""
╔═══════════════════════════════════════════════════════════════════════════════════╗
║                      RiseTrader API Server                                        ║
║                  Autonomous Trading Platform                                      ║
╠═══════════════════════════════════════════════════════════════════════════════════╣
║  Version: {settings.app_version:<50}                                              ║
║  Host:    {settings.host:<50}                                                     ║
║  Port:    {settings.port:<50}                                                     ║
║  Debug:   {str(settings.debug):<50}                                               ║
╠═══════════════════════════════════════════════════════════════════════════════════╣
║  Endpoints:                                                                       ║
║    - API Docs:  http://{settings.host}:{settings.port}/docs                       ║
║    - Health:    http://{settings.host}:{settings.port}/health                     ║
║    - Metrics:   http://{settings.host}:{settings.port}/metrics                    ║
║    - Agents:    http://{settings.host}:{settings.port}/api/v1/agents              ║
║    - Trading:   http://{settings.host}:{settings.port}/api/v1/trading             ║
║    - Data:      http://{settings.host}:{settings.port}/api/v1/market-data         ║
║    - Forecasts: http://{settings.host}:{settings.port}/api/v1/forecasts           ║
╠═══════════════════════════════════════════════════════════════════════════════════╣
║  Features:                                                                        ║
║    - Paper Trading: {str(settings.enable_paper_trading):<37}                      ║
║    - Live Trading:  {str(settings.enable_live_trading):<37}                       ║
║    - ML Forecasts:  {str(settings.enable_forecasting):<37}                        ║
╠═══════════════════════════════════════════════════════════════════════════════════╣
║  Database: {settings.database_url[:44]:<44}                                       ║
║  Redis:    {settings.redis_url:<44}                                               ║
╚═══════════════════════════════════════════════════════════════════════════════════╝
    """)

    # Configure uvicorn
    uvicorn_config = uvicorn.Config(
        "src.api.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.reload,
        log_level=settings.log_level.lower(),
        workers=settings.workers if not settings.reload else 1,
        access_log=True,
    )

    # Create and run server
    server = uvicorn.Server(uvicorn_config)

    try:
        server.run()
    except KeyboardInterrupt:
        print("\n\n[INFO] Shutting down RiseTrader API server...")
    except Exception as e:
        print(f"\n\n[ERROR] Server error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
