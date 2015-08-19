mfc
===

Python driver and command-line tool for [MKS mass flow controllers](http://www.mksinst.com/product/category.aspx?CategoryID=406).

<p align="center">
  <img src="http://www.mksinst.com/images/gseries.jpg" />
</p>

Installation
============

```
pip install mfc
```

If you don't like pip, you can also install from source:

```
git clone https://github.com/numat/mfc.git
cd mfc
python setup.py install
```

Usage
=====

This driver uses the ethernet port *on the side of the device* for communication.
If you use this driver, you only need to provide power to the top ports.

###Command Line

To test your connection and stream real-time data, use the command-line
interface. You can read the flow rate with:

```
$ mfc 192.168.1.200
{
  "actual": 4.99,
  "connected": true,
  "gas": "CO2",
  "ip": "192.168.1.200",
  "max": 37,
  "setpoint": 5.00,
  "temperature": 27.34
}
```

You can optionally specify a setpoint flow and gas with e.g.
`mfc 192.168.1.150 --set 7.5 --set-gas O2`. See `mfc --help` for more.

###Python (Asynchronous)

Asynchronous programming allows us to send out all of our requests in parallel, and
then handle responses as they trickle in. For more information, read through
[krondo's twisted introduction](http://krondo.com/?page_id=1327).

```python
from mfc import FlowController
from tornado.ioloop import IOLoop, PeriodicCallback

def on_response(response):
    """This function gets run whenever a device responds."""
    print(response)

def loop():
    """This function will be called in an infinite loop by tornado."""
    flow_controller.get(on_response)

flow_controller = FlowController('192.168.1.200')

PeriodicCallback(loop, 500).start()
IOLoop.current().start()
```

This looks more complex, but the advantages are well worth it at scale.
Essentially, sleeping is replaced by scheduling functions with tornado. This
allows your code to do other things while waiting for responses.
