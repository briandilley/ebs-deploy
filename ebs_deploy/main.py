#!/usr/bin/env python

import argparse
import yaml
import sys
import os
import logging
from boto.sts import STSConnection
from ebs_deploy import AwsCredentials, EbsHelper, get, out, init_logging, configure_logging
from ebs_deploy.commands import get_command, usage


def parse_args(argv, **defaults):
    # bail if we don't have a command
    if len(argv) < 2:
        usage()
        return -1

    # get the command
    command_name = argv[1]

    # setup arguments
    parser = argparse.ArgumentParser(description='Deploy to Amazon Beanstalk', usage='%(prog)s '+command_name+' [options]')
    parser.set_defaults(**defaults)
    parser.add_argument('-c', '--config-file', help='Configuration file', default='ebs.config')
    parser.add_argument('-v', '--verbose', help='Enable debug logging', action='store_true')
    parser.add_argument('-lg', '--use-logging', help='Use Python logging instead of stdout', action='store_true')
    parser.add_argument('-ra', '--role-arn', help='Role ARN to switch to (ie: arn:aws:iam::111111111111:role/RoleName)', required=False)
    parser.add_argument('-rn', '--role-name', help='Set display name for role (If using --role-arn, this is required)', required=False)
    parser.add_argument('-wt', '--wait-time', help='timeout for command', required=False, type=int, default=300)
    command = get_command(command_name)

    # let commands add arguments
    try:
        command.add_arguments(parser)
    except AttributeError:
        pass

    # check for help
    if len(argv) == 3 and argv[2] == 'help':
        parser.print_help()
        return -1

    # parse arguments
    args = parser.parse_args(argv[2:])

    return command, args, parser


def load_config(config_file):
    # load config
    with open(config_file, 'r') as f:
        contents = f.read()
    contents_with_environment_variables_expanded = os.path.expandvars(contents)
    return yaml.load(contents_with_environment_variables_expanded)


def make_aws_credentials(config, role_arn=None, role_name=None):
    if role_arn:
        try:
            sts_connection = STSConnection()
            assumedRoleObject = sts_connection.assume_role(
                role_arn=role_arn,
                role_session_name=role_name
            )
        except:
            out("Oops! something went wrong trying to assume the specified role")
        else:
            # create credentials for switching roles
            aws = AwsCredentials(
                assumedRoleObject.credentials.access_key,
                assumedRoleObject.credentials.secret_key,
                assumedRoleObject.credentials.session_token,
                get(config, 'aws.region',           os.environ.get('AWS_DEFAULT_REGION')),
                get(config, 'aws.bucket',           os.environ.get('AWS_BEANSTALK_BUCKET_NAME')),
                get(config, 'aws.bucket_path',      os.environ.get('AWS_BEANSTALK_BUCKET_NAME_PATH')))
            out("Using Role: "+role_name)
    else:
        # create credentials
        aws = AwsCredentials(
            get(config, 'aws.access_key',       os.environ.get('AWS_ACCESS_KEY_ID')),
            get(config, 'aws.secret_key',       os.environ.get('AWS_SECRET_ACCESS_KEY')),
            get(config, 'aws.secret_token',     os.environ.get('AWS_SECRET_TOKEN')),
            get(config, 'aws.region',           os.environ.get('AWS_DEFAULT_REGION')),
            get(config, 'aws.bucket',           os.environ.get('AWS_BEANSTALK_BUCKET_NAME')),
            get(config, 'aws.bucket_path',      os.environ.get('AWS_BEANSTALK_BUCKET_NAME_PATH')))
    return aws


# the commands
def run_ebs_deploy(command, args, parser=None):
    """
    the main
    """
    init_logging(args.use_logging)

    # make sure we have an archive or a directory
    if not args.config_file or not os.path.exists(args.config_file):
        out("Config file not found: "+args.config_file)
        parser and parser.print_help()
        return -1

    # make sure that if we have a role to assume, that we also have a role name to display
    if (args.role_arn and not args.role_name) or (args.role_name and not args.role_arn):
        out("You must use and --role-arn and --role-name together")
        parser and parser.print_help()
        return -1

    # enable logging
    if args.verbose:
        from boto import set_stream_logger
        set_stream_logger('boto')

    config = load_config(args.config_file)
    aws = make_aws_credentials(config, args.role_arn, args.role_name)
    helper = EbsHelper(aws, app_name=get(config, 'app.app_name'), wait_time_secs=args.wait_time)

    # execute the command
    return command.execute(helper, config, args)


def main():
    command, args, parser = parse_args(sys.argv)
    if args.use_logging:
        logging.basicConfig()
        configure_logging(logging.INFO, logging.root.handlers)
    rc = run_ebs_deploy(command, args, parser)
    exit(rc)


# start the madness
if __name__ == "__main__":
    main()
