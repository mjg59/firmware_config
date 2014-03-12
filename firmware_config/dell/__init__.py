import pywsman
import time
from firmware_config import FirmwareConfig


def generate_dell_selectors(name):
    return { "Name": "DCIM:%sService" % name,
             "SystemName": "DCIM:ComputerSystem",
             "SystemCreationClassName": "DCIM_ComputerSystem",
             "CreationClassName": "DCIM_%sService" % name }


def set_dell_selectors(client_options, selectors):
    for selector in selectors:
        client_options.add_selector(selector, selectors[selector])


def set_power_selectors(client_options):
    client_options.add_selector("Name", "pwrmgtsvc:1")
    client_options.add_selector("SystemName", "systemmc")
    client_options.add_selector("CreationClassName", "DCIM_CSPowerManagementService")
    client_options.add_selector("SystemCreationClassName", "DCIM_SPComputerSystem")
    return client_options


def generate_xml(method, schema, content):
    xml = '''<p:%s_INPUT xmlns:p="%s">''' % (method, schema)
    xml += content
    xml += '''</p:%s_INPUT>''' % method

    return xml


class DellFirmwareConfig(FirmwareConfig):
    def __init__(self, host, user, password):
        super(DellFirmwareConfig, self).__init__(host, user, password)

    def get_boot_options(self):
        options = {}
        client = self.get_dell_client()
        schema = "http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/root/dcim/DCIM_BootSourceSetting"
        client_options = pywsman.ClientOptions()

        #client_options.set_cim_namespace("root/dcim")
        boot_options = client.enumerate(client_options, None, schema)

        if boot_options is None:
            return options

        context = boot_options.context()

        while context:
            try:
                boot_option = client.pull(client_options, None, schema,
                                          context.__str__())
                context = boot_option.context()
                boot_option = boot_option.root().find(None,
                                                      "DCIM_BootSourceSetting")
                boot_type = boot_option.find(None, "BootSourceType").__str__()
                label = boot_option.find(None, "BootString").__str__()
                enabled = boot_option.find(None, "CurrentEnabledStatus").__str__()
                current = boot_option.find(None, "CurrentAssignedSequence").__str__()
                pendingpos = boot_option.find(None, "PendingAssignedSequence").__str__()
                pendingenabled = boot_option.find(None, "PendingEnabledStatus").__str__()
                boot_id = boot_option.find(None, "InstanceID").__str__()
                name = "BootOrder" + boot_type
                if name not in options:
                    options[name] = dict(current=[], default="", possible=[],
                                         pending=[], new_value=None, dell_id={},
                                         dell_enabled={}, dell_type=boot_type,
                                         dell_pending={}, dell_pendingenabled={},
                                         dell_boot=True, is_list=True)
                if enabled != "0":
                    options[name]['current'].append(label)
                options[name]['possible'].append(label)
                options[name]['dell_id'][label] = boot_id
                options[name]['dell_enabled'][label] = enabled
                options[name]['dell_pending'][pendingpos] = label
                options[name]['dell_pendingenabled'][label] = pendingenabled
                options[name]['dell_schema'] = 'BIOS'
                options[name]['dell_fqdd'] = 'BIOS.Setup.1-1'
            except AttributeError:
                break

        for name in options.keys():
            for i in range(len(options[name]['dell_pending'])):
                label = options[name]['dell_pending'][str(i)]
                if options[name]['dell_pendingenabled'][label] == "1":
                    options[name]['pending'].append(label)
        return options

    def get_options(self, name):
        schema = "http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/root/dcim/DCIM_%sEnumeration" % name
        tag = "DCIM_%sEnumeration" % name
        options = {}

        client = self.get_dell_client()

        client_options = pywsman.ClientOptions()

        firmware_options = client.enumerate(client_options, None, schema)

        if firmware_options is None:
            return options

        context = firmware_options.context()

        while context:
            try:
                firmware_option = client.pull(client_options, None, schema,
                                              context.__str__())
                context = firmware_option.context()
                firmware_option = firmware_option.root().find(None, tag)
                attribute_name = firmware_option.find(None, "AttributeName").__str__()
                current_value = firmware_option.find(None, "CurrentValue").__str__()
                pending_value = firmware_option.find(None, "PendingValue").__str__()
                default_value = firmware_option.find(None, "DefaultValue").__str__()
                fqdd = firmware_option.find(None, "FQDD").__str__()
                if fqdd == "None":
                    fqdd = None
                group_name = firmware_option.find(None, "GroupID").__str__()
                if group_name == "None":
                    group_name = ""
                    dell_name = attribute_name
                    option_name = "%s.%s" % (name, attribute_name)
                else:
                    if name == "BIOS" or name == "NIC":
                        dell_name = attribute_name
                    else:
                        dell_name = "%s#%s" % (group_name, attribute_name)
                    if name == "NIC":
                        option_name = "%s.%s.%s" % (name, fqdd,
                                                    attribute_name)
                    else:
                        option_name = "%s.%s.%s" % (name,
                                                    group_name,
                                                    attribute_name)

                possible_values = []
                possible = firmware_option.find(None, "PossibleValues")
                while possible:
                    possible_values.append(possible.__str__())
                    possible = possible.next()

                options[option_name] = dict(current=current_value,
                                            default=default_value,
                                            possible=possible_values,
                                            pending=pending_value,
                                            is_list=False,
                                            dell_boot=False,
                                            dell_schema=name,
                                            dell_name=dell_name,
                                            new_value=None,
                                            dell_fqdd=fqdd)
            except AttributeError:
                continue

        return options

    def get_fw_options(self):
        host_options = self.get_options("BIOS")
        lc_options = self.get_options("LC")
        idrac_options = self.get_options("iDRACCard")
        nic_options = self.get_options("NIC")
        boot_options = self.get_boot_options()

        # Merge with the boot options
        options = dict(host_options.items() + lc_options.items() +
                       idrac_options.items() + nic_options.items() +
                       boot_options.items())
        return options

    def wait_for_jobs(self, jobs):
        client = self.get_dell_client()
        schema = "http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/root/dcim/DCIM_LifecycleJob"
        client_options = pywsman.ClientOptions()
        pending = False

        while jobs:
            joblist = client.enumerate(client_options, None, schema)

            context = joblist.context()

            while not context:
                os.sleep(30)
                context = joblist.context()

            while context:
                job = client.pull(client_options, None, schema,
                                  context.__str__())
                context = job.context()
                jobid = job.root().find(None, "InstanceID").__str__()
                complete = job.root().find(None, "PercentComplete").__str__()
                if jobid not in jobs:
                    continue

                if complete == "100":
                    jobs.remove(jobid)
            if jobs:
                time.sleep(30)

    def set_nic_options(self, options):
        NICs = []
        result = True

        for option in options:
            if options[option]['dell_schema'] != "NIC":
                continue

            if options[option]['dell_fqdd'] not in NICs:
                NICs.append(options[option]['dell_fqdd'])

        for NIC in NICs:
            if self.set_options(options, "NIC", NIC) == False:
                result = False

        return result

    def set_boot_options(self, options):
        schema = "http://schemas.dell.com/wbem/wscim/1/cim-schema/2/DCIM_BootConfigSetting"
        method = "ChangeBootOrderByInstanceID"
        enable_method = "ChangeBootSourceState"
        changes = False

        client = self.get_dell_client()

        client_options = pywsman.ClientOptions()

        client_options.set_cim_namespace("root/dcim")

        xml = ""
        enable_xml = ""
        for option in options:
            if not options[option]['dell_boot']:
                continue

            # Skip option if we haven't been asked to set a value
            if options[option]['new_value'] is None:
                continue
            # Skip option if it matches the current state, as long as there's
            # no outstanding pending changes
            if options[option]['current'] == options[option]['new_value']:
                if options[option]['pending'] == []:
                    continue

            # Skip option if it matches the already pending state
            if options[option]['pending'] == options[option]['new_value']:
                continue

            changes = True

            boot_type = options[option]['dell_type']
            for boot in options[option]['new_value']:
                boot_id = options[option]['dell_id'][boot]
                enabled = options[option]['dell_enabled'][boot]
                xml += "<p:source>%s</p:source>" % boot_id
                enable_xml += "<p:EnabledState>1</p:EnabledState>"
                enable_xml += "<p:source>%s</p:source>" % boot_id

        if not changes:
            return True

        enable_xml = generate_xml(enable_method, schema, enable_xml)
        client_options.add_selector("InstanceID", boot_type)
        wsxml = pywsman.create_doc_from_string(enable_xml)
        result = client.invoke(client_options, schema, enable_method, wsxml)

        if result is None:
            return False

        status = result.root().find(None, "ReturnValue")
        if status is None:
            return False

        status = status.__str__()

        if status == "2":
            return False

        xml = generate_xml(method, schema, xml)
        wsxml = pywsman.create_doc_from_string(xml)
        result = client.invoke(client_options, schema, method, wsxml)

        if result is None:
            return False

        status = result.root().find(None, "ReturnValue")
        if status is None:
            return False

        status = status.__str__()

        if status != "0":
            return False

    def set_options(self, options, name, settings_type):
        changes = False
        schema = "http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/root/dcim/DCIM_%sService" % name
        method = "SetAttributes"

        if settings_type:
            xml = "<p:Target>%s</p:Target>" % settings_type
        else:
            xml = ""

        for option in options.keys():
            if options[option]['dell_schema'] != name:
                continue

            # Each NIC needs to have settings applied separately. Skip any
            # that we haven't been asked to handle.
            fqdd = options[option]['dell_fqdd']
            if fqdd and fqdd != settings_type:
                continue

            # Skip option if we haven't been asked to set a value
            if options[option]['new_value'] is None:
                continue

            # Skip option if it matches the current state, as long as there's
            # no outstanding pending changes
            if options[option]['current'] == options[option]['new_value']:
                if options[option]['pending'] == []:
                    continue

            # Boot options are somewhat magic, so handle them specially
            if options[option]['dell_boot']:
                continue

            changes = True

            xml += "<p:AttributeName>%s</p:AttributeName>\r\n" % options[option]['dell_name']
            xml += "<p:AttributeValue>%s</p:AttributeValue>\r\n" % options[option]['new_value']

        if not changes:
            return True

        xml = generate_xml(method, schema, xml)

        wsxml = pywsman.create_doc_from_string(xml)

        client = self.get_dell_client()
        client_options = pywsman.ClientOptions()
        selectors = generate_dell_selectors(name)
        set_dell_selectors(client_options, selectors)

        result = client.invoke(client_options, schema, method, wsxml)

        if result is None:
            return False

        status = result.root().find(None, "ReturnValue")
        if status is None:
            return False

        status = status.__str__()

        if status != "0":
            return False

        reboot = result.root().find(None, "RebootRequired")
        if reboot is not None:
            reboot = reboot.__str__()
            if reboot == "Yes":
                self.reboot_required = True

        if name == "LC":
            method = "CreateConfigJob"
            result = client.invoke(client_options, schema, method, None)

        if name == "iDRACCard":
            client = self.get_dell_client()
            client_options = pywsman.ClientOptions()
            method = "CreateTargetedConfigJob"
            xml = "<p:Target>%s</p:Target> \
<p:ScheduledStartTime>TIME_NOW</p:ScheduledStartTime>" % \
            settings_type

            xml = generate_xml(method, schema, xml)
            wsxml = pywsman.create_doc_from_string(xml)

            selectors = generate_dell_selectors(name)
            set_dell_selectors(client_options, selectors)
            client_options.set_cim_namespace("root/dcim")
            result = client.invoke(client_options, schema, method, wsxml)

    def set_fw_options(self, options):
        ret = True

        if self.set_options(options, "BIOS", "BIOS.Setup.1-1") == False:
            ret = False

        if self.set_options(options, "LC", None) == False:
            ret = False

        if self.set_options(options, "iDRACCard", "iDRAC.Embedded.1") == False:
            ret = False

        if self.set_nic_options(options) == False:
            ret = False

        if self.set_boot_options(options) == False:
            ret = False

        return ret

    def factory_reset(self):
        schema = "http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/root/dcim/DCIM_LCService"
        method = "LCWipe"
        client = self.get_dell_client()

        client_options = pywsman.ClientOptions()
        selectors = generate_dell_selectors("LC")
        set_dell_selectors(client_options, selectors)

        result = client.invoke(client_options, schema, method, None)

    def force_reboot(self):
        schema = "http://schemas.dell.com/wbem/wscim/1/cim-schema/2/DCIM_CSPowerManagementService"
        client = self.get_dell_client()
        client_options = pywsman.ClientOptions()
        method = "RequestPowerStateChange"

        xml = '''<p:PowerState>5</p:PowerState>'''
        xml = generate_xml(method, schema, xml)

        wsxml = pywsman.create_doc_from_string(xml)

        set_power_selectors(client_options)

        result = client.invoke(client_options, schema, method, wsxml)

        if result is None:
            return False

        status = result.root().find(None, "ReturnValue").__str__()

        if status == '0':
            return True

        return False

    def really_apply_settings(self, type, target):
        xml = ""
        schema = "http://schemas.dmtf.org/wbem/wscim/1/cim-schema/2/root/dcim/DCIM_%sService" % type
        method = "CreateTargetedConfigJob"
        client = self.get_dell_client()

        client_options = pywsman.ClientOptions()
        selectors = generate_dell_selectors(type)
        set_dell_selectors(client_options, selectors)

        xml = '''<p:Target>%s</p:Target>
        <p:RebootJobType>2</p:RebootJobType>
        <p:ScheduledStartTime>TIME_NOW</p:ScheduledStartTime>''' % target

        xml = generate_xml(method, schema, xml)

        wsxml = pywsman.create_doc_from_string(xml)

        result = client.invoke(client_options, schema, method, wsxml)

        if result is None:
            return None

        status = result.root().find(None, "ReturnValue").__str__()

        if status == '0' or status == '4096':
            selector = result.root().find(None, "Selector")
            while selector:
                attr = selector.attr_find(None, 'Name')
                if attr.value() == 'InstanceID':
                    return selector.__str__()
                selector = selector.next()

        return None

    def apply_settings(self, options):
        fqdds = {}
        jobs = []
        success = True

        if options is None:
            return success

        for option in options:
            if not options[option]['new_value'] and \
               not options[option]['pending']:
                continue
            if options[option]['dell_fqdd'] not in fqdds:
                fqdd = options[option]['dell_fqdd']
                schema = options[option]['dell_schema']
                fqdds[fqdd] = schema

        for fqdd in fqdds:
            if fqdds[fqdd] == "LC" or fqdds[fqdd] == "iDRAC":
                continue
            job = self.really_apply_settings(fqdds[fqdd], fqdd)
            if job is None:
                success = False
            else:
                jobs.append(job)

        if jobs:
            self.wait_for_jobs(jobs)

        return success

    def reboot_system(self, options):
        if self.apply_settings(options) == False:
            self.force_reboot()

    def get_dell_client(self):
        client = pywsman.Client("https://%s:%s@%s:443/wsman" % (self.user, self.password, self.host))

        client.transport().set_verify_host(0)
        client.transport().set_verify_peer(0)

        return client
