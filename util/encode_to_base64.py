#!/usr/bin/env python3

import base64

# Use this to encode your passwords and then paste them in the config.json file
# AND THEN.. remove the original passwords from here!

def encode_config_pwd():
    router_pwd = base64.b64encode("[PWD_HERE]".encode("utf-8"))
    gopro_pwd = base64.b64encode("[PWD_HERE]".encode("utf-8"))

    print("Encoded passwords")
    print(f"wifi {router_pwd}")
    print(f"GoPro {gopro_pwd}")

    print("Decoded passwords")
    print(base64.b64decode(router_pwd).decode("utf-8"))
    print(base64.b64decode(gopro_pwd).decode("utf-8"))

encode_config_pwd()
