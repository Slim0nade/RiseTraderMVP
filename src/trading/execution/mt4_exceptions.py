"""
Custom exceptions for MT4 integration (T108).

Provides specific exception types for better error handling and debugging.
"""


class MT4Error(Exception):
    """Base exception for all MT4-related errors."""
    pass


class MT4ConnectionError(MT4Error):
    """Raised when MT4 connection fails or is lost."""
    pass


class MT4TimeoutError(MT4Error):
    """Raised when MT4 command times out."""
    pass


class MT4CommandError(MT4Error):
    """Raised when MT4 command execution fails."""
    
    def __init__(self, message: str, error_code: int = None, error_details: dict = None):
        super().__init__(message)
        self.error_code = error_code
        self.error_details = error_details or {}


class MT4ValidationError(MT4Error):
    """Raised when MT4 response validation fails."""
    pass


class MT4EncryptionError(MT4Error):
    """Raised when encryption setup or operation fails."""
    pass


class MT4OrderRejectedError(MT4CommandError):
    """Raised when MT4 rejects an order."""
    pass


class MT4InsufficientMarginError(MT4OrderRejectedError):
    """Raised when order rejected due to insufficient margin."""
    pass


class MT4InvalidSymbolError(MT4CommandError):
    """Raised when symbol is invalid or not available."""
    pass


class MT4InvalidVolumeError(MT4CommandError):
    """Raised when order volume is invalid."""
    pass


class CircuitOpenError(MT4Error):
    """Raised when circuit breaker is open."""
    
    def __init__(self, message: str, circuit_state: str = "OPEN"):
        super().__init__(message)
        self.circuit_state = circuit_state


# Error code mappings from MT4
MT4_ERROR_CODES = {
    1: "ERR_NO_ERROR",
    2: "ERR_NO_RESULT",
    3: "ERR_COMMON_ERROR",
    4: "ERR_INVALID_TRADE_PARAMETERS",
    5: "ERR_SERVER_BUSY",
    6: "ERR_OLD_VERSION",
    7: "ERR_NO_CONNECTION",
    8: "ERR_NOT_ENOUGH_RIGHTS",
    9: "ERR_TOO_FREQUENT_REQUESTS",
    64: "ERR_ACCOUNT_DISABLED",
    65: "ERR_INVALID_ACCOUNT",
    128: "ERR_TRADE_TIMEOUT",
    129: "ERR_INVALID_PRICE",
    130: "ERR_INVALID_STOPS",
    131: "ERR_INVALID_TRADE_VOLUME",
    132: "ERR_MARKET_CLOSED",
    133: "ERR_TRADE_DISABLED",
    134: "ERR_NOT_ENOUGH_MONEY",
    135: "ERR_PRICE_CHANGED",
    136: "ERR_OFF_QUOTES",
    137: "ERR_BROKER_BUSY",
    138: "ERR_REQUOTE",
    139: "ERR_ORDER_LOCKED",
    140: "ERR_LONG_POSITIONS_ONLY_ALLOWED",
    141: "ERR_TOO_MANY_REQUESTS",
    145: "ERR_TRADE_MODIFY_DENIED",
    146: "ERR_TRADE_CONTEXT_BUSY",
    147: "ERR_TRADE_EXPIRATION_DENIED",
    148: "ERR_TRADE_TOO_MANY_ORDERS",
}


def get_error_description(error_code: int) -> str:
    """Get human-readable description for MT4 error code."""
    return MT4_ERROR_CODES.get(error_code, f"UNKNOWN_ERROR_{error_code}")


def create_mt4_error(error_code: int, message: str = None) -> MT4Error:
    """
    Create appropriate MT4 error based on error code.
    
    Args:
        error_code: MT4 error code
        message: Optional error message
        
    Returns:
        Appropriate MT4Error subclass
    """
    error_desc = get_error_description(error_code)
    full_message = f"{error_desc}: {message}" if message else error_desc
    
    # Map specific error codes to exception types
    if error_code == 134:
        return MT4InsufficientMarginError(full_message, error_code)
    elif error_code == 4:
        return MT4InvalidSymbolError(full_message, error_code)
    elif error_code == 131:
        return MT4InvalidVolumeError(full_message, error_code)
    elif error_code in [7, 128]:
        return MT4ConnectionError(full_message)
    elif error_code in [129, 130, 132, 133, 135, 136, 138]:
        return MT4OrderRejectedError(full_message, error_code)
    else:
        return MT4CommandError(full_message, error_code)


print("✓ T108: Custom exceptions created")
