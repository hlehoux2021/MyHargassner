"""
Module for MQTT client to handle to boiler
"""

import typing
import logging
from queue import Queue,Empty
from threading import Thread
from ha_mqtt_discoverable import Settings, DeviceInfo
from ha_mqtt_discoverable.sensors import Sensor, SensorInfo
from ha_mqtt_discoverable.sensors import Button, ButtonInfo
from paho.mqtt.client import Client, MQTTMessage
import hargconfig
from shared import SOCKET_TIMEOUT,BUFF_SIZE
from telnetproxy import TelnetClient

class MqttBase():
    """
    common base class for MqttInformer and MqttActuator
    """
    config: hargconfig.HargConfig
    mqtt_settings: Settings.MQTT
    device_info: DeviceInfo

    def __init__(self):
        self.config= hargconfig.HargConfig()
        #TODO remove password from code. note, this is an experimental dev jeedom without internet access
        self.mqtt_settings= Settings.MQTT(host="192.168.100.8",
                username="jeedom",
                password="rL4jVLF1JTcXUQBXSU1K479WzIBbCrJVtC7ch9sQllBIjZT5C9MJBsFjXfbIfHIH")

class MqttActuator(MqttBase):
    """
    This class implements MQTT Buttons and the corresponding actions
    """
    PORT = 4000
    _client: TelnetClient

    def __init__(self, device_info: DeviceInfo):
        super().__init__()
        self.device_info= device_info
        self._client= TelnetClient()

    # To receive button commands from HA, define a callback function:
    def my_callback(self, client: Client, data, message: MQTTMessage):
        _str: str = str(data)
        logging.info('call back called with %s', _str)
        #TODO find a way to remove langage dependency here
        match _str:
            case 'Arr':
                pass
            case 'Ballon':
                pass
            case 'Auto':
                pass
            case 'Arr combustion':
                pass

    def create_button(self, myid: str, range: int):
        assert self.config is not None
        _button_info= ButtonInfo(name=self.config.buttons[myid],
                                unique_id= myid,
                                device= self.device_info)
        _button_settings= Settings(mqtt= self.mqtt_settings, entity= _button_info)
        _my_button= Button(_button_settings, self.my_callback, myid+':'+str(range))

    def createPR001(self) -> None:
        """
        assumes format is like: $PR001;6;3;4;1;0;0;0;Mode;Manu;Arr;Ballon;Auto;Arr combustion;0;\r\n blablabla\r\n
        """
        _data: bytes = bytes()
        _addr: bytes = bytes()
        self._client.send(b'$par get PR001\r\n')
        _data, _addr = self._client.recvfrom()
        _str_parts = _data.decode('ascii').split('\r\n')
        for _part in _str_parts:
            if _part.startswith('$PR001'):
                _str_values: list[str] = _part.split(';')
                # start after "Mode" parameter
                for i in range(9, len(_str_values)-2):
                    logging.debug('test parse %s:%d', _str_values[i],i-9)
                    if _str_values[i] in self.config.buttons:
                        self.create_button(_str_values[i], i-9)

    def service(self):
        #TODO implemnent and use this telnet service
        self._client.connect('localhost', port=self.PORT)

        #button_info = ButtonInfo(name="My Button", unique_id="my_button", device=self._device_info)
        #button_settings = Settings(mqtt=self.mqtt_settings, entity=button_info)
        #user_data = "Some custom data"
        #my_button = Button(button_settings, self.my_callback, user_data)

        #we will create button for each config available in PR001 from the boiler
        self.createPR001()
        # each time a HA/MQTT Button is clicked, MqttActuator::my_callback() is called
        logging.critical('exiting MqttActuator run()')

EntityType = typing.TypeVar("EntityType", bound= MqttActuator)

class Threaded(typing.Generic[EntityType]):
    """
    this class threads an entity
    """
    _entity: EntityType
    _thread: Thread

    def __init__(self, device: DeviceInfo) -> None:
        #self._entity= EntityType(device)
        self._entity.device_info= device
        self._thread= Thread(target= self._entity.service)

    def start(self) -> None:
        self._thread.start()

class ThreadedMqttActuator(Threaded[MqttActuator]):
    """
    MqttActuator that runs in a Thread
    """
    def void(self) -> None:
        pass

class MySensor(Sensor):
    def __init__(self,_name: str, _id: str, _dict: dict, _config:hargconfig.HargConfig, _device_info: DeviceInfo, _mqtt: Settings.MQTT):
        if _id in _dict:
            _state= _dict[_id]
        else:
            _state= ""
        if _id in _config.wanted:
            _info= SensorInfo(name= _name,
                              state= _state,
                              unique_id= _id+"/"+_dict["BL_ADDR"],
                              unit_of_measurement= _config.desc[_id]['unit'],
                              device=_device_info)
        else:
            _info= SensorInfo(name= _name,
                              state= _state,
                              unique_id= _id+"/"+_dict["BL_ADDR"],
                              device=_device_info)
        _settings= Settings(mqtt=_mqtt, entity= _info)
        super().__init__(_settings)
        if _id in _config.desc:
            self.set_attributes({'description': _config.desc[_id]['desc']})
        
class MqttInformer(MqttBase):
    """
    class MqttInformer provides Boiler information via MQTT

    Name: will be BL_ADDR ip adress of the boiler
    Identifiers:
    - $login key:
    - $SN:
    - $setkomm: mandatory , i choose this as a primary identifiers (Boiler number)

    """
    _info_queue: Queue
    _dict: dict
    _sensors: dict
    _token: Sensor
    _web_app: Sensor
    _key: Sensor
    _kt: Sensor
    #_swv: Sensor = None
    _ma: ThreadedMqttActuator

    def __init__(self):
        super().__init__()
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
        self._web_app = MySensor("HargaWebApp","HargaWebApp", self._dict, self.config, self.device_info, self.mqtt_settings)
        self._token = MySensor("Login Token", "TOKEN", self._dict, self.config, self.device_info, self.mqtt_settings)
        self._key = MySensor("Login Key", "KEY", self._dict, self.config, self.device_info, self.mqtt_settings)
        # sensors coming in normal mode
        #self._kt = self._create_sensor("KT","KT")
        #self._swv = self._create_sensor("Software Version", "SWV")
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
                _str_parts = msg.split('££')
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
 #                       if _str_parts[0] == 'SWV':
 #                           self._swv.set_state(_str_parts[1])
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
                        # we create and launch an actuator in a separate thread
                        _ma= ThreadedMqttActuator(self.device_info)
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
