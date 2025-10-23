#!/usr/bin/env python3
"""
Test program for MqttActuator
Reuses the actual MqttActuator class to test the real implementation.
Mocks only the dependencies (telnet client and PubSub communicator).
"""

import logging
import threading
from typing import Optional
import re

# Apply paho-mqtt debugging patch BEFORE importing anything that uses paho
import paho_mqtt_debug_patch
paho_mqtt_debug_patch.apply_patch()

from ha_mqtt_discoverable import DeviceInfo  # type: ignore

from myhargassner.appconfig import AppConfig
from myhargassner.mqtt_actuator import MqttActuator
from myhargassner.pubsub.pubsub import PubSub, ChanelQueue


class MockTelnetClient:
    """Mock telnet client that simulates boiler responses"""

    def __init__(self, src_iface: bytes, dst_addr: bytes, buffer_size: int = 4096, port: int = 4000):
        """Initialize mock telnet client"""
        self.src_iface = src_iface
        self.dst_addr = dst_addr
        self.buffer_size = buffer_size
        self.port = port
        self.connected = False
        self._response_buffer = b''
        logging.info("MockTelnetClient initialized")

    def connect(self) -> None:
        """Simulate connection"""
        self.connected = True
        logging.info("MockTelnetClient connected")

    def send(self, data: bytes) -> None:
        """
        Simulate sending command and prepare mock response

        Args:
            data: Command bytes to send
        """
        command = data.decode('latin1').strip()
        logging.info("MockTelnetClient received command: %s", command)

        # Parse command and generate appropriate response
        # Format: $par set "PARAM_ID;TYPE;VALUE"\r\n
        if command.startswith('$par set'):
            # Extract parameter details
            match = re.search(r'"([^;]+);(\d+);([^"]+)"', command)
            if match:
                param_id = match.group(1)
                param_type = match.group(2)
                value = match.group(3)

                # Generate acknowledgment response
                if param_type == '6':  # Select parameter
                    # Map index to option name - using REAL boiler options
                    options_map = {
                        'PR001': ['Manu', 'Arr', 'Ballon', 'Auto', 'Arr combustion'],
                        'PR011': ['Arr', 'Auto', 'Réduire', 'Confort', '1x Confort', 'Refroid.'],
                        'PR012': ['Arr', 'Auto', 'Réduire', 'Confort', '1x Confort', 'Refroid.'],
                        'PR040': ['Non', 'Oui']
                    }
                    options = options_map.get(param_id, ['Unknown'])
                    try:
                        value_str = options[int(value)]
                    except (ValueError, IndexError):
                        value_str = 'Unknown'

                    response = f'zPa N: {param_id} (Test Mode) = {value_str}\r\n$ack\r\n'

                elif param_type == '3':  # Number parameter
                    response = f'zPa N: {param_id} (Test Param) = {value}\r\n$ack\r\n'

                else:
                    response = '$ack\r\n'

                self._response_buffer = response.encode('latin1')
                logging.info("MockTelnetClient prepared response: %s", response.strip())

    def recv(self, timeout: float = 2.0) -> bytes:
        """
        Simulate receiving data from boiler

        Args:
            timeout: Timeout in seconds (not used in mock)

        Returns:
            Buffered response bytes
        """
        data = self._response_buffer
        self._response_buffer = b''
        return data

    def disconnect(self) -> None:
        """Simulate disconnection"""
        self.connected = False
        logging.info("MockTelnetClient disconnected")


class MockChanelQueue:
    """Mock ChanelQueue that provides boiler configuration"""

    def __init__(self, channel: str):
        """Initialize mock queue"""
        self.channel = channel
        self._config_provided = False
        self.subscriber = "MockSubscriber"
        logging.info("MockChanelQueue created for channel: %s", channel)

    def listen(self, block: bool = True, timeout: Optional[float] = None):
        """
        Mock listen that provides boiler configuration as an iterator (generator)

        Yields:
            Dictionary with 'data' and 'id' keys
        """
        if not self._config_provided:
            self._config_provided = True
            # Return REAL boiler parameter configuration from production logs
            # Format: Multiple parameters separated by $
            # Select parameters MUST start with $PR for proper parsing
            config = (
                # PR001: Mode (5 options)
                "$PR001;6;0;4;3;0;0;0;Mode;Manu;Arr;Ballon;Auto;Arr combustion;0;"
                # PR011: Zone 1 Mode (6 options)
                "$PR011;6;0;5;1;0;0;0;Zone 1 Mode;Arr;Auto;Réduire;Confort;1x Confort;Refroid.;0;"
                # PR012: Zone 2 Mode (6 options)
                "$PR012;6;0;5;1;0;0;0;Zone 2 Mode;Arr;Auto;Réduire;Confort;1x Confort;Refroid.;0;"
                # PR040: Tampon Démarrer chrgt (2 options)
                "$PR040;6;0;1;0;0;0;0;Tampon Démarrer chrgt;Non;Oui;0;"
                # ID 4: Zone 1 Temp. ambiante jour (number: 14-26°C, step 0.5, current 20.0, default 20.0)
                "$4;3;20.000;14.000;26.000;0.500;°C;20.000;0;0;0;Zone 1 Temp. ambiante jour;"
                # ID 5: Zone 1 Température ambiante de réduit (number: 8-24°C, step 0.5, current 18.0, default 16.0)
                "$5;3;18.000;8.000;24.000;0.500;°C;16.000;0;0;0;Zone 1 Température ambiante de réduit;"
            )
            logging.info("MockChanelQueue: providing REAL boiler config (6 parameters)")
            yield {'data': config, 'id': 0}
        # Generator ends here (no more messages)


class MockPubSub(PubSub):
    """Mock PubSub communicator that provides boiler configuration"""

    def __init__(self):
        """Initialize mock PubSub"""
        # Call parent constructor
        super().__init__()
        logging.info("MockPubSub initialized")

    def subscribe(self, channel: str, subscriber: Optional[str] = None) -> ChanelQueue:
        """
        Mock subscribe that returns a mock queue

        Args:
            channel: The channel name
            subscriber: Optional subscriber name

        Returns:
            A mock ChanelQueue
        """
        # Return a mock queue instead of the real one
        mock_queue = MockChanelQueue(channel)
        logging.info("MockPubSub: subscribed to %s", channel)
        return mock_queue  # type: ignore

    def publish(self, channel: str, message: str) -> None:
        """Mock publish (not used in test)"""
        logging.info("MockPubSub: published to %s: %s", channel, message[:100] if len(message) > 100 else message)


class TestMqttActuator:
    """Test wrapper that uses the real MqttActuator with mocked dependencies"""

    def __init__(self, appconfig: AppConfig, device_info: DeviceInfo):
        """
        Initialize the test wrapper

        Args:
            appconfig: Application configuration with MQTT settings
            device_info: Device information for MQTT discovery
        """
        self._appconfig = appconfig
        self._device_info = device_info
        self._service_lock = threading.Lock()

        # Create mock communicator
        self._communicator = MockPubSub()

        # Create the REAL MqttActuator
        self._actuator = MqttActuator(
            appconfig=appconfig,
            communicator=self._communicator,
            device_info=device_info,
            src_iface=b'\x00\x00\x00\x00',  # Mock source interface
            lock=self._service_lock
        )

        # Replace the telnet client with mock
        self._actuator._client = MockTelnetClient(
            src_iface=b'\x00\x00\x00\x00',
            dst_addr=b'',
            buffer_size=appconfig.buff_size(),
            port=4000
        )

        logging.info("TestMqttActuator initialized with REAL MqttActuator")

    def service(self) -> None:
        """Run the REAL MqttActuator service method"""
        try:
            logging.info("Starting REAL MqttActuator service")
            logging.info("This tests the actual implementation, not a duplicate!")

            # Call the REAL service method from MqttActuator
            self._actuator.service()

        except KeyboardInterrupt:
            logging.info("Service interrupted by user")
        except Exception as e:
            logging.error("Error in service loop: %s", e, exc_info=True)
        finally:
            logging.info("Service stopped")


def main():
    """Main entry point"""
    # Setup logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    logging.info("=" * 60)
    logging.info("Test MQTT Actuator - Testing REAL Implementation")
    logging.info("=" * 60)

    # Load configuration
    try:
        appconfig = AppConfig()
        logging.info("Configuration loaded successfully")
        logging.info("MQTT broker: %s:%d", appconfig.mqtt_host(), appconfig.mqtt_port())
    except Exception as e:
        logging.error("Failed to load configuration: %s", e)
        return 1

    # Create device info (mimicking real Hargassner boiler)
    device_info = DeviceInfo(
        identifiers="test_hargassner_001",
        name="Test Hargassner Boiler",
        model="Hargassner Test",
        manufacturer="Hargassner",
        sw_version="1.0.0"
    )

    logging.info("Device created: %s", device_info.name)

    # Create and run the test actuator (uses REAL MqttActuator)
    test_wrapper = TestMqttActuator(appconfig, device_info)
    test_wrapper.service()

    return 0


if __name__ == "__main__":
    exit(main())
