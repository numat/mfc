mfc
===

Python driver and command-line tool for [MKS mass flow controllers](http://www.mksinst.com/product/category.aspx?CategoryID=406).

<p align="center">
  <img src="https://www.engineering-sci.com/images/editor/G-Series%20Thermal%20Mass%20Flow%20Controllers%20&%20Meters%20with%20Fast%20&%20Repeatable%20Performance.jpg" />
</p>

Installation
============

```
pip install mfc
```

If you want the older python2/tornado driver, use `pip install mfc==0.2.11` and review [this README](https://github.com/numat/mfc/tree/1af5162b67041c6b5d934a5ef5f1aea0c8a5731e).

Usage
=====

This driver uses the ethernet port *on the side of the device* for communication.
If you use this driver, you only need to provide power to the top ports.

### Command Line

To test your connection and stream real-time data, use the command-line
interface. You can read the flow rate with:

```
$ mfc 192.168.1.200
{
  "actual": 4.99,
  "gas": "CO2",
  "max": 37,
  "setpoint": 5.00,
  "temperature": 27.34
}
```

You can optionally specify a setpoint flow and/or gas with e.g.
`mfc 192.168.1.150 --set 7.5 --set-gas N2`. See `mfc --help` for more.

### Python

This uses Python ≥3.5's async/await syntax to asynchronously communicate with
the mass flow controller. For example:

```python
import asyncio
from mfc import FlowController

async def get():
    async with FlowController('the-mfc-ip-address') as fc:
        print(await fc.get())

asyncio.run(get())
```

The API that matters is `get`, `set`, and `set_gas`.

```python
>>> await fc.get()
{
  "actual": 4.99,
  "gas": "CO2",
  "max": 37,
  "setpoint": 5.00,
  "temperature": 27.34
}
```
```python
>>> await fc.set(10)
>>> await fc.open()   # set to max flow
>>> await fc.close()  # set to zero flow
```
```python
>>> await fc.set_gas('N2')
```

There is also `set_display`, which will only work on devices that support it.

```python
>>> await fc.set_display('flow')
```
