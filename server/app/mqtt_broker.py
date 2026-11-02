import asyncio
import logging
import socket
import threading
from typing import Optional

logger = logging.getLogger("dcems.broker")

_broker_thread: Optional[threading.Thread] = None
_broker_instance = None
_broker_loop: Optional[asyncio.AbstractEventLoop] = None

def is_port_in_use(port: int = 1883, host: str = "127.0.0.1") -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.5)
        return s.connect_ex((host, port)) == 0

def _run_broker_loop(loop: asyncio.AbstractEventLoop, config: dict):
    asyncio.set_event_loop(loop)
    from amqtt.broker import Broker

    global _broker_instance
    _broker_instance = Broker(config, loop=loop)

    async def _start():
        await _broker_instance.start()
        logger.info("Embedded MQTT Broker successfully listening on 0.0.0.0:1883")
        while True:
            await asyncio.sleep(3600)

    try:
        loop.run_until_complete(_start())
    except Exception as e:
        logger.info(f"Embedded MQTT Broker event loop terminated: {e}")

def start_embedded_broker(port: int = 1883) -> bool:
    """
    Starts an in-process asyncio MQTT broker on port 1883 if no external
    broker (like standalone Mosquitto) is currently running.
    """
    global _broker_thread, _broker_loop

    if is_port_in_use(port):
        logger.info(f"Port {port} is already in use by an external MQTT broker. Skipping embedded broker.")
        return False

    config = {
        "listeners": {
            "default": {
                "type": "tcp",
                "bind": f"0.0.0.0:{port}",
                "max_connections": 100,
            }
        },
        "sys_interval": 20,
        "auth": {
            "allow_anonymous": True,
            "plugins": ["auth_anonymous"],
        },
    }

    _broker_loop = asyncio.new_event_loop()
    _broker_thread = threading.Thread(
        target=_run_broker_loop,
        args=(_broker_loop, config),
        name="DCEMS-EmbeddedBroker",
        daemon=True,
    )
    _broker_thread.start()
    return True

def stop_embedded_broker():
    global _broker_instance, _broker_loop
    if _broker_instance and _broker_loop:
        try:
            future = asyncio.run_coroutine_threadsafe(_broker_instance.shutdown(), _broker_loop)
            future.result(timeout=2.0)
        except Exception:
            pass
        _broker_instance = None
