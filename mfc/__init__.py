"""
Python driver for MKS flow controllers.

Distributed under the GNU General Public License v2
Copyright (C) 2019 NuMat Technologies
"""
from mfc.driver import FlowController


def command_line():
    """Command-line tool for MKS mass flow controllers."""
    import argparse
    import asyncio
    import json
    import sys
    red, reset = '\033[1;31m', '\033[0m'

    parser = argparse.ArgumentParser(description="Control an MKS MFC from "
                                     "the command line.")
    parser.add_argument('address', help="The IP address of the MFC")
    parser.add_argument('--set', '-s', default=None, type=float, help="Sets "
                        "the setpoint flow of the mass flow controller, in "
                        "units specified in the manual (likely sccm).")
    parser.add_argument('--set-gas', '-g', default=None, help="Sets the mass "
                        "flow controller gas type, e.g. 'CO2', 'N2'.")
    args = parser.parse_args()

    async def get():
        try:
            async with FlowController(args.address) as fc:
                if args.set_gas:
                    await fc.set_gas(args.set_gas)
                if args.set is not None:
                    await fc.set(args.set)
                    await asyncio.sleep(0.1)
                print(json.dumps(await fc.get(), indent=4, sort_keys=True))
        except asyncio.TimeoutError:
            sys.stderr.write(f'{red}Could not connect to device.{reset}\n')
        except Exception as e:
            sys.stderr.write(f'{red}{e}{reset}\n')

    loop = asyncio.get_event_loop()
    loop.run_until_complete(get())
    loop.close()


if __name__ == '__main__':
    command_line()
