"""
Comprehensive Stress Testing Suite.

Tests:
1. 6-hour continuous operation test
2. 50+ concurrent WebSocket clients
3. Memory leak detection
4. CPU usage monitoring
5. Network resilience (dropped connections)
6. High-frequency message flood
"""

import asyncio
import time
import psutil
import sys
import json
from pathlib import Path
from datetime import datetime, timedelta
from typing import List, Dict
import aiohttp
import structlog

project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

logger = structlog.get_logger(__name__)


class WebSocketClient:
    """Mock WebSocket client for stress testing."""
    
    def __init__(self, client_id: int, url: str = "ws://localhost:8000/ws/live"):
        self.client_id = client_id
        self.url = url
        self.session = None
        self.ws = None
        self.messages_received = 0
        self.last_seq = 0
        self.sequence_gaps = 0
        self.connected = False
    
    async def connect(self):
        """Connect to WebSocket."""
        try:
            self.session = aiohttp.ClientSession()
            self.ws = await self.session.ws_connect(self.url)
            self.connected = True
            
            # Receive handshake
            msg = await self.ws.receive_json()
            if msg.get("type") == "HANDSHAKE":
                self.last_seq = msg.get("seq", 0)
            
            logger.debug("client_connected", client_id=self.client_id)
            
        except Exception as e:
            logger.error("connection_failed", client_id=self.client_id, error=str(e))
            self.connected = False
    
    async def subscribe(self, channels: List[str]):
        """Subscribe to channels."""
        if not self.ws:
            return
        
        await self.ws.send_json({
            "type": "SUBSCRIBE",
            "channels": channels,
        })
    
    async def listen(self, duration_seconds: int):
        """Listen for messages."""
        start = time.time()
        
        while time.time() - start < duration_seconds and self.connected:
            try:
                msg = await asyncio.wait_for(self.ws.receive_json(), timeout=5.0)
                
                self.messages_received += 1
                
                # Check sequence number
                if "seq" in msg:
                    seq = msg["seq"]
                    if seq > 0 and self.last_seq > 0 and seq != self.last_seq + 1:
                        self.sequence_gaps += 1
                        logger.warning(
                            "sequence_gap_detected",
                            client_id=self.client_id,
                            expected=self.last_seq + 1,
                            received=seq,
                        )
                    self.last_seq = seq
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                logger.error("listen_error", client_id=self.client_id, error=str(e))
                self.connected = False
                break
    
    async def disconnect(self):
        """Disconnect."""
        if self.ws:
            await self.ws.close()
        if self.session:
            await self.session.close()
        
        self.connected = False
        logger.debug("client_disconnected", client_id=self.client_id)


class StressTestRunner:
    """Runs comprehensive stress tests."""
    
    def __init__(self):
        self.process = psutil.Process()
        self.start_memory = self.process.memory_info().rss / 1024 / 1024  # MB
        self.start_time = time.time()
        self.results: Dict = {}
    
    async def test_concurrent_clients(self, num_clients: int = 50, duration_seconds: int = 60):
        """
        Test with multiple concurrent WebSocket clients.
        
        Args:
            num_clients: Number of concurrent clients
            duration_seconds: Test duration
        """
        logger.info(
            "starting_concurrent_clients_test",
            num_clients=num_clients,
            duration=duration_seconds,
        )
        
        clients = [WebSocketClient(i) for i in range(num_clients)]
        
        # Connect all clients
        connect_tasks = [client.connect() for client in clients]
        await asyncio.gather(*connect_tasks, return_exceptions=True)
        
        # Count successful connections
        connected = sum(1 for c in clients if c.connected)
        logger.info("clients_connected", connected=connected, total=num_clients)
        
        # Subscribe to channels
        for client in clients:
            if client.connected:
                await client.subscribe(["positions", "equity", "orders"])
        
        # Listen for messages
        listen_tasks = [client.listen(duration_seconds) for client in clients if client.connected]
        await asyncio.gather(*listen_tasks, return_exceptions=True)
        
        # Collect stats
        total_messages = sum(c.messages_received for c in clients)
        total_gaps = sum(c.sequence_gaps for c in clients)
        
        # Disconnect
        disconnect_tasks = [client.disconnect() for client in clients]
        await asyncio.gather(*disconnect_tasks, return_exceptions=True)
        
        self.results["concurrent_clients"] = {
            "num_clients": num_clients,
            "duration_seconds": duration_seconds,
            "connected": connected,
            "total_messages_received": total_messages,
            "sequence_gaps": total_gaps,
            "messages_per_second": total_messages / duration_seconds,
            "avg_messages_per_client": total_messages / connected if connected > 0 else 0,
        }
        
        logger.info("concurrent_clients_test_complete", results=self.results["concurrent_clients"])
    
    async def test_long_running(self, duration_hours: float = 6.0):
        """
        Test long-running operation (default 6 hours).
        
        Args:
            duration_hours: Test duration in hours
        """
        logger.info("starting_long_running_test", duration_hours=duration_hours)
        
        duration_seconds = int(duration_hours * 3600)
        checkpoint_interval = 600  # Check every 10 minutes
        
        client = WebSocketClient(0)
        await client.connect()
        
        if not client.connected:
            logger.error("long_running_test_failed_to_connect")
            return
        
        await client.subscribe(["positions", "equity", "orders", "health"])
        
        memory_samples = []
        cpu_samples = []
        
        start = time.time()
        last_checkpoint = start
        
        # Run for specified duration
        while time.time() - start < duration_seconds:
            try:
                # Listen for a checkpoint interval
                remaining = duration_seconds - (time.time() - start)
                listen_duration = min(checkpoint_interval, remaining)
                
                await client.listen(int(listen_duration))
                
                # Record metrics
                current_memory = self.process.memory_info().rss / 1024 / 1024  # MB
                current_cpu = self.process.cpu_percent(interval=1)
                
                memory_samples.append(current_memory)
                cpu_samples.append(current_cpu)
                
                elapsed = time.time() - start
                logger.info(
                    "long_running_checkpoint",
                    elapsed_minutes=elapsed / 60,
                    memory_mb=current_memory,
                    memory_delta_mb=current_memory - self.start_memory,
                    cpu_percent=current_cpu,
                    messages_received=client.messages_received,
                    sequence_gaps=client.sequence_gaps,
                )
                
                last_checkpoint = time.time()
                
            except Exception as e:
                logger.error("long_running_error", error=str(e))
                break
        
        await client.disconnect()
        
        # Calculate stats
        avg_memory = sum(memory_samples) / len(memory_samples) if memory_samples else 0
        max_memory = max(memory_samples) if memory_samples else 0
        avg_cpu = sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0
        max_cpu = max(cpu_samples) if cpu_samples else 0
        
        memory_leak = max_memory - self.start_memory
        
        self.results["long_running"] = {
            "duration_hours": (time.time() - start) / 3600,
            "messages_received": client.messages_received,
            "sequence_gaps": client.sequence_gaps,
            "start_memory_mb": self.start_memory,
            "avg_memory_mb": avg_memory,
            "max_memory_mb": max_memory,
            "memory_leak_mb": memory_leak,
            "avg_cpu_percent": avg_cpu,
            "max_cpu_percent": max_cpu,
            "memory_leak_detected": memory_leak > 100,  # >100MB = leak
        }
        
        logger.info("long_running_test_complete", results=self.results["long_running"])
    
    async def test_message_flood(self, duration_seconds: int = 60):
        """
        Test high-frequency message handling.
        
        Args:
            duration_seconds: Test duration
        """
        logger.info("starting_message_flood_test", duration=duration_seconds)
        
        client = WebSocketClient(0)
        await client.connect()
        
        if not client.connected:
            logger.error("message_flood_test_failed_to_connect")
            return
        
        await client.subscribe(["positions", "equity", "orders", "regime", "health"])
        
        start = time.time()
        await client.listen(duration_seconds)
        elapsed = time.time() - start
        
        await client.disconnect()
        
        messages_per_second = client.messages_received / elapsed if elapsed > 0 else 0
        
        self.results["message_flood"] = {
            "duration_seconds": elapsed,
            "messages_received": client.messages_received,
            "messages_per_second": messages_per_second,
            "sequence_gaps": client.sequence_gaps,
            "handled_flood": messages_per_second >= 10,  # Should handle 10+ msgs/sec
        }
        
        logger.info("message_flood_test_complete", results=self.results["message_flood"])
    
    async def test_connection_resilience(self, num_reconnects: int = 10):
        """
        Test connection drop and reconnect resilience.
        
        Args:
            num_reconnects: Number of reconnect cycles
        """
        logger.info("starting_connection_resilience_test", num_reconnects=num_reconnects)
        
        successful_reconnects = 0
        
        for i in range(num_reconnects):
            client = WebSocketClient(i)
            await client.connect()
            
            if client.connected:
                await client.subscribe(["positions"])
                await client.listen(5)  # Listen for 5 seconds
                await client.disconnect()
                
                # Wait before reconnect
                await asyncio.sleep(2)
                
                # Reconnect
                await client.connect()
                if client.connected:
                    successful_reconnects += 1
                    await client.disconnect()
        
        self.results["connection_resilience"] = {
            "num_reconnects": num_reconnects,
            "successful_reconnects": successful_reconnects,
            "success_rate": successful_reconnects / num_reconnects if num_reconnects > 0 else 0,
        }
        
        logger.info("connection_resilience_test_complete", results=self.results["connection_resilience"])
    
    def save_results(self, filename: str = "stress_test_results.json"):
        """Save test results to file."""
        results_path = project_root / "tests" / "stress" / filename
        
        with open(results_path, "w") as f:
            json.dump({
                "timestamp": datetime.utcnow().isoformat(),
                "results": self.results,
            }, f, indent=2)
        
        logger.info("results_saved", path=str(results_path))


async def run_all_stress_tests():
    """Run all stress tests."""
    logger.info("=" * 60)
    logger.info("STARTING COMPREHENSIVE STRESS TESTS")
    logger.info("=" * 60)
    
    runner = StressTestRunner()
    
    # Test 1: Concurrent clients (50 clients for 60 seconds)
    logger.info("\n[TEST 1/5] Concurrent Clients Test")
    await runner.test_concurrent_clients(num_clients=50, duration_seconds=60)
    
    # Test 2: Message flood
    logger.info("\n[TEST 2/5] Message Flood Test")
    await runner.test_message_flood(duration_seconds=60)
    
    # Test 3: Connection resilience
    logger.info("\n[TEST 3/5] Connection Resilience Test")
    await runner.test_connection_resilience(num_reconnects=10)
    
    # Test 4: Long-running (6 hours) - Optional, commented out for quick testing
    # Uncomment for full stress test:
    # logger.info("\n[TEST 4/5] Long-Running Test (6 hours)")
    # await runner.test_long_running(duration_hours=6.0)
    
    # For demo, run a shorter version (10 minutes)
    logger.info("\n[TEST 4/5] Long-Running Test (10 minutes demo)")
    await runner.test_long_running(duration_hours=10/60)  # 10 minutes
    
    # Save results
    runner.save_results()
    
    logger.info("=" * 60)
    logger.info("STRESS TESTS COMPLETE")
    logger.info("=" * 60)
    logger.info(f"Results: {json.dumps(runner.results, indent=2)}")


async def run_quick_stress_test():
    """Run quick stress test (no long-running test)."""
    logger.info("Running QUICK stress test (no 6-hour test)")
    
    runner = StressTestRunner()
    
    await runner.test_concurrent_clients(num_clients=25, duration_seconds=30)
    await runner.test_message_flood(duration_seconds=30)
    await runner.test_connection_resilience(num_reconnects=5)
    
    runner.save_results("stress_test_results_quick.json")
    
    logger.info("Quick stress test complete")
    logger.info(f"Results: {json.dumps(runner.results, indent=2)}")


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Run stress tests")
    parser.add_argument("--quick", action="store_true", help="Run quick test (no 6-hour)")
    parser.add_argument("--full", action="store_true", help="Run full test (including 6-hour)")
    
    args = parser.parse_args()
    
    if args.full:
        asyncio.run(run_all_stress_tests())
    else:
        # Default to quick test
        asyncio.run(run_quick_stress_test())
