"""Unit tests for Stage D: GPU Inference Gateway, Request Queue, and Fair-Scheduler."""

import asyncio
import uuid
import pytest

from app.services.llm.gateway import InferenceGateway, GPUOverloadError
from app.services.llm.base import LLMStructuredResponse


@pytest.mark.asyncio
async def test_gateway_concurrency_and_metrics():
    """Verify that the gateway limits concurrency and tracks latency metrics."""
    gw = InferenceGateway(
        max_concurrent=2,
        max_queue_size=5,
        queue_timeout_seconds=2.0,
        request_timeout_seconds=2.0,
    )
    t_id = uuid.uuid4()

    def dummy_fallback(parse_raw=None):
        return LLMStructuredResponse(status="ANSWERED", answer="Mock answer", evidence_ids=[], claims=[])

    # Run 2 requests concurrently
    tasks = [
        gw.execute_inference(tenant_id=t_id, payload={"prompt": "test 1"}, fallback_fn=dummy_fallback),
        gw.execute_inference(tenant_id=t_id, payload={"prompt": "test 2"}, fallback_fn=dummy_fallback),
    ]
    results = await asyncio.gather(*tasks)
    assert len(results) == 2
    assert all(r.status == "ANSWERED" for r in results)

    status = gw.get_status_summary()
    assert status["gateway_status"] == "ONLINE"
    assert status["total_requests"] == 2
    assert status["completed_requests"] == 2
    assert status["active_requests"] == 0
    assert status["rejected_requests"] == 0
    assert "hardware" in status


@pytest.mark.asyncio
async def test_gateway_queue_saturation_rejection():
    """Verify that requests exceeding queue depth are rejected with GPUOverloadError."""
    # Set queue size to 0 so any queued request beyond semaphore is rejected immediately
    gw = InferenceGateway(
        max_concurrent=1,
        max_queue_size=0,
        queue_timeout_seconds=0.1,
    )
    t1 = uuid.uuid4()
    t2 = uuid.uuid4()

    gate_event = asyncio.Event()

    def blocking_fallback(parse_raw=None):
        return LLMStructuredResponse(status="ANSWERED", answer="Blocked answer", evidence_ids=[], claims=[])

    # Mock execute_inference slow run
    async def slow_inference(t_id):
        async with gw._lock:
            gw.metrics.total_requests += 1
            gw.metrics.queued_requests += 1

        await gw._semaphore.acquire()
        try:
            async with gw._lock:
                gw.metrics.queued_requests -= 1
                gw.metrics.active_requests += 1
            await gate_event.wait()
            return blocking_fallback()
        finally:
            async with gw._lock:
                gw.metrics.active_requests -= 1
            gw._semaphore.release()

    task1 = asyncio.create_task(slow_inference(t1))
    await asyncio.sleep(0.05)

    # Second request should immediately trigger queue saturation since max_queue_size=0
    with pytest.raises(GPUOverloadError) as exc_info:
        await gw.execute_inference(
            tenant_id=t2,
            payload={"prompt": "overflow"},
            fallback_fn=blocking_fallback,
        )
    assert "queue saturated" in str(exc_info.value).lower()

    # Release task 1
    gate_event.set()
    await task1


@pytest.mark.asyncio
async def test_gateway_fair_scheduling_tenant_ceiling():
    """Verify that one tenant cannot exceed their assigned concurrent slot ceiling."""
    gw = InferenceGateway(
        max_concurrent=4,
        max_queue_size=10,
        max_tenant_concurrent=1,  # Only 1 slot per tenant allowed
    )
    t_alpha = uuid.uuid4()

    def dummy_fallback(parse_raw=None):
        return LLMStructuredResponse(status="ANSWERED", answer="Mock", evidence_ids=[], claims=[])

    # Simulate tenant alpha having 1 in-flight request
    gw._tenant_inflight[str(t_alpha)] = 1

    # Second request from tenant alpha should be rejected for fair-scheduling violation
    with pytest.raises(GPUOverloadError) as exc_info:
        await gw.execute_inference(
            tenant_id=t_alpha,
            payload={"prompt": "second request"},
            fallback_fn=dummy_fallback,
        )
    assert "exceeded concurrent inference slot limit" in str(exc_info.value).lower()


def test_gateway_hardware_stats():
    """Verify GPU hardware stats query returns structured diagnostics."""
    gw = InferenceGateway()
    stats = gw.get_gpu_hardware_stats()
    assert "device_type" in stats
    assert "gpu_name" in stats
    assert "vram_total_mib" in stats
    assert "status" in stats

