# This file is executed on every boot (including wake-boot from deepsleep)
#import esp
#esp.osdebug(None)
#import webrepl
#webrepl.start()
import network

wlan = network.WLAN(network.STA_IF)
wlan.active(True)
while not wlan.active():
    pass
if not wlan.isconnected():
    wlan.connect("TELUS2317", "7mdjycn3pz")
    while not wlan.isconnected():
        pass
print("connected to:", wlan.config("essid"), "@", wlan.ifconfig())