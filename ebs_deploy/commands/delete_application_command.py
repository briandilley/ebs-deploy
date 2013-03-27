
from ebs_deploy import out, get, parse_env_config, parse_option_settings

def add_arguments(parser):
    """
    Args for the delete application command
    """
    parser.add_argument('-w', '--dont-wait', help='Skip waiting for the app to be deleted', action='store_true')

def execute(helper, config, args):
    """
    Deletes an environment
    """
    helper.delete_application()

    # wait
    if not args.dont_wait:

        # get environments
        environment_names = []
        for env in helper.get_environments():
            environment_names.append(env['EnvironmentName'])

        # wait for them
        helper.wait_for_environments(environment_names, status='Terminated')
    return 0