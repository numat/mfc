mks
===

#####This driver is currently untested. Use with caution.

Python driver and command-line tool for [MKS EtherCAT mass flow controllers](http://www.mksinst.com/product/category.aspx?CategoryID=406).

<p align="center">
  <img src="http://www.mksinst.com/images/gseries.jpg" />
</p>

Installation
============

This driver currently depends on [IgH EtherCAT Master](http://www.etherlab.org/en/ethercat/).
To install this dependency, clone the repo, install
[this patch](http://lists.etherlab.org/pipermail/etherlab-dev/2014/000435.html),
build, and register an ethernet port for use.

```
hg clone http://hg.code.sf.net/p/etherlabmaster/code ethercat-hg
cd ethercat-hg
# Patch, if needed
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

Once this is working, you can install this library with:

```
pip install git+https://github.com/numat/mks
```

###Command Line

To test your connection and stream real-time data, use the command-line
interface. You can read the flow rate with:

```
$ mks
{
  "flow": 0.1,
  "setpoint": 0.1
}
```

You can optionally specify an etherCAT position (default 0), and a setpoint flow.

```
$ mks 2 --set 1
{
  "flow": 0.1,
  "setpoint": 1
}
```

See `mks --help` for more.

###Python

For more complex behavior, you can write a python script to interface with
other sensors and actuators.

```python
from mks import FlowController
flow_controller = FlowController(position=1)
print(flow_controller.get())
```

If the controller is operating at that address, this should output a
dictionary of the form:

```python
{
  'flow': 0.1  # Current flow rate, in units specified by device model
  'setpoint': 0.1  # Setpoint flow rate, also in units specified by device model
}
```
