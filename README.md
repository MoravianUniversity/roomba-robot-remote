# Installation

From a clean Raspbian install do the following:

```bash
sudo apt-get update
sudo apt-get dist-upgrade
sudo apt-get install virtualenv vim
sudo apt-get purge plymouth*
sudo apt-get autoremove

sudo systemctl set-default multi-user.target
sudo systemctl enable ssh
sudo systemctl start ssh
sudo systemctl disable apt-daily.service
sudo systemctl disable apt-daily.timer
sudo systemctl disable apt-daily-upgrade.service
sudo systemctl disable apt-daily-upgrade.timer

sudo reboot
```

At this point the boot time should be <15secs. The largest component of that is dhcpcd, about 60% of the total boot time, and disabling that would likely result in problems.

Now we can setup the server itself:

```bash
virtualenv -p `which python3` remote
cd remote
. bin/activate
pip install tornado yarc 
# TODO: git clone ... && cd ...
./remote.py
```

Now the server is running on port 8888 as the pi user. This may be fine for most situations. Limitations/Problems:

* Does not autostart at boot, restarting the pi means you need to SSH back in and start the server
* Can only be accessed by people on the same network (and thus must be on a network)
* Not the most power efficient

## Autostart the server at boot

The program will run as root on port 80 with this method.

Adapted from <https://www.raspberrypi.org/documentation/linux/usage/systemd.md>

```bash
sudo tee /etc/systemd/system/roomba-remote.service <<EOF
[Unit]
Description=Roomba Remote Server
Requires=network.target

[Service]
Type=simple
ExecStart=/home/pi/remote/run_remote_server --port=80
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable roomba-remote
sudo systemctl start roomba-remote
```

With this setup you no longer need to connect to port 8888 but just the default 80.

Even though the server is running all the time, only when a websocket is open will the Pi be communicating with Roomba (and for a short time after the websocket is closed in case it is woken up soon). This means that you can start a debug server at the same time as long as nothing is accessing the server.

## Turn Pi into a Wifi AP for standalone network

During this you are going to need the Pi connected to a monitor/keyboard or the wired LAN due to the disruption in wireless networking when changing these settings. After doing this you will either need one of those setups or to connect to its personal wireless network.

Adapted from <https://www.raspberrypi.org/documentation/configuration/wireless/access-point.md>

This will also set up the DNS server to resolve all names to the address of the server itself.

```bash
sudo apt-get install dnsmasq hostapd

sudo tee -a /etc/dhcpcd.conf <<EOF
interface wlan0
    static ip_address=192.168.4.1/24
    nohook wpa_supplicant
EOF

sudo systemctl restart dhcpcd

sudo mv /etc/dnsmasq.conf /etc/dnsmasq.conf.orig
sudo tee /etc/dnsmasq.conf <<EOF
interface=wlan0
dhcp-range=192.168.4.2,192.168.4.20,255.255.255.0,24h
address=/#/192.168.4.1
EOF

sudo systemctl reload dnsmasq

sudo tee /etc/hostapd/hostapd.conf <<EOF
interface=wlan0
driver=nl80211
ssid=RoombaRobot
hw_mode=g
channel=7
wmm_enabled=0
macaddr_acl=0
auth_algs=1
ignore_broadcast_ssid=0
wpa=2
wpa_passphrase=RoombaRobot
wpa_key_mgmt=WPA-PSK
wpa_pairwise=TKIP
rsn_pairwise=CCMP
EOF

sudo nano /etc/default/hostapd
# Replace #DAEMON_CONF line with:
#    DAEMON_CONF="/etc/hostapd/hostapd.conf"

sudo systemctl unmask hostapd
sudo systemctl enable hostapd
sudo systemctl start hostapd

sudo reboot # I needed to do this to get things fully working
```

Now you can start the server, connect to the RoombaRobot wifi, and open 192.168.4.1. The Pi doesn't need to be on a network! However, it can be attached with an ethernet cable for an alternate access to the device.

## Power Saving

We are running completely headless and don't need many of the features of the Pi. If we disable them the Raspberry Pi won't drain the Roomba's battery as rapidly.

Overall I was able reduce the power usage from ~240 mA @ 5.18V on Raspberry Pi Model B to ~75 mA @ 5.26V. This is cutting off nearly 70% of the power usage. Additionally, the boot time went from ~14 to 7.5 seconds - nearly half! (NOTE: the Roomba itself can boot in about 3 seconds).

Some documents to read for more details:

* <https://www.jeffgeerling.com/blogs/jeff-geerling/raspberry-pi-zero-conserve-energy>
* <https://learn.pi-supply.com/make/how-to-save-power-on-your-raspberry-pi/>
* <https://www.raspberrypi.org/forums/viewtopic.php?t=208110#p1286812>
* <https://github.com/raspberrypi/firmware/issues/1141>
* <http://www.earth.org.uk/note-on-Raspberry-Pi-setup.html>

### Disable additional services

The following services aren't necessary in most cases and can be disabled. However, disabling them is likely not going to get you much benefit either.

* `avahi-daemon` - Apple's Bonjour (Zero-Conf) service
* `keyboard-setup` - keyboards still work without it and I usally SSH in anyways

### Runtime Disabled Peripherals

These are runtime commands to reduce power by disabling a peripheral. All can be reversed without rebooting to restore the peripheral. If you want them to happen on every boot then place in the `/etc/rc.local` (see <https://www.raspberrypi.org/documentation/linux/usage/rc-local.md>).

* `/opt/vc/bin/tvservice -off` - disables HDMI port, save ~20mA
  * Restored with `/opt/vc/bin/tvservice -p; fbset -depth 8; fbset -depth 16`
* `sudo ifconfig eth0 down` - disables ehternet, saves minimal power if no cable is plugged in anyways
  * Restored with `sudo ifconfig eth0 up`
  * `llctl f0 l0 d0` - disables ethernet LEDs, see <https://www.raspberrypi.org/forums/viewtopic.php?t=72070> for getting the program
  * the `dhcpcd` service is still running and it takes time to start (up to 30 secs) but with `eth0` disabled and `wlan0` using a static IP the basic built-in networking system is sufficent and faster (shaved off over 5 seconds of boot time for me):
    * NOTE: This will automatically disable (never bring up) the `eth0` interface at boot although it can still be brought up manually (editing the file below can change that)
    * Disable with `dhcpcd` service
    * Add the file `/etc/network/interfaces.d/static-wifi` with the contents:

```bash
auto lo
iface lo inet loopback

auto wlan0
iface wlan0 inet static
address 192.168.4.1/24
```

TODO: do we need to add the static route?

```bash
sudo ip route add 0.0.0.0/0 via 192.168.4.1 dev wlan0
```

How to make permanent?

### Boot Disabled Peripherals

Some peripherals need to be disabled during boot. This means that they cannot be brought back without a reboot. Some of these just speed the boot process instead of saving any significant power.

* comment out `dtparam=audio=on` in `/boot/config.txt` - disables audio, should also disable the `alsa-restore` service
* `dtoverlay=pi3-disable-bt` in `/boot/config.txt` - disables bluetooth, should also disable the `bluetooth` and `hciuart` services
* `boot_delay=0` in `/boot/config.txt` - speeds boot time by 1 second, poor quality SD cards may not work with no delay though
* `disable_splash=1` in `/boot/config.txt` - no rainbow splash screen during boot

### LEDs

This disables the PWR and ACT LEDs. This will save <10mA.

To disable at runtime:

```bash
echo gpio | sudo tee /sys/class/leds/led1/trigger
echo 0 | sudo tee /sys/class/leds/led0/brightness
echo none | sudo tee /sys/class/leds/led0/trigger
```

To disable them between boots:

```bash
sudo tee -a /boot/config.txt <<EOF
dtparam=act_led_trigger=none
dtparam=act_led_activelow=off
dtparam=pwr_led_trigger=none
dtparam=pwr_led_activelow=off
EOF
```

### Things we can't disable in a straight-forward way (yet)

* `sudo ifconfig wlan0 down` - disables wifi, saves ~30mA, can't be done when using a wifi remote, but maybe use a button on the Roomba/Create2 to turn it back on for while?
  * `dtoverlay=pi3-disable-wifi` in `/boot/config.txt` disables it between boots
* `echo 0 | sudo tee /sys/bus/usb/devices/1-1/bConfigurationValue | sudo tee /sys/bus/usb/devices/usb1/bConfigurationValue` - disables USB (+ ethernet and bluetooth), saves ~120mA, can't be done if the Roomba/Create2 is connected via USB, working on making a GPIO/serial connector
  * See page 2 of <https://www.irobotweb.com/-/media/MainSite/PDFs/About/STEM/Create/Create_2_Serial_to_33V_Logic.pdf>
  * Will end up using UART0 TX (physical pin 8, BCM 14), UART0 RX (phycial pin 10, BCM 15), one additional pin for BRC (recommended BCM17), and possibly grounds
  * Need to disable bluetooth (`dtoverlay=pi3-disable-bt=1` in `/boot/config.txt`) and BT modem server (`sudo systemctl disable hciuart`) to enable the 'good' UART port to be available, see <https://www.raspberrypi.org/documentation/configuration/uart.md>
  * Likely need to add `enable_uart=1` to `/boot/config.txt` and remove anything that looks like `console=serial0,115200` from `/boot/cmdline.txt`
    * Can also be setup with the `raspi-config` program
