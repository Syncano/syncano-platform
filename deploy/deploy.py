#! /usr/bin/env python3
"""
Deployment command.

"""
import argparse
import os
import subprocess
import sys
import zipfile
from datetime import datetime


def main():
    parser = argparse.ArgumentParser(description='Deploy Syncano Platform.')
    parser.add_argument(
        '--target', default='staging', help='target of your deployment.', choices=['production', 'staging'])
    parser.add_argument(
        '--tag',
        required=True,
        help='tag used in deployment.'
    )

    args = parser.parse_args()
    deploy(args.target, 'codebox', args.tag)


def deploy(target, environment, tag):
    config = initialize_options(target, tag)
    create_dockerrun_configuration(tag, config)
    deploy_environment(environment, config)
    print('Done!')


def initialize_options(target, tag):
    branch = os.environ.get('CIRCLE_BRANCH',
                            subprocess.check_output('git rev-parse --abbrev-ref HEAD'.split()).strip())
    last_commit_hash = subprocess.check_output('git rev-parse HEAD'.split())
    config = {
        'BUILD_BUNDLE_SUFFIX': '{tag}_bundle.zip'.format(tag=tag),
        'DEPLOY_TARGET': target,
        'BRANCH': branch,
        'LAST_COMMIT_HASH': last_commit_hash,
        'IMAGE_NAME': 'syncanoplatform_web',
        'AUTH_BUCKET': 'syncano-docker',
    }

    if target == 'production':
        config.update({
            # elastic beanstalk environments
            'CODEBOX_ENVIRONMENT': 'syncano-v4-prod-codebox',
            'EBS_CONFIG_FILE': 'ebs_prod.config',
        })
    else:
        config.update({
            # elastic beanstalk environments
            'CODEBOX_ENVIRONMENT': 'syncano-v4-codebox-d1',
            'EBS_CONFIG_FILE': 'ebs_devel.config',
        })

    environment_secrets = _load_environment_secrets(target)
    config.update(environment_secrets)
    return config


def _load_environment_secrets(target):
    prefix = ''
    if target == 'production':
        prefix += 'PROD_'

    return {'codebox': {'LE_TOKEN': os.environ.get(prefix + 'CODEBOX_LE_TOKEN')}}


def create_dockerrun_configuration(tag, config):
    with open('Dockerrun.aws.json.template', 'r') as f:
        text = f.read()
    with open('Dockerrun.aws.json', 'w') as f:
        text = text.replace('<TAG>', tag)
        text = text.replace('<AUTH_BUCKET>', config['AUTH_BUCKET'])
        f.write(text)


def deploy_environment(environment, config):
    build_bundle = _build_ebextension_bundle(environment, config)
    _ebs_deploy(environment, build_bundle, config)


def _fill_logentries_template(environment, config):
    with open('.ebextensions/03-logentries-forwarding-template.config') as f:
        logentries_template = f.read()

    logentries_config = '.ebextensions/03-logentries-forwarding-{environment}.config'.format(environment=environment)
    with open(logentries_config, 'w') as f:
        f.write(logentries_template.replace('LE_TOKEN', config[environment]['LE_TOKEN']))


def _fill_env_dependent_template(path, eb_env, config):
    with open(path) as f:
        codebox_download_template = f.read()

    with open(path.replace('template', eb_env), 'w') as f:
        branch = config['BRANCH']
        if branch != 'master':
            branch = 'devel'
        f.write(codebox_download_template.replace('BRANCH', branch))


def _build_ebextension_bundle(environment, config):
    build_bundle = '{environment}-{BUILD_BUNDLE_SUFFIX}'.format(
        environment=environment, BUILD_BUNDLE_SUFFIX=config['BUILD_BUNDLE_SUFFIX'])

    _fill_logentries_template(environment, config)
    _fill_env_dependent_template('.ebextensions/12-codebox-download-template.config', 'codebox', config)
    _fill_env_dependent_template('.ebextensions/13-docker-watchdog-template.config', 'common', config)

    zf = zipfile.ZipFile(build_bundle, mode='w')
    bundle_filenames = _prepare_filenames_for_bundle(environment)
    for filename in bundle_filenames:
        zf.write(filename)
    zf.close()
    return build_bundle


def _prepare_filenames_for_bundle(environment):
    filenames = ['Dockerrun.aws.json']
    filenames += ['.ebextensions/scripts/' + filename for filename in os.listdir('.ebextensions/scripts')]
    filenames += ['.ebextensions/' + filename for filename in os.listdir('.ebextensions')
                  if (filename.endswith('common.config') or
                      filename.endswith('{environment}.config'.format(environment=environment)))]
    return filenames


def _ebs_deploy(environment, build_bundle, config):
    environment_name = config['%s_ENVIRONMENT' % environment.upper()]
    version_label = '%s_%s' % (datetime.now().strftime('%Y%m%d_%H%M%S'), environment)
    process = subprocess.Popen(
        ['ebs-deploy', 'deploy', '-c', config['EBS_CONFIG_FILE'], '-f', '-a', build_bundle, '-e', environment_name,
         '-l', version_label, '-wt', '900'], stdout=subprocess.PIPE)
    for line in iter(process.stdout.readline, b''):
        line = line.decode()
        sys.stdout.write(line)
        sys.stdout.flush()
        if '{"Error"}' in line:
            raise ValueError('Problem with elastic beanstalk deployment!')


if __name__ == '__main__':
    main()
