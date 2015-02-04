class FirmwareConfig(object):
    def __init__(self, host, user, password):
        self.reboot_required = False
        self.host = host
        self.user = user
        self.password = password

    def reboot(self):
        return self.reboot_required

import firmware_config.cisco as cisco
import firmware_config.dell as dell
import firmware_config.ibm as ibm


def create(vendor, host, user, password):
    if vendor == "cisco":
        return cisco.CiscoFirmwareConfig(host, user, password)
    elif vendor == "dell":
        return dell.DellFirmwareConfig(host, user, password)
    elif vendor == "ibm":
        return ibm.IBMFirmwareConfig(host, user, password)

    return None
