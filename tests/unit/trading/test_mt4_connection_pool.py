"""
Unit tests for MT4ConnectionPool (T059-T060 - User Story 5).

Tests magic number allocation, port allocation, and EA registry management.
"""
import pytest
from unittest.mock import AsyncMock, Mock, patch
from datetime import datetime

from src.trading.execution.mt4_connection_pool import MT4ConnectionPool


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def connection_pool():
    """Create MT4ConnectionPool instance."""
    return MT4ConnectionPool(
        base_magic_number=100000,
        base_rep_port=5555,
        base_pub_port=5556
    )


# =============================================================================
# Magic Number Allocation Tests (T059)
# =============================================================================

def test_allocate_magic_number_first_allocation(connection_pool):
    """Test allocating first magic number."""
    magic_number = connection_pool.allocate_magic_number()

    assert magic_number == 100000
    assert magic_number in connection_pool._allocated_magic_numbers


def test_allocate_magic_number_sequential(connection_pool):
    """Test sequential magic number allocation."""
    magic1 = connection_pool.allocate_magic_number()
    magic2 = connection_pool.allocate_magic_number()
    magic3 = connection_pool.allocate_magic_number()

    assert magic1 == 100000
    assert magic2 == 100001
    assert magic3 == 100002


def test_allocate_magic_number_within_range(connection_pool):
    """Test magic numbers stay within valid range (100000-999999)."""
    for _ in range(100):
        magic = connection_pool.allocate_magic_number()
        assert 100000 <= magic <= 999999


def test_allocate_magic_number_skips_used(connection_pool):
    """Test allocation skips already used magic numbers."""
    # Manually mark some as used
    connection_pool._allocated_magic_numbers.add(100000)
    connection_pool._allocated_magic_numbers.add(100001)

    magic = connection_pool.allocate_magic_number()
    assert magic == 100002


def test_allocate_magic_number_exhaustion(connection_pool):
    """Test behavior when magic number range is exhausted."""
    # Fill up the range (simulate near-exhaustion)
    for i in range(100000, 100010):
        connection_pool._allocated_magic_numbers.add(i)

    # Should still find available number
    magic = connection_pool.allocate_magic_number()
    assert magic == 100010


def test_deallocate_magic_number(connection_pool):
    """Test deallocating magic number for reuse."""
    magic = connection_pool.allocate_magic_number()

    connection_pool.deallocate_magic_number(magic)

    assert magic not in connection_pool._allocated_magic_numbers


def test_deallocate_magic_number_allows_reuse(connection_pool):
    """Test deallocated magic numbers can be reallocated."""
    magic1 = connection_pool.allocate_magic_number()  # 100000
    magic2 = connection_pool.allocate_magic_number()  # 100001

    connection_pool.deallocate_magic_number(magic1)

    # Next allocation should reuse 100000
    magic3 = connection_pool.allocate_magic_number()
    assert magic3 == 100000


def test_is_magic_number_allocated(connection_pool):
    """Test checking if magic number is allocated."""
    magic = connection_pool.allocate_magic_number()

    assert connection_pool.is_magic_number_allocated(magic)
    assert not connection_pool.is_magic_number_allocated(999999)


# =============================================================================
# Port Allocation Tests (T060)
# =============================================================================

def test_allocate_ports_first_allocation(connection_pool):
    """Test allocating first port pair."""
    rep_port, pub_port = connection_pool.allocate_ports()

    assert rep_port == 5555
    assert pub_port == 5556


def test_allocate_ports_sequential(connection_pool):
    """Test sequential port allocation."""
    rep1, pub1 = connection_pool.allocate_ports()
    rep2, pub2 = connection_pool.allocate_ports()
    rep3, pub3 = connection_pool.allocate_ports()

    # Ports should increment by 2 (REP and PUB use consecutive ports)
    assert rep1 == 5555
    assert pub1 == 5556
    assert rep2 == 5557
    assert pub2 == 5558
    assert rep3 == 5559
    assert pub3 == 5560


def test_allocate_ports_no_conflicts(connection_pool):
    """Test allocated ports don't conflict."""
    ports = []
    for _ in range(10):
        rep, pub = connection_pool.allocate_ports()
        ports.extend([rep, pub])

    # All ports should be unique
    assert len(ports) == len(set(ports))


def test_allocate_ports_within_valid_range(connection_pool):
    """Test ports stay within valid range (1024-65535)."""
    for _ in range(20):
        rep, pub = connection_pool.allocate_ports()
        assert 1024 <= rep <= 65535
        assert 1024 <= pub <= 65535


def test_deallocate_ports(connection_pool):
    """Test deallocating port pair."""
    rep, pub = connection_pool.allocate_ports()

    connection_pool.deallocate_ports(rep, pub)

    assert rep not in connection_pool._allocated_rep_ports
    assert pub not in connection_pool._allocated_pub_ports


def test_deallocate_ports_allows_reuse(connection_pool):
    """Test deallocated ports can be reallocated."""
    rep1, pub1 = connection_pool.allocate_ports()
    rep2, pub2 = connection_pool.allocate_ports()

    connection_pool.deallocate_ports(rep1, pub1)

    # Next allocation should reuse first ports
    rep3, pub3 = connection_pool.allocate_ports()
    assert rep3 == rep1
    assert pub3 == pub1


def test_are_ports_allocated(connection_pool):
    """Test checking if ports are allocated."""
    rep, pub = connection_pool.allocate_ports()

    assert connection_pool.are_ports_allocated(rep, pub)
    assert not connection_pool.are_ports_allocated(9999, 10000)


# =============================================================================
# EA Registry Tests
# =============================================================================

def test_register_ea(connection_pool):
    """Test registering new EA."""
    ea_id = "ea_test_001"
    magic = connection_pool.allocate_magic_number()
    rep, pub = connection_pool.allocate_ports()

    connection_pool.register_ea(
        ea_id=ea_id,
        magic_number=magic,
        rep_port=rep,
        pub_port=pub,
        host="localhost",
        symbol="CrudeOIL"
    )

    assert ea_id in connection_pool._ea_registry
    ea_info = connection_pool._ea_registry[ea_id]
    assert ea_info["magic_number"] == magic
    assert ea_info["rep_port"] == rep
    assert ea_info["pub_port"] == pub


def test_register_ea_duplicate_raises_error(connection_pool):
    """Test registering duplicate EA ID raises error."""
    ea_id = "ea_test_001"
    connection_pool.register_ea(
        ea_id=ea_id,
        magic_number=100000,
        rep_port=5555,
        pub_port=5556,
        host="localhost",
        symbol="CrudeOIL"
    )

    with pytest.raises(ValueError, match="already registered"):
        connection_pool.register_ea(
            ea_id=ea_id,
            magic_number=100001,
            rep_port=5557,
            pub_port=5558,
            host="localhost",
            symbol="EURUSD"
        )


def test_unregister_ea(connection_pool):
    """Test unregistering EA."""
    ea_id = "ea_test_001"
    magic = 100000
    connection_pool.register_ea(
        ea_id=ea_id,
        magic_number=magic,
        rep_port=5555,
        pub_port=5556,
        host="localhost",
        symbol="CrudeOIL"
    )

    connection_pool.unregister_ea(ea_id)

    assert ea_id not in connection_pool._ea_registry
    assert magic not in connection_pool._allocated_magic_numbers


def test_get_ea_info(connection_pool):
    """Test retrieving EA information."""
    ea_id = "ea_test_001"
    connection_pool.register_ea(
        ea_id=ea_id,
        magic_number=100000,
        rep_port=5555,
        pub_port=5556,
        host="localhost",
        symbol="CrudeOIL"
    )

    ea_info = connection_pool.get_ea_info(ea_id)

    assert ea_info is not None
    assert ea_info["magic_number"] == 100000
    assert ea_info["symbol"] == "CrudeOIL"


def test_get_ea_info_not_found(connection_pool):
    """Test retrieving non-existent EA returns None."""
    ea_info = connection_pool.get_ea_info("non_existent")
    assert ea_info is None


def test_get_all_eas(connection_pool):
    """Test retrieving all registered EAs."""
    connection_pool.register_ea("ea_1", 100000, 5555, 5556, "localhost", "CrudeOIL")
    connection_pool.register_ea("ea_2", 100001, 5557, 5558, "localhost", "EURUSD")
    connection_pool.register_ea("ea_3", 100002, 5559, 5560, "localhost", "GBPUSD")

    all_eas = connection_pool.get_all_eas()

    assert len(all_eas) == 3
    assert "ea_1" in all_eas
    assert "ea_2" in all_eas
    assert "ea_3" in all_eas


def test_get_ea_count(connection_pool):
    """Test counting registered EAs."""
    assert connection_pool.get_ea_count() == 0

    connection_pool.register_ea("ea_1", 100000, 5555, 5556, "localhost", "CrudeOIL")
    assert connection_pool.get_ea_count() == 1

    connection_pool.register_ea("ea_2", 100001, 5557, 5558, "localhost", "EURUSD")
    assert connection_pool.get_ea_count() == 2
