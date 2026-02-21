# Backtest Execution Flow Diagram

Complete flow of the RiseTrader backtesting system from UI trigger to completion.

## Complete System Flow

```mermaid
flowchart TD
    %% ===== FRONTEND LAYER =====
    subgraph Frontend["Frontend (React/TypeScript)"]
        UI[Backtesting.tsx<br/>User clicks 'Start Run']
        CreateModal[CreateBacktestModal.tsx<br/>Form with config]

        UI -->|1. User selects config| HandleStart[handleStartRun handler]
        HandleStart -->|2. Prepare request| APICall[POST /api/backtesting/runs]

        HandleStart -.->|Sets state| RunningState[runningConfigs.add config_id]
        HandleStart -.->|Clears cache| InvalidateQuery[queryClient.invalidateQueries]
    end

    %% ===== API LAYER =====
    subgraph API["FastAPI Backend"]
        APIRoute["/runs endpoint<br/>backtesting.py:359"]

        APICall -->|3. HTTP Request| APIRoute

        APIRoute -->|4. Create run record| CreateRun[BacktestRun<br/>status=RUNNING<br/>run_id=UUID]
        APIRoute -->|5. Schedule task| BGTask[BackgroundTasks.add_task]
        APIRoute -->|6. Return immediately| Response202[HTTP 202 ACCEPTED<br/>run_id, status]

        Response202 -->|7. Response| Frontend
    end

    %% ===== BACKGROUND EXECUTION =====
    subgraph Background["Background Task (Async)"]
        BGTask -->|8. Execute async| TaskFunc[run_backtest_task]

        TaskFunc -->|9. Create services| Services[BacktestService<br/>BacktestRepository<br/>MarketDataRepository]

        TaskFunc -->|10. Check mode| ModeCheck{execution_mode?}

        ModeCheck -->|full_pipeline| FullMode[_run_full_pipeline_mode]
        ModeCheck -->|synthetic_fast| SynthMode[_run_synthetic_mode]
    end

    %% ===== SYNTHETIC MODE FLOW =====
    subgraph SyntheticFlow["Synthetic Mode (Rule-Based)"]
        SynthMode -->|11. Create engine| SynthEngine[SyntheticEngine<br/>strategy=config.synthetic_strategy<br/>params=config.synthetic_params]

        SynthEngine -->|12. Start replay| DataReplay[DataReplayEngine.replay_with_progress<br/>symbol, timeframe, dates]

        DataReplay -->|13. Stream candles| CandleLoop{For each candle}

        CandleLoop -->|14. Update portfolio| PortfolioUpdate[portfolio.update_market_price<br/>symbol, close]

        CandleLoop -->|15. Get decision| DecisionEngine[decision_engine tick<br/>→ SyntheticEngine.process_tick]

        DecisionEngine -->|16. Returns| Decision{action?}

        Decision -->|buy/sell| OpenPos[TradeSimulator.execute_entry<br/>→ create_trade in DB]
        Decision -->|close| ClosePos[TradeSimulator.execute_exit<br/>→ update_trade in DB]
        Decision -->|None| CandleLoop

        OpenPos --> CandleLoop
        ClosePos --> CandleLoop

        CandleLoop -->|All candles done| CalcMetrics[MetricsCalculator.calculate_all_metrics]
    end

    %% ===== FULL PIPELINE MODE FLOW =====
    subgraph FullPipelineFlow["Full Pipeline Mode (Agent-Based)"]
        FullMode -->|11. Initialize| AgentInit[AgentIntegrator<br/>model, ollama_base_url<br/>decision_threshold]

        AgentInit -->|12. Check Ollama| OllamaCheck{Ollama<br/>available?}

        OllamaCheck -->|No| FailFast[Raise ValueError<br/>'Ollama not accessible']
        OllamaCheck -->|Yes| AgentReady[integrator.initialize<br/>timeout=120s]

        AgentReady -->|13. Start replay| AgentReplay[DataReplayEngine.replay_with_progress]

        AgentReplay -->|14. Stream candles| AgentLoop{For each Nth candle<br/>interval=10}

        AgentLoop -->|15. Build context| MarketCtx[MarketContext<br/>price, OHLCV, portfolio,<br/>positions, cash]

        MarketCtx -->|16. Query agent| AgentDecision[integrator.get_trading_decision<br/>→ LLM call]

        AgentDecision -->|17. LLM provider| LLMRouter{Which model?}

        LLMRouter -->|Ollama| OllamaClient[create_ollama_client<br/>qwen3:14b / deepseek-r1:14b<br/>FREE]
        LLMRouter -->|OpenAI| OpenAIClient[create_openai_client<br/>gpt-4o-mini / gpt-4o<br/>ModelInfo required<br/>$$$]
        LLMRouter -->|Anthropic| ClaudeClient[create_anthropic_client<br/>claude-3-5-sonnet<br/>ModelInfo required<br/>base_url=anthropic.com/v1<br/>$$$]

        OllamaClient -->|18. API call| OllamaAPI[HTTP POST<br/>192.168.0.123:11434/v1/chat/completions]
        OpenAIClient -->|18. API call| OpenAIAPI[HTTP POST<br/>api.openai.com/v1/chat/completions<br/>Authorization: Bearer OPENAI_API_KEY]
        ClaudeClient -->|18. API call| ClaudeAPI[HTTP POST<br/>api.anthropic.com/v1/chat/completions<br/>x-api-key: ANTHROPIC_API_KEY]

        OllamaAPI -->|19. Response| LLMResponse[TradingDecision<br/>action, quantity,<br/>conviction, rationale]
        OpenAIAPI -->|19. Response or 401| LLMResponse
        ClaudeAPI -->|19. Response or 401| LLMResponse

        LLMResponse -->|20. Log decision| LogDB[AgentDecisionLog.create<br/>timestamp, input, output<br/>→ agent_decision_logs table]

        LogDB -->|21. Execute?| TradeExec{action != hold?}

        TradeExec -->|buy/sell| AgentTrade[TradeSimulator.execute_entry<br/>→ simulated_trades table]
        TradeExec -->|close_long| AgentClose[TradeSimulator.execute_exit<br/>→ update simulated_trades]
        TradeExec -->|hold| AgentLoop

        AgentTrade --> AgentLoop
        AgentClose --> AgentLoop

        AgentLoop -->|All candles done| AgentMetrics[MetricsCalculator.calculate_all_metrics]
        AgentMetrics -->|22. Update run| UpdateRun[update agent_decisions_count]
    end

    %% ===== COMPLETION =====
    subgraph Completion["Completion (Both Modes)"]
        CalcMetrics -->|23. Calculate| MetricsObj[PerformanceMetrics<br/>Sharpe, return, drawdown,<br/>win_rate, profit_factor]
        UpdateRun --> MetricsObj

        MetricsObj -->|24. Update run| FinalUpdate[BacktestRun.update<br/>status=COMPLETED<br/>metrics, final_capital]

        FinalUpdate -->|25. Commit| DBCommit[session.commit]
    end

    %% ===== ERROR HANDLING =====
    subgraph Errors["Error Handling"]
        FailFast -.->|Exception| ErrorHandler[Update run<br/>status=FAILED<br/>error_message]
        OllamaAPI -.->|Network error| ErrorHandler
        OpenAIAPI -.->|401 Invalid key| ErrorHandler
        ClaudeAPI -.->|401 Invalid key| ErrorHandler

        ErrorHandler -.->|Commit| DBCommit
    end

    %% ===== POLLING =====
    subgraph Polling["Frontend Polling"]
        DBCommit -->|26. Available| PollEndpoint[GET /api/backtesting/runs/run_id/status]

        PollEndpoint -->|27. React Query| QueryHook[useQuery run_id<br/>refetchInterval=2000ms]

        QueryHook -->|28. Update UI| UIUpdate[Show metrics, trades,<br/>decisions, charts]

        UIUpdate -->|29. If failed| RetryButton[Retry Button<br/>onClick=handleStartRun]
    end

    %% ===== DATA MODELS =====
    subgraph Database["PostgreSQL Tables"]
        RunsTable[(backtest_runs<br/>id, config_id, status<br/>candles_processed<br/>metrics, error_message)]

        TradesTable[(simulated_trades<br/>id, run_id, symbol<br/>entry/exit price/time<br/>gross_pnl, net_pnl)]

        DecisionsTable[(agent_decision_logs<br/>id, run_id, timestamp<br/>input_data, output_decision)]

        FinalUpdate -.->|Insert/Update| RunsTable
        OpenPos -.->|Insert| TradesTable
        ClosePos -.->|Update| TradesTable
        LogDB -.->|Insert| DecisionsTable
    end

    %% ===== ENVIRONMENT VARIABLES =====
    subgraph EnvVars["Environment Variables (.env → Docker)"]
        EnvFile[.env file<br/>OPENAI_API_KEY<br/>ANTHROPIC_API_KEY<br/>OLLAMA_BASE_URL]

        DockerCompose[docker-compose.yml<br/>api service<br/>environment:]

        EnvFile -.->|Loaded by| DockerCompose
        DockerCompose -.->|Injected into| Container[risetrader-api container<br/>os.getenv 'OPENAI_API_KEY']

        Container -.->|Used by| OpenAIClient
        Container -.->|Used by| ClaudeClient
        Container -.->|Used by| OllamaClient
    end

    style UI fill:#e1f5ff
    style APIRoute fill:#fff4e1
    style FullMode fill:#ffe1f5
    style SynthMode fill:#e1ffe1
    style LLMResponse fill:#f5e1ff
    style ErrorHandler fill:#ffe1e1
    style DBCommit fill:#e1f5e1
    style RunsTable fill:#f0f0f0
```

## Key Files and Methods

### Frontend
- **File**: `dashboard/src/pages/Backtesting.tsx`
  - **Method**: `handleStartRun(config_id: UUID, e: Event)`
  - **Input**: Configuration UUID
  - **Output**: API call to `/api/backtesting/runs`
  - **State**: Sets `runningConfigs`, invalidates queries

### API Layer
- **File**: `src/api/routes/backtesting.py`
  - **Endpoint**: `POST /runs` (line ~358)
  - **Method**: `run_backtest(request: RunBacktestRequest)`
  - **Input**: `config_id`, `timeframe`, `synthetic_strategy`, `synthetic_params`
  - **Output**: `BacktestRunStatusResponse` (HTTP 202)
  - **Side Effect**: Creates `BacktestRun` record, schedules background task
  - **⚠️ Critical**: Background task creates its own `AsyncSessionLocal()` session to avoid session lifecycle issues

### Backtest Service
- **File**: `src/services/backtesting/backtest_service.py`
  - **Method**: `run_backtest(config_id, timeframe, decision_engine, existing_run_id)` (line ~162)
  - **Input**: Configuration, optional decision engine
  - **Output**: Completed `BacktestRun` with metrics
  - **Orchestrates**: Data replay, portfolio, simulator, metrics

### Synthetic Mode
- **File**: `src/services/backtesting/backtest_service.py`
  - **Method**: `_run_synthetic_mode(run, config, portfolio, simulator)` (line ~289)
  - **Flow**:
    1. **If no decision_engine provided**: Reads `config.config_params` for `synthetic_strategy` and `synthetic_params`
    2. Creates `SyntheticEngine` from config params (supports `crude_oil_v3`, `ma_crossover`, `rsi`, etc.)
    3. Wraps engine in `decision_engine` callable
    4. Replays historical data via `DataReplayEngine`
    5. Calls `decision_engine(tick)` for each candle
    6. Executes trades via `TradeSimulator`
    7. Saves to `simulated_trades` table
  - **⚠️ Config Formats Supported**:
    - `{"synthetic_strategy": "crude_oil_v3", "synthetic_params": {...}}`
    - `{"strategy": "crude_oil_v3", "ema_fast": 8, ...}` (flat)

### Full Pipeline Mode
- **File**: `src/services/backtesting/backtest_service.py`
  - **Method**: `_run_full_pipeline_mode(run, config, portfolio, simulator)` (line ~435)
  - **Flow**:
    1. Creates `AgentIntegrator` with LLM config
    2. Checks Ollama availability (fails fast if unavailable)
    3. Replays data with interval (every 10 candles)
    4. Builds `MarketContext` from current state
    5. Calls `integrator.get_trading_decision(context)`
    6. Logs decision to `agent_decision_logs` table
    7. Executes trade if action != hold

### Agent Integrator
- **File**: `src/services/backtesting/agent_integrator.py`
  - **Method**: `get_trading_decision(market_context: MarketContext)`
  - **Input**: Market data + portfolio state
  - **Output**: `TradingDecision` (action, quantity, conviction, rationale)
  - **Side Effect**: Logs to `agent_decision_logs` via `_log_decision()`

### LLM Clients
- **OpenAI**: `src/agents/providers/openai_client.py`
  - **Method**: `create_openai_client(model, temperature, max_tokens, api_key)`
  - **Requires**: `OPENAI_API_KEY` env var, `ModelInfo` object
  - **Returns**: `OpenAIChatCompletionClient`

- **Anthropic**: `src/agents/providers/anthropic_client.py`
  - **Method**: `create_anthropic_client(model, temperature, max_tokens, api_key)`
  - **Requires**: `ANTHROPIC_API_KEY` env var, `ModelInfo` object
  - **Base URL**: `https://api.anthropic.com/v1`
  - **Returns**: `OpenAIChatCompletionClient` (OpenAI-compatible)

- **Ollama**: `src/agents/providers/ollama_client.py`
  - **Method**: `create_ollama_client(model, ollama_base_url, temperature)`
  - **Default URL**: `http://192.168.0.123:11434/v1`
  - **No API key required** (local/free)

### Database Models

#### Backtesting Tables
- **BacktestRun**: `src/database/models/backtest.py`
  - Fields: `id`, `config_id`, `status`, `candles_processed`, `metrics`, `error_message`

- **SimulatedTrade**: `src/database/models/simulated_trade.py`
  - Fields: `id`, `run_id`, `entry_price/time`, `exit_price/time`, `gross_pnl`, `net_pnl`

- **AgentDecisionLog**: `src/database/models/simulated_trade.py`
  - Table: `agent_decision_logs`
  - Purpose: Logs agent decisions during backtesting
  - Fields: `id`, `backtest_run_id` (FK), `timestamp`, `input_data`, `output_decision`, `agent_identifier`
  - Used by: Full Pipeline mode only

#### Live Trading Tables
- **DecisionLog**: `src/database/models/` (production)
  - Table: `decision_log`
  - Purpose: Logs agent decisions during live trading
  - Fields: `id`, `agent_id` (FK), `agent_type`, `strategy_team_id` (FK), `input_data`, `decision_data`, `was_executed`, `execution_result`, `pnl_impact`, `sharpe_impact`
  - Used by: Live trading agents only

## Variable Flow (Example: Agent Mode)

```
UI Click (config_id)
  → API Request {config_id, timeframe="M5", synthetic_strategy=null}
    → BacktestRun created {id=uuid4(), status=RUNNING}
      → Background task executes
        → Load config from DB → BacktestConfiguration object
          → execution_mode="full_pipeline"
            → AgentIntegrator(model="qwen3:14b", ollama_base_url="http://192.168.0.123:11434/v1")
              → Check Ollama: GET http://192.168.0.123:11434/api/tags
                → If 200: Continue
                → If error: Raise ValueError
              → integrator.initialize()
                → Create LLM client
              → For each 10th candle:
                → MarketContext {symbol="CrudeOIL", price=75.43, cash=10000, ...}
                  → integrator.get_trading_decision(context)
                    → Format prompt with context
                    → LLM API call:
                      - Ollama: POST http://192.168.0.123:11434/v1/chat/completions
                      - OpenAI: POST https://api.openai.com/v1/chat/completions (Header: Authorization: Bearer sk-...)
                      - Anthropic: POST https://api.anthropic.com/v1/chat/completions (Header: x-api-key: sk-ant-...)
                    → Response: {action="buy", quantity=1.0, conviction=0.75, rationale="..."}
                      → AgentDecisionLog.create {run_id, timestamp, input_data=context, output_decision=response}
                      → If action="buy":
                        → TradeSimulator.execute_entry(symbol, price, quantity)
                          → SimulatedTrade.create {run_id, entry_price, entry_timestamp, ...}
                      → Continue to next candle
              → After all candles:
                → MetricsCalculator.calculate_all_metrics(equity_curve, trades)
                  → PerformanceMetrics {sharpe=1.23, return_pct=15.4, ...}
                    → BacktestRun.update {status=COMPLETED, metrics=..., final_capital=...}
                      → session.commit()
                        → Available to polling: GET /runs/{run_id}/status
```

## Error Scenarios

### 1. Invalid OpenAI API Key
```
Environment: OPENAI_API_KEY=sk-invalid...
  → create_openai_client(api_key=sk-invalid...)
    → POST https://api.openai.com/v1/chat/completions
      → Response: 401 Unauthorized
        → Exception in integrator.get_trading_decision()
          → Logged but NOT raised (silent failure in old code)
          → Decision count = 0, backtest continues
          → Final result: 0 trades, 0 decisions, status=COMPLETED ❌
```

**Fix**: Proper API key from https://platform.openai.com/account/api-keys

### 2. Invalid Anthropic API Key
```
Environment: ANTHROPIC_API_KEY=sk-ant-invalid...
  → create_anthropic_client(api_key=sk-ant-invalid...)
    → POST https://api.anthropic.com/v1/chat/completions
      → Response: 401 Invalid Anthropic API Key
        → Exception in integrator.get_trading_decision()
          → Logged but NOT raised
          → Backtest continues with 0 decisions ❌
```

**Fix**: Valid API key from https://console.anthropic.com/settings/keys

### 3. Ollama Server Unreachable
```
Config: ollama_base_url="http://192.168.0.123:11434/v1"
  → _run_full_pipeline_mode()
    → httpx.get("http://192.168.0.123:11434/api/tags")
      → Timeout or Connection Refused
        → Raise ValueError("Ollama server not accessible")
          → BacktestRun.update {status=FAILED, error_message="Ollama server not accessible"}
          → UI shows: "Backtest Failed" with error message ✅
```

## Performance Characteristics

- **Synthetic Mode**: ~100-1000 candles/second (rule-based, no LLM, no decision logging)
- **Full Pipeline Mode (Ollama)**: ~0.2 candles/second (5s per LLM call, logs to `agent_decision_logs`)
- **Full Pipeline Mode (GPT-4o)**: ~0.1-0.3 candles/second (3-10s per API call + network, logs to `agent_decision_logs`)
- **Decision Interval**: Every 10 candles (configurable) to reduce LLM calls
- **Database Commits**: Every 5000 candles for progress updates
- **Progress Publishing**: Every 1000 candles to Redis (for SSE streaming)

**Note**: Live trading uses `decision_log` table instead of `agent_decision_logs`

## Cost Analysis (Full Pipeline Mode)

**Assumptions**: 30,000 candles, decision_interval=10 → 3,000 decisions

- **Ollama (qwen3:14b)**: $0 (free, local)
- **OpenAI (gpt-4o-mini)**: ~$0.15-0.30 per 1M tokens → ~$0.45-0.90 per run
- **Anthropic (claude-3-5-sonnet)**: ~$3 per 1M tokens → ~$9-18 per run
- **GPT-4o**: ~$5 per 1M tokens → ~$15-30 per run

**Recommendation**: Use Ollama for development/testing, proprietary models for production validation only.

---

## Recent Bug Fixes (2025-12-26)

### Fix 1: Background Task Session Lifecycle

**Problem**: Background tasks were using the API request's database session, which closes after HTTP response returns. This caused backtests to hang at 0 candles with silent failures.

**Symptom**: `status=running`, `candles_processed=0` forever, no error logs.

**Solution**: Background task now creates its own fresh session:
```python
async def run_backtest_task():
    async with AsyncSessionLocal() as task_session:  # Fresh session!
        task_service = BacktestService(session=task_session, ...)
        await task_service.run_backtest(...)
```

**File**: `src/api/routes/backtesting.py` (line ~393)

---

### Fix 2: Synthetic Engine Creation from config_params

**Problem**: `_run_synthetic_mode()` expected `decision_engine` to be passed in, but when using `config_params` (e.g., from UI), no engine was created. Backtests processed candles but generated 0 trades.

**Symptom**: `status=completed`, `candles_processed=50000`, `total_trades=0`.

**Solution**: `_run_synthetic_mode()` now reads `config.config_params` to create `SyntheticEngine` if no `decision_engine` provided:
```python
if decision_engine is None and config.config_params:
    synthetic_strategy = config.config_params.get("synthetic_strategy")
    if synthetic_strategy:
        synthetic_engine = SyntheticEngine(strategy=synthetic_strategy, ...)
        decision_engine = lambda tick: {...}  # Wrap engine
```

**File**: `src/services/backtesting/backtest_service.py` (line ~289)

---

### Fix 3: Background Task Error Handling

**Problem**: When background task crashed, run status stayed at `RUNNING` forever. Errors were logged but not persisted to database.

**Symptom**: `status=running` with error in logs, but UI shows "running" indefinitely.

**Solution**: Background task now updates run status to `FAILED` on exception:
```python
except Exception as e:
    await task_backtest_repo.update_run(
        run_id=run_id,
        update_data={
            "status": DBRunStatus.FAILED,
            "error_message": str(e),
        }
    )
    await task_session.commit()
```

**File**: `src/api/routes/backtesting.py` (line ~470)
