import os
import sys

from ebs_deploy import out

COMMAND_MODULE_SUFFIX = '_command.py'
COMMAND_MODULE_PATH = os.path.dirname(__file__)


def usage():
    commands = get_command_names()
    out("usage: ebs-deploy command [options | help]")
    out("Where command is one of:")
    for cmd in commands:
        out("    " + cmd)


def get_command_names():
    """
    Returns a list of command names supported
    """
    ret = []
    for f in os.listdir(COMMAND_MODULE_PATH):
        if os.path.isfile(os.path.join(COMMAND_MODULE_PATH, f)) and f.endswith(COMMAND_MODULE_SUFFIX):
            ret.append(f[:-len(COMMAND_MODULE_SUFFIX)])
    return ret


def get_command(name):
    """
    Returns a command module
    """
    try:
        result = get_command_without_error_checking(name)
    except:
        result = get_command_without_error_checking('help')
    return result


def get_command_without_error_checking(name):
    """
    Returns a command module
    """
    __import__('ebs_deploy.commands.' + name + '_command')
    return sys.modules['ebs_deploy.commands.' + name + '_command']
