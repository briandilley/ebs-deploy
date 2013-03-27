
from ebs_deploy import out, get, parse_env_config, parse_option_settings

def execute(helper, config, args):
    """
    Lists solution stacks
    """
    out("Available solution stacks")
    for stack in helper.list_available_solution_stacks():
        out("    "+str(stack))
    return 0

