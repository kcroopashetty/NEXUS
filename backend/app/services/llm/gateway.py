"""Centralized GPU Inference Gateway, Queue Manager, and Fair-Scheduler."""

import asyncio
import logging
import subprocess
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Any, List, Optional
import httpx

from app.core.config import settings
from app.core.errors import NexusException
from app.services.llm.base import LLMStructuredResponse

logger = logging.getLogger("nexus.inference_gateway")


class GPUOverloadError(NexusException):
    """Raised when GPU inference queue is saturated or wait exceeds SLA."""

    def __init__(self, message: str = "GPU inference service is currently at maximum capacity. Please retry shortly."):
        super().__init__(message=message, code="GPU_OVERLOADED", status_code=503)


@dataclass
class GatewayMetrics:
    """Real-time operational metrics for GPU inference and scheduling."""

    total_requests: int = 0
    completed_requests: int = 0
    failed_requests: int = 0
    rejected_requests: int = 0
    active_requests: int = 0
    queued_requests: int = 0
    total_tokens_generated: int = 0
    avg_latency_ms: float = 0.0
    avg_queue_wait_ms: float = 0.0
    last_request_at: Optional[str] = None


class InferenceGateway:
    """
    Centralized GPU resource manager, request admission controller, and fair-scheduler.
    
    Guarantees:
    1. Bounded concurrency (prevents GPU VRAM OOM on hardware).
    2. Bounded queue with timeouts (prevents unbounded queue latency).
    3. Fair scheduling per tenant (prevents one tenant from starving others).
    4. Hardware monitoring (VRAM, utilization, temperature via nvidia-smi with CPU fallback).
    5. Multi-endpoint load balancing readiness for multi-GPU server pools.
    """

    def __init__(
        self,
        max_concurrent: int = 2,
        max_queue_size: int = 16,
        queue_timeout_seconds: float = 15.0,
        request_timeout_seconds: float = 45.0,
        max_tenant_concurrent: int = 2,
        endpoints: Optional[List[str]] = None,
    ):
        self.max_concurrent = max_concurrent
        self.max_queue_size = max_queue_size
        self.queue_timeout_seconds = queue_timeout_seconds
        self.request_timeout_seconds = request_timeout_seconds
        self.max_tenant_concurrent = max_tenant_concurrent

        # Multi-GPU endpoint readiness
        self.endpoints = endpoints or [settings.OLLAMA_BASE_URL.rstrip("/")]
        self._endpoint_index = 0

        # Concurrency & Tenant Quota State
        self._semaphore = asyncio.Semaphore(self.max_concurrent)
        self._tenant_inflight: Dict[str, int] = {}
        self._lock = asyncio.Lock()

        # Operational metrics
        self.metrics = GatewayMetrics()
        self._latency_samples: List[float] = []
        self._queue_wait_samples: List[float] = []

    def get_gpu_hardware_stats(self) -> Dict[str, Any]:
        """Query host GPU utilization and VRAM statistics via nvidia-smi with graceful fallback."""
        try:
            cmd = [
                "nvidia-smi",
                "--query-gpu=name,memory.total,memory.used,memory.free,utilization.gpu,temperature.gpu",
                "--format=csv,noheader,nounits",
            ]
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=2.0)
            if res.returncode == 0 and res.stdout.strip():
                parts = [p.strip() for p in res.stdout.strip().split(",")]
                if len(parts) >= 6:
                    return {
                        "device_type": "NVIDIA_GPU",
                        "gpu_name": parts[0],
                        "vram_total_mib": float(parts[1]),
                        "vram_used_mib": float(parts[2]),
                        "vram_free_mib": float(parts[3]),
                        "gpu_utilization_pct": float(parts[4]),
                        "temperature_celsius": float(parts[5]),
                        "status": "HEALTHY",
                    }
        except Exception:
            pass

        return {
            "device_type": "CPU_OR_UNAVAILABLE",
            "gpu_name": "Host Processor (Deterministic / CPU Fallback)",
            "vram_total_mib": 0.0,
            "vram_used_mib": 0.0,
            "vram_free_mib": 0.0,
            "gpu_utilization_pct": 0.0,
            "temperature_celsius": 0.0,
            "status": "FALLBACK_READY",
        }

    def _select_endpoint(self) -> str:
        """Round-robin endpoint selector for multi-GPU distribution."""
        ep = self.endpoints[self._endpoint_index % len(self.endpoints)]
        self._endpoint_index += 1
        return ep

    async def execute_inference(
        self,
        tenant_id: uuid.UUID,
        payload: Dict[str, Any],
        fallback_fn,
    ) -> LLMStructuredResponse:
        """
        Execute request under fair-scheduling admission control with queue timeouts.
        """
        tenant_key = str(tenant_id)
        queue_start = time.perf_counter()

        # 1. Admission Check & Queue Bounding
        async with self._lock:
            if self.metrics.queued_requests >= self.max_queue_size:
                self.metrics.rejected_requests += 1
                logger.warning("InferenceGateway queue saturated (%d in queue). Rejecting request.", self.metrics.queued_requests)
                raise GPUOverloadError(
                    f"GPU inference queue saturated ({self.metrics.queued_requests} pending). Please retry shortly."
                )

            # Fair scheduling: Check tenant in-flight ceiling
            active_for_tenant = self._tenant_inflight.get(tenant_key, 0)
            if active_for_tenant >= self.max_tenant_concurrent:
                self.metrics.rejected_requests += 1
                logger.warning("Tenant %s exceeded concurrent GPU slot ceiling (%d).", tenant_key, self.max_tenant_concurrent)
                raise GPUOverloadError(
                    f"Workspace exceeded concurrent inference slot limit ({self.max_tenant_concurrent} active). Please wait for prior queries to complete."
                )

            self.metrics.total_requests += 1
            self.metrics.queued_requests += 1

        # 2. Acquire Concurrency Slot with Queue Timeout
        slot_acquired = False
        try:
            await asyncio.wait_for(
                self._semaphore.acquire(),
                timeout=self.queue_timeout_seconds,
            )
            slot_acquired = True
        except asyncio.TimeoutError:
            async with self._lock:
                self.metrics.queued_requests = max(0, self.metrics.queued_requests - 1)
                self.metrics.rejected_requests += 1
            logger.warning("Inference request queued for tenant %s timed out waiting for GPU slot.", tenant_key)
            raise GPUOverloadError("Inference request timed out in queue waiting for GPU resources.")

        # 3. Request Execution
        queue_wait_ms = (time.perf_counter() - queue_start) * 1000
        exec_start = time.perf_counter()

        async with self._lock:
            self.metrics.queued_requests = max(0, self.metrics.queued_requests - 1)
            self.metrics.active_requests += 1
            self._tenant_inflight[tenant_key] = self._tenant_inflight.get(tenant_key, 0) + 1

        try:
            target_endpoint = self._select_endpoint()

            # Attempt Ollama call asynchronously with timeout
            async with httpx.AsyncClient(timeout=float(self.request_timeout_seconds)) as client:
                resp = await client.post(
                    f"{target_endpoint}/api/chat",
                    json=payload,
                )
                if resp.status_code == 200:
                    data = resp.json()
                    raw_reply = data.get("message", {}).get("content", "").strip()
                    parsed = fallback_fn(parse_raw=raw_reply)
                    if parsed:
                        self.metrics.completed_requests += 1
                        return parsed

            # If Ollama returns non-200 or unparseable, use deterministic fallback
            res = fallback_fn()
            self.metrics.completed_requests += 1
            return res

        except Exception as exc:
            logger.warning("Inference execution through Ollama failed (%s). Using deterministic fallback.", exc)
            res = fallback_fn()
            self.metrics.completed_requests += 1
            return res

        finally:
            exec_duration_ms = (time.perf_counter() - exec_start) * 1000
            async with self._lock:
                self.metrics.active_requests = max(0, self.metrics.active_requests - 1)
                self._tenant_inflight[tenant_key] = max(0, self._tenant_inflight.get(tenant_key, 1) - 1)
                self._latency_samples.append(exec_duration_ms)
                self._queue_wait_samples.append(queue_wait_ms)
                if len(self._latency_samples) > 100:
                    self._latency_samples.pop(0)
                    self._queue_wait_samples.pop(0)
                self.metrics.avg_latency_ms = round(sum(self._latency_samples) / len(self._latency_samples), 1)
                self.metrics.avg_queue_wait_ms = round(sum(self._queue_wait_samples) / len(self._queue_wait_samples), 1)
                self.metrics.last_request_at = datetime.now(timezone.utc).isoformat()

            if slot_acquired:
                self._semaphore.release()

    def get_status_summary(self) -> Dict[str, Any]:
        """Aggregate gateway metrics and GPU hardware state."""
        return {
            "gateway_status": "ONLINE",
            "concurrency_limit": self.max_concurrent,
            "max_queue_size": self.max_queue_size,
            "queue_timeout_seconds": self.queue_timeout_seconds,
            "active_requests": self.metrics.active_requests,
            "queued_requests": self.metrics.queued_requests,
            "total_requests": self.metrics.total_requests,
            "completed_requests": self.metrics.completed_requests,
            "rejected_requests": self.metrics.rejected_requests,
            "avg_latency_ms": self.metrics.avg_latency_ms,
            "avg_queue_wait_ms": self.metrics.avg_queue_wait_ms,
            "last_request_at": self.metrics.last_request_at,
            "hardware": self.get_gpu_hardware_stats(),
        }


# Singleton gateway instance
inference_gateway = InferenceGateway()

