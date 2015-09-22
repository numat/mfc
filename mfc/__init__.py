#!/usr/bin/python
"""
A Python driver for MKS flow controllers.

Distributed under the GNU General Public License v2
Copyright (C) 2015 NuMat Technologies
"""
from binascii import unhexlify
from functools import partial
from struct import unpack
import xml.etree.ElementTree as ET

try:
    from urllib.parse import quote_plus as quote
except ImportError:
    from urllib import quote_plus as quote

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

    def __init__(self, address, callback=None):
        """Saves IP address and checks for live connection.

        Args:
            address: The IP address of the device, as a string.
            callback: (Optional) Fires when controller driver is initialized.
        """
        self.ip = address
        self.client = AsyncHTTPClient()

        # There's no documented method to change requested data, but it can be
        # done with e.g. `flow_controller.fields.append('counter')`.
        self.fields = ['actual', 'setpoint', 'temperature']

        # Analog controllers (like the piMFC) need to be digitally enabled
        # for flow setting to work.
        self.is_analog, self.analog_setpoint = False, 0
        self._check_if_analog()

        # Retrieves data on available gas options. Fires callback on complete.
        self.max_flow, self.selected_gas = None, None
        self._get_gas_instances(partial(self._get_selected_gas, callback))

    def get(self, callback, retries=3):
        """Retrieves the current state of the device through ToolWeb.

        Args:
            callback: This function will be triggered asyncronously on
                response, and provided a dictionary of state values.
            retries: (Optional) Number of communication reattempts. Default 3.
        """
        def on_response(response):
            if response.body:
                parsed = self._process(response)
                # Analog mfcs zero their setpoints if not occasionally reset
                if (self.is_analog and
                        abs(parsed['setpoint'] - self.analog_setpoint) > 1e-3):
                    self.set(self.analog_setpoint)
                # Redundant data check if the constructor fails
                if self.max_flow is None:
                    self._get_selected_gas()
                    self._get_gas_instances()
                    self._check_if_analog()
                callback(parsed)
            elif retries > 0:
                self.get(callback, retries=retries-1)
            else:
                callback({'connected': False, 'ip': self.ip})

        address = 'http://{}/ToolWeb/Cmd'.format(self.ip)
        ids = ('<V Name="{}"/>'.format(self.evids[f]) for f in self.fields)
        body = '<PollRequest>{}</PollRequest>'.format(''.join(ids))
        request = HTTPRequest(address, 'POST', body=body,
                              headers={'Content-Type': 'text/xml'})
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
        def on_setpoint_response(response):
            if response.body:
                if callback:
                    callback()
            elif retries > 0:
                self.set(setpoint, callback, retries=retries-1)
            else:
                raise IOError("Could not set MFC flow rate.")

        def set_setpoint():
            address = 'http://{}/flow_setpoint_html'.format(self.ip)
            body = 'iobuf.setpoint={:.2f}&SUBMIT=Submit'.format(setpoint)
            request = HTTPRequest(address, 'POST', body=body)
            self.client.fetch(request, on_setpoint_response)

        if setpoint < 0 or setpoint > self.max_flow:
            raise ValueError("Setpoint must be between 0 and {:d} sccm."
                             .format(self.max_flow))

        if self.is_analog:
            self.analog_setpoint = setpoint
            self._enable_digital(set_setpoint)
        else:
            set_setpoint()

    def set_gas(self, gas, callback=None, password='config', retries=3):
        """Sets the gas, affecting flow control range.

        In order to use this, *you must first create gas instances through
        the website* (the MFC froze when I tried to automate this). This
        method will look up the appropriate instance and change the gas.

        Args:
            gas: Gas to set. Must be in `controller.gases.keys()`.
            callback: (Optional) If specified, will run after gas is set.
                No arguments are passed.
            password: (Optional) Password used to enter configuration mode.
                Default 'config'.
            retries: (Optional) Number of communication reattempts. Default 3.
        """
        def on_login():
            address = 'http://{}/device_html_selected_gas'.format(self.ip)
            body = 'device_html.selected_gas={}&SUBMIT=Set'.format(
                    quote(self.gases[gas]))
            request = HTTPRequest(address, 'POST', body=body)
            self.client.fetch(request, on_response)

        def on_response(response):
            if response.body:
                self._get_selected_gas()
                if callback:
                    callback()
            elif retries > 0:
                self.set_gas(gas, callback, password, retries=retries-1)
            else:
                raise IOError("Could not set gas.")

        if gas not in self.gases:
            raise ValueError("Gas must be in {}.".format(
                             list(self.gases.keys())))

        self._login(on_login, password)

    def set_display(self, mode, callback=None, password='config', retries=3):
        """If a device option, sets the display mode.

        Args:
            mode: One of 'ip', 'flow', or 'temperature'.
            callback: (Optional) If specified, will run after display is set.
                No arguments are passed.
            password: (Optional) Password used to enter configuration mode.
                Default 'config'.
            retries: (Optional) Number of communication reattempts. Default 3.
        """
        def on_login():
            address = 'http://{}/change_display_mode'.format(self.ip)
            mode_index = ['ip', 'flow', 'temperature'].index(mode.lower())
            body = 'DISPLAY_MODE={:d}&SUBMIT=Submit'.format(mode_index)
            request = HTTPRequest(address, 'POST', body=body)
            self.client.fetch(request, on_display_response)

        def on_display_response(response):
            if response.body:
                if callback:
                    callback()
            elif retries > 0:
                self.set_display(mode, callback, password, retries=retries-1)
            else:
                raise IOError("Could not set MFC display mode.")

        self._login(on_login, password)

    def _login(self, callback=None, password='config', retries=3):
        """Logs in to the device. Required for gas and display setting."""
        def on_login_response(response):
            if response.body:
                if callback:
                    callback()
            elif retries > 0:
                self._login(callback, password, retries=retries-1)
            else:
                raise IOError("Could not log in to MFC config mode.")

        address = 'http://{}/configure_html_check'.format(self.ip)
        body = 'CONFIG_PASSWORD={}&SUBMIT=Change+Settings'.format(password)
        request = HTTPRequest(address, 'POST', body=body)
        self.client.fetch(request, on_login_response)

    def _get_selected_gas(self, callback=None, retries=3):
        """Gets the current specified gas and max flow rate."""
        def on_response(response):
            if response.body:
                selected_gas, max_flow = None, None
                lines = response.body.decode('ascii').split('\n')
                for line in lines:
                    if 'device_html.selected_gas' in line:
                        selected_gas = line.split(': ')[1].rstrip('";')
                    elif 'device_html.full_scale_amount' in line:
                        max_flow = int(float(line.split('=')[1].rstrip(';')))
                self.selected_gas, self.max_flow = selected_gas, max_flow
                if callback:
                    callback()
            elif retries > 0:
                self._get_selected_gas(callback, retries=retries-1)
            else:
                raise IOError("Could not get selected gas.")

        request = HTTPRequest('http://{}/device_html.js'.format(self.ip))
        self.client.fetch(request, on_response)

    def _get_gas_instances(self, callback=None, retries=3):
        """Gets the current gas instance configuration."""
        def on_response(response):
            if response.body:
                self.gases = {}
                lines = response.body.decode('ascii').split('\n')
                start = lines.index('instancelist = new Array();') + 1
                for line in lines[start:]:
                    if line:
                        gas_command = line.split('"')[1].rstrip('";').strip()
                        gas_name = gas_command.split(': ')[1]
                        if gas_name != "NOGAS":
                            self.gases[gas_name] = gas_command
                if callback:
                    callback()
            elif retries > 0:
                self._get_gas_instances(callback, retries=retries-1)
            else:
                raise IOError("Could not get available gas instances.")

        request = HTTPRequest('http://{}/gaslist.js'.format(self.ip))
        self.client.fetch(request, on_response)

    def _process(self, response):
        """Converts XML response string into a simplified dictionary.

        This method adds some internal variables to the output.
        """
        if response.error or not response.body:
            return {'connected': False, 'ip': self.ip}
        state = {'connected': True, 'ip': self.ip}
        tree = ET.fromstring(response.body)
        for item in tree.findall('V'):
            evid, value = item.get("Name"), item.text
            key = next(k for k, v in self.evids.items() if v == evid)
            state[key] = unpack('!f', unhexlify(value[2:]))[0]

        state['max'] = self.max_flow
        state['gas'] = self.selected_gas

        return state

    def _check_if_analog(self, callback=None, retries=3):
        """Checks if digital control enabling is required.

        Analog controllers (e.g. PiMFC) take analog input over digital by
        default. This prevents the driver from setting flow rates. We must
        enable digital override on start, and again on every controller reboot.
        """
        def on_response(response):
            if response.body:
                self.is_analog = ('mfc.sp_adc_enable' in str(response.body))
                if self.is_analog:
                    self._enable_digital()
                    self.set_display('flow')
                if callback:
                    callback()
            elif retries > 0:
                self._check_if_analog(callback, retries=retries-1)
            else:
                raise IOError("Could not get controller information.")

        request = HTTPRequest('http://{}/mfc.js'.format(self.ip))
        self.client.fetch(request, on_response)

    def _enable_digital(self, callback=None, retries=3):
        """Enables digital setpoints on analog controllers. Run on start."""
        def on_response(response):
            if response.body:
                if callback:
                    callback()
            elif retries > 0:
                self._enable_digital(retries=retries-1)
            else:
                raise IOError("Could not set analog MFC mode.")

        address = 'http://{}/flow_setpoint_html'.format(self.ip)
        body = 'mfc.sp_adc_enable=0'
        request = HTTPRequest(address, 'POST', body=body)
        self.client.fetch(request, on_response)


def command_line():
    import argparse
    import json
    from json import encoder
    encoder.FLOAT_REPR = lambda o: format(o, '.2f')

    parser = argparse.ArgumentParser(description="Control an MKS MFC from "
                                     "the command line.")
    parser.add_argument('address', help="The IP address of the MFC")
    parser.add_argument('--set', '-s', default=None, type=float, help="Sets "
                        "the setpoint flow of the mass flow controller, in "
                        "units specified in the manual (likely sccm).")
    parser.add_argument('--set-gas', '-g', default=None, help="Sets the mass "
                        "flow controller gas type, e.g. 'CO2', 'N2'.")
    args = parser.parse_args()

    def on_init():
        if args.set_gas:
            controller.set_gas(args.set_gas, on_set_gas_response)
        else:
            on_set_gas_response()

    def on_set_gas_response():
        """Gas is (optionally) set first."""
        if args.set is not None:
            ioloop.call_later(0.01, partial(controller.set, args.set,
                                            on_set_flow_response))
        else:
            on_set_flow_response()

    def on_set_flow_response():
        """Then, flow rate is (optionally) set."""
        ioloop.call_later(0.01, partial(controller.get, print_flows))

    def print_flows(flows):
        """Finally, the state is printed."""
        print(json.dumps(flows, indent=2, sort_keys=True))
        ioloop.stop()

    controller = FlowController(args.address, on_init)
    ioloop = IOLoop.current()
    ioloop.start()


if __name__ == '__main__':
    command_line()
