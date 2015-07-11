import time
from ebs_deploy import out, get, parse_env_config, parse_option_settings, upload_application_archive
from datetime import datetime

def add_arguments(parser):
    """
    adds arguments for the describe events command
    """
    parser.add_argument('-e', '--environment', help='Environment name', required=True)


def execute(helper, config, args):
    """
    Describes recent events for an environment.
    """
    environment_name = args.environment

    (events, next_token) = helper.describe_events(environment_name, start_time=datetime.now().isoformat())

    # swap C-Names
    for event in events:
        print("["+event['Severity']+"] "+event['Message'])
