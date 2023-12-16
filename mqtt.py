"""
Module for MQTT client to handle to boiler
"""

import logging
from queue import Queue,Empty

from ha_mqtt_discoverable import Settings, DeviceInfo
from ha_mqtt_discoverable.sensors import Text, TextInfo

class MqttInformer():
    """
    class MqttInformer provides Boiler information via MQTT

    Name: will be BL_ADDR ip adress of the boiler
    Identifiers:
    - $login key:
    - $SN:
    - $setkomm: mandatory , i choose this as a primary identifiers (Boiler number)

    """

    mqtt_settings: Settings.MQTT = None
    device_info: DeviceInfo = None
    _info_queue: Queue = None
    _dict: dict = None
    _web_app: Text = None
    _login_key: Text = None

    def __init__(self, queue: Queue):
        self.mqtt_settings= Settings.MQTT(host="192.168.100.8",
                                                 username="jeedom",
                                                 password="0y96wXQJ0E8KHjEyLdacPq95RGQEOdjpCLDskj7LWWC9EihjCJXbZOFZ9m4KCMWu")
        self._info_queue= queue
        self._dict = {}
        self._web_app = Text(Settings(mqtt=self.mqtt_settings,
                                      entity=TextInfo(name="HargaWebApp", state="0")),
                             lambda *_: None)
        self._kt = Text(Settings(mqtt=self.mqtt_settings,
                                      entity=TextInfo(name="KT", state="0")),
                             lambda *_: None)

    def start(self):
        """This method runs the MqttInformer, waiting for message on _info_queue"""
        _stage: str = ''
        while True:
            try:
                msg = self._info_queue.get(block=True, timeout=5)
                _str_parts = msg.split(':')
                self._dict[_str_parts[0]] = _str_parts[1]
                logging.debug('MqttInformer added %s:%s to dict', _str_parts[0], _str_parts[1])
                if _str_parts[0] == 'BL_ADDR':
                    _stage = 'name_ok'
                if _str_parts[0] == '$setkomm':
                    _stage = 'id_ok'
            except Empty:
                logging.debug("Queue is empty")
            if _stage == 'id_ok':
                # Define the device. At least one of `identifiers` or `connections` must be supplied
                lstr= list()
                if '$slogin key' in self._dict:
                    lstr.append(self._dict["$slogin key"])
                if '$SN' in self._dict:
                    lstr.append(self._dict["$SN"])
                if '$setkomm' in self._dict:
                    lstr.append(self._dict["$setkomm"])
                self.device_info = DeviceInfo(name=self._dict['BL_ADDR'],
                                              identifiers=lstr)
                _stage = 'device_info_ok'
                # we need to init first value of sensors
                if '$KT' in self._dict:
                    logging.debug('$KT in dict --> set_text')
                    self._kt.set_text(self._dict['$KT'])

            if _stage == 'device_info_ok':
                if ((_str_parts[0] in self._dict) and (_str_parts[1] != self._dict[_str_parts[0]])) or (not _str_parts[0] in self._dict):
                    # the value is new or has changed
                    logging.debug('new value:[%s/%s]', _str_parts[0], _str_parts[1])
                    self._dict[_str_parts[0]] = _str_parts[1]
                    if _str_parts[0] == 'HargaWebApp':
                        self._web_app.set_text(_str_parts[1])
                    if _str_parts[0] == '$KT':
                        self._kt.set_text(_str_parts[1])
                else:
                    logging.debug('ignored [%s/%s]', _str_parts[0], _str_parts[1])
                    logging.debug('in dict:%s', (_str_parts[0] in self._dict) )


            logging.debug('MqttInformer stage is now %s', _stage)
