"""
Python driver for MKS flow controllers.

Distributed under the GNU General Public License v2
Copyright (C) 2019 NuMat Technologies
"""
from binascii import unhexlify
from struct import unpack
from urllib.parse import quote_plus
from xml.etree import ElementTree

import aiohttp


class FlowController(object):
    """Driver for MKS mass flow controllers."""

    evids = {
        'actual': 'EVID_0',      # sccm
        'setpoint': 'EVID_1',    # sccm
        'temperature': 'EVID_3'  # °C
    }

    def __init__(self, address: str, timeout: float = 1.0, password: str = 'config'):
        """Initialize device.

        Note that this constructor does not not connect. This will happen
        on the first avaiable async call (ie. `await mfc.get()` or
        `async with FlowController(ip) as mfc`).

        Args:
            address: The IP address of the device, as a string.
            timeout (optional): Time to wait for a response before throwing
                a TimeoutError. Default 1s.
            password (optional): Password used to access admin settings on the
                web interface. Default "config".

        """
        self.address = f"http://{address.lstrip('http://').rstrip('/')}/"
        self.session = None
        self.Timeout = aiohttp.ClientTimeout(total=timeout)
        self.password = password
        self.analog_setpoint = 0
        ids = ''.join(f'<V Name="{evid}"/>' for evid in self.evids.values())
        self.get_request_body = f'<PollRequest>{ids}</PollRequest>'

    async def __aenter__(self):
        """Support `async with` by entering a client session."""
        try:
            await self.connect()
        except Exception as e:
            await self.__aexit__(e)
        return self

    async def __aexit__(self, *err):
        """Support `async with` by exiting a client session."""
        await self.disconnect()

    async def connect(self):
        """Connect and download configuration information.

        This function connects a standard HTTP session, and then follows up
        with a few requests to manage some quirks and get configuration data.

        The first checks if the controller is designed to be used as an analog
        device (ex. piMFC). These devices have a flag that must be set to be
        used digitally. Additionally, I've found these devices reset themselves
        every few hours. This driver will reconfigure analog devices when
        this is detected.

        The second gets all configured gas instances. There are some set on
        the device by default, and extras can be configured on the device
        website. After the driver has these instances, a final request figures
        out the currently selected gas.
        """
        self.session = aiohttp.ClientSession(timeout=self.Timeout)
        self.is_analog = await self._check_if_analog()
        self.gases = await self._get_gas_instances()
        self.selected_gas, self.max_flow = await self._get_selected_gas()

    async def disconnect(self):
        """Close the underlying session, if it exists."""
        if self.session is not None:
            await self.session.close()
            self.session = None

    async def get(self):
        """Retrieve the device state.

        This is done through ToolWeb, a simple HTTP endpoint that delivers an
        XML response. One quirk - getting data is accomplished by a POST.
        """
        response = await self._request('ToolWeb/Cmd', body=self.get_request_body)
        parsed = self._process(response)
        await self._handle_analog(parsed['setpoint'])
        return parsed

    async def set(self, setpoint):
        """Set the setpoint flow rate, in sccm.

        This uses an undocumented HTTP extension, `flow_setpoint_html`. This
        extension is used by the web interface and returns an entire HTML
        page on success.

        This also handles analog devices by storing the setpoint in a cached
        variable and ensuring the device is configured to respond to digital
        setpoints.

        Args:
            setpoint: Setpoint flow, as a float, in sccm.

        """
        if setpoint < 0 or setpoint > self.max_flow:
            raise ValueError(f"Setpoint must be between 0 and {self.max_flow:d} sccm.")
        if self.is_analog:
            self.analog_setpoint = setpoint
            await self._enable_digital()
            await self.set_display('flow')
        body = f'iobuf.setpoint={setpoint:.2f}&SUBMIT=Submit'
        await self._request('flow_setpoint_html', body)

    async def open(self):
        """Set the flow to its maximum value."""
        await self.set(self.max_flow)

    async def close(self):
        """Set the flow to zero."""
        await self.set(0)

    async def set_gas(self, gas):
        """Set the gas, affecting flow control range.

        In order to use this, *you must first create gas instances through
        the website* (the MFC froze when I tried to automate this). This
        method will look up the appropriate instance and change the gas.

        Args:
            gas: Gas to set. Must be in `controller.gases.keys()`.

        """
        if gas not in self.gases:
            raise ValueError(f"Gas must be in {list(self.gases.keys())}.")
        await self._login()
        body = f'device_html.selected_gas={quote_plus(self.gases[gas])}&SUBMIT=Set'
        await self._request('device_html_selected_gas', body)
        self.selected_gas, self.max_flow = await self._get_selected_gas()

    async def set_display(self, mode):
        """If a device option, sets the display mode.

        Args:
            mode: One of 'ip', 'flow', or 'temperature'.

        """
        await self._login()
        mode_index = ['ip', 'flow', 'temperature'].index(mode.lower())
        body = f'DISPLAY_MODE={mode_index:d}&SUBMIT=Submit'
        await self._request('change_display_mode', body)

    async def _login(self):
        """Log in to the device. Required for gas and display setting."""
        body = f'CONFIG_PASSWORD={self.password}&SUBMIT=Change+Settings'
        await self._request('configure_html_check', body)

    async def _get_selected_gas(self):
        """Get the current specified gas and max flow rate."""
        response = await self._request('device_html.js')
        selected_gas, max_flow = None, None
        lines = response.split('\n')
        for line in lines:
            if 'device_html.selected_gas' in line:
                selected_gas = line.split(': ')[1].rstrip('";')
            elif 'device_html.full_scale_amount' in line:
                max_flow = int(float(line.split('=')[1].rstrip(';')))
        return (selected_gas, max_flow)

    async def _get_gas_instances(self, callback=None, retries=3):
        """Get the current gas instance configuration."""
        response = await self._request('gaslist.js')
        gases = {}
        lines = response.split('\n')
        start = lines.index('instancelist = new Array();') + 1
        for line in lines[start:]:
            if line:
                gas_command = line.split('"')[1].rstrip('";').strip()
                gas_name = gas_command.split(': ')[1]
                if gas_name != 'NOGAS':
                    gases[gas_name] = gas_command
        return gases

    def _process(self, response):
        """Convert XML response string into a simplified dictionary.

        This also adds the max flow rate and selected gas, which are cached
        values from other requests.
        """
        state = {'max': self.max_flow, 'gas': self.selected_gas}
        tree = ElementTree.fromstring(response)
        for item in tree.findall('V'):
            evid, value = item.get('Name'), item.text
            key = next(k for k, v in self.evids.items() if v == evid)
            state[key] = unpack('!f', unhexlify(value[2:]))[0]
        return state

    async def _check_if_analog(self):
        """Check if digital control enabling is required.

        Analog controllers (e.g. PiMFC) take analog input over digital by
        default. This prevents the driver from setting flow rates. We must
        enable digital override on start, and again on every controller reboot.
        """
        response = await self._request('mfc.js')
        return ('mfc.sp_adc_enable' in response)

    async def _handle_analog(self, setpoint):
        """Handle intermittent analog controller reboots.

        The analog devices reboot occasionally, setting the flow to zero. If
        this driver detects a reboot, it will set the flow rate to the last
        set value.
        """
        if self.is_analog and abs(setpoint - self.analog_setpoint) > 1e-3:
            await self.set(self.analog_setpoint)

    async def _enable_digital(self):
        """Enable digital setpoints on analog controllers. Run on start."""
        await self._request('flow_setpoint_html', 'mfc.sp_adc_enable=0')

    async def _request(self, endpoint, body=None):
        """Handle sending an HTTP request.

        The headers are important! aiohttp overwrites many Content-Type headers
        with text/html, and this took me a while to figure out. I ended up
        debugging with 1. the order tornado implementation, and 2. curl:

        The following command does not work with the bracketed header flag:
        curl --data 'iobuf.setpoint=1.00&SUBMIT=Submit'
        [--header "Content-Type: text/html"] http://address/flow_setpoint_html

        curl defaults to application/x-www-form-urlencoded, which appears to
        work with the mfc.

        """
        if self.session is None:
            await self.connect()
        url = self.address + endpoint
        method = ('POST' if body else 'GET')
        headers = {'Content-Type': 'text/xml' if endpoint == 'ToolWeb/Cmd'
                                   else 'application/x-www-form-urlencoded'}
        async with self.session.request(method, url, headers=headers, data=body) as r:
            response = await r.text()
            if not response or r.status > 200:
                raise IOError(f"Could not communicate with MFC at '{endpoint}'.")
            return response
