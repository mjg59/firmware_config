firmware_config

This module provides a broadly vendor-neutral interface for out of band
firmware configuration. It currently allows the retrieval and setting of
firmware values on Dell and Cisco hardware.

The interface is as follows:

firmware_config.create(vendor, host, user, password)
    vendor: cisco or dell
    host: hostname or IP address of the BMC on the system to be configured
    user: username for the BMC
    password: password for the bmc

firmware_config.get_fw_options()
    returns a dict of dicts. The key in the first dict is the name of the
    configuration option (this will vary between vendors and potentially
    between models from the same vendor). The inner dict contains the following
    keys:

    current: the current firmware configuration value
    pending: the updated firmware configuration value
    new_value: the desired firmware configuration value
    possible: the set of possible configuration values
    is_list: the firmware option takes a list of values. current, pending and new_value should be lists rather than strings.

firmware_config.set_fw_options(options)
    set firmware configuration values to those contained in options.

    options: a dict of dicts as described in get_fw_options().
             get_fw_options() must always be called before set_fw_options,
	     and the modified options passed back.

firmware_config.reboot()
    returns a boolean indicating whether or not the system must be rebooted
    in order to apply the pending changes

firmware_config.reboot_system()
    performs a reboot of the system. This should be used in preference to any
    other form of reboot, as it may set flags to inform the firmware to
    perform the updates

