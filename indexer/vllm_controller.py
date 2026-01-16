"""
vLLM Sleep/Wake Controller

Controls vLLM service sleep states to efficiently share GPU memory
between pipeline stages. Uses vLLM's sleep mode API to offload
model weights to CPU RAM (level 1) or disk (level 2).

IMPORTANT: Sleep mode does NOT release GPU memory - it just offloads weights.
For GPU-intensive tasks like Docling OCR, we need to actually STOP containers.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Literal

import httpx

logger = logging.getLogger(__name__)

# Try to import docker, but make it optional
try:
    import docker
    HAS_DOCKER = True
except ImportError:
    HAS_DOCKER = False
    logger.warning("[vLLM] docker package not installed - container stop/start disabled")

ServiceName = Literal["entity", "chat", "embed"]


class VLLMController:
    """Control vLLM service sleep/wake states."""

    # Service name -> endpoint mapping
    # These match the docker-compose service names
    SERVICES: dict[ServiceName, str] = {
        "entity": "http://vllm-llm:8000",      # LFM2-1.2B-Extract
        "chat": "http://vllm-chat:8000",        # Qwen2.5-7B-Instruct
        "embed": "http://vllm-embed:8000",      # BGE-M3
    }

    # Human-readable names for logging
    SERVICE_MODELS: dict[ServiceName, str] = {
        "entity": "LFM2-1.2B-Extract",
        "chat": "Qwen2.5-7B-Instruct",
        "embed": "BGE-M3",
    }

    # Docker container names
    CONTAINER_NAMES: dict[ServiceName, str] = {
        "entity": "vllm-llm",
        "chat": "vllm-chat",
        "embed": "vllm-embed",
    }

    def __init__(self, timeout: float = 30.0):
        """Initialize controller.

        Args:
            timeout: HTTP request timeout in seconds
        """
        self.timeout = timeout
        self._states: dict[ServiceName, str] = {}  # Track known states

    async def sleep(self, service: ServiceName, level: int = 1) -> bool:
        """Put service to sleep.

        Args:
            service: Service name (entity, chat, embed)
            level: Sleep level
                - 1: Offload weights to CPU RAM (fast wake ~0.1-2s)
                - 2: Discard weights (slower wake, minimal RAM)

        Returns:
            True if successful, False otherwise
        """
        url = f"{self.SERVICES[service]}/sleep"
        model = self.SERVICE_MODELS[service]

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url, params={"level": level})
                response.raise_for_status()

            self._states[service] = f"sleeping_L{level}"
            logger.info(f"[vLLM] {model} -> sleep (level {level})")
            return True

        except httpx.HTTPStatusError as e:
            logger.error(f"[vLLM] Failed to sleep {model}: {e.response.status_code}")
            return False
        except httpx.RequestError as e:
            logger.error(f"[vLLM] Connection error sleeping {model}: {e}")
            return False

    async def wake(self, service: ServiceName) -> bool:
        """Wake sleeping service.

        Args:
            service: Service name (entity, chat, embed)

        Returns:
            True if successful, False otherwise
        """
        url = f"{self.SERVICES[service]}/wake_up"
        model = self.SERVICE_MODELS[service]

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                response = await client.post(url)
                response.raise_for_status()

            self._states[service] = "awake"
            logger.info(f"[vLLM] {model} -> awake")
            return True

        except httpx.HTTPStatusError as e:
            logger.error(f"[vLLM] Failed to wake {model}: {e.response.status_code}")
            return False
        except httpx.RequestError as e:
            logger.error(f"[vLLM] Connection error waking {model}: {e}")
            return False

    async def is_healthy(self, service: ServiceName) -> bool:
        """Check if service is responding.

        Args:
            service: Service name

        Returns:
            True if service responds to health check
        """
        url = f"{self.SERVICES[service]}/health"

        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(url)
                return response.status_code == 200
        except httpx.RequestError:
            return False

    async def sleep_all(self, level: int = 1) -> dict[ServiceName, bool]:
        """Sleep all services to free GPU for other tasks (e.g., Docling).

        Args:
            level: Sleep level (1=RAM, 2=disk)

        Returns:
            Dict of service -> success status
        """
        logger.info("[vLLM] Sleeping all services...")
        results = {}

        for service in self.SERVICES:
            results[service] = await self.sleep(service, level)

        return results

    async def wake_all(self) -> dict[ServiceName, bool]:
        """Wake all services.

        Returns:
            Dict of service -> success status
        """
        logger.info("[vLLM] Waking all services...")
        results = {}

        for service in self.SERVICES:
            results[service] = await self.wake(service)

        return results

    async def ensure_only(self, service: ServiceName, sleep_level: int = 1) -> bool:
        """Ensure only the specified service is awake.

        Sleeps all other services and wakes the target service.
        This is the primary method for stage transitions.

        Args:
            service: Service to keep awake
            sleep_level: Level to use when sleeping others

        Returns:
            True if target service is awake
        """
        model = self.SERVICE_MODELS[service]
        logger.info(f"[vLLM] Ensuring only {model} is awake...")

        # Sleep others first to free GPU memory
        for s in self.SERVICES:
            if s != service:
                await self.sleep(s, sleep_level)

        # Wake target service
        return await self.wake(service)

    async def wait_for_services(self, services: list[ServiceName] | None = None,
                                 timeout: float = 120.0) -> bool:
        """Wait for services to become healthy.

        Args:
            services: Services to wait for (default: all)
            timeout: Max wait time in seconds

        Returns:
            True if all services are healthy
        """
        if services is None:
            services = list(self.SERVICES.keys())

        logger.info(f"[vLLM] Waiting for services: {services}")
        start = asyncio.get_event_loop().time()

        while asyncio.get_event_loop().time() - start < timeout:
            all_healthy = True
            for service in services:
                if not await self.is_healthy(service):
                    all_healthy = False
                    break

            if all_healthy:
                logger.info("[vLLM] All services healthy")
                return True

            await asyncio.sleep(2.0)

        logger.error(f"[vLLM] Timeout waiting for services after {timeout}s")
        return False

    def stop_all_containers(self) -> bool:
        """Stop all vLLM containers to fully release GPU memory.

        This is necessary because vLLM sleep mode doesn't release GPU
        memory allocations - it only offloads weights to CPU/disk.

        Returns:
            True if successful
        """
        if not HAS_DOCKER:
            logger.warning("[vLLM] Docker not available, using sleep mode instead")
            asyncio.run(self.sleep_all(level=1))
            return False

        try:
            client = docker.from_env()
            logger.info("[vLLM] Stopping all vLLM containers...")

            for service, container_name in self.CONTAINER_NAMES.items():
                try:
                    container = client.containers.get(container_name)
                    if container.status == "running":
                        container.stop(timeout=10)
                        logger.info(f"[vLLM] Stopped {container_name}")
                except docker.errors.NotFound:
                    logger.warning(f"[vLLM] Container {container_name} not found")
                except Exception as e:
                    logger.error(f"[vLLM] Error stopping {container_name}: {e}")

            # Wait a moment for GPU memory to be released
            time.sleep(2)
            return True

        except Exception as e:
            logger.error(f"[vLLM] Error connecting to Docker: {e}")
            return False

    async def start_container(self, service: ServiceName, wait_healthy: bool = True,
                              timeout: float = 120.0) -> bool:
        """Start a specific vLLM container.

        Args:
            service: Service to start
            wait_healthy: Wait for service to be healthy
            timeout: Max wait time for health check

        Returns:
            True if container started (and healthy if wait_healthy=True)
        """
        if not HAS_DOCKER:
            logger.warning("[vLLM] Docker not available")
            return False

        container_name = self.CONTAINER_NAMES[service]
        model = self.SERVICE_MODELS[service]

        try:
            client = docker.from_env()
            container = client.containers.get(container_name)

            if container.status != "running":
                logger.info(f"[vLLM] Starting {container_name} ({model})...")
                container.start()

            if wait_healthy:
                logger.info(f"[vLLM] Waiting for {model} to be healthy...")
                start_time = time.time()
                while time.time() - start_time < timeout:
                    if await self.is_healthy(service):
                        logger.info(f"[vLLM] {model} is healthy")
                        return True
                    await asyncio.sleep(2)
                logger.error(f"[vLLM] {model} did not become healthy within {timeout}s")
                return False

            return True

        except docker.errors.NotFound:
            logger.error(f"[vLLM] Container {container_name} not found")
            return False
        except Exception as e:
            logger.error(f"[vLLM] Error starting {container_name}: {e}")
            return False

    async def start_only(self, service: ServiceName, timeout: float = 120.0) -> bool:
        """Start only the specified container, keep others stopped.

        This is the preferred method for stage transitions when GPU
        memory is limited and sleep mode doesn't release allocations.

        Args:
            service: Service to start
            timeout: Max wait time for health check

        Returns:
            True if service started and healthy
        """
        if not HAS_DOCKER:
            # Fall back to sleep/wake
            return await self.ensure_only(service)

        # Stop all first
        self.stop_all_containers()

        # Start the needed one
        return await self.start_container(service, wait_healthy=True, timeout=timeout)
