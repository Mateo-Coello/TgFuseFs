
## TgFuseFs
This project was implemented following the guide developed by Davoli, Sbaraglia, Lodi & Maffei from the University of Bolognia. The
guide was introduced as a way for students to apply theoretical concepts from an operating systems class specifically a file system.
The implmentation was made using Python 3.10, pyfuse 3.2.1 (fuse bindings for python), asyncio 3.4.3 (python library for asynchronous
programming) and, telethon 1.25.0 (Telegram's API for python). The report of this project explains the basic notions of a file system and
comments on the implementation aspects of the TgFuseFs. The steps to initialize the file system are both presented in the project report
and in the demo video of the implementation. Recall that this implementation only works for distributions of Linux, with the one developed
by Davoli et al. being tested under Ubuntu and this implementation being tested under Arch Linux. 

### Steps to initialize TgFuseFs
1. Obtain your **api_id** and **api_hash** for Telegram authentication using the following url: https://core.telegram.org/api/obtaining_api_id
2. Set the static variables **api_id** and **api_hash** of the class TgFuseWrapper to yours (obtained in the previous step)
   within the *wrapper.py* file.
3. Execute the script *mktgfs.py* with your phone number as an argument as follows: *python3 mktgfs.py +[country-code][phone-number]*.
   For instance for a mexican phone number the script will be executed as follows: ***python3 mktgfs.py +524831212891***.
4. Create an empty directory to which the file system will be mounted, for instance: ***mkdir mnt***.
5. Execute tne script *tgfuse.py* with the directory name created and your phone number as arguments.
   For instance: ***python3 tgfuse.py mnt +524831212891***

Note: Watch the demo video of the implementation to know the functionalities of the file system. Only the commands presented are available,
commands like *mv* or *cp* could be added but are not ready to use from the beggining.  

### Reference
Davoli, R., Sbaraglia, D. M., Lodi, D. M., & Maffei, R. TgFuseFs: How High School Students Can Write a Filesystem Prototype.
