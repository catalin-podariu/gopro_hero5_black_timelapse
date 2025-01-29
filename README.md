
`

                     .d8888b.           8888888b.                                     
                    d88P  Y88b          888   Y88b                        o           
                    888    888          888    888                       d8b          
                    888         .d88b.  888   d88P 888d888  .d88b.      d888b     ©    
                    888  88888 d88""88b 8888888P"  888P"   d88""88b "Y888888888P"     
                    888    888 888  888 888        888     888  888   "Y88888P"       
                    Y88b  d88P Y88..88P 888        888     Y88..88P   d88P"Y88b       
                     "Y8888P88  "Y88P"  888        888      "Y88P"   dP"     "Yb      
        88888888888 d8b                        888                                    
            888     Y8P                        888                                    
            888                                888                                    
            888     888 88888b.d88b.   .d88b.  888  8888b.  88888b.  .d8888b   .d88b. 
            888     888 888 "888 "88b d8P  Y8b 888     "88b 888 "88b 88K      d8P  Y8b
            888     888 888  888  888 88888888 888 .d888888 888  888 "Y8888b. 88888888
            888     888 888  888  888 Y8b.     888 888  888 888 d88P      X88 Y8b.    
            888     888 888  888  888  "Y8888  888 "Y888888 88888P"   88888P'  "Y8888 
                                                            888                       
                                                            888                       
                                                            888  script by @mrbigheart

`


# Abstract

*Did you ever want to create an ultra-long GoPro time-lapse without special equipment? I'm using here a 
GoPro Hero5 Black ..which as of 2025 is already very old :)*
<br>
<br>
*This project provides a Python-based solution to automate the entire workflow, with the help of a Raspberry Pi (v4 in this case). 
It handles wifi switching between the rpi and the GoPro, configurable periodic photo captures, 
keeps the system time in sync and even sends alerts if something goes wrong. Most of this is configurable.
Designed to run continuously with the help of `timelapse.service`, it ensures the timelapse runs 
smoothly for extended periods with minimal intervention (hopefully none).*

*This was designed for a six month timelapse, taking three photos per hour. But feel free to adapt it.*

<br>
<br>

# Typical Flow

### **Waiting**
This is where we spend most of the time. We check if it's time to take a photo or time to keep the wifi alive.
<br>
<br>
The script starts in `WAITING`, and connects to the GoPro wifi. Every 5 seconds, it checks if is time to take a photo.
If it’s not time, it will call `keep_alive()` and keep the GoPro wifi available. This is the most important part of the 
script because the GoPro will go to sleep after a few minutes of inactivity. If this happens.. there's no way to get it 
back. See the error handling, lower. But, as the script is written now, this doesn't happen even if the power goes out 
for 1..2 minutes.

### **Taking Photos**
When it's time to take a photo, the script transitions to `TAKE_PHOTO`. If the rpi isn’t on the GoPro wifi, it switches,
wakes up the camera, takes a photo, then we transition to `SEND_UPDATE`.

### **Sending Updates**
Once a photo is taken, the script switches to your router wifi (`SEND_UPDATE`), synchronizes the system time, and sends 
a status push to PushBullet, then it saves the state and then switches back to the GoPro wifi (`WAITING`). 

### **Error Handling**
If there is a file missing, or we get (mostly) any other error, the script doesn't fail. BUT! If we can't connect to the
GoPro wifi.. which is the most important thing, the script goes to `ERROR` where retries a few times, and if it is still 
failing.. it goes into `OFFLINE_ALERT`. This means it sends push notifications every twenty minutes, until connectivity 
is restored. But this means user intervention is needed. Unfortunately, the GoPro can't be 'restarted'. Or, not in any 
way I tried so far. *So, if you're going to use this script, you need to be aware of this!*

### **Service Mode**
A systemd unit file `timelapse.service` runs this script at boot. Beware of permissions and all that.
Also, there's a `crontab` that makes sure this doesn't get stuck in a GoPro operation. I've removed the photo count,
for example, because this will get stuck, every now and then, with no warning. And it'll halt the script. But the cronjob
will restart the service if it's not writing in the logs for more than 40 seconds.

#

## Good to know

The rpi is isolated most of the time, from the outside world. That's why we sync the time and we send push notifications
once an hour. This is to make sure the rpi is still alive and kicking. If we need to change the behavior remotely, we can
create a AWS server that can be checked every time we 'surface' and if so, we download and replace the new config.
Unless you keep the setup in a remote location.. this is not needed. But it's an idea.


Enjoy! :)

P.S. _If you're gonna' whine about the monkey-patch or the ASCII art.. save it!<br>
I like it._
