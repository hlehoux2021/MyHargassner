"""
This module defines MqttBase, a base class for controlling MqttActuator and MqttInformer.
"""

# Standard library imports
import logging

# Third party imports
from ha_mqtt_discoverable import Settings, DeviceInfo  # type: ignore

# Project imports
import hargconfig
import shared

class MqttBase():
    """
    common base class for MqttInformer and MqttActuator
    """
    config: hargconfig.HargConfig
    mqtt_settings: Settings.MQTT
    _device_info: DeviceInfo

    def __init__(self):
        """
        Initialize the MqttBase class.
        Sets up the configuration and MQTT settings with default values.
        Initializes device info as None.
        """
        self.config = hargconfig.HargConfig()
        #TODO remove password from code.
        self.mqtt_settings = Settings.MQTT(
            host=shared.MQTT_HOST,
            username=shared.MQTT_USERNAME,
            password=shared.MQTT_PASSWORD)

    @staticmethod
    def attach_paho_logger(sensor):
        """
        Attach a logger to the Paho MQTT client for debugging.
        """
        client = getattr(sensor, 'mqtt_client', None)
        if client is not None:
            def on_log(client, userdata, level, buf):
                logging.debug(f"PAHO: {buf}")
            client.on_log = on_log
            # Optionally, integrate with Python logging
            try:
                client.enable_logger()
            except Exception:
                pass

    def name(self) -> str:
        """
        Get the class name of the instance.

        Returns:
            str: The name of the class.
        """
        return self.__class__.__name__

    def _create_device_info(self, _name: str) -> None:
        """
        Create device information for MQTT discovery.

        Args:
            _name (str): The name to use for the device.
        """
        lstr = list()
        lstr.append(_name)
        self._device_info = DeviceInfo(
                            name=_name,
                            manufacturer="Hargassner",
                            sw_version="1.0",
                            hw_version="1.0",
                            identifiers=lstr)
