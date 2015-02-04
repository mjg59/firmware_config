#!/usr/bin/env python

import EfiCompressor
import firmware_config.ibm.EfiDecompressor
import struct
import time
import random
import pyghmi.exceptions
from lxml import etree
from pyghmi.ipmi import command

from firmware_config import FirmwareConfig
from firmware_config import exceptions as exc

IMM_NETFN = 0x2e
IMM_COMMAND = 0x90
IBM_ENTERPRISE = [0x4d, 0x4f, 0x00]

OPEN_RO_COMMAND = [0x01, 0x05, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00, 0x10]
OPEN_WO_COMMAND = [0x01, 0x03, 0x01]
READ_COMMAND = [0x02]
WRITE_COMMAND = [0x03]
CLOSE_COMMAND = [0x05]
SIZE_COMMAND = [0x06]


class IBMFirmwareConfig(FirmwareConfig):
    def __init__(self, host, user, password):
        self.connection = None
        super(IBMFirmwareConfig, self).__init__(host, user, password)

    def imm_connect(self, host, username, password):
        try:
            connection = command.Command(bmc=host, userid=username,
                                         password=password)
        except pyghmi.exceptions.IpmiException:
            raise exc.AuthException

        assert connection is not None
        self.connection = connection

    def imm_size(self, filename):
        data = []
        data += IBM_ENTERPRISE
        data += SIZE_COMMAND
        for i in range(len(filename)):
            data += [ord(filename[i])]

        response = self.connection.raw_command(netfn=IMM_NETFN,
                                               command=IMM_COMMAND, data=data)

        size = ''.join(chr(c) for c in response['data'][3:7])

        size = struct.unpack("i", size)
        return size[0]

    def imm_open(self, filename, write=False, size=None):
        response = None
        retries = 6
        data = []
        data += IBM_ENTERPRISE
        if write is False:
            data += OPEN_RO_COMMAND
        else:
            assert size is not None
            data += OPEN_WO_COMMAND
            hex_size = struct.pack("<I", size)
            for byte in hex_size[:4]:
                data += [ord(byte)]
            data += [0x01, 0x10]
        for i in range(len(filename)):
            data += [ord(filename[i])]
        while len(data) < 38:
            data += [0x00]

        while retries:
            retries = retries-1
            response = self.connection.raw_command(netfn=IMM_NETFN,
                                                   command=IMM_COMMAND,
                                                   data=data)
            try:
                if response['code'] == 0 or retries == 0:
                    break
            except KeyError:
                pass

            time.sleep(10)
            # Make sure that the connection hasn't timed out
            self.imm_connect(self.host, self.user, self.password)

        filehandle = ''.join(chr(byte) for byte in response['data'][3:7])

        filehandle = struct.unpack("<I", filehandle)[0]
        return filehandle

    def imm_close(self, filehandle):
        data = []
        data += IBM_ENTERPRISE
        data += CLOSE_COMMAND

        hex_filehandle = struct.pack("<I", filehandle)

        for byte in hex_filehandle[:4]:
            data += [ord(byte)]

        response = self.connection.raw_command(netfn=IMM_NETFN,
                                               command=IMM_COMMAND, data=data)

    def imm_write(self, filehandle, size, inputdata):
        blocksize = 0xc8
        offset = 0
        remaining = size

        hex_filehandle = struct.pack("<I", filehandle)

        while remaining > 0:
            data = []
            data += IBM_ENTERPRISE
            data += WRITE_COMMAND
            for byte in hex_filehandle[:4]:
                data += [ord(byte)]
            hex_offset = struct.pack("<I", offset)
            for byte in hex_offset[:4]:
                data += [ord(byte)]
            if remaining < blocksize:
                amount = remaining
            else:
                amount = blocksize
            for byte in inputdata[offset:offset+amount]:
                data += [ord(byte)]
            remaining -= blocksize
            offset += blocksize

            response = self.connection.raw_command(netfn=IMM_NETFN,
                                                   command=IMM_COMMAND,
                                                   data=data)

    def imm_read(self, filehandle, size):
        blocksize = 0xc8
        offset = 0
        output = []
        remaining = size

        hex_filehandle = struct.pack("<I", filehandle)
        hex_blocksize = struct.pack("<H", blocksize)

        while remaining > 0:
            data = []
            data += IBM_ENTERPRISE
            data += READ_COMMAND
            for byte in hex_filehandle[:4]:
                data += [ord(byte)]
            hex_offset = struct.pack("<I", offset)
            for byte in hex_offset[:4]:
                data += [ord(byte)]
            if remaining < blocksize:
                hex_blocksize = struct.pack("<H", remaining)
            for byte in hex_blocksize[:2]:
                data += [ord(byte)]
            remaining -= blocksize
            offset += blocksize

            response = self.connection.raw_command(netfn=IMM_NETFN,
                                                   command=IMM_COMMAND,
                                                   data=data)

            output += response['data'][5:]

        return ''.join(chr(c) for c in output)

    def factory_reset(self):
        options = self.get_fw_options()
        for option in options:
            if options[option]['is_list']:
                options[option]['new_value'] = [options[option]['default']]
            else:
                options[option]['new_value'] = options[option]['default']
        self.set_fw_options(options)

    def get_fw_options(self):
        options = {}
        for i in range(0, 10):
            self.imm_connect(self.host, self.user, self.password)
            filehandle = self.imm_open("config.efi")
            size = self.imm_size("config.efi")
            data = self.imm_read(filehandle, size)
            self.imm_close(filehandle)
            data = EfiDecompressor.Decompress(data)
            if len(data) != 0:
                break;

            time.sleep(10)

        xml = etree.fromstring(data)

        for config in xml.iter("config"):
            ibm_id = config.get("ID")
            for group in config.iter("group"):
                ibm_group = group.get("ID")
                for setting in group.iter("setting"):
                    is_list = False
                    ibm_setting = setting.get("ID")
                    possible = []
                    current = None
                    default = None
                    reset = False
                    name = setting.find("mriName").text

                    if setting.find("list_data") is not None:
                        is_list = True
                        current = []

                    for choice in setting.iter("choice"):
                        label = choice.find("label").text
                        possible.append(label)
                        instance = choice.find("instance")
                        if instance is not None:
                            if is_list:
                                current.append(label)
                            else:
                                current = label
                        if choice.get("default") == "true":
                            default = label
                        if choice.get("reset-required") == "true":
                            reset = True
                    optionname = "%s.%s" % (ibm_id, name)
                    options[optionname] = dict(current=current,
                                               default=default,
                                               possible=possible,
                                               pending=None,
                                               new_value=None,
                                               is_list=is_list,
                                               ibm_id=ibm_id,
                                               ibm_group=ibm_group,
                                               ibm_setting=ibm_setting,
                                               ibm_reboot=reset,
                                               ibm_instance="")

        return options

    def set_fw_options(self, options):
        reboot = False
        changes = False
        random.seed()
        ident = 'ASU-%x-%x-%x-0' % (random.getrandbits(48),
                                    random.getrandbits(32),
                                    random.getrandbits(64))

        configurations = etree.Element('configurations', ID=ident,
                                       type='update', update='ASU Client')

        for option in options.keys():
            if options[option]['new_value'] is None:
                continue
            if options[option]['current'] == options[option]['new_value']:
                continue
            if options[option]['pending'] == options[option]['new_value']:
                continue

            options[option]['pending'] = options[option]['new_value']

            is_list = options[option]['is_list']
            count = 0
            changes = True
            config = etree.Element('config', ID=options[option]['ibm_id'])
            configurations.append(config)
            group = etree.Element('group', ID=options[option]['ibm_group'])
            config.append(group)
            setting = etree.Element('setting',
                                    ID=options[option]['ibm_setting'])
            group.append(setting)

            if is_list:
                container = etree.Element('list_data')
                setting.append(container)
            else:
                container = etree.Element('enumerate_data')
                setting.append(container)

            for value in options[option]['new_value']:
                choice = etree.Element('choice')
                container.append(choice)
                label = etree.Element('label')
                label.text = value
                choice.append(label)
                if is_list:
                    count += 1
                    instance = etree.Element('instance',
                                             ID=options[option]['ibm_instance'],
                                             order=str(count))
                else:
                    instance = etree.Element('instance',
                                             ID=options[option]['ibm_instance'])
                choice.append(instance)

            if options[option]['ibm_reboot'] is True:
                reboot = True

        if not changes:
            return

        xml = etree.tostring(configurations)
        data = EfiCompressor.FrameworkCompress(xml, len(xml))
        self.imm_connect(self.host, self.user, self.password)
        filehandle = self.imm_open("asu_update.efi", write=True,
                                   size=len(data))
        self.imm_write(filehandle, len(data), data)
        self.imm_close(filehandle)

        # FIXME - wait for commit

        if reboot is True:
            self.reboot_required = True

    def reboot_system(self, options):
        state = self.connection.get_power()
        if state['powerstate'] == 'on':
            self.connection.set_power("reset")
        else:
            self.connection.set_power("on")
