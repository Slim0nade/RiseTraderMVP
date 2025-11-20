<!--
Sync Impact Report:
- Version change: 0.0.0 (initial) → 1.0.0 (first ratification)
- Modified principles: N/A (initial creation)
- Added sections: All sections (initial creation)
  - Core Principles (8 principles)
  - Security Requirements
  - Agent System Governance
  - Governance
- Removed sections: N/A (initial creation)
- Templates requiring updates:
  ✅ plan-template.md: Constitution Check section will reference these principles
  ✅ spec-template.md: Requirements must align with testing and security principles
  ✅ tasks-template.md: Task categorization includes security, testing, and observability tasks
- Follow-up TODOs: None - all placeholders filled
-->

# RiseTrader Constitution

## Core Principles

### I. Test-First Development (NON-NEGOTIABLE)

**Rule**: Every feature MUST follow strict Test-Driven Development (TDD):
- Tests are written FIRST and approved by user before implementation
- Tests MUST fail before implementation begins (Red phase)
- Implementation makes tests pass (Green phase)
- Code is refactored while keeping tests passing (Refactor phase)
- Minimum 85% test coverage target for all production code

**Rationale**: Autonomous trading systems make financial decisions affecting real capital.
Rigorous testing is the only acceptable path to production. TDD ensures testability is
built-in from the start and catches issues before they reach production where they could
cause financial losses.

**Applies to**: All agent logic, trading strategies, risk management, ML models, API
endpoints, database operations, and integration points.

### II. Security-First Design

**Rule**: Security MUST be addressed at every layer before production deployment:
- MT4 connection MUST use CurveZMQ encryption or VPN tunnel (no plaintext ZMQ)
- API endpoints MUST implement JWT + API key authentication
- Rate limiting MUST protect all public endpoints
- Secrets MUST NEVER be committed to version control
- All external inputs MUST be validated and sanitized
- Security review REQUIRED for every trading-related feature

**Rationale**: Trading platforms are high-value targets for attackers. A security breach
could result in unauthorized trades, data theft, or system compromise. The MT4 connection
is currently exposed without encryption - this MUST be fixed before live trading.

**Blocking requirement**: No live trading deployment without security implementation.

### III. Observability & Monitoring

**Rule**: Every component MUST be observable:
- Structured logging (JSON format) with correlation IDs for all operations
- Metrics instrumentation for performance tracking (Prometheus-compatible)
- Distributed tracing for request flows (Jaeger integration)
- Agent decision logs MUST be auditable with full context
- All trading actions MUST be logged with timestamp, agent, rationale, and outcome
- Performance targets: API <200ms p95, ML inference <50ms, execution <500ms, agent <100ms

**Rationale**: Debugging autonomous agent systems requires complete visibility into
decision-making processes. When a trade goes wrong, we need to trace exactly why the agent
made that decision. Performance monitoring ensures the system meets latency requirements
critical for algorithmic trading.

### IV. Agent Autonomy with Guardrails

**Rule**: Agents operate autonomously within strict boundaries:
- Each agent has a clearly defined scope and decision authority
- Risk limits MUST be enforced at multiple layers (agent, service, system)
- Circuit breakers MUST prevent cascading failures
- Emergency stop mechanisms MUST be always available
- Agents MUST validate all inputs from other agents or external systems
- Agent decisions MUST be explainable and auditable

**Rationale**: The multi-agent system coordinates 10 specialized agents making autonomous
trading decisions. Without proper guardrails, a single agent malfunction could trigger
system-wide failures or unauthorized trades. Layered risk management ensures no single
point of failure.

**Critical**: RiskManagerAgent and RiskOverseerAgent provide redundant safety checks.

### V. Paper Trading Before Live Trading

**Rule**: New strategies and features MUST validate in paper trading mode:
- Paper trading MUST be functionally identical to live trading (same code paths)
- Minimum validation period: 1 week of paper trading with realistic data
- Success criteria: Strategy meets performance targets without risk violations
- Gradual rollout: Enable ONE strategy at a time in production
- Feature flags MUST control live vs paper trading mode

**Rationale**: Paper trading provides a final validation layer before risking real capital.
It catches issues that unit and integration tests may miss, such as timing problems,
market condition edge cases, or unexpected agent interactions.

### VI. Repository Pattern & Service Layer

**Rule**: Data access and business logic MUST be properly separated:
- Database operations abstracted through repository classes (`src/database/repositories/`)
- Business logic in service layer (`src/services/`), not in API routes or agents
- Repositories provide async CRUD operations using SQLAlchemy 2.0+
- Agents and API routes orchestrate through services, never direct DB access
- Each repository corresponds to a domain entity (positions, trades, forecasts, etc.)

**Rationale**: Clean separation enables independent testing of business logic without
database dependencies, supports multiple data sources, and makes the codebase more
maintainable as complexity grows. Async operations are essential for high-performance
trading systems.

### VII. Event-Driven Agent Communication

**Rule**: Agents communicate via events through the MCP server:
- Direct agent-to-agent calls are FORBIDDEN (except through MCP)
- Events follow standardized schema with type, timestamp, source, and payload
- Redis pub/sub provides asynchronous message delivery
- Event handlers MUST be idempotent (safe to replay)
- Circuit breakers protect against event storm scenarios
- All events MUST be logged for audit trail

**Rationale**: Event-driven architecture decouples agents, enabling parallel development,
independent testing, and resilience to individual agent failures. It also provides a
natural audit trail of all system actions, critical for understanding trading decisions.

**Example flow**: MarketDataAgent emits "new_tick" → SignalGeneratorAgent processes →
emits "signal_generated" → RiskManagerAgent validates → emits "trade_validated" →
ExecutionAgent executes → emits "trade_executed".

### VIII. Version Control & Backward Compatibility

**Rule**: Changes MUST maintain backward compatibility where possible:
- Database migrations MUST be reversible (Alembic down migrations required)
- API versions MUST be maintained during deprecation periods
- Agent event schemas MUST version changes to avoid breaking consumers
- Breaking changes require documented migration path and deprecation notice
- Configuration changes MUST have sensible defaults for existing deployments

**Rationale**: Zero-downtime deployment is critical for 24/7 trading operations. Rolling
back a bad deployment should not require data loss or system downtime. Gradual migration
paths reduce deployment risk.

## Security Requirements

### Pre-Production Blockers

These MUST be implemented before any live trading:

1. **MT4 Connection Encryption**
   - Implement ZMQ CurveZMQ with `ZMQ_CLIENT_SECRET_KEY`, `ZMQ_CLIENT_PUBLIC_KEY`,
     `ZMQ_SERVER_PUBLIC_KEY`
   - OR: Establish VPN tunnel to MT4 server at 75.154.254.186
   - Current state: EXPOSED - no encryption

2. **API Authentication & Authorization**
   - JWT tokens for user sessions with `JWT_SECRET_KEY`
   - API key validation for service-to-service calls with `VALID_API_KEYS`
   - Role-based access control (RBAC) for sensitive operations
   - Current state: NO AUTH IMPLEMENTED

3. **Rate Limiting**
   - slowapi middleware protecting all public endpoints
   - Per-IP and per-API-key rate limits
   - Graduated response: warn → throttle → block
   - Current state: NO RATE LIMITING

4. **Secrets Management**
   - Environment variables for all secrets (never in code)
   - `.env` files in `.gitignore`
   - Production secrets in secure vault (e.g., AWS Secrets Manager, HashiCorp Vault)
   - Rotation procedures documented

### Security Testing Requirements

- Input validation tests for all API endpoints
- Authentication/authorization tests for protected resources
- SQL injection, XSS, and CSRF protection tests
- Secrets scanning in CI/CD pipeline
- Regular dependency vulnerability scanning

## Agent System Governance

### Agent Development Standards

Each agent MUST have:

1. **Clear Scope**: Documented responsibility boundaries and decision authority
2. **Event Contracts**: Published event schemas (input and output)
3. **Error Handling**: Graceful degradation when dependencies fail
4. **Health Checks**: Expose health endpoint with dependency status
5. **Configuration**: YAML config at `config/agents.yaml` with validation
6. **Testing**: Unit tests (85%+ coverage), integration tests, and contract tests

### Agent Decision Auditability

Every agent decision that affects trading MUST log:

- **Timestamp**: When the decision was made (ISO 8601 with microseconds)
- **Agent ID**: Which agent made the decision
- **Input Context**: All inputs considered (market data, signals, positions, etc.)
- **Decision**: What action was chosen
- **Rationale**: Why this action was selected (rules triggered, scores, thresholds)
- **Outcome**: Result of the action (success, failure, rejected by downstream agent)

**Log format**: Structured JSON with correlation ID for request tracing.

### MCP Server Requirements

The Model Context Protocol (MCP) server at `src/agents/mcp_server.py` is the coordination
hub. It MUST:

- Route events between agents with guaranteed delivery
- Maintain shared context (positions, balances, risk state)
- Enforce agent rate limits and circuit breakers
- Provide agent registry and discovery
- Health check and restart failed agents
- Log all inter-agent communication

### Agent Testing Strategy

**Unit Tests**: Mock dependencies, test agent logic in isolation
**Integration Tests**: Test agent pairs communicating via MCP
**Contract Tests**: Validate event schemas between agents
**E2E Tests**: Full trading flow from market data to execution
**Chaos Tests**: Inject failures to validate resilience

## Governance

### Amendment Process

This constitution can be amended through:

1. **Proposal**: Document proposed changes with rationale
2. **Impact Analysis**: Review affected components and migration requirements
3. **Approval**: Project maintainer approval required
4. **Migration**: Implement changes across codebase with updated templates
5. **Versioning**: Increment version following semantic versioning:
   - **MAJOR**: Backward incompatible governance/principle removals or redefinitions
   - **MINOR**: New principle/section added or materially expanded guidance
   - **PATCH**: Clarifications, wording, typo fixes, non-semantic refinements

### Compliance Review

All pull requests and features MUST verify compliance with this constitution:

- Security requirements addressed (pre-production blockers identified)
- Tests written first and failing before implementation (TDD)
- Observability instrumentation included (logging, metrics, tracing)
- Agent communication via events only (no direct calls)
- Repository pattern used for data access
- Paper trading validation planned (for trading features)
- Documentation updated

### Enforcement

- **Constitution Check** section in `plan.md` template verifies compliance
- **Code Review**: Reviewers MUST verify principle adherence
- **CI/CD Gates**: Automated checks for test coverage, security scanning, code quality
- **Quarterly Audit**: Review adherence and update constitution as needed

### Exception Process

Principle violations MUST be justified in the "Complexity Tracking" section of `plan.md`:

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [Specific principle] | [Business/technical requirement] | [Why compliant approach insufficient] |

Exceptions require approval from project maintainer.

### Living Document

This constitution evolves with the project:

- Feedback from implementation experience informs amendments
- New risks or requirements may add principles
- Overly restrictive rules may be relaxed with proper justification
- Regular review ensures relevance and practicality

**Version**: 1.0.0 | **Ratified**: 2025-11-20 | **Last Amended**: 2025-11-20
