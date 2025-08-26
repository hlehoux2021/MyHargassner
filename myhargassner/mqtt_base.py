"""
This module defines MqttBase, a base class for controlling MqttActuator and MqttInformer.
"""

# Standard library imports
import logging

# Third party imports
from ha_mqtt_discoverable import Settings, DeviceInfo  # type: ignore

# Project imports
from myhargassner.appconfig import AppConfig
import myhargassner.hargconfig as hargconfig

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

    def _update_device_info(self, **kwargs) -> None:
        """
        Update device information while preserving identifiers.
        
        Args:
            **kwargs: Device info fields to update (name, manufacturer, model, sw_version, hw_version)
        """
        # Keep the existing identifiers
        identifiers = self._device_info.identifiers

        # Create new device info with updated fields but same identifiers
        self._device_info = DeviceInfo(
            name=kwargs.get('name', self._device_info.name),
            manufacturer=kwargs.get('manufacturer', self._device_info.manufacturer),
            model=kwargs.get('model', getattr(self._device_info, 'model', None)),
            sw_version=kwargs.get('sw_version', self._device_info.sw_version),
            hw_version=kwargs.get('hw_version', self._device_info.hw_version),
            identifiers=identifiers
        )
