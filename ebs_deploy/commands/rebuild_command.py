
from ebs_deploy import out, get, parse_env_config, parse_option_settings

def add_arguments(parser):
    """
    adds arguments for the rebuild command
    """
    parser.add_argument('-e', '--environment',  help='Environment name', required=True)
    parser.add_argument('-w', '--dont-wait',    help='Skip waiting for the init to finish', action='store_true')

def execute(helper, config, args):
    """
    Rebuilds an environment
    """
    env_config = parse_env_config(config, args.environment)
    helper.rebuild_environment(args.environment)

    # wait
    if not args.dont_wait:
        helper.wait_for_environments(args.environment, health='Green', status='Ready')