## The Idea

Like many omg-will-this-ever-end projects, it started with a simple idea: why not install a sensor on my (snail)
mailbox to tell me when we get a delivery?

## TL;DR Version

It was a long journey with lots of pitfalls. Wrote a lot more code than expected. But I finally have a
reliably working sensor.

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
which would let me glue the cable directly to concrete. This saved me cabling probably 20 to 25 extra feet (see pic
below).

3. ### Raspberry Pi 4<br>

At this point, I installed the RPi 4. I had done this plenty times before, so it was trivial to get it up and running in
"headless" mode. Python also wasn't a problem; I've been programming in it for many years. I used GPIO pin #23 and
GPIO pin #1 to connect to the reed switch. The mailbox had the switch installed by this time too. Brimming with
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
this [thread](https://forums.raspberrypi.com/viewtopic.php?t=356246) on the Raspberry Pi forum.

4. ### Fun with reed(ish) switches

By now it was obsessing about the cable length and how it could be the issue. It led to much googlation and discovering
the possibility I could damage the RPi because I did not have a resistor on the connection - or maybe a capacitor -
opinions varied. Much time was spent chasing this down. It was clear my design workable, but not optimum.<br>

In moment of desperation, I was reviewing the documentation from the reed switch vendor and came across this:<br>
![](.README_images/5d13c214.png)<br>
...which is exactly the [opposite](https://en.wikipedia.org/wiki/Reed_switch) of the Normally Open (NO)/Normally Closed
(NC) standard.<br><br>
Here is how it is **supposed** to work:<br>
_"The contacts are usually normally open, closing when a magnetic field is present, or they may be normally closed and
open when a magnetic field is applied. "_<br>
So I switched to the "incorrect" connection on the switch and it began to work - sorta. I did get the expected behavior
from the switch, but it was still intermittent. Sometimes when closing the mailbox door (and theoretically closing the
circuit) nothing would happen. The Python script did not sense any change. That convinced me to try using a more
powerful magnet to close the circuit (see pic below). I glued the new magnet to the mailbox door and saw
much improvement.<br>
Now the script was behaving as expected most of the time and the magnets properly closed the circuit when the door was
closed. Opening the door was reported correctly too.<br>
But there was one remaining issue. There were still intermittent "open" and "close" states being reported
when nothing was being touched. Frustrating.

5. ### Enter Pico W<br>

Rather than continue to wrestle with cable length, resistors and/or capacitors, and potentially damaging my RPi, I
decided on another approach. Instead of a 50' switch connection, I would abandon the RPi 4 and use a microcontroller
(Pico W). That way I could colocate it with the reed switch on the mailbox itself. The cable length issues would go
away and the existing cable could be used to conduct the 5 volts needed by the Pico. Much simpler design.<br>
I installed the Pico in a small box, then connected the power and reed switch to it. The Pico box was then installed
under the mailbox (see pics below). Everything was good to go in the hardware realm.

6. ### Micropython<br>

Now all I had to do was port my script over to Micropython. How hard could that be? Turns out it wasn't hard - but
there are caveats. <br>
In a sense, scripting on a microcontroller is monolithic. Things that are handled by the operating
system on a full-blown operating system have to be dealt with in Python (or rather Micropython). For example, it is
responsible for setting up and maintaining the Wi-Fi connection.<br>
Coding the Wi-Fi function was simple enough, but the connections were unstable. Had to recode it a few times before
I got stable, reliable connectivity. There were other little quirks too - like the fact that hostnames can only be
a max of 15 characters. After finding that out, my host naming started working.

7. ### OTA? What OTA?<br>

Up to this point, the Pico was USB attached to my laptop most of the time. I would code changes, download them, and
do testing. When satisfied with the results, I would then physically carry the unit to my mailbox and install it.
This got tedious fast. All of this coding-testing-recoding effort highlighted the fact that some kind of remote
updating facility was needed.<br>
Research on the subject revealed that Over-The-Air (OTA) updates were possible, but not yet standardized on the Pico.
The best solutions I found were git-based. That is, when a user committed something to git, the OTA process would
detect the changes and pull a copy onto the Pico. I really liked that design. I found some interesting YouTube videos
on the subject (like [here](https://www.youtube.com/watch?v=f1widOJYQDc&t=162s)
and [here](https://www.youtube.com/watch?v=UX87SrdqIoc)). <br>
They were good solutions. Both were really clever and interesting, but not exactly what I wanted. For example, in both
cases the expectation was that I would have to include an OTA module in all my repos. In other words, identical code
would have to be copied to each Pico project. That could turn into a maintenance problem. Any changes to the OTA
code would mean copying it and committing it in multiple places. I foresaw headaches. I have several Pico projects.<br>
So I decided to write my own OTA module to help mitigate the multiple copy issue.<br>
Yes, it was a major digression. But it would avoid much pain in the long run.

8. ### Fun with Micropython Classes<br>

Leveraging Tim McAleer's [work](https://github.com/kevinmcaleer/ota), I created my
own [OTA project](https://github.com/gamename/micropython-over-the-air-utility).<br>
It was time-consuming, but fun. I managed to circumvent the multiple copies issue by adding support for multiple repos.
Have a look at the project if you're interested.<br>

9. ### Cognitive Complexity<br>

Meanwhile, by mailbox code was turning into spaghetti. The linter I used, SonarLint, started complaining about
"Cognitive Complexity" (i.e. maintainability) issues. I agreed. <br>
What started out as a simple effort had turned into a substantial collection of flags and recursive if-elsif-else
(il)logic. It was becoming less and less comprehensible. <br>
The solution was to write a mailbox class containing a finite state machine (FSM). The result is the
`MailBoxStateMachine` in the `mailbox.py` file. It was another semi-digression, but well worth the time. I could offload
much of the logic in the main script by doing that. Now the `main.py` script just had to instantiate a mailbox object
along with the OTA object. Much better.

10. ### Mem Leaks R Us<br>

Then things went nuts. I was getting crashes all over the place. All of them were related to memory. At
first, I thought the issue was the Pico simply didn't have enough memory to support the new mailbox/OTA objects. Great,
I thought, the effort to write those classes was wasted.<br>
But I stuck with the debugging. Lots of logging and error-recovery code got written. I began logging all the
tracebacks to files. Forcing a restart of the Pico turned out to be a pretty good stopgap for the memory issues.
But that led to some crash-reload-crash loops. (At one point, I completely filled up the filesystem with traceback logs.
Recovering from that was an adventure.) That led to another stopgap where I would limit the number of system resets.
After crashing and reloading a set number of times, I would give up and let the system stay down.<br>
Eventually it became clear the problem was related to HTTPS GETs and POSTs. They seemed to cause a mem leak. After 6 or
so invocations of `requests.get()` or `requests.post()`, I would get some kind of memory exception. That gave me the
diagnostics I needed. I opened an [issue](https://github.com/micropython/micropython-lib/issues/741#issue-1920297025) in
`micropython-lib` and waited.

11. ### Back to embedded C<br>

I didn't know how long it could be before someone would respond. My experience has not always been a good with open
source projects. I assumed the worst and began researching options.<br>
In spite of what I was seeing on Micropython, I like the Pico. I wanted to stay with that platform. Maybe, I thought,
writing my app in C would be a more solid solution? There was, I knew, OTA support on FreeRTOS with Amazon Web Services
(AWS). Its been a while, but I've written in C and have lots of AWS experience. Why not give it a try?<br>
With some hesitation, I started down this new path. The setup for FreeRTOS was challenging, but I managed to get sample
apps (like `blink.c`) to work without much trouble. I coded a C app that was a close equivalent of the Micropython
version and began testing.<br>
Debugging was where it got interesting. Debugging an embedded app on a Pico is non-trivial. You have to load libraries
and toolchains. Then you need to assemble (or buy)
the "[PicoProbe](https://datasheets.raspberrypi.com/pico/getting-started-with-pico.pdf?_gl=1*pxb6kq*_ga*MTM4NDkzMjQzNS4xNjc4MTM5NDg3*_ga_22FD70LWDS*MTY5NjM4NDAxNi40Ny4xLjE2OTYzODQ2MjguMC4wLjA.)"
hardware dongle.<br>
There were major issues getting this rig to work. I couldn't set breakpoints or make GDB "see" the Pico. It turned
out I had to make app changes to accommodate it. I was working my way through the extensive set of debugging
requirements when I heard back from the micropython-lib folks... <br>

12. ### Some good news<br>

["jimmo"](https://github.com/jimmo) on GitHub informed me that I needed to make a simple change to my code and the
memory leaks should go away. Although the solution is not very 'pythonic' (Python should be doing its own garbage
collection), I was grateful he got back to me. Time to give this new fix a try.<br>
And it made a big difference. The memory problems disappeared. My Micropython code is now working pretty well. So far,
the mailbox code has been running multiple days without incident. I **think** I finally have the solution I set out to
create. It was a long, fun road - when it wasn't driving me nuts.

## Pictures

1. ### Corner of the garage were the cable joins the edge of the driveway<br>

![](.README_images/de4dfd91.png)

2. ### Cable secured to the garage entrance edge with the construction adhesive<br>

![](.README_images/406fff0c.png)

3. ### Example of how the cable is secured to the driveway's edge using landscape staples<br>

![](.README_images/886d5c11.png)

4. ### Cable going up the support pole to the mailbox (it required 3 holes to be drilled)<br>

![](.README_images/b1ac0302.png)

5. ### Box containing the Pico W

![](.README_images/fc90b915.png)

6. ### Underside of the Pico box. Note the magnets used to secure it under the mailbox.

![](.README_images/0f23a73e.png)

7. ### Contents of the Pico box. Note the Pico is not soldered to a board, but seated in a breakout board. Makes swapping the Pico very easy.<br>

![](.README_images/421630e3.png)

8. ### Reed switch inside the mailbox.<br>

![](.README_images/406b29af.png)

9. ### Closeup of the stronger magnets used to close the switch<br>

![](.README_images/55657797.png)

10. ### The Pico box installed underneath mailbox.

![](.README_images/06a3173f.png)