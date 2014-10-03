
from ebs_deploy.commands import usage

def add_arguments(parser):
    """
    adds arguments for the help command
    """
    usage()
    exit(0)

def execute(helper, config, args):
    """
    empty command to allow help messages to work
    """
    pass

