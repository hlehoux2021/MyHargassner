#!/usr/bin/env python3

import socket
import time
import logging
import platform

src_iface=b'wlan0'
dst_iface=b'wlan0'
UDP_PORT= 35601
dst_port=0
dst_addr=b''

LOG_PATH = "./" #chemin où enregistrer les logs
SOCKET_TIMEOUT= 0.2

#----------------------------------------------------------#
#        definition des logs                               #
#----------------------------------------------------------#
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('log')
logger.setLevel(logging.DEBUG) # choisir le niveau de log : DEBUG, INFO, ERROR...

handler_debug = logging.FileHandler(LOG_PATH + "boiler.log", mode="a", encoding="utf-8")
handler_debug.setFormatter(formatter)
handler_debug.setLevel(logging.DEBUG)
logger.addHandler(handler_debug)

#----------------------------------------------------------#

listen= socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)  # UDP
listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
listen.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
if platform.system() == 'Linux':
	listen.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, src_iface)
	listen.bind( ('',UDP_PORT) )
else:
	#on Darwin, for simulation
	listen.bind( ('',UDP_PORT+1) )

resend= socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
resend.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
resend.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
if platform.system() == 'Linux':
	resend.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, dst_iface)
resend.settimeout(SOCKET_TIMEOUT)

bound= False
while True:
	data, addr = listen.recvfrom(1024)
	logger.debug('received buffer of %d bytes from %s : %d ==>%s', len(data), addr[0], addr[1], data.decode())
	dst_port= addr[1]
	dst_addr= addr[0]
	if bound == False:
		resend.bind( ('',dst_port) );
		logger.debug('sender bound to %s :  %d', dst_iface.decode(), dst_port)
		bound = True

	if bound == True:
		_str = data.decode()
		if _str.startswith('get services'):
			logger.info('received get services request')
			resend.sendto(b'00024853562f434c20392d36304b57205631342e306e33000000000000000000485356310000000000000000000000000000001700507061722e6367690000000000000000000000000000000000000000000000646171646573632e636769000000000000000000000000000000000000000000646171646174612e636769000000000000000000000000000000000000000000746f6b656e2e63676900000000000000000000000000000000000000000000006576656e74732f717569742e63676900000000000000000000000000000000006576656e74732f636c6561722e636769000000000000000000000000000000006576656e74732f6c6973742e63676900000000000000000000000000000000007472796b65792e6367690000000000000000000000000000000000000000000034464242423730430000', (dst_addr, dst_port) )
		else:
			resend.sendto(data, (dst_addr, dst_port) )
		logger.info('resent %d bytes to %s : %d', len(data),  dst_addr, dst_port)
		#temporarily use broadcast
		#resend.sendto(data, ('<broadcast>', dst_port) )
		#logger.info('resent %d bytes to <broadcast> : %d', len(data), dst_port)
