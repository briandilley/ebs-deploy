
from ebs_deploy import out, get, parse_env_config, parse_option_settings

def execute(helper, config, args):
    """
    Lists environments
    """
    envs = config.get('app', {}).get('environments', [])
    out("Parsed environments:")
    for name, conf in envs.items():
        out('\t'+name)
    envs = helper.get_environments()
    out("Deployed environments:")
    for env in envs:
        if env['Status'] != 'Terminated':
            out('\t'+env['EnvironmentName']+' ('+env['Status']+', '+env['CNAME']+')')
