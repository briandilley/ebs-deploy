from boto.exception import S3ResponseError
from boto.s3.connection import S3Connection
from boto.beanstalk import connect_to_region
from boto.s3.key import Key

from datetime import datetime
from time import time, sleep
import zipfile
import os
import subprocess
import sys
import yaml
import re


def out(message):
    """
    print alias
    """
    sys.stdout.write(message + "\n")
    sys.stdout.flush()


def merge_dict(dict1, dict2):
    ret = dict(dict2)
    for key, val in dict1.items():
        val2 = dict2.get(key)
        if val2 is None:
            ret[key] = val
        elif isinstance(val, dict) and isinstance(val2, dict):
            ret[key] = merge_dict(val, val2)
        elif isinstance(val, (list)) and isinstance(val2, (list)):
            ret[key] = val + val2
        else:
            ret[key] = val2
    return ret


def get(vals, key, default_val=None):
    """
    Returns a dictionary value
    """
    val = vals
    for part in key.split('.'):
        if isinstance(val, dict):
            val = val.get(part, None)
            if val is None:
                return default_val
        else:
            return default_val
    return val


def parse_option_settings(option_settings):
    """
    Parses option_settings as they are defined in the configuration file
    """
    ret = []
    for namespace, params in option_settings.items():
        for key, value in params.items():
            ret.append((namespace, key, value))
    return ret


def parse_env_config(config, env_name):
    """
    Parses an environment config
    """
    all_env = get(config, 'app.all_environments', {})
    env = get(config, 'app.environments.' + str(env_name), {})
    return merge_dict(all_env, env)


def upload_application_archive(helper, env_config, archive=None, directory=None, version_label=None):
    if version_label is None:
        version_label = datetime.now().strftime('%Y%m%d_%H%M%S')
    archive_file_name = None
    if archive:
        archive_file_name = os.path.basename(archive)

    # generate the archive externally
    if get(env_config, 'archive.generate'):
        cmd = get(env_config, 'archive.generate.cmd')
        output_file = get(env_config, 'archive.generate.output_file')
        use_shell = get(env_config, 'archive.generate.use_shell', True)
        exit_code = get(env_config, 'archive.generate.exit_code', 0)
        if not cmd or not output_file:
            raise Exception('Archive generation requires cmd and output_file at a minimum')
        output_regex = None
        try:
            output_regex = re.compile(output_file)
        except:
            pass
        result = subprocess.call(cmd, shell=use_shell)
        if result != exit_code:
            raise Exception('Generate command execited with code %s (expected %s)' % (result, exit_code))

        if output_file and os.path.exists(output_file):
            archive_file_name = os.path.basename(output_file)
        else:
            for root, dirs, files in os.walk(".", followlinks=True):
                for f in files:
                    fullpath = os.path.join(root, f)
                    if fullpath.endswith(output_file):
                        archive = fullpath
                        archive_file_name = os.path.basename(fullpath)
                        break
                    elif output_regex and output_regex.match(fullpath):
                        archive = fullpath
                        archive_file_name = os.path.basename(fullpath)
                        break
                if archive:
                    break
            if not archive or not archive_file_name:
                raise Exception('Unable to find expected output file matching: %s' % (output_file))

    # create the archive
    elif not archive:
        if not directory:
            directory = "."
        includes = get(env_config, 'archive.includes', [])
        excludes = get(env_config, 'archive.excludes', [])
        archive_files = get(env_config, 'archive.files', [])

        def _predicate(f):
            for exclude in excludes:
                if re.match(exclude, f):
                    return False
            if len(includes) > 0:
                for include in includes:
                    if re.match(include, f):
                        return True
                return False
            return True
        archive = create_archive(directory, str(version_label) + ".zip", config=archive_files, ignore_predicate=_predicate)
        archive_file_name = str(version_label) + ".zip"

    helper.upload_archive(archive, archive_file_name)
    helper.create_application_version(version_label, archive_file_name)
    return version_label


def create_archive(directory, filename, config={}, ignore_predicate=None, ignored_files=['.git', '.svn']):
    """
    Creates an archive from a directory and returns
    the file that was created.
    """
    zip = zipfile.ZipFile(filename, 'w', compression=zipfile.ZIP_DEFLATED)
    root_len = len(os.path.abspath(directory))

    # create it
    out("Creating archive: " + str(filename))
    for root, dirs, files in os.walk(directory, followlinks=True):
        archive_root = os.path.abspath(root)[root_len + 1:]
        for f in files:
            fullpath = os.path.join(root, f)
            archive_name = os.path.join(archive_root, f)

            # ignore the file we're creating
            if filename in fullpath:
                continue

            # ignored files
            if ignored_files is not None:
                for name in ignored_files:
                    if fullpath.endswith(name):
                        out("Skipping: " + str(name))
                        continue

            # do predicate
            if ignore_predicate is not None:
                if not ignore_predicate(archive_name):
                    out("Skipping: " + str(archive_name))
                    continue

            out("Adding: " + str(archive_name))
            zip.write(fullpath, archive_name, zipfile.ZIP_DEFLATED)

    # add config
    for conf in config:
        for conf, tree in conf.items():
            if tree.has_key('yaml'):
                content = yaml.dump(tree['yaml'], default_flow_style=False)
            else:
                content = tree.get('content', '')
            out("Writing config file for " + str(conf))
            zip.writestr(conf, content)

    zip.close()
    return filename


class AwsCredentials:
    """
    Class for holding AwsCredentials
    """

    def __init__(self, access_key, secret_key, region, bucket, bucket_path):
        self.access_key = access_key
        self.secret_key = secret_key
        self.bucket = bucket
        self.region = region
        self.bucket_path = bucket_path
        if not self.bucket_path.endswith('/'):
            self.bucket_path += '/'


class EbsHelper(object):
    """
    Class for helping with ebs
    """

    def __init__(self, aws, app_name=None):
        """
        Creates the EbsHelper
        """
        self.aws = aws
        self.ebs = connect_to_region(aws.region, aws_access_key_id=aws.access_key,
                                     aws_secret_access_key=aws.secret_key)
        self.s3 = S3Connection(aws.access_key, aws.secret_key, host=(
            lambda r: 's3.amazonaws.com' if r == 'us-east-1' else 's3-' + r + '.amazonaws.com')(aws.region))
        self.app_name = app_name

    def swap_environment_cnames(self, from_env_name, to_env_name):
        """
        Swaps cnames for an environment
        """
        self.ebs.swap_environment_cnames(source_environment_name=from_env_name,
                                         destination_environment_name=to_env_name)

    def upload_archive(self, filename, key, auto_create_bucket=True):
        """
        Uploads an application archive version to s3
        """
        try:
            bucket = self.s3.get_bucket(self.aws.bucket)
            if ((
                  self.aws.region != 'us-east-1' and self.aws.region != 'eu-west-1') and bucket.get_location() != self.aws.region) or (
                  self.aws.region == 'us-east-1' and bucket.get_location() != '') or (
                  self.aws.region == 'eu-west-1' and bucket.get_location() != 'eu-west-1'):
                raise Exception("Existing bucket doesn't match region")
        except S3ResponseError:
            bucket = self.s3.create_bucket(self.aws.bucket, location=self.aws.region)

        def __report_upload_progress(sent, total):
            if not sent:
                sent = 0
            if not total:
                total = 0
            out("Uploaded " + str(sent) + " bytes of " + str(total) \
                + " (" + str(int(float(max(1, sent)) / float(total) * 100)) + "%)")

        # upload the new version
        k = Key(bucket)
        k.key = self.aws.bucket_path + key
        k.set_metadata('time', str(time()))
        k.set_contents_from_filename(filename, cb=__report_upload_progress, num_cb=10)

    def list_available_solution_stacks(self):
        """
        Returns a list of available solution stacks
        """
        stacks = self.ebs.list_available_solution_stacks()
        return stacks['ListAvailableSolutionStacksResponse']['ListAvailableSolutionStacksResult']['SolutionStacks']

    def create_application(self, description=None):
        """
        Creats an application and sets the helpers current
        app_name to the created application
        """
        out("Creating application " + str(self.app_name))
        self.ebs.create_application(self.app_name, description=description)

    def delete_application(self):
        """
        Creats an application and sets the helpers current
        app_name to the created application
        """
        out("Deleting application " + str(self.app_name))
        self.ebs.delete_application(self.app_name, terminate_env_by_force=True)

    def application_exists(self):
        """
        Returns whether or not the given app_name exists
        """
        response = self.ebs.describe_applications(application_names=[self.app_name])
        return len(response['DescribeApplicationsResponse']['DescribeApplicationsResult']['Applications']) > 0

    def create_environment(self, env_name, version_label=None,
                           solution_stack_name=None, cname_prefix=None, description=None,
                           option_settings=None, tier_name='WebServer', tier_type='Standard', tier_version='1.1'):
        """
        Creates a new environment
        """
        out("Creating environment: " + str(env_name) + ", tier_name:" + str(tier_name) + ", tier_type:" + str(tier_type))
        self.ebs.create_environment(self.app_name, env_name,
                                    version_label=version_label,
                                    solution_stack_name=solution_stack_name,
                                    cname_prefix=cname_prefix,
                                    description=description,
                                    option_settings=option_settings,
                                    tier_type=tier_type,
                                    tier_name=tier_name,
                                    tier_version=tier_version)

    def environment_exists(self, env_name):
        """
        Returns whether or not the given environment exists
        """
        response = self.ebs.describe_environments(application_name=self.app_name, environment_names=[env_name],
                                                  include_deleted=False)
        return len(response['DescribeEnvironmentsResponse']['DescribeEnvironmentsResult']['Environments']) > 0 \
               and response['DescribeEnvironmentsResponse']['DescribeEnvironmentsResult']['Environments'][0][
                       'Status'] != 'Terminated'

    def rebuild_environment(self, env_name):
        """
        Rebuilds an environment
        """
        out("Rebuilding " + str(env_name))
        self.ebs.rebuild_environment(environment_name=env_name)

    def get_environments(self):
        """
        Returns the environments
        """
        response = self.ebs.describe_environments(application_name=self.app_name, include_deleted=False)
        return response['DescribeEnvironmentsResponse']['DescribeEnvironmentsResult']['Environments']

    def delete_environment(self, environment_name):
        """
        Deletes an environment
        """
        self.ebs.terminate_environment(environment_name=environment_name, terminate_resources=True)

    def update_environment(self, environment_name, description=None, option_settings=[], tier_type=None, tier_name=None,
                           tier_version='1.0'):
        """
        Updates an application version
        """
        out("Updating environment: " + str(environment_name))
        messages = self.ebs.validate_configuration_settings(self.app_name, option_settings,
                                                            environment_name=environment_name)
        messages = messages['ValidateConfigurationSettingsResponse']['ValidateConfigurationSettingsResult']['Messages']
        ok = True
        for message in messages:
            if message['Severity'] == 'error':
                ok = False
            out("[" + message['Severity'] + "] " + str(environment_name) + " - '" \
                + message['Namespace'] + ":" + message['OptionName'] + "': " + message['Message'])
        self.ebs.update_environment(
            environment_name=environment_name,
            description=description,
            option_settings=option_settings,
            tier_type=tier_type,
            tier_name=tier_name,
            tier_version=tier_version)

    def environment_name_for_cname(self, env_cname):
        """
        Returns an environment name for the given cname
        """
        envs = self.get_environments()
        for env in envs:
            if env['Status'] != 'Terminated' and env['CNAME'].lower().startswith(env_cname.lower() + '.'):
                return env['EnvironmentName']
        return None

    def deploy_version(self, environment_name, version_label):
        """
        Deploys a version to an environment
        """
        out("Deploying " + str(version_label) + " to " + str(environment_name))
        self.ebs.update_environment(environment_name=environment_name, version_label=version_label)

    def create_application_version(self, version_label, key):
        """
        Creates an application version
        """
        out("Creating application version " + str(version_label) + " for " + str(key))
        self.ebs.create_application_version(self.app_name, version_label,
                                            s3_bucket=self.aws.bucket, s3_key=self.aws.bucket_path+key)

    def delete_unused_versions(self, versions_to_keep=10):
        """
        Deletes unused versions
        """

        # get versions in use
        environments = self.ebs.describe_environments(application_name=self.app_name, include_deleted=False)
        environments = environments['DescribeEnvironmentsResponse']['DescribeEnvironmentsResult']['Environments']
        versions_in_use = []
        for env in environments:
            versions_in_use.append(env['VersionLabel'])

        # get all versions
        versions = self.ebs.describe_application_versions(application_name=self.app_name)
        versions = versions['DescribeApplicationVersionsResponse']['DescribeApplicationVersionsResult'][
            'ApplicationVersions']
        versions = sorted(versions, reverse=True, cmp=lambda x, y: cmp(x['DateCreated'], y['DateCreated']))

        # delete versions in use
        for version in versions[versions_to_keep:]:
            if version['VersionLabel'] in versions_in_use:
                out("Not deleting " + version["VersionLabel"] + " because it is in use")
            else:
                out("Deleting unused version: " + version["VersionLabel"])
                self.ebs.delete_application_version(application_name=self.app_name,
                                                    version_label=version['VersionLabel'])
                sleep(2)

    def wait_for_environments(self, environment_names, health=None, status=None, version_label=None,
                              include_deleted=True, wait_time_secs=300):
        """
        Waits for an environment to have the given version_label
        and to be in the green state
        """

        # turn into a list
        if not isinstance(environment_names, (list, tuple)):
            environment_names = [environment_names]
        environment_names = environment_names[:]

        # print some stuff
        s = "Waiting for environment(s) " + (", ".join(environment_names)) + " to"
        if health is not None:
            s += " have health " + health
        else:
            s += " have any health"
        if version_label is not None:
            s += " and have version " + version_label
        if status is not None:
            s += " and have status " + status
        out(s)

        started = time()
        while True:
            # bail if they're all good
            if len(environment_names) == 0:
                break

            # wait
            sleep(5)

            # # get the env
            environments = self.ebs.describe_environments(
                application_name=self.app_name,
                environment_names=environment_names,
                include_deleted=include_deleted)

            environments = environments['DescribeEnvironmentsResponse']['DescribeEnvironmentsResult']['Environments']
            if len(environments) <= 0:
                raise Exception("Couldn't find any environments")

            # loop through and wait
            for env in environments[:]:
                env_name = env['EnvironmentName']

                # the message
                msg = "Environment " + env_name + " is " + str(env['Health'])
                if version_label is not None:
                    msg = msg + " and has version " + str(env['VersionLabel'])
                if status is not None:
                    msg = msg + " and has status " + str(env['Status'])

                # what we're doing
                good_to_go = True
                if health is not None:
                    good_to_go = good_to_go and str(env['Health']) == health
                if status is not None:
                    good_to_go = good_to_go and str(env['Status']) == status
                if version_label is not None:
                    good_to_go = good_to_go and str(env['VersionLabel']) == version_label

                if env['Status'] == 'Ready' and env['Health'] == 'Red':
                    out('Deploy failed')
                    raise Exception('Ready and red')

                # log it
                if good_to_go:
                    out(msg + " ... done")
                    environment_names.remove(env_name)
                else:
                    out(msg + " ... waiting")

            # check the time
            elapsed = time() - started
            if elapsed > wait_time_secs:
                message = "Wait time for environment(s) {environments} to be {health} expired".format(
                    environments=" and ".join(environment_names), health=(health or "Green")
                )
                raise Exception(message)
