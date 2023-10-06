## The Idea

Like many omg-will-this-ever-end projects, it started with a simple idea: why not install a sensor on my (snail)
mailbox to tell me when we get a delivery?

## TL;DR Version

It was a PITA journey with lots of pitfalls, but I finally have a reliably working sensor.

## Long Version

1. ### Original Design <br>

What I had in mind initially was to use a single RPi 4 in my garage to be both my garage door sensor (another project)
and mailbox sensor. The plan was to run a 2-conductor cable from said garage RPi 4 to my mailbox (about 50 feet). The
need for a 2-conductor cable was because I expected to house a reed switch in the mailbox. I ordered the cable and it
arrived a couple days later. I was careful to order outdoor-rated cable since it would be running down my driveway
to the mailbox.

2. ### Of Cables, Staples, and Glue<br>

Two issues came up fairly quickly. One was how to secure the cables to my driveway, and the other was how to secure it
inside the garage. After some research, I found
these ["landscape staples"](https://www.amazon.com/gp/product/B0B3XFFKRD/ref=ppx_yo_dt_b_search_asin_title?ie=UTF8&th=1)
to bolt down the cable along the driveway perimeter. Issue #1 solved. Issue #2 was trickier. I was concerned about the
cable length potentially interfering with the reed switch's ability to function correctly. With that in mind, I wanted
to avoid doing things like routing cable up and over my garage door - which would add several feet. After invoking The
Google several times, I
discovered [construction adhesive](https://www.amazon.com/gp/product/B015CJ94TQ/ref=ppx_yo_dt_b_search_asin_title?ie=UTF8&th=1)
which would let me glue the cable directly to concrete. This saved me probably 20 to 25 extra feet of cable.

3. ### Raspberry Pi 4<br>

At this point, I installed the RPi 4. I had done this plenty times before, so it was trivial to get it up and running in
"headless" mode. Python also wasn't a problem; I've been programming in it for many years. I used GPIO pin #23 and
GPIO pin #1 to connect to the reed switch. The mailbox had the reed switch installed by this time too. Brimming with
confidence, I fired up a simple script:

```python
import RPi.GPIO as GPIO
import time

GPIO_CONTACT_PIN = 23  # Physical pin 16

GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
GPIO.setup(GPIO_CONTACT_PIN, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

while True:
    if GPIO.input(GPIO_CONTACT_PIN):
        print('Input was HIGH')
    else:
        print('Input was LOW')
    time.sleep(1)
```

...and nothing worked. The switch only worked intermittently. Sometimes the RPi sensed the switch, sometimes not. At
other times it gave the wrong answer based on switch state. After much research, I created
this [thread](https://forums.raspberrypi.com/viewtopic.php?t=356246)
on the Raspberry Pi forum.

4. ### Fun with reed(ish) switches

By now it was obsessing about the cable length and how it could be the issue. It led to much googlation and the
possibility
I could damage the RPi because I did not have a resistor on the connection - or maybe a capacitor - opinions varied.
Much
time was spent chasing this down. In moment of desperation, I was reviewing the documentation from the reed switch
vendor
and came across this:<br>
![](.README_images/5d13c214.png)<br>
...which is exactly the [opposite](https://en.wikipedia.org/wiki/Reed_switch) of the Normally Open (NO)/Normally Closed
(NC) standard.<br><br>
Here is how it is supposed to work:<br>
_"The contacts are usually normally open, closing when a magnetic field is present, or they may be normally closed and
open when a magnetic field is applied. "_<br>
So I switched to the "incorrect" connection on the switch and it began to work - sorta. I did get the expected behavior
from the switch, but it was still intermittent. Sometimes when closing the mailbox door (and theoretically closing the
circuit) nothing would happen. The Python script did not sense any change. That convinced me to try using a more
powerful magnet to close the circuit (see pic below). I glued the new magnet to the mailbox door. Results improved.<br>
Now the script was behaving as expected most of the time and the switch properly closed the circuit when the door was
closed. Open was reported correctly too.<br>
But there was one remaining issue. There were still intermittent "open" and "close" states being reported
when nothing was being touched.

5. ### Enter Pico W<br>

Rather than continue to wrestle with cable length, resistors and/or capacitors, and potentially damaging my RPi, I
decided on another approach. Instead of a 50' switch connection, I would convert to a microcontroller (Pico W)
so that I could colocate it with the reed switch. The existing cable could be used to conduct the 5 volts needed
by the Pico.<br>
I installed the Pico in a small box, then connected the power and reed switch to it. The Pico box was then installed
under the mailbox (see pics below).

6. ### Micropython<br>

Now all I had to do was port my script over to Micropython. How hard could that be? Turns out it wasn't
very hard - but there are caveats.

- Monolithic. Basically a script runner
- Script responsible for everything.
- Problems maintaining connectivity - applied Watchdog - lived to regret that. Needed to periodically check wifi.
- Host naming didn't work. Turns out there is a 15-character limit.
- Needed to update while developing. Need OTA.

7. ### OTA? What OTA?<br>

- Saw OTA solutions on YouTube (mention names/videos)
- Decided to implement my own
- Need to support multiple repos
- Use the GitHub API to gather status
- Lotsa fun with generating SHA values for existing files

8. ### Fun with Classes<br>

Rarely written classes in Python. Had fun creating one.

9. ### Cognitive Complexity<br>

- Mailbox state handing was turning into spaghetti code. Cognitive Complexity complaints.
- Decided to create a mailbox class.
- FSM for mailbox states

10. ### Mem leaks R us<br>

- Crashes everywhere.
- Implemented traceback logging.
- Crash loops.
- Filled filesystem.
- Added max reset attempts handling
- Code riddled with exception handlers and garbage collection.
- Eventually narrowed problem down to "urequests" library.
- Added handlers, but still very unstable.
- Couldn't do OTA updates without crashing.
- Opened issue in Micropython lib repo

11. ### Back to embedded C<br>

- Began exploring FreeRTOS as a solution. OTA is supported via AWS.
- Got compilation working.
- Began work on FSM for mailbox states.
- Was in debugging mode when I heard from Sydney

12. ### Finally some good news<br>

- Need to issue a `response.close()` to requests.
- Not very Pythonic (IMHO), but it worked
- Mailbox scripts finally stable
- OTA working pretty well