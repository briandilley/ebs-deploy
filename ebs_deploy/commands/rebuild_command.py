
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
    cname_prefix = env_config.get('cname_prefix', None)
    real_env_name = helper.environment_name_for_cname(cname_prefix)

    helper.rebuild_environment(real_env_name)

    # wait
    if not args.dont_wait:
        helper.wait_for_environments(real_env_name, health='Green', status='Ready')