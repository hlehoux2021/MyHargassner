"""
This module defines MqttBase, a base class for controlling MqttActuator and MqttInformer.
"""

# Standard library imports
import logging

# Third party imports
from ha_mqtt_discoverable import Settings, DeviceInfo  # type: ignore

# Project imports
from appconfig import AppConfig
import hargconfig

class MqttBase():
    """
    common base class for MqttInformer and MqttActuator
    """
    config: hargconfig.HargConfig
    mqtt_settings: Settings.MQTT
    _device_info: DeviceInfo
    _appconfig: AppConfig

    def __init__(self, appconfig: AppConfig):
        """
        Initialize the MqttBase class.
        Sets up the configuration and MQTT settings with default values.
        Initializes device info as None.
        """
        self.config = hargconfig.HargConfig()
        self._appconfig = appconfig

        self.mqtt_settings = Settings.MQTT(
            host=self._appconfig.mqtt_host(),
            username=self._appconfig.mqtt_username(),
            password=self._appconfig.mqtt_password())

    @staticmethod
    def attach_paho_logger(sensor):
        """
        Attach a logger to the Paho MQTT client for debugging.
        """
        client = getattr(sensor, 'mqtt_client', None)
        if client is not None:
            def on_log(client, userdata, level, buf): # pylint: disable=unused-argument
                logging.debug("PAHO: %s",buf)
            client.on_log = on_log
            # Optionally, integrate with Python logging
            try:
                client.enable_logger()
            except Exception: # pylint: disable=broad-except
                pass

    def name(self) -> str:
        """
        Get the class name of the instance.

        Returns:
            str: The name of the class.
        """
        return self.__class__.__name__

    def init_device_info(self, _name: str) -> None:
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
    def device_info(self) -> DeviceInfo:
        """
        Get the device information.

        Returns:
            DeviceInfo: The device information object.
        """
        return self._device_info
