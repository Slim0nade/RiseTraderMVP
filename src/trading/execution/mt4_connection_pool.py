"""
MT4 Connection Pool for managing multiple Expert Advisors.

Handles magic number allocation, port allocation, and EA registry.
"""
from datetime import datetime
from typing import Dict, Optional, Set, Tuple
import threading


class MT4ConnectionPool:
    """
    Connection pool for managing multiple MT4 Expert Advisors.

    Manages:
    - Magic number allocation (100000-999999 range)
    - Port pair allocation (REP and PUB sockets)
    - EA registry with connection details
    - Resource tracking and deallocation
    """

    def __init__(
        self,
        base_magic_number: int = 100000,
        base_rep_port: int = 5555,
        base_pub_port: int = 5556
    ):
        """
        Initialize connection pool.

        Args:
            base_magic_number: Starting magic number (default 100000)
            base_rep_port: Starting REP socket port (default 5555)
            base_pub_port: Starting PUB socket port (default 5556)
        """
        self.base_magic_number = base_magic_number
        self.base_rep_port = base_rep_port
        self.base_pub_port = base_pub_port

        # Allocated resources
        self._allocated_magic_numbers: Set[int] = set()
        self._allocated_rep_ports: Set[int] = set()
        self._allocated_pub_ports: Set[int] = set()

        # EA registry: ea_id -> {magic_number, rep_port, pub_port, host, symbol, ...}
        self._ea_registry: Dict[str, Dict] = {}

        # Thread safety
        self._lock = threading.Lock()

    # =========================================================================
    # Magic Number Management (T065-T066)
    # =========================================================================

    def allocate_magic_number(self) -> int:
        """
        Allocate a unique magic number.

        Returns:
            Allocated magic number in range 100000-999999

        Raises:
            RuntimeError: If no magic numbers available (extremely unlikely)
        """
        with self._lock:
            # Find next available magic number
            magic = self.base_magic_number
            max_magic = 999999

            while magic <= max_magic:
                if magic not in self._allocated_magic_numbers:
                    self._allocated_magic_numbers.add(magic)
                    return magic
                magic += 1

            raise RuntimeError("No magic numbers available (range exhausted)")

    def deallocate_magic_number(self, magic_number: int) -> None:
        """
        Deallocate magic number for reuse.

        Args:
            magic_number: Magic number to release
        """
        with self._lock:
            self._allocated_magic_numbers.discard(magic_number)

    def is_magic_number_allocated(self, magic_number: int) -> bool:
        """
        Check if magic number is currently allocated.

        Args:
            magic_number: Magic number to check

        Returns:
            True if allocated, False otherwise
        """
        with self._lock:
            return magic_number in self._allocated_magic_numbers

    # =========================================================================
    # Port Allocation (T060, T065-T066)
    # =========================================================================

    def allocate_ports(self) -> Tuple[int, int]:
        """
        Allocate port pair for REP and PUB sockets.

        Returns:
            Tuple of (rep_port, pub_port)

        Raises:
            RuntimeError: If no ports available
        """
        with self._lock:
            # Find next available port pair
            rep_port = self.base_rep_port
            pub_port = self.base_pub_port
            max_port = 65535

            while rep_port <= max_port - 1:
                if (rep_port not in self._allocated_rep_ports and
                    pub_port not in self._allocated_pub_ports):
                    self._allocated_rep_ports.add(rep_port)
                    self._allocated_pub_ports.add(pub_port)
                    return (rep_port, pub_port)

                # Increment by 2 (REP and PUB are consecutive)
                rep_port += 2
                pub_port += 2

            raise RuntimeError("No port pairs available")

    def deallocate_ports(self, rep_port: int, pub_port: int) -> None:
        """
        Deallocate port pair for reuse.

        Args:
            rep_port: REP socket port
            pub_port: PUB socket port
        """
        with self._lock:
            self._allocated_rep_ports.discard(rep_port)
            self._allocated_pub_ports.discard(pub_port)

    def are_ports_allocated(self, rep_port: int, pub_port: int) -> bool:
        """
        Check if ports are currently allocated.

        Args:
            rep_port: REP socket port
            pub_port: PUB socket port

        Returns:
            True if both ports are allocated, False otherwise
        """
        with self._lock:
            return (rep_port in self._allocated_rep_ports and
                    pub_port in self._allocated_pub_ports)

    # =========================================================================
    # EA Registry Management (T067-T068)
    # =========================================================================

    def register_ea(
        self,
        ea_id: str,
        magic_number: int,
        rep_port: int,
        pub_port: int,
        host: str,
        symbol: str,
        **kwargs
    ) -> None:
        """
        Register EA in the connection pool.

        Args:
            ea_id: Unique EA identifier
            magic_number: Allocated magic number
            rep_port: REP socket port
            pub_port: PUB socket port
            host: MT4 server host
            symbol: Trading symbol
            **kwargs: Additional EA metadata

        Raises:
            ValueError: If EA ID already registered
        """
        with self._lock:
            if ea_id in self._ea_registry:
                raise ValueError(f"EA '{ea_id}' already registered")

            self._ea_registry[ea_id] = {
                "magic_number": magic_number,
                "rep_port": rep_port,
                "pub_port": pub_port,
                "host": host,
                "symbol": symbol,
                "registered_at": datetime.utcnow(),
                **kwargs
            }

    def unregister_ea(self, ea_id: str) -> None:
        """
        Unregister EA and release its resources.

        Args:
            ea_id: EA identifier to unregister
        """
        with self._lock:
            if ea_id in self._ea_registry:
                ea_info = self._ea_registry[ea_id]

                # Release resources
                self.deallocate_magic_number(ea_info["magic_number"])
                self.deallocate_ports(ea_info["rep_port"], ea_info["pub_port"])

                # Remove from registry
                del self._ea_registry[ea_id]

    def get_ea_info(self, ea_id: str) -> Optional[Dict]:
        """
        Get EA information.

        Args:
            ea_id: EA identifier

        Returns:
            EA info dictionary or None if not found
        """
        with self._lock:
            return self._ea_registry.get(ea_id)

    def get_all_eas(self) -> Dict[str, Dict]:
        """
        Get all registered EAs.

        Returns:
            Dictionary of ea_id -> ea_info
        """
        with self._lock:
            return dict(self._ea_registry)

    def get_ea_count(self) -> int:
        """
        Get count of registered EAs.

        Returns:
            Number of registered EAs
        """
        with self._lock:
            return len(self._ea_registry)

    def get_ea_by_magic_number(self, magic_number: int) -> Optional[str]:
        """
        Find EA ID by magic number.

        Args:
            magic_number: Magic number to search for

        Returns:
            EA ID or None if not found
        """
        with self._lock:
            for ea_id, ea_info in self._ea_registry.items():
                if ea_info["magic_number"] == magic_number:
                    return ea_id
            return None

    # =========================================================================
    # Health Monitoring (T068)
    # =========================================================================

    def update_ea_health(
        self,
        ea_id: str,
        last_heartbeat: Optional[datetime] = None,
        status: str = "ACTIVE",
        **health_data
    ) -> None:
        """
        Update EA health status and heartbeat (T068).

        Args:
            ea_id: EA identifier
            last_heartbeat: Last heartbeat timestamp (default: now)
            status: Health status (ACTIVE, STALE, ERROR)
            **health_data: Additional health metrics (e.g., last_tick_time, error_count)
        """
        with self._lock:
            if ea_id not in self._ea_registry:
                return

            # Update health fields
            self._ea_registry[ea_id]["last_heartbeat"] = last_heartbeat or datetime.utcnow()
            self._ea_registry[ea_id]["health_status"] = status
            self._ea_registry[ea_id].update(health_data)

    def get_ea_health(self, ea_id: str) -> Optional[Dict]:
        """
        Get EA health status (T068).

        Args:
            ea_id: EA identifier

        Returns:
            Dictionary with health info or None if EA not found
        """
        with self._lock:
            if ea_id not in self._ea_registry:
                return None

            ea_info = self._ea_registry[ea_id]
            last_heartbeat = ea_info.get("last_heartbeat")

            if last_heartbeat:
                seconds_since_heartbeat = (datetime.utcnow() - last_heartbeat).total_seconds()
                is_healthy = seconds_since_heartbeat < 60  # 60 second threshold
            else:
                seconds_since_heartbeat = None
                is_healthy = False

            return {
                "ea_id": ea_id,
                "magic_number": ea_info["magic_number"],
                "health_status": ea_info.get("health_status", "UNKNOWN"),
                "last_heartbeat": last_heartbeat,
                "seconds_since_heartbeat": seconds_since_heartbeat,
                "is_healthy": is_healthy
            }

    def get_all_ea_health(self) -> Dict[str, Dict]:
        """
        Get health status for all registered EAs (T068).

        Returns:
            Dictionary of ea_id -> health_info
        """
        with self._lock:
            health_status = {}
            for ea_id in self._ea_registry.keys():
                # Release lock temporarily for get_ea_health call
                pass

        # Call get_ea_health without holding lock
        for ea_id in list(self._ea_registry.keys()):
            health_info = self.get_ea_health(ea_id)
            if health_info:
                health_status[ea_id] = health_info

        return health_status
