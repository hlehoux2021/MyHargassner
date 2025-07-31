#$par get PR001\r\n
#   $PR001;6;3;4;1;0;0;0;Mode;Manu;Arr;Ballon;Auto;Arr combustion;0;\r\n
import logging
def parse_parameter(param: str, data: str) -> list[str]:
    """
    parse a parameter response from the Boiler
    assumes format is like: $PR001;6;3;4;1;0;0;0;Mode;Manu;Arr;Ballon;Auto;Arr combustion;0;\r\n blablabla\r\n
    param: str like $PR001
    data: str from boiler
    return: list of found parameters
    """
    _result= list()
    _str_parts = data.split('\r\n')
    for _part in _str_parts:
        if _part.startswith(param):
            _str_values: list[str] = None
            _str_values= _part.split(';')
            # start after "Mode" parameter
            for i in range(9, len(_str_values)-2):
                logging.debug('test parse %s', _str_values[i])
                _result.append(_str_values[i])
    return _result

logging.basicConfig(filename='trace.log', level=logging.DEBUG,
                    format='%(asctime)s - %(levelname)s - %(threadName)s - %(message)s',
                    filemode='a')

logging.info('Started')

liste= list()
liste= parse_parameter('$PR001',"$PR001;6;3;4;1;0;0;0;Mode;Manu;Arr;Ballon;Auto;Arr combustion;0;\r\nzPa A: PR011 (Mode) = Arr\r\nz")
