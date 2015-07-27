#!/usr/bin/python
"""
A Python driver for MKS etherCAT flow controllers.

Distributed under the GNU General Public License v2
Copyright (C) 2015 NuMat Technologies
"""
import binascii
import fcntl
import logging
import random
import socket
import struct
import traceback

import tornado.ioloop
import tornado.iostream


class FlowController(object):
    """Python driver for [MKS EtherCAT mass flow controllers](http://www.
    mksinst.com/product/category.aspx?CategoryID=406).
    """
    dest = 'ffffffffffff'
    ethertype = '88a4'
    ethercat_header = '9a10'
    working_count = '0000'
    packet_size = 170
    upload = '40'
    download = '23'
    prep_template = ('07{i}{pos}3001028000000000000005{j}{next}'
                     '0010800000000a00010000030020{command}{pdo}{size}{data}')
    run_template = '07{i}{pos}3001028000000000000004{j}{next}001480'

    def __init__(self, position=0, interface='eth0'):
        """Connects a raw socket to an interface, and wraps with tornado."""
        self.socket = socket.socket(socket.PF_PACKET, socket.SOCK_RAW,
                                    socket.htons(int(self.ethertype, 16)))
        self.socket.bind((interface, 0))
        self.stream = tornado.iostream.IOStream(self.socket)

        self.position = self._flip('{:04x}'.format(position))
        self.next_position = self._flip('{:04x}'.format(position + 1))
        self.interface = interface
        self.source = self._get_mac()
        self.response_source = '{:x}'.format(int(self.source, 16) + 2 ** 41)
        self.ethernet_header = self.dest + self.source + self.ethertype
        self.template = (self.ethernet_header + self.ethercat_header +
                         '{payload}' + self.working_count)
        self.setting_flow = False
        self.ioloop = tornado.ioloop.IOLoop.current()

    def get(self, callback, *args, **kwargs):
        """Returns the setpoint and actual flow rates as a dictionary.

        This method calls `get_flow` and `get_setpoint` in tandem. If you
        only need one of the two values, use these methods instead.
        """
        def actual_callback(response):
            """After flow is retrieved, call `get_setpoint`."""
            self.get_setpoint(lambda r: setpoint_callback(r, response))

        def setpoint_callback(setpoint, actual):
            """After setpoint is retrieved, fire user's callback."""
            callback({'actual': actual, 'setpoint': setpoint}, *args, **kwargs)

        self.get_actual(actual_callback)

    def get_actual(self, callback, *args, **kwargs):
        """Gets the current flow rate."""
        self._handle_communication('6000', '01', self.upload,
                                   callback, *args, **kwargs)

    def get_setpoint(self, callback, *args, **kwargs):
        """Gets the setpoint flow rate."""
        self._handle_communication('7003', '01', self.upload,
                                   callback, *args, **kwargs)

    def set(self, setpoint, retries=3):
        """Sets the setpoint flow rate.

        This method requests a lock on the socket, deferring all other
        requests until a value has been set.
        """
        def on_setpoint():
            """After setting the flow, remove the lock and request a check."""
            self.setting_flow = False
            self.get_setpoint(check_setpoint)

        def check_setpoint(response):
            """Check that the flow controller's setpoint matches target."""
            if abs(setpoint - response) < 0.01:
                logging.debug("Set flow setpoint to {:.2f}.".format(response))
            elif retries <= 0:
                raise IOError("Could not set setpoint.")
            else:
                logging.debug("Could not set setpoint. Retrying...")
                self.set(setpoint, retries=retries-1)

        self.setting_flow = True
        self._handle_communication('7003', '01', self.download,
                                   on_setpoint, data=setpoint)

    def _handle_communication(self, pdo, size, command, callback, data=None,
                              *args, **kwargs):
        """Communicates with the EtherCAT device to retrieve data.

        This is the bulk of the driver, and was thrown together by reverse
        engineering etherCAT frames sent from IgH EtherCAT master. By removing
        the need for kernel modifications, this should be more portable.

        Largely, the etherCAT data is treated as a binary payload wrapped in
        an ethernet frame. By doing this, we lose many of the benefits of
        etherCAT (e.g. fast response times, packet minimization).
        However, these benefits are negligible considering the internal
        mechanical delays of flow controllers.

        Some precautions were made to ensure proper functionality. Requests
        follow a req-res-req-res pattern, and will restart the chain when an
        error is detected. Set the loglevel to debug to watch more.
        """
        def defer():
            """Re-calls the function after a slight delay."""
            self.ioloop.call_later(0.05, lambda: self._handle_communication(
                                    pdo, size, command, callback, data))

        if self.setting_flow and command == self.upload:
            logging.debug("Request for data deferred while setting flow.")
            defer()
            return

        index = random.randint(10, 240)

        def send_preparation_request():
            """The first request. Appears to prepare the device for I/O."""
            kwargs = {'pdo': self._flip(pdo), 'pos': self.position,
                      'size': size, 'i': '{:02x}'.format(index),
                      'j': '{:02x}'.format(index + 1), 'command': command,
                      'data': binascii.hexlify(struct.pack('<f', data))
                      if data else '', 'next': self.next_position}
            ethercat = self.prep_template.format(**kwargs)
            prep_command = self.template.format(payload=self._pad(ethercat))
            self.stream.write(binascii.unhexlify(prep_command))

            if self.stream.reading():
                logging.debug("Stream busy. Restarting request.")
                defer()
                return
            else:
                self.stream.read_bytes(self.packet_size,
                                       on_prepared_confirmation)

        def on_prepared_confirmation(result):
            """Checks the device reply and continues if okay.

            The device takes the etherCAT frame and flips some bits. Working
            counters are incremented, slave positions are incremented,
            and one of the source MAC address bits is flipped. We're assuming
            one-device communication, so we can test this behavior to ensure
            we have the right packet.
            """
            res = binascii.hexlify(result)
            try:
                self._check(res, index)
            except ValueError:
                logging.debug("Malformed response: " + traceback.format_exc())
                send_preparation_request()
                return
            send_data_request()

        def send_data_request():
            """The second request. Appears to ask for data."""
            ethercat = self.run_template.format(pos=self.position,
                                                next=self.next_position,
                                                i='{:02x}'.format(index + 4),
                                                j='{:02x}'.format(index + 5))
            run_command = self.template.format(payload=self._pad(ethercat))
            self.stream.write(binascii.unhexlify(run_command))
            if self.stream.reading():
                logging.debug("Stream busy. Restarting request.")
                defer()
                return
            else:
                self.stream.read_bytes(self.packet_size, on_data_received)

        def on_data_received(result):
            """Retrieves device data and fires user callbacks.

            If we asked for data, this response will have it.
            """
            res = binascii.hexlify(result)
            try:
                self._check(res, index + 4)
            except ValueError:
                logging.debug("Malformed response: " + traceback.format_exc())
                send_data_request()
                return

            received_pdo = self._flip(res[98:102])
            # This occurs when the request happens faster than the update
            if received_pdo != pdo:
                send_data_request()
            elif command == self.upload:
                callback(struct.unpack('!f', bytes(result[52:56][::-1]))[0],
                         *args, **kwargs)
            elif command == self.download:
                callback(*args, **kwargs)

        send_preparation_request()

    def _get_mac(self):
        """Returns the MAC address of the bound interface."""
        info = fcntl.ioctl(self.socket.fileno(), 0x8927,
                           struct.pack('256s', self.interface[:15]))
        return binascii.hexlify(info[18:24])

    def _check(self, response, index):
        """A random series of sanity checks for the etherCAT packet."""
        if len(response) != self.packet_size * 2:
            raise ValueError("Improper packet size. This driver is hardcoded "
                             "to expect a size of {:d}."
                             .format(self.packet_size))
        if any((response[:12] != self.dest,
                response[12:24] != self.response_source,
                response[24:28] != self.ethertype,
                response[28:32] != self.ethercat_header)):
            received = ':'.join((response[:12], response[12:24],
                                 response[24:28], response[28:32]))
            expected = ':'.join((self.dest, self.response_source,
                                 self.ethertype, self.ethercat_header))
            raise ValueError("Malformed headers. Received '{}', but expected "
                             "'{}'.".format(received, expected))
        if int(response[34:36], 16) != index:
            raise ValueError("EtherCAT index mismatch. Wrong packet received.")

    def _flip(self, data):
        """Flips the endianness of a hex byte representation.

        This driver uses 0-f ascii characters as its internal representation
        of binary. It's twice the size of pure bytes, but easier to debug. We
        lose the benefit of struct packing (e.g. < vs. > for endianness), so
        we need to write our own.
        """
        return ''.join([data[i:i+2] for i in range(0, len(data), 2)][::-1])

    def _pad(self, ethercat_data):
        """Pads the etherCAT frame with zeroes.

        From the IgH etherCAT master frames, we set a minimum size for the
        etherCAT frames. The controller gets nowhere near this size, so we
        have plenty of room.

        TODO This fixed-size padding approach could be eliminated easily.
        """

        pad_size = self.packet_size - 18 - len(ethercat_data) / 2
        return ethercat_data + '0' * 2 * pad_size


def command_line():
    import argparse
    import json
    from json import encoder
    encoder.FLOAT_REPR = lambda o: format(o, '.2f')

    parser = argparse.ArgumentParser(description="Control an MKS etherCAT MFC "
                                     "from the command line.")
    parser.add_argument('position', nargs='?', default=0, type=int,
                        help="The etherCAT address of the flow controller.")
    parser.add_argument('--set', '-s', default=None, type=float, help="Sets "
                        "the setpoint flow of the mass flow controller, in "
                        "units specified in the manual.")
    args = parser.parse_args()

    flow_controller = FlowController(args.position)

    ioloop = tornado.ioloop.IOLoop.current()

    def print_flows(flows):
        """Prints the flows and stops async loop once data is retrieved."""
        print(json.dumps(flows, indent=2, sort_keys=True))
        ioloop.stop()

    if args.set is not None:
        flow_controller.set(args.set)
    flow_controller.get(print_flows)
    ioloop.start()


if __name__ == '__main__':
    command_line()
