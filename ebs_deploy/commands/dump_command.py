
from ebs_deploy import out, get, parse_env_config, parse_option_settings

def add_arguments(parser):
    """
    adds arguments for the dump command
    """
    parser.add_argument('-e', '--environment', help='Environment name', required=True)

def execute(helper, config, args):
    """
    dump command dumps things
    """
    settings = parse_option_settings(get(parse_env_config(config, args.environment), 'option_settings', []))
    for setting in settings:
        out(str(setting))

