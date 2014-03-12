#!/usr/bin/env python

from distutils.core import setup

setup(name='firmware_config',
      version='1.0',
      description='Python Firmware Configuration Utilities',
      author='Matthew Garrett',
      author_email='matthew.garrett@nebula.com',
      packages=['firmware_config', 'firmware_config.cisco', 'firmware_config.dell'],
)
