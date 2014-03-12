from lxml import etree
import urllib2
from firmware_config import FirmwareConfig


class CiscoFirmwareConfig(FirmwareConfig):
    def __init__(self, host, user, password):
        self.cookie = None
        super(CiscoFirmwareConfig, self).__init__(host, user, password)

    def cisco_firmware_request(self, data):
        xmldata = etree.tostring(data)
        req = urllib2.Request("https://%s/nuova" % self.host, xmldata)
        response = urllib2.urlopen(req)
        return etree.fromstring(response.read())

    def cisco_login(self):
        auth = etree.Element('aaaLogin', inName=self.user,
                             inPassword=self.password)
        response = self.cisco_firmware_request(auth)
        if response.get("response") != "yes":
            print etree.tostring(response)
            return False

        self.cookie = response.get("outCookie")
        if self.cookie is None:
            print "Unable to get auth cookie"
            return False

        return True

    def cisco_logout(self):
        auth = etree.Element('aaaLogout', cookie=self.cookie,
                             inCookie=self.cookie)
        response = self.cisco_firmware_request(auth)

    def get_boot_options(self):
        bootorder = {}
        bootdict = dict(default=[], possible=[], new_value=[], pending=[],
                        current=[], is_list=True)

        if self.cisco_login() is not True:
            return None

        config = etree.Element('configResolveClass', cookie=self.cookie,
                               inHierarchical="true", classId="lsbootDef")

        settings = self.cisco_firmware_request(config)

        self.cisco_logout()

        settings = settings.find('.//lsbootDef')
        for boot in settings:
            order = boot.get("order")
            if boot.tag == "lsbootVirtualMedia":
                if boot.get("access") == "read-only":
                    bootorder['virt-cdrom'] = order
                else:
                    bootorder['virt-fdd'] = order
            elif boot.tag == "lsbootLan":
                bootorder['lan'] = order
            elif boot.tag == 'lsbootStorage':
                bootorder['hdd'] = order
            elif boot.tag == 'lsbootEfi':
                bootorder['efi'] = order

        for bootitem in sorted(bootorder, key=bootorder.get):
            bootdict['current'].append(bootitem)

        return bootdict

    def factory_reset(self):
        options = self.get_fw_options()
        for option in options:
            options[option]['new_value'] = "platform-default"
        self.set_fw_options(options)

    def get_fw_options(self):
        options = {}

        if self.cisco_login() is not True:
            print "Failed to login"
            return

        config = etree.Element('configResolveClass', cookie=self.cookie,
                               inHierarchical="true", classId="biosSettings")

        settings = self.cisco_firmware_request(config)

        for setting in settings.iter("biosSettings"):
            for child in setting.iter():
                tag = child.tag
                cisco_rn = child.get("rn")
                for attribute in child.keys():
                    if attribute == "rn":
                        continue
                    options[attribute[2:]] = dict(current=child.get(attribute),
                                                  default=None, possible=None,
                                                  new_value=None, pending=None,
                                                  cisco_rn=cisco_rn,
                                                  cisco_tag=tag, is_list=False)

        self.cisco_logout()

        options['boot_order'] = self.get_boot_options()

        return options

    def set_boot_options(self, options):
        order = 1

        if options == "platform-default":
            return

        self.cisco_login()
        config = etree.Element('configConfMo',
                               dn='sys/rack-unit-1/boot-policy',
                               inHierarchical='true', cookie=self.cookie)
        inconfig = etree.Element('inConfig')
        lsbootdef = etree.Element('lsbootDef',
                                  dn="sys/rack-unit-1/boot-policy",
                                  rebootOnUpdate="no")
        config.append(inconfig)
        inconfig.append(lsbootdef)

        for option in options:
            if option == "lan":
                lan = etree.Element('lsbootLan', rn="lan-read-only",
                                    access="read-only", prot="pxe", type="lan",
                                    order=str(order))
                lsbootdef.append(lan)
            elif option == "virt-cdrom":
                cdrom = etree.Element('lsbootVirtualMedia', rn='vm-read-only',
                                      access="read-only", type="virtual-media",
                                      order=str(order))
                lsbootdef.append(cdrom)
            elif option == "virt-fdd":
                fdd = etree.Element('lsbootVirtualMedia', rn='vm-read-write',
                                    access="read-write", type="virtual-media",
                                    order=str(order))
                lsbootdef.append(fdd)
            elif option == "hdd":
                hdd = etree.Element('lsbootStorage', rn='storage-read-write',
                                    access='read-write', type='storage',
                                    order=str(order))
                local = etree.Element('lsbootLocalStorage', rn='local-storage')
                hdd.append(local)
                lsbootdef.append(hdd)
            elif option == "efi":
                efi = etree.Element('lsbootEfi', rn='efi-read-only',
                                    access="read-only", type='efi',
                                    order=str(order))
                lsbootdef.append(efi)
            order += 1

        response = self.cisco_firmware_request(config)
        self.cisco_logout()

    def set_fw_options(self, options):
        changes = False

        config = etree.Element('configConfMo',
                               dn='sys/rack-unit-1/bios/bios-settings',
                               inHierarchical='true')
        inconfig = etree.Element('inConfig')
        biossettings = etree.Element('biosSettings')

        config.append(inconfig)
        inconfig.append(biossettings)

        for option in options.keys():
            if options[option]['new_value'] is None:
                continue
            if options[option]['current'] == options[option]['new_value']:
                continue
            if options[option]['pending'] == options[option]['new_value']:
                continue

            if option == "boot_order":
                self.set_boot_options(options[option]['new_value'])
                self.reboot_required = True
                continue

            changes = True
            setting = etree.Element(options[option]['cisco_tag'],
                                    dn="sys/rack-unit-1/bios/bios-settings/%s"
                                    % options[option]['cisco_rn'])
            setting.set("vp%s" % option, options[option]['new_value'])
            biossettings.append(setting)

            options[option]['pending'] = options[option]['new_value']

        if not changes:
            return

        self.cisco_login()

        config.set('cookie', self.cookie)

        response = self.cisco_firmware_request(config)

        self.cisco_logout()

        if response.get("response") != "yes":
            return False

        self.reboot_required = True

        return True

    def reboot_system(self, options):
        self.cisco_login()

        config = etree.Element('configConfMo', dn='sys/rack-unit-1/',
                               cookie=self.cookie, inHierarchical='false')
        inconfig = etree.Element('inConfig')
        action = etree.Element('computeRackUnit', adminPower="cycle-immediate",
                               dn="sys/rack-unit-1")

        config.append(inconfig)
        inconfig.append(action)

        response = self.cisco_firmware_request(config)

        self.cisco_logout()

        if response.get("response") != "yes":
            return False

        return True
