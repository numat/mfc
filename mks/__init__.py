#!/usr/bin/python
"""
A Python driver for MKS' etherCAT flow controllers.

Distributed under the GNU General Public License v2
Copyright (C) 2015 NuMat Technologies
"""
import logging
from subprocess import call, check_output


class FlowController(object):
    """Python driver for [MKS EtherCAT mass flow controllers](http://www.
    mksinst.com/product/category.aspx?CategoryID=406).

    This driver is a simple command-line wrapper around IgH EtherCAT master.
    This will change in a future version.
    """
    def __init__(self, position=0):
        """Specifies etherCAT position and tests connection."""
        self.position = position
        self._get_flow_command = ['ethercat', 'upload', '-p',
                                  str(self.position), '0x6000', '0x01']
        self._get_setpoint_command = ['ethercat', 'upload', '-p',
                                      str(self.position), '0x7003', '0x01']
        self._set_setpoint_command = ['ethercat', 'download', '-p',
                                      str(self.position), '0x7003', '0x01']
        self._check_command = ['ethercat', 'slaves', '-p', str(self.position)]
        self.retries = 0
        self._check()

    def get(self):
        """Gets the current and setpoint flow of the device."""
        flow = check_output(self._get_flow_command)
        setpoint = check_output(self._get_setpoint_command)
        return {'flow': float(flow), 'setpoint': float(setpoint)}

    def set(self, setpoint):
        """Sets the setpoint flow, and checks to guarantee set."""
        call(self._set_setpoint_command + [str(setpoint)])
        current_setpoint = check_output(self._get_setpoint_command)
        if abs(setpoint - float(current_setpoint)) < 1e-3:
            self.retries = 0
        elif self.retries >= 3:
            self.retries = 0
            raise IOError("Can not set flow.")
        else:
            logging.info("Flow setpoint not updated. Retrying.")
            self.retries += 1
            self.set(setpoint)

    def _check(self):
        """Checks that an MKS controller is communicating."""
        result = check_output(self._check_command)
        if not result:
            raise IOError("No device found at position {:d}.".format(
                          self.position))
        name = result.decode('ascii').split(maxsplit=4)[-1]
        if 'EtherCAT MFC' not in name:
            raise IOError("MFC not found at position {:d}. Current device is"
                          " '{}'.".format(self.position, name))


def command_line():
    import argparse
    import json

    parser = argparse.ArgumentParser(description="Control an MKS etherCAT MFC "
                                     "from the command line.")
    parser.add_argument('position', nargs='?', default=0, help="The etherCAT "
                        "address of the mass flow controller.")
    parser.add_argument('--set', '-s', default=None, type=float, help="Sets "
                        "the setpoint flow of the mass flow controller, in "
                        "units specified in the manual.")
    args = parser.parse_args()

    flow_controller = FlowController(args.position)
    if args.set is not None:
        flow_controller.set(args.set)
    print(json.dumps(flow_controller.get(), indent=2, sort_keys=True))


if __name__ == '__main__':
    command_line()
