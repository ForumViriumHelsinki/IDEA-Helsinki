"""Example usage of the health check module.

This file demonstrates how services can integrate the health check module
for both synchronous and asynchronous services.
"""

import asyncio
import time
from pathlib import Path

from idea_shared.health.checks import (
    ExternalAPIHealthCheck,
    FileSystemHealthCheck,
    HealthCheck,
    HealthCheckResult,
)
from idea_shared.health.server import HealthServer


# Custom health check implementation for InfluxDB
class InfluxDBHealthCheck(HealthCheck):
    """Example InfluxDB health check."""

    def __init__(self, connection_string: str):
        super().__init__(
            name="influxdb",
            timeout=5.0,
            critical=True,
            cache_ttl=5.0,  # Cache for 5 seconds
        )
        self.connection_string = connection_string

    async def check(self) -> HealthCheckResult:
        """Check InfluxDB connectivity."""
        # This is a simplified example - real implementation would use influxdb-client
        try:
            # Simulate checking InfluxDB connection
            # In real implementation:
            # from influxdb_client import InfluxDBClient
            # client = InfluxDBClient(url=self.connection_string, ...)
            # result = client.ping()

            # For example purposes, we'll simulate success
            await asyncio.sleep(0.1)  # Simulate network call

            return HealthCheckResult(
                name=self.name,
                status="healthy",
                message="InfluxDB is responsive",
                metadata={"version": "2.7.0", "uptime_seconds": 3600},
            )

        except Exception as e:
            return HealthCheckResult(
                name=self.name,
                status="unhealthy",
                message=f"InfluxDB connection failed: {str(e)}",
            )


# Example 1: Synchronous service (e.g., fcd-manager, traffic-monitor)
def example_sync_service():
    """Example of using health checks in a synchronous service."""
    print("Starting synchronous service with health checks...")

    # Create health server
    health_server = HealthServer(
        port=8080,
        app_name="FCD Manager Service",
        enable_metrics=True,  # Enable Prometheus metrics endpoint
    )

    # Add health checks
    health_server.add_check(
        "influxdb",
        InfluxDBHealthCheck("http://localhost:8086"),
    )

    health_server.add_check(
        "data_directory",
        FileSystemHealthCheck(
            name="data_directory",
            path="/tmp/fcd_data",  # Example data directory
            check_write=True,
            critical=True,
        ),
    )

    health_server.add_check(
        "azure_storage",
        ExternalAPIHealthCheck(
            name="azure_storage",
            url="https://youraccount.blob.core.windows.net/?comp=properties",
            expected_status=200,
            critical=False,  # Non-critical - service can work with cached data
            cache_ttl=30.0,  # Cache for 30 seconds
        ),
    )

    # Start health server in background thread
    health_server.start_background()

    try:
        # Main service loop
        while True:
            print("Processing FCD data...")
            time.sleep(5)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Stop health server
        health_server.stop()


# Example 2: Asynchronous service (e.g., idea-helsinki)
async def example_async_service():
    """Example of using health checks in an asynchronous service."""
    print("Starting asynchronous service with health checks...")

    # Create health server
    health_server = HealthServer(
        port=8080,
        app_name="IDEA Helsinki Service",
    )

    # Add multiple database checks for different InfluxDB buckets
    health_server.add_check(
        "influxdb_fcd",
        InfluxDBHealthCheck("http://localhost:8086/fcd_bucket"),
    )

    health_server.add_check(
        "influxdb_validation",
        InfluxDBHealthCheck("http://localhost:8086/validation_bucket"),
    )

    health_server.add_check(
        "segments_file",
        FileSystemHealthCheck(
            name="segments_file",
            path="data/segments_mapping.json",
            check_write=False,  # Only need read access
            critical=True,
        ),
    )

    # Start health server asynchronously
    health_task = asyncio.create_task(health_server.start_async())

    try:
        # Main async service loop
        while True:
            print("Running IDEA validation...")
            await asyncio.sleep(5)

    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        # Stop health server
        await health_server.stop_async()
        health_task.cancel()
        try:
            await health_task
        except asyncio.CancelledError:
            pass


# Example 3: Using context managers
def example_with_context_manager():
    """Example using context manager for automatic cleanup."""
    print("Using health server with context manager...")

    # Synchronous context manager
    with HealthServer(port=8080, app_name="Context Manager Example") as server:
        server.add_check(
            "test_check",
            FileSystemHealthCheck(name="temp", path="/tmp"),
        )

        # Service runs here
        print("Health server is running...")
        time.sleep(10)

    print("Health server automatically stopped")


async def example_with_async_context_manager():
    """Example using async context manager."""
    print("Using async health server with context manager...")

    # Asynchronous context manager
    async with HealthServer(port=8080, app_name="Async Context Example") as server:
        server.add_check(
            "test_check",
            FileSystemHealthCheck(name="temp", path="/tmp"),
        )

        # Service runs here
        print("Async health server is running...")
        await asyncio.sleep(10)

    print("Async health server automatically stopped")


# Example 4: Dynamic health check management
class ServiceWithDynamicChecks:
    """Example of dynamically adding/removing health checks."""

    def __init__(self):
        self.health_server = HealthServer(
            port=8080,
            app_name="Dynamic Health Check Service",
        )
        self.health_server.start_background()

    def connect_to_database(self, db_name: str, connection_string: str):
        """Add health check when connecting to a database."""
        print(f"Connecting to {db_name}...")
        self.health_server.add_check(
            f"database_{db_name}",
            InfluxDBHealthCheck(connection_string),
        )

    def disconnect_from_database(self, db_name: str):
        """Remove health check when disconnecting from a database."""
        print(f"Disconnecting from {db_name}...")
        self.health_server.remove_check(f"database_{db_name}")

    def run(self):
        """Run the service."""
        # Initially connect to one database
        self.connect_to_database("main", "http://localhost:8086")

        try:
            # Simulate adding more connections over time
            time.sleep(5)
            self.connect_to_database("analytics", "http://localhost:8087")

            time.sleep(5)
            self.disconnect_from_database("main")

            # Keep running
            while True:
                time.sleep(1)

        except KeyboardInterrupt:
            print("\nShutting down...")
        finally:
            self.health_server.stop()


if __name__ == "__main__":
    import sys

    # Create /tmp/fcd_data directory for the example
    Path("/tmp/fcd_data").mkdir(exist_ok=True)

    if len(sys.argv) > 1 and sys.argv[1] == "async":
        # Run async example
        asyncio.run(example_async_service())
    elif len(sys.argv) > 1 and sys.argv[1] == "context":
        # Run context manager example
        example_with_context_manager()
    elif len(sys.argv) > 1 and sys.argv[1] == "async_context":
        # Run async context manager example
        asyncio.run(example_with_async_context_manager())
    elif len(sys.argv) > 1 and sys.argv[1] == "dynamic":
        # Run dynamic checks example
        service = ServiceWithDynamicChecks()
        service.run()
    else:
        # Run sync example by default
        example_sync_service()