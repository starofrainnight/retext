# This file is part of ReText
# Copyright: 2012-2015 Dmitry Shachnev
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import functools
import struct
from PyQt5.QtCore import pyqtSignal
from PyQt5.QtCore import QObject
from PyQt5.QtCore import QSharedMemory
from PyQt5.QtNetwork import QLocalServer
from PyQt5.QtNetwork import QLocalSocket

class SingleApplication(QObject):
	"""
	SingleApplication is a class that wrap around the single application
	framework.
	"""

	# Modes
	(
		# Server mode indicated that we started the first application
		Server,
		# Client mode means that another App already started, we should just
		# exit or send some message to that App bef
		Client,
	) = range(0, 2)

	# Signals

	receivedMessage = pyqtSignal(bytes)

	def __init__(self, name, parent=None):
		QObject.__init__(self, parent)
		self._name = name
		self._mode = self.Server
		self._sharedMemory = None
		self._server = None
		self._client = None
		self._localSockets = {}

	@property
	def name(self):
		return self._name

	@property
	def mode(self):
		return self._mode

	def _onLocalSocketReadyRead(self, localSocket):
		if localSocket.bytesAvailable() <= 0:
			return

		self._localSockets[localSocket] += localSocket.readAll()
		data = self._localSockets[localSocket]
		if len(data) > 4:
			# First 4bytes is an native Long.
			dataSize = struct.unpack("@L", data[:4])[0]
			receivedDataSize = len(data) - 4
			if receivedDataSize < dataSize:
				return

			self.receivedMessage.emit(bytes(data[4:]))
			
			# Remove the command socket
			del self._localSockets[localSocket]
			localSocket.deleteLater()

	def _onServerNewConnection(self):
		while self._server.hasPendingConnections():
			localSocket = self._server.nextPendingConnection()
			self._localSockets[localSocket] = b""
			localSocket.readyRead.connect(functools.partial(
				self._onLocalSocketReadyRead, localSocket))

	def start(self):
		# Ensure we run only one application
		self._sharedMemory = QSharedMemory(self._name)
		if self._sharedMemory.create(1, QSharedMemory.ReadWrite):
			self._mode = self.Server
			self._server = QLocalServer(self)
			self._server.newConnection.connect(self._onServerNewConnection)

			if not self._server.listen(self._name):
				# Failed to listen, is there have another application crashed
				# without normally shutdown it's server?
				#
				# We try to remove the old dancing server and restart a new
				# server.
				self._server.removeServer(self._name)
				if not self._server.listen(self._name):
					raise RuntimeError("Local server failed to listen on '%s'" % self._name)
		else:
			self._mode = self.Client
			self._client = QLocalSocket(self)
			self._client.connectToServer(self._name)

	def sendMessage(self, message):
		# Only accept bytes message
		assert(type(message) == bytes)
		data = struct.pack("@L%ss" % len(message), len(message), message)
		self._client.write(data)
	
