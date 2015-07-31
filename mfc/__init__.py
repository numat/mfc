#!/usr/bin/python
"""
A Python driver for MKS flow controllers.

Distributed under the GNU General Public License v2
Copyright (C) 2015 NuMat Technologies
"""
from binascii import unhexlify
from struct import unpack
import xml.etree.ElementTree as ET

from tornado.httpclient import HTTPRequest, AsyncHTTPClient
from tornado.ioloop import IOLoop


class FlowController(object):
    """Python driver for [MKS mass flow controllers](http://www.mksinst.com/
    product/category.aspx?CategoryID=406).
    """
    evids = {'actual': 'EVID_0',  # sccm
             'setpoint': 'EVID_1',  # sccm
             'valve command': 'EVID_2',  # mA
             'temperature': 'EVID_3',  # C
             'minimum valve command': 'EVID_4',  # A
             'temp comp flow': 'EVID_5',  # V
             'counter': 'EVID_8'}

    def __init__(self, address='192.168.1.100'):
        """Saves IP address and checks for live connection.

        Args:
            address: The IP address of the device, as a string.
                Default '192.168.1.100'.
        """
        self.ip = address
        self.address = 'http://{}/ToolWeb/Cmd'.format(address)
        self.setpoint_address = 'http://{}/flow_setpoint_html'.format(address)
        self.headers = {'Content-Type': 'text/xml'}

        # There's no documented method to change requested data, but it can be
        # done with e.g. `flow_controller.fields.append('counter')`.
        self.fields = ['actual', 'setpoint', 'temperature']
        self.client = AsyncHTTPClient()

    def get(self, callback, retries=3):
        """Retrieves the current state of the device through ToolWeb.

        Args:
            callback: This function will be triggered asyncronously on
                response, and provided a dictionary of state values.
            retries: (Optional) Number of communication reattempts. Default 3.
        """
        def on_response(response):
            if response.body:
                callback(self._process(response))
            elif retries > 0:
                self.get(callback, retries=retries-1)
            else:
                raise IOError("Could not read from MFC.")

        ids = ('<V Name="{}"/>'.format(self.evids[f]) for f in self.fields)
        body = '<PollRequest>{}</PollRequest>'.format(''.join(ids))
        request = HTTPRequest(self.address, 'POST', body=body,
                              headers=self.headers)
        self.client.fetch(request, on_response)

    def set(self, setpoint, callback=None, retries=3):
        """Sets the setpoint flow rate, in sccm.

        This uses an undocumented HTTP extension, `flow_setpoint_html`. This
        extension is used by the web interface, and returns an entire HTML
        page on success.

        Args:
            setpoint: Setpoint flow, as a float, in sccm.
            callback: (Optional) If specified, will run after flow is set.
                No arguments are passed.
            retries: (Optional) Number of communication reattempts. Default 3.
        """
        def on_response(response):
            if response.body:
                self.setpoint = setpoint
                if callback:
                    callback()
            elif retries > 0:
                self.set(setpoint, callback, retries=retries-1)
            else:
                raise IOError("Could not set MFC flow rate.")

        body = 'iobuf.setpoint={:.2f}&SUBMIT=Submit'.format(setpoint)
        request = HTTPRequest(self.setpoint_address, 'POST', body=body)
        self.client.fetch(request, on_response)

    def _process(self, response):
        """Converts XML response string into a simplified dictionary."""
        if response.error:
            return {'connected': False, 'ip': self.ip}
        state = {'connected': True, 'ip': self.ip}
        tree = ET.fromstring(response.body)
        for item in tree.findall('V'):
            evid, value = item.get("Name"), item.text
            key = next(k for k, v in self.evids.items() if v == evid)
            state[key] = unpack('!f', unhexlify(value[2:]))[0]
        return state


def command_line():
    import argparse
    from functools import partial
    import json
    from json import encoder
    encoder.FLOAT_REPR = lambda o: format(o, '.2f')

    parser = argparse.ArgumentParser(description="Control an MKS MFC from "
                                     "the command line.")
    parser.add_argument('address', nargs='?', default='192.168.1.100',
                        help="The IP address of the MFC. Default "
                             "'192.168.1.100'.")
    parser.add_argument('--set', '-s', default=None, type=float, help="Sets "
                        "the setpoint flow of the mass flow controller, in "
                        "units specified in the manual (likely sccm).")
    args = parser.parse_args()

    controller = FlowController(args.address)
    ioloop = IOLoop.current()

    def print_flows(flows):
        """Prints the flows and stops async loop once data is retrieved."""
        print(json.dumps(flows, indent=2, sort_keys=True))
        ioloop.stop()

    if args.set is None:
        controller.get(print_flows)
    else:
        def on_set_response():
            ioloop.call_later(0.01, partial(controller.get, print_flows))
        controller.set(args.set, on_set_response)
    ioloop.start()


if __name__ == '__main__':
    command_line()
