from ebs_deploy import out


def execute(helper, config, args):
    """
    Lists environments
    """
    versions = helper.get_versions()
    out("Deployed versions:")
    for version in versions:
        out(version)
