"""
Input validation for MT4 responses (T109).

Validates all data received from MT4 to ensure integrity and prevent issues.
"""
from decimal import Decimal, InvalidOperation
from datetime import datetime
from typing import Any, Dict, Optional

from src.trading.execution.mt4_exceptions import MT4ValidationError


class MT4ResponseValidator:
    """Validator for MT4 response data (T109)."""
    
    @staticmethod
    def validate_response_structure(response: Dict[str, Any]) -> None:
        """
        Validate basic response structure.
        
        Args:
            response: Response dictionary from MT4
            
        Raises:
            MT4ValidationError: If validation fails
        """
        if not isinstance(response, dict):
            raise MT4ValidationError(f"Response must be dict, got {type(response)}")
        
        # Check required fields
        if "success" not in response:
            raise MT4ValidationError("Response missing 'success' field")
        
        if not isinstance(response["success"], bool):
            raise MT4ValidationError(
                f"'success' must be bool, got {type(response['success'])}"
            )
    
    @staticmethod
    def validate_decimal(value: Any, field_name: str, allow_none: bool = False) -> Optional[Decimal]:
        """
        Validate and convert to Decimal.
        
        Args:
            value: Value to validate
            field_name: Field name for error messages
            allow_none: Whether None is acceptable
            
        Returns:
            Decimal value or None
            
        Raises:
            MT4ValidationError: If validation fails
        """
        if value is None:
            if allow_none:
                return None
            raise MT4ValidationError(f"{field_name} cannot be None")
        
        try:
            dec_value = Decimal(str(value))
            return dec_value
        except (InvalidOperation, ValueError, TypeError) as e:
            raise MT4ValidationError(
                f"{field_name} must be numeric, got {type(value)}: {e}"
            )
    
    @staticmethod
    def validate_positive_decimal(
        value: Any,
        field_name: str,
        allow_zero: bool = False
    ) -> Decimal:
        """
        Validate positive decimal value.
        
        Args:
            value: Value to validate
            field_name: Field name for error messages
            allow_zero: Whether zero is acceptable
            
        Returns:
            Decimal value
            
        Raises:
            MT4ValidationError: If validation fails
        """
        dec_value = MT4ResponseValidator.validate_decimal(value, field_name)
        
        if allow_zero:
            if dec_value < 0:
                raise MT4ValidationError(f"{field_name} must be >= 0, got {dec_value}")
        else:
            if dec_value <= 0:
                raise MT4ValidationError(f"{field_name} must be > 0, got {dec_value}")
        
        return dec_value
    
    @staticmethod
    def validate_integer(
        value: Any,
        field_name: str,
        min_value: int = None,
        max_value: int = None
    ) -> int:
        """
        Validate integer value.
        
        Args:
            value: Value to validate
            field_name: Field name for error messages
            min_value: Optional minimum value
            max_value: Optional maximum value
            
        Returns:
            Integer value
            
        Raises:
            MT4ValidationError: If validation fails
        """
        if not isinstance(value, int):
            try:
                value = int(value)
            except (ValueError, TypeError) as e:
                raise MT4ValidationError(
                    f"{field_name} must be integer, got {type(value)}: {e}"
                )
        
        if min_value is not None and value < min_value:
            raise MT4ValidationError(
                f"{field_name} must be >= {min_value}, got {value}"
            )
        
        if max_value is not None and value > max_value:
            raise MT4ValidationError(
                f"{field_name} must be <= {max_value}, got {value}"
            )
        
        return value
    
    @staticmethod
    def validate_string(
        value: Any,
        field_name: str,
        max_length: int = None,
        allowed_values: list = None
    ) -> str:
        """
        Validate string value.
        
        Args:
            value: Value to validate
            field_name: Field name for error messages
            max_length: Optional maximum length
            allowed_values: Optional list of allowed values
            
        Returns:
            String value
            
        Raises:
            MT4ValidationError: If validation fails
        """
        if not isinstance(value, str):
            raise MT4ValidationError(
                f"{field_name} must be string, got {type(value)}"
            )
        
        if max_length is not None and len(value) > max_length:
            raise MT4ValidationError(
                f"{field_name} exceeds max length {max_length}: {len(value)}"
            )
        
        if allowed_values is not None and value not in allowed_values:
            raise MT4ValidationError(
                f"{field_name} must be one of {allowed_values}, got '{value}'"
            )
        
        return value
    
    @staticmethod
    def validate_order_response(response: Dict[str, Any]) -> None:
        """
        Validate order execution response.
        
        Args:
            response: Order response from MT4
            
        Raises:
            MT4ValidationError: If validation fails
        """
        # Basic structure
        MT4ResponseValidator.validate_response_structure(response)
        
        # If successful, validate required fields
        if response["success"]:
            if "ticket_number" not in response:
                raise MT4ValidationError("Successful order missing ticket_number")
            
            MT4ResponseValidator.validate_integer(
                response["ticket_number"],
                "ticket_number",
                min_value=1
            )
            
            if "execution_price" in response:
                MT4ResponseValidator.validate_positive_decimal(
                    response["execution_price"],
                    "execution_price"
                )
        
        # If failed, validate error fields
        else:
            if "error_code" in response:
                MT4ResponseValidator.validate_integer(
                    response["error_code"],
                    "error_code",
                    min_value=0
                )
    
    @staticmethod
    def validate_account_info(response: Dict[str, Any]) -> None:
        """
        Validate account info response.
        
        Args:
            response: Account info from MT4
            
        Raises:
            MT4ValidationError: If validation fails
        """
        required_fields = [
            "balance", "equity", "margin", "free_margin",
            "margin_level", "account_number", "leverage"
        ]
        
        for field in required_fields:
            if field not in response:
                raise MT4ValidationError(f"Account info missing '{field}'")
        
        # Validate numeric fields
        MT4ResponseValidator.validate_positive_decimal(
            response["balance"], "balance", allow_zero=True
        )
        MT4ResponseValidator.validate_positive_decimal(
            response["equity"], "equity", allow_zero=True
        )
        MT4ResponseValidator.validate_positive_decimal(
            response["margin"], "margin", allow_zero=True
        )
        
        # Validate account number
        MT4ResponseValidator.validate_integer(
            response["account_number"],
            "account_number",
            min_value=1
        )
        
        # Validate leverage
        MT4ResponseValidator.validate_integer(
            response["leverage"],
            "leverage",
            min_value=1,
            max_value=10000
        )
    
    @staticmethod
    def validate_position_info(position: Dict[str, Any]) -> None:
        """
        Validate position information.
        
        Args:
            position: Position info from MT4
            
        Raises:
            MT4ValidationError: If validation fails
        """
        required_fields = [
            "ticket", "symbol", "type", "volume",
            "open_price", "current_price", "magic_number"
        ]
        
        for field in required_fields:
            if field not in position:
                raise MT4ValidationError(f"Position missing '{field}'")
        
        # Validate ticket
        MT4ResponseValidator.validate_integer(
            position["ticket"], "ticket", min_value=1
        )
        
        # Validate symbol
        MT4ResponseValidator.validate_string(
            position["symbol"], "symbol", max_length=20
        )
        
        # Validate type
        MT4ResponseValidator.validate_string(
            position["type"],
            "type",
            allowed_values=["BUY", "SELL"]
        )
        
        # Validate volume
        MT4ResponseValidator.validate_positive_decimal(
            position["volume"], "volume"
        )
        
        # Validate prices
        MT4ResponseValidator.validate_positive_decimal(
            position["open_price"], "open_price"
        )
        MT4ResponseValidator.validate_positive_decimal(
            position["current_price"], "current_price"
        )
        
        # Validate magic number
        MT4ResponseValidator.validate_integer(
            position["magic_number"],
            "magic_number",
            min_value=0,
            max_value=999999
        )


# Module loaded - validation ready (print removed for MCP compatibility)
