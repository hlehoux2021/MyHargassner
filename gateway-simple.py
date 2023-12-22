#!/usr/bin/env python3

import socket
import time

server = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)

# Enable port reusage so we will be able to run multiple clients and servers on single (host, port).
# Do not use socket.SO_REUSEADDR except you using linux(kernel<3.9): goto https://stackoverflow.com/questions/14388706/how-do-so-reuseaddr-and-so-reuseport-differ for more information.
# For linux hosts all sockets that want to share the same address and port combination must belong to processes that share the same effective user ID!
# So, on linux(kernel>=3.9) you have to run multiple servers and clients under one user to share the same (host, port).
# Thanks to @stevenreddie
server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)

# Enable broadcasting mode
server.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

# Set a timeout so the socket does not block
# indefinitely when trying to receive data.
server.settimeout(0.2)
server.bind( ('',50000) )
message1 = b"HargaWebApp v6.4.1\r\nSN:0039808"
message2 = b"get services"

while True:
	print("sending:", message1.decode() )
	server.sendto(message1, ('<broadcast>', 35601))
	print("message sent!", flush=True)
	time.sleep(5)

	print("sending:", message2.decode() )
	server.sendto(message2, ('<broadcast>', 35601))

	time.sleep(10)
