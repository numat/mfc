mfc
===

Python driver and command-line tool for [MKS EtherCAT mass flow controllers](http://www.mksinst.com/product/category.aspx?CategoryID=406).

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

###Command Line

To test your connection and stream real-time data, use the command-line
interface. You can read the flow rate with:

```
$ mfc
{
  "flow": 0.1,
  "setpoint": 0.1
}
```

You can optionally specify an etherCAT position (default 0), and a setpoint flow.

```
$ mfc 2 --set 1
{
  "flow": 0.1,
  "setpoint": 1
}
```

See `mfc --help` for more.

###Python (Asynchronous)

Asynchronous programming allows us to send out all of our requests in parallel, and then
handle responses as they trickle in. For more information, read through
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

flow_controller = FlowController(position=1)

PeriodicCallback(loop, 500).start()
IOLoop.current().start()
```

This looks more complex, but the advantages are well worth it at scale.
Essentially, sleeping is replaced by scheduling functions with tornado. This
allows your code to do other things while waiting for responses.

Other Tools
===========

#### Wireshark

[Wireshark](https://www.wireshark.org/) is a packet analyzer that comes with
[built-in etherCAT support](https://wiki.wireshark.org/Protocols/ethercat).
Use this to view etherCAT packets as they traverse your network.

#### IgH EtherCAT Master

[IgH EtherCAT Master](http://www.etherlab.org/en/ethercat/) is a fully featured
etherCAT tool, and can be used to debug new devices. It's not required for this
driver to function, but it'll help if you're having problems.

However, it's a pain to install. Clone the repo (it's on sourceforge, which is
currently down), install [this patch](http://lists.etherlab.org/pipermail/etherlab-dev/2014/000435.html),
build, insert kernel mods, and register an ethernet port for use.

```
hg clone http://hg.code.sf.net/p/etherlabmaster/code ethercat-hg
cd ethercat-hg
# Patch
./bootstrap linux
./configure --disable-8139too
make
make modules
sudo insmod master/ec_master.ko main_devices=[mac address]  # Get mac from e.g. `ifconfig`
sudo chmod 666 /dev/EtherCAT0
sudo insmod devices/ec_generic.ko
sudo ifconfig eth[X] up
```

If you encounter issues, consult [this forum post](http://lists.etherlab.org/pipermail/etherlab-dev/2014/000368.html).
Test with:

```
dmesg
ethercat --help
ethercat pdos
```

It requires kernel headers, which don't come by default on some linux distros (e.g. raspbian).
