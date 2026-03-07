"""Health check server implementation using FastAPI."""

import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from datetime import UTC, datetime

import uvicorn
from fastapi import FastAPI, Response
from fastapi.responses import JSONResponse

from .checks import HealthCheck
from .models import LivenessResponse, MetricsResponse, ReadinessResponse

logger = logging.getLogger(__name__)


class HealthServer:
    """Health check server for Kubernetes probes."""

    def __init__(
        self,
        port: int = 8080,
        host: str = "0.0.0.0",
        app_name: str = "Service Health Check",
        enable_metrics: bool = False,
        liveness_status_code: int = 200,
        readiness_success_code: int = 200,
        readiness_failure_code: int = 503,
        startup_success_code: int = 200,
        startup_failure_code: int = 503,
    ):
        """Initialize health server.

        Args:
            port: Port to listen on (must be 1-65535)
            host: Host to bind to
            app_name: Name of the application
            enable_metrics: Whether to enable metrics endpoint
            liveness_status_code: HTTP status code for successful liveness probe
            readiness_success_code: HTTP status code for successful readiness probe
            readiness_failure_code: HTTP status code for failed readiness probe
            startup_success_code: HTTP status code for successful startup probe
            startup_failure_code: HTTP status code for failed startup probe

        Raises:
            ValueError: If port is not in valid range (1-65535)
        """
        if not 1 <= port <= 65535:
            raise ValueError(f"Port must be between 1 and 65535, got {port}")
        self.port = port
        self.host = host
        self.app_name = app_name
        self.enable_metrics = enable_metrics
        self.liveness_status_code = liveness_status_code
        self.readiness_success_code = readiness_success_code
        self.readiness_failure_code = readiness_failure_code
        self.startup_success_code = startup_success_code
        self.startup_failure_code = startup_failure_code
        self._health_checks: dict[str, HealthCheck] = {}
        self._startup_checks: dict[str, HealthCheck] = {}
        self._server: uvicorn.Server | None = None
        self._thread: threading.Thread | None = None
        self._shutdown_event = threading.Event()
        self._app: FastAPI | None = None
        self._startup_complete = False
        self._setup_app()

    def _setup_app(self):
        """Set up the FastAPI application."""

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            # Startup
            logger.info(f"Starting health check server for {self.app_name}")
            yield
            # Shutdown
            logger.info(f"Shutting down health check server for {self.app_name}")

        self._app = FastAPI(
            title=f"{self.app_name} Health Check",
            lifespan=lifespan,
        )

        # Liveness probe endpoint
        @self._app.get("/healthz", response_model=LivenessResponse)
        async def liveness(response: Response):
            """Liveness probe endpoint.

            Returns configured status code if the service is alive.
            """
            response.status_code = self.liveness_status_code
            return LivenessResponse()

        # Readiness probe endpoint
        @self._app.get("/ready", response_model=ReadinessResponse)
        async def readiness(response: Response):
            """Readiness probe endpoint.

            Returns 200 if all critical checks pass, 503 otherwise.
            """
            checks = {}
            all_ready = True

            # Perform all health checks
            for name, check in self._health_checks.items():
                try:
                    result = await check.check_with_cache()
                    checks[name] = result.status
                    if check.critical and result.status == "unhealthy":
                        all_ready = False
                except Exception as e:
                    logger.error(f"Health check {name} failed with error: {e}")
                    checks[name] = "unhealthy"
                    if check.critical:
                        all_ready = False

            # Set response status code
            if all_ready:
                response.status_code = self.readiness_success_code
            else:
                response.status_code = self.readiness_failure_code

            return ReadinessResponse(
                ready=all_ready,
                checks=checks,
                timestamp=datetime.now(UTC),
            )

        # Startup probe endpoint
        @self._app.get("/startup", response_model=ReadinessResponse)
        async def startup(response: Response):
            """Startup probe endpoint for Kubernetes 1.16+.

            Returns configured success code when startup checks pass.
            """
            checks = {}
            all_ready = True

            # Check if we have startup checks defined
            checks_to_run = (
                self._startup_checks if self._startup_checks else self._health_checks
            )

            # Perform all startup checks
            for name, check in checks_to_run.items():
                try:
                    result = await check.check_with_cache()
                    checks[name] = result.status
                    if check.critical and result.status != "healthy":
                        all_ready = False
                except Exception as e:
                    logger.error(f"Startup check {name} failed with error: {e}")
                    checks[name] = "unhealthy"
                    if check.critical:
                        all_ready = False

            # Mark startup as complete if all checks pass
            if all_ready and not self._startup_complete:
                self._startup_complete = True
                logger.info("Startup checks completed successfully")

            # Set response status code
            if all_ready:
                response.status_code = self.startup_success_code
            else:
                response.status_code = self.startup_failure_code

            return ReadinessResponse(
                ready=all_ready,
                checks=checks,
                timestamp=datetime.now(UTC),
            )

        # Optional metrics endpoint
        if self.enable_metrics:

            @self._app.get("/metrics", response_model=MetricsResponse)
            async def metrics():
                """Metrics endpoint for Prometheus (placeholder).

                This is a placeholder for future Prometheus metrics integration.
                """
                # This would be replaced with actual Prometheus client library integration
                return MetricsResponse(
                    metrics={
                        "health_checks_total": len(self._health_checks),
                        "service_name": self.app_name,
                    }
                )

        # Detailed health endpoint for debugging
        @self._app.get("/health/detail")
        async def health_detail():
            """Detailed health check endpoint for debugging."""
            results = {}

            for name, check in self._health_checks.items():
                try:
                    result = await check.check_with_cache()
                    results[name] = {
                        "status": result.status,
                        "message": result.message,
                        "metadata": result.metadata,
                        "critical": check.critical,
                    }
                except Exception as e:
                    results[name] = {
                        "status": "error",
                        "message": str(e),
                        "critical": check.critical,
                    }

            return JSONResponse(
                content={
                    "service": self.app_name,
                    "timestamp": datetime.now(UTC).isoformat(),
                    "checks": results,
                }
            )

    def add_check(
        self, name: str, check: HealthCheck, startup_only: bool = False
    ) -> None:
        """Add a health check.

        Args:
            name: Unique name for the check
            check: HealthCheck instance
            startup_only: If True, only use this check for startup probes
        """
        if startup_only:
            if name in self._startup_checks:
                logger.warning(f"Overwriting existing startup check: {name}")
            self._startup_checks[name] = check
            logger.info(f"Added startup check: {name}")
        else:
            if name in self._health_checks:
                logger.warning(f"Overwriting existing health check: {name}")
            self._health_checks[name] = check
            logger.info(f"Added health check: {name}")

    def remove_check(self, name: str, startup_only: bool = False) -> None:
        """Remove a health check.

        Args:
            name: Name of the check to remove
            startup_only: If True, only remove from startup checks
        """
        if startup_only:
            if name in self._startup_checks:
                del self._startup_checks[name]
                logger.info(f"Removed startup check: {name}")
        else:
            if name in self._health_checks:
                del self._health_checks[name]
                logger.info(f"Removed health check: {name}")

    def start_background(self) -> None:
        """Start the health server in a background thread.

        This method is for synchronous services that need the health server
        to run alongside their main loop.
        """
        if self._thread and self._thread.is_alive():
            logger.warning("Health server is already running")
            return

        def run_server():
            """Run the uvicorn server in a thread."""
            try:
                config = uvicorn.Config(
                    app=self._app,
                    host=self.host,
                    port=self.port,
                    log_level="info",
                    access_log=False,  # Disable access logs for health checks
                )
                self._server = uvicorn.Server(config)

                asyncio.run(self._server.serve())
            except OSError as e:
                if "Address already in use" in str(e) or "bind" in str(e).lower():
                    logger.error(
                        f"Failed to bind to {self.host}:{self.port} - port already in use"
                    )
                else:
                    logger.error(f"Failed to start health server: {e}")
                raise
            except Exception as e:
                logger.error(f"Health server error: {e}")
                raise
            finally:
                self._shutdown_event.set()

        self._thread = threading.Thread(target=run_server, daemon=True)
        self._thread.start()
        logger.info(f"Health server started in background on {self.host}:{self.port}")

    async def start_async(self) -> None:
        """Start the health server asynchronously.

        This method is for async services that can integrate the health server
        into their existing async loop.

        Raises:
            OSError: If the port is already in use or binding fails
        """
        try:
            config = uvicorn.Config(
                app=self._app,
                host=self.host,
                port=self.port,
                log_level="info",
                access_log=False,
            )
            self._server = uvicorn.Server(config)

            logger.info(f"Starting async health server on {self.host}:{self.port}")
            await self._server.serve()
        except OSError as e:
            if "Address already in use" in str(e) or "bind" in str(e).lower():
                logger.error(
                    f"Failed to bind to {self.host}:{self.port} - port already in use"
                )
            else:
                logger.error(f"Failed to start async health server: {e}")
            raise

    def stop(self) -> None:
        """Stop the health server gracefully."""
        logger.info("Stopping health server...")

        if self._server:
            # Signal the server to shutdown
            self._server.should_exit = True

        if self._thread and self._thread.is_alive():
            # Wait for thread to finish
            self._shutdown_event.wait(timeout=5)

        logger.info("Health server stopped")

    async def stop_async(self) -> None:
        """Stop the async health server gracefully."""
        if self._server:
            logger.info("Stopping async health server...")
            self._server.should_exit = True
            # Give the server a moment to shut down gracefully
            await asyncio.sleep(0.1)
            logger.info("Async health server stopped")

    def __enter__(self):
        """Context manager entry."""
        self.start_background()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()

    async def __aenter__(self):
        """Async context manager entry.

        Returns:
            Self for use in async with statements
        """
        asyncio.create_task(self.start_async())
        # Give the server a moment to start
        await asyncio.sleep(0.1)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit.

        Returns:
            None to propagate any exceptions
        """
        await self.stop_async()
