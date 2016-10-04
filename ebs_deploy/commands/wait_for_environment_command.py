import time
from ebs_deploy import out, get, parse_env_config, parse_option_settings, upload_application_archive
from datetime import datetime

def add_arguments(parser):
    """
    adds arguments for the describe events command
    """
    parser.add_argument('-e', '--environment', help='Environment name', required=True)
    parser.add_argument('-hl', '--health', help='The health to wait for', required=True)


def execute(helper, config, args):
    """
    Waits for an environment to be healthy
    """
    helper.wait_for_environments(args.environment, health=args.health)