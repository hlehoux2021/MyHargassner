"""
Module for MQTT client to handle to boiler
"""

import logging
from queue import Queue,Empty
from ha_mqtt_discoverable import Settings, DeviceInfo
from ha_mqtt_discoverable.sensors import Sensor, SensorInfo
import hargconfig

class MqttInformer():
    """
    class MqttInformer provides Boiler information via MQTT

    Name: will be BL_ADDR ip adress of the boiler
    Identifiers:
    - $login key:
    - $SN:
    - $setkomm: mandatory , i choose this as a primary identifiers (Boiler number)

    """
    config: hargconfig.HargConfig = None
    mqtt_settings: Settings.MQTT = None
    device_info: DeviceInfo = None
    _info_queue: Queue = None
    _dict: dict = None
    _sensors: dict = None
    _token: Sensor = None
    _web_app: Sensor = None
    _key: Sensor = None
    _kt: Sensor = None
    _swv: Sensor = None

    def __init__(self):
        self.config= hargconfig.HargConfig()
        self.mqtt_settings= Settings.MQTT(host="192.168.100.8",
                username="jeedom",
                password="rL4jVLF1JTcXUQBXSU1K479WzIBbCrJVtC7ch9sQllBIjZT5C9MJBsFjXfbIfHIH")
        self._info_queue= Queue()
        self._dict = {}
        self._sensors= {}

    def _init_sensors(self):
        """This method init the basis sensors"""
        if 'HargaWebApp' in self._dict:
            logging.debug('HargaWebApp in dict --> set')
            self._web_app.set_state(self._dict['HargaWebApp'])
        if 'TOKEN' in self._dict:
            logging.debug('TOKEN in dict --> set')
            self._token.set_state(self._dict['TOKEN'])
        if 'KEY' in self._dict:
            logging.debug('KEY in dict --> set')
            self._key.set_state(self._dict['KEY'])

    def _create_device_info(self):
        lstr= list()
        lstr.append(self._dict["BL_ADDR"])
        lstr.append(self._dict["SETKOMM"])
        self.device_info = DeviceInfo(
                            name=self._dict['BL_ADDR'],
                            manufacturer="Hargassner",
                            model=self._dict['HSV'],
                            sw_version="1.0",
                            hw_version="1.0",
                           identifiers=lstr)
    def _create_sensor(self, _name: str, _id: str) -> Sensor:
        if _id in self._dict:
            _state= self._dict[_id]
        else:
            _state= ""
        if _id in self.config.wanted:
            _info= SensorInfo(name= _name,
                              state= _state,
                              unique_id= _id+"/"+self._dict["BL_ADDR"],
                              unit_of_measurement= self.config.desc[_id]['unit'],
                              device=self.device_info)
        else:
            _info= SensorInfo(name= _name,
                              state= _state,
                              unique_id= _id+"/"+self._dict["BL_ADDR"],
                              device=self.device_info)
        _settings= Settings(mqtt=self.mqtt_settings, entity= _info)
        _sensor= Sensor(_settings)
        if _id in self.config.desc:
            _sensor.set_attributes({'description': self.config.desc[_id]['desc']})
        return _sensor

    def _create_all_sensors(self):
        # create basis mandatory sensors
        # sensors before normal mode
        self._web_app = self._create_sensor("HargaWebApp","HargaWebApp")
        self._token = self._create_sensor("Login Token", "TOKEN")
        self._key = self._create_sensor("Login Key", "KEY")
        # sensors coming in normal mode
        self._kt = self._create_sensor("KT","KT")
        self._swv = self._create_sensor("Software Version", "SWV")
        # sensors wanted from the pm buffer
        for _part in self.config.wanted:
            _sensor= self._create_sensor(self.config.desc[_part]['name'],_part)
            _sensor.set_state("")
            self._sensors[_part]= _sensor

    def start(self):
        """This method runs the MqttInformer, waiting for message on _info_queue"""
        _stage: str = ''
        while True:
            try:
                msg = self._info_queue.get(block=True, timeout=10)
                _str_parts = msg.split(':')
                if _stage == 'device_info_ok':
                    # we are in normal mode, we handle new or modified values
                    logging.debug('normal mode analyse message')
                    if ((_str_parts[0] in self._dict) and (_str_parts[1] != self._dict[_str_parts[0]])) or (not _str_parts[0] in self._dict):
                        # the value is new or has changed
                        logging.debug('new value:[%s/%s]', _str_parts[0], _str_parts[1])
                        self._dict[_str_parts[0]] = _str_parts[1]
                        if _str_parts[0] == 'HargaWebApp':
                            self._web_app.set_state(_str_parts[1])
                        if _str_parts[0] == 'KT':
                            self._kt.set_state(_str_parts[1])
                        if _str_parts[0] == 'SWV':
                            self._swv.set_state(_str_parts[1])
                        # treat sensors from telnet pm buffer
                        if _str_parts[0] in self.config.wanted and _str_parts[0] in self._sensors:
                            logging.info('updating state of sensor:%s',_str_parts[0])
                            self._sensors[_str_parts[0]].set_state(_str_parts[1])
                    else:
                        logging.debug('ignored [%s/%s]', _str_parts[0], _str_parts[1])
                else:
                    # device_info is not yes init
                    logging.debug("device_info not ready")
                    self._dict[_str_parts[0]] = _str_parts[1]
                    logging.debug('MqttInformer added %s:%s to dict', _str_parts[0], _str_parts[1])
                    if 'BL_ADDR' in self._dict:
                        logging.debug("BL_ADDR:%s",self._dict["BL_ADDR"])
                    else:
                        logging.debug("BL_ADDR missing")
                    if 'SETKOMM' in self._dict:
                        logging.debug("SETKOMM:%s", self._dict["SETKOMM"])
                    else:
                        logging.debug("SETKOMM missing")
                    if 'HSV' in self._dict:
                        logging.debug("HSV:%s", self._dict['HSV'])
                    else:
                        logging.debug("HSV missing")

                    if ('BL_ADDR' in self._dict) and ('SETKOMM' in self._dict) and ('HSV' in self._dict):
                        # we have all the info to init device_info
                        logging.debug('MqttInformer device_info_ok')
                        # Define the device. At least one of `identifiers` or `connections` must be supplied
                        self._create_device_info()
                        logging.debug("Device Info initialized")
                        self._create_all_sensors()
                        _stage = 'device_info_ok'
                        # now we init the already available sensors
                        self._init_sensors()
            except Empty:
                logging.debug("Queue is empty")
            logging.debug('MqttInformer stage is now %s', _stage)

    def queue(self) -> Queue:
        """
        This method returns the queue to receive data from.
        """
        return self._info_queue
