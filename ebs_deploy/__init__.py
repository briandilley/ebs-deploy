
from boto.exception import S3ResponseError
from boto.s3.connection import S3Connection
from boto.beanstalk.layer1 import Layer1
from boto.s3.key import Key
from boto.regioninfo import RegionInfo
from boto import set_stream_logger
# set_stream_logger('boto')

from time import time, sleep
import zipfile
import os
import sys


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
            self.bucket_path = self.bucket_path+'/'


class EbsHelper(object):
    """
    Class for helping with ebs
    """

    def __init__(self, aws, app_name=None):
        """
        Creates the EbsHelper
        """
        self.aws            = aws
        self.region         = RegionInfo(name=aws.region, endpoint='elasticbeanstalk.'+aws.region+'.amazonaws.com')
        self.ebs            = Layer1(aws_access_key_id=aws.access_key, aws_secret_access_key=aws.secret_key, region=self.region)
        self.s3             = S3Connection(aws.access_key, aws.secret_key)
        self.app_name       = app_name

    def parse_option_settings(self, option_settings):
        """
        Parses option_settings as they are defined in the configuration file
        """
        ret = []
        for settings_group in option_settings:
            for namespace, params in settings_group.items():
                for key, value in params.items():
                    ret.append((namespace, key, value))
        return ret


    def create_archive(self, directory, filename, ignore_predicate=None, ignored_files=['.git', '.svn']):
        """
        Creates an archive from a directory and returns
        the file that was created.
        """
        zip = zipfile.ZipFile(filename, 'w', compression=zipfile.ZIP_DEFLATED)
        root_len = len(os.path.abspath(directory))

        # create it
        print("Creating archive: "+filename)
        for root, dirs, files in os.walk(directory, followlinks=True):
            archive_root = os.path.abspath(root)[root_len:]
            for f in files:
                fullpath = os.path.join(root, f)

                # ignore the file we're createing
                if filename in fullpath:
                    continue

                # ignored files
                if ignored_files is not None:
                    for name in ignored_files:
                        if fullpath.endswith(name):
                            continue

                # do predicate
                if ignore_predicate is not None:
                    if not ignore_predicate(name):
                        continue

                archive_name = os.path.join(archive_root, f)
                print("Adding: "+fullpath)
                zip.write(fullpath, archive_name, zipfile.ZIP_DEFLATED)
        zip.close()
        return filename


    def upload_archive(self, filename, key, auto_create_bucket=True):
        """
        Uploads an application archive version to s3
        """
        bucket = None
        try:
            bucket = self.s3.get_bucket(self.aws.bucket)
            if bucket.get_location() != self.aws.region:
                raise Exception("Existing bucket doesn't match region")
        except S3ResponseError:
            bucket = self.s3.create_bucket(self.aws.bucket, location=self.aws.region)

        def __report_upload_progress(sent, total):
            if not sent:
                sent = 0
            if not total:
                total = 0
            print("Uploaded "+str(sent)+" bytes of "+str(total) \
                +" ("+str( int(float(max(1, sent))/float(total)*100) )+"%)")

        # upload the new version
        k = Key(bucket)
        k.key = self.bucket_path+key
        k.set_metadata('time', str(time()))
        f = open(filename)
        k.set_contents_from_file(f, cb=__report_upload_progress, num_cb=10)
        f.close()

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
        print("Creating application "+self.app_name)
        self.ebs.create_application(self.app_name, description=description)


    def application_exists(self):
        """
        Returns whether or not the given app_name exists
        """
        response = self.ebs.describe_applications(application_names=[self.app_name])
        return len(response['DescribeApplicationsResponse']['DescribeApplicationsResult']['Applications']) > 0


    def create_environment(self, env_name, version_label=None,
        solution_stack_name=None, cname_prefix=None, description=None,
        option_settings=None, wait=True):
        """
        Creates a new environment
        """
        print("Creating environment "+env_name)
        self.ebs.create_environment(self.app_name, env_name,
            version_label=version_label,
            solution_stack_name=solution_stack_name,
            cname_prefix=cname_prefix,
            description=description,
            option_settings=option_settings)

        if wait:
            self._wait_for_environment(env_name, version_label=version_label)

    def environment_exists(self, env_name):
        """
        Returns whether or not the given environment exists
        """
        response = self.ebs.describe_environments(application_name=self.app_name, environment_names=[env_name], include_deleted=False)
        return len(response['DescribeEnvironmentsResponse']['DescribeEnvironmentsResult']['Environments']) > 0



    # TODO:
    def create_application_version(self, version_label, key, versions_to_keep=10):
        """
        Creates an application version
        """
        self.ebs.create_application_version(self.app_name, version_label, s3_bucket=self.aws.bucket, s3_key=self.bucket_path+key)



    # TODO:
    def update_environment(self, version_label):
        """
        Updates an application version
        """
        self.ebs.update_environment(environment_name=self.env_name, version_label=version_label)
        if wait_time_secs <= 0:
            return

        if wait:
            self._wait_for_environment(env_name, version_label)



    # TODO:
    def delete_unused_versions(self, versions_to_keep=10):
        """
        Deletes unused versions
        """

        # get all versions
        versions = self.ebs.describe_application_versions(application_name=self.app_name)
        versions = versions['DescribeApplicationVersionsResponse']['DescribeApplicationVersionsResult']['ApplicationVersions']
        versions = sorted(versions, reverse=True, cmp=lambda x, y: cmp(x['DateCreated'], y['DateCreated']))

        # delete versions in use
        for version in versions[versions_to_keep:]:
            if version['VersionLabel'] in versions_in_use:
                print("Not deleting "+version["VersionLabel"]+" because it is in use")
            else:
                print("Deleting unused version: "+version["VersionLabel"])
                self.ebs.delete_application_version(application_name=self.app_name, version_label=version['VersionLabel'])
                sleep(2)


    def _wait_for_environment(self, env_name, version_label=None, wait_time_secs=600):
        """
        Waits for an environment to have the given version_label
        and to be in the green state
        """

        s = "Waiting for environemnt "+env_name+" to be Green"
        if version_label is not None:
            s = s + " and have version "+version_label

        started = time()
        while True:
            sleep(5)

            ## get the env
            environments = self.ebs.describe_environments(
                application_name=self.app_name, environment_names=[env_name], include_deleted=False)
            environments = environments['DescribeEnvironmentsResponse']['DescribeEnvironmentsResult']['Environments']
            if len(environments)<=0:
                raise Exception("Couldn't find environment")
            env = environments[0]

            heathy = env['Health'] == 'Green'
            if version_label is not None:
                if heathy and env['VersionLabel'] == version_label:
                    print("Environment "+env_name+" is Green and with expected version")
                    break
                else:
                    print("Environment "+env_name+" is "+env['Health']+" and has version "+env['VersionLabel']+" waiting...")

            else:
                if heathy:
                    print("Environment "+env_name+" is Green")
                    break
                else:
                    print("Environment "+env_name+" is "+env['Health']+" waiting...")

            # check th etime
            elapsed = time()-started
            if elapsed > self.wait_time_secs:
                raise Exception("Wait time for environment to be green with new version expired")
