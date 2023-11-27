#!/usr/bin/python
# -*- coding: utf-8 -*-

# 100.84: <broadcast>	50000->35601	HargaWebApp
# 100.84: <broadcast>	50002->50001	hargassner.diagnostics.request
# 100.84: <broadcast>	50000->35601	get services
# 100.13: 100.84	35601->50000	HSV/CL etc *.cgi
# 100.84: 100.13	51975-->23	$login token
# 100.13: 100.84	23-->51975	$3313C1
# 100.13: 100.84	23->51975	F2\r\n
# 100.84: 100.13	51975->23	$login key 137171BD37643C72131D59797D966A730E\r\n
# 100.13: 100.84	23->51975	zclient login (7421)\r\n$ack\r\n

import socket,select, netifaces
import time
import logging
import sys
from threading import Thread, Lock
import signal

#----------------------------------------------------------#
UDP_PORT= 35601 # destination port to which gateway is broadcasting
SRC_IFACE= b"eth0" # network interface connected to the gateway
DST_IFACE= b"eth1" # network interface connected to the boiler
LOG_PATH = "/home/pi/harg/" #chemin où enregistrer les logs
SOCKET_TIMEOUT= 0.2
BUFF_SIZE= 1024

#----------------------------------------------------------#

gw_port = 0 # source port from which gateway is sending
gw_addr= b''
bl_addr= b''

#----------------------------------------------------------#
#        definition des logs                               #
#----------------------------------------------------------#
formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger('log')
logger.setLevel(logging.DEBUG) # choisir le niveau de log : DEBUG, INFO, ERROR...

handler_debug = logging.FileHandler(LOG_PATH + "trace.log", mode="a", encoding="utf-8")
handler_debug.setFormatter(formatter)
handler_debug.setLevel(logging.DEBUG)
logger.addHandler(handler_debug)

def listen_and_resend(lock, src_iface,dst_iface, src_port, mode='gateway'):
	global gw_port # to save the gateway port when discovered
	global gw_addr # to save the gateway ip adress when discovered
	global bl_addr # to save the boiler ip address when discovered

	logger.info('%s listen_and_resend started: %s , %s, %d',mode,src_iface,dst_iface,src_port)
	listen= socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)  # UDP
	listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
	listen.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
	listen.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, src_iface)

	if mode=='gateway':
		listen.bind( ('',src_port) )
		logger.debug('%s listener bound to %s, port %d', mode, src_iface.decode(), src_port)
	else:
		while gw_port == 0:
			logger.debug('mode %s , waiting discovery of gateway source port',mode)
			time.sleep(1)
		logger.debug('%s binding listener to %s:%d',mode,src_iface.decode(), gw_port)
		logger.debug('netifaces: address %s for %s', netifaces.ifaddresses(src_iface)[ni.AF_INET][0]['addr'], src_iface.decode())
		listen.bind( ('10.0.4.1',gw_port) )
		logger.debug('%s listener bound to %s, port %d', mode, src_iface.decode(), gw_port)

	resend= socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
	resend.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
	resend.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
	resend.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, dst_iface) # bind to vlan iface
	resend.settimeout(SOCKET_TIMEOUT)

	bound= False
	while True:
		logger.debug('%s waiting data',mode)
		data, addr = listen.recvfrom(1024)
		logger.info('%s received buffer of %d bytes from %s : %d', mode, len(data), addr[0], addr[1])
		logger.debug('%s', data)
		if bound == False:
			logger.debug('%s first packet, listener not bound yet',mode) 
			# first time we receive a packet, bind from the source port
			lock.acquire()
			if mode=='gateway':
				logger.info('%s discovered  %s:%d',mode,gw_addr,gw_port)
				gw_port= addr[1]
				gw_addr= addr[0]
			else:
				logger.info('%s discovered  %s:%d',mode, addr[0], addr[1])
				bl_addr= addr[0]
			logger.debug('boiler address set to: %s',bl_addr.decode())
			lock.release()

			resend.bind( ('',addr[1]) );
			logger.debug('%s sender bound to port: %d', mode, addr[1])
			bound = True
		# now would resend the packet on destination
		if mode=='gateway':
			#to act as the gateway, we rebroadcast the udp frame
			logger.debug('%s resending %d bytes to %s : %d', mode,len(data), dst_iface.decode(), gw_port)
			resend.sendto(data, ('<broadcast>', src_port) )
			logger.info('%s resent %d bytes to %s : %d', mode, len(data), dst_iface.decode(), src_port)
		else:
			#to act as the boiler, we send directly to the gateway
			logger.debug('%s resending %d bytes to %s : %d', mode,len(data), gw_addr, gw_port)
			resend.sendto(data, (gw_addr, gw_port) )
			logger.info('%s resent %d bytes to %s : %d', mode, len(data),  gw_addr, gw_port)


def telnet_proxy(lock, src_iface, dst_iface, port):
	global gw_addr
	global gwt_port
	global bl_addr

	logger.info('telnet proxy started: %s , %s', src_iface, dst_iface)
	listen= socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	listen.setsockopt(socket.SOL_SOCKET, socket.SO_BINDTODEVICE, src_iface)
	listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
	listen.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

	logger.debug('telnet binding to port %s', port)
	listen.bind( ('', port) )

	logger.debug('telnet listenning')
	listen.listen()

	logger.debug('telnet accepting a connection')
	telnet, addr = listen.accept()
	logger.info('telnet connection from %s:%d accepted', addr[0], addr[1])
	if addr[0] !=  gw_addr:
		logger.error('%s connected to telnet whereas should be the gateway on %s', addr[0], gw_addr)
		logger.error('TO DO: refuse the connection and loop')
	lock.acquire()
	#remember the source port from which gateway is telneting
	gwt_port= addr[1] 
	lock.release()

	#we will now create the socket to resend the telnet request
	resend= socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	resend.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
	resend.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
	resend.settimeout(SOCKET_TIMEOUT)

	logger.info('telnet connecting to %s:%d', bl_addr.decode(), port) 
	resend.connect( (bl_addr,port) )

	socket_list= [telnet, resend]
	while True:
		logger.debug('telnet waiting data')
		read_sockets, write_sockets, error_sockets = select.select(socket_list , [], [])
		for sock in read_sockets:
			if sock==telnet:
				#so we received a request
				data, addr = telnet.recvfrom(BUFF_SIZE)
				logger.info('telnet received  request %d bytes from  %s:%d ==>%s', len(data), addr[0], addr[1], data.decode() )
				#we should resend it
				logger.info('resending %d bytes to %s:%d', len(data), bl_addr.decode(), port)
				resend.send(data)
			if sock==resend:
				#so we received a reply
				data, addr = resend.recvfrom(BUFF_SIZE)
				logger.info('telnet received response %d bytes from  %s:%d ==>%s', len(data), addr[0], addr[1], data.decode() )

				logger.debug('sending %d bytes to %s:%d', len(data), gw_addr.decode(), gwt_port )
				telnet.send(data)
				logger.info('telnet sent back response to client')

logger.info('starting')

# we will create a Lock() to synchronize threads access to shared data
#mind bl_port is defined in UDP_PORT global
lock= Lock()

#listener(SRC_IFACE, DST_IFACE, UDP_PORT)
try:
	#  start a thread to listen to gateway broadcast messages and rebroadcast to boiler vlan
	t1= Thread(target=listen_and_resend,  args=(lock, SRC_IFACE, DST_IFACE, UDP_PORT, 'gateway') )
	t1.start()

# cannot start another thread listening to port 50001 because would overwrite shared global variable gw_port
#	t1b= Thread(target=listen_and_resend,  args=(lock, SRC_IFACE, DST_IFACE, 50001, 'gateway') )
#	t1b.start()

	# start a thread to listen to boiler(vlan/interface) answers
	t2= Thread(target=listen_and_resend, args=(lock, DST_IFACE, SRC_IFACE, UDP_PORT, 'boiler') )
#	t2b= Thread(target=listen_and_resend, args=(lock, DST_IFACE, SRC_IFACE, 50001, 'boiler') )
	t2.start()
#	t2b.start()

	t3= Thread(target=telnet_proxy, args=(lock, SRC_IFACE, DST_IFACE, 23) )
	t3.start()
	signal.pause()
except (KeyboardInterrupt, SystemExit):
	logger.warning('Received keyboard interrupt, quitting threads.')

#t1.join()
#t2.join()
logger.info('exit main')

