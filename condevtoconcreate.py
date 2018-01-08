#!/usr/bin/python

import argparse
import ruamel.yaml
import os
import sys


class MyParser(argparse.ArgumentParser):

    def error(self, message):
        self.print_help()
        sys.stderr.write('\nError: %s\n' % message)
        sys.exit(2)

def run(descriptor_path):
    target_file = descriptor_path

    ct = ruamel.yaml.tokens.CommentToken('\n\n', ruamel.yaml.error.CommentMark(0), None)

    with open(descriptor_path, "r") as source:
        for descriptor in ruamel.yaml.round_trip_load_all(source, preserve_quotes=True):
            descriptor.insert(0, 'schema_version', 1)
            # Add blank line after schema_version key
            descriptor.ca.items['schema_version'] = [None, None, ct, None]

            # Prepare labels, can be modified during conversion later
            if 'labels' in descriptor:
                labels = descriptor.pop('labels')
            else:
                labels = []

            # Move maintainer key to label
            if 'maintainer' in descriptor:
                maintainer = descriptor.pop('maintainer')
                labels.append({'name': 'maintainer', 'value': maintainer})

            # Add labels back, if necessary
            if labels:
                descriptor.insert(5, 'labels', labels)

            # Convert scripts to modules
            modules_to_install = []

            if 'cct' or 'scripts' in descriptor:
                modules = {}

            if 'scripts' in descriptor:
                scripts = descriptor.pop('scripts')
                scripts_dir = os.path.join(os.path.dirname(descriptor_path), 'scripts')
                modules_dir = os.path.join(os.path.dirname(descriptor_path), 'modules')

                if os.path.exists(scripts_dir):
                    os.rename(scripts_dir, modules_dir)

                for script in scripts:
                    modules_to_install.append({'name': script['package']})

                    yaml = ruamel.yaml.YAML()
                    module_descriptor = ruamel.yaml.comments.CommentedMap()
                    module_descriptor['schema_version'] = 1
                    module_descriptor.ca.items['schema_version'] = [None, None, ct, None]
                    module_descriptor['name'] = script['package']
                    module_descriptor['execute'] = [{'script': script['exec']}]

                    with open(os.path.join(modules_dir, script['package'], 'module.yaml'), 'w') as dest:
                        ruamel.yaml.round_trip_dump(
                            module_descriptor, dest, indent=6, width=500, line_break=False, block_seq_indent=4)

            # Convert cct section to modules
            if 'cct' in descriptor:
                cct = descriptor.pop('cct')
                modules['repositories'] = [{'git': {'url': 'https://github.com/jboss-openshift/cct_module.git', 'ref': 'master'}}]

                for cct_entry in cct:
                    changes = cct_entry['changes']
                    for change in changes:
                        name = change.keys()[0][11:]

                        added = False
                        for script_name in change.items()[0][1]:
                            if script_name.keys()[0] == 'configure_passwd_sh':
                                modules_to_install.append({'name': 'openshift-passwd'})
                                added = True
                        if not added:
                            modules_to_install.append({'name': name})

            if modules_to_install:
                modules['install'] = modules_to_install

            if modules:
                descriptor['modules'] = modules

            # Convert packages section
            if 'packages' in descriptor:
                packages = descriptor.pop('packages')
                descriptor['packages'] = {'install': packages, 'repositories': ['jboss-os', 'jboss-ocp', 'jboss-rhscl']}

            # Convert sources section
            if 'sources' in descriptor:
                sources = descriptor.pop('sources')
                for source in sources:
                    if 'artifact' in source:
                        artifact = source.pop('artifact')
                        if artifact.startswith('http'):
                            source.insert(0, 'url', artifact)
                        else:
                            source.insert(0, 'path', artifact)
                    if 'hint' in source:
                        source.insert(1, 'description', source.pop('hint'))

                descriptor['artifacts'] = sources

            # Convert run section
            run = ruamel.yaml.comments.CommentedMap()

            for key in ['user', 'entrypoint', 'cmd', 'workdir']:
                if key in descriptor:
                    run[key] = descriptor.pop(key)

            if run:
                descriptor['run'] = run

            # Convert dogen section
            if 'dogen' in descriptor:
                dist_git = descriptor.pop('dogen').get('plugins', {}).get('dist_git', {})

                if dist_git:
                    descriptor['osbs'] = {'repository': {'name': dist_git['repo'], 'branch': dist_git['branch']}}

            # Save everything to file
            with open(target_file, 'w') as dest:
                ruamel.yaml.round_trip_dump(
                    descriptor, dest, indent=6, width=500, line_break=False, block_seq_indent=4)

            print("Conversion is done, please review changes.")

def cli():
    parser = MyParser(
        description='Image descriptor converter',
        formatter_class=argparse.RawDescriptionHelpFormatter)

    parser.add_argument('--descriptor',
                        default='image.yaml',
                        help="path to image descriptor file, default: image.yaml")

    args = parser.parse_args()

    if not os.path.exists(args.descriptor):
        print("Descriptor file '%s' does not exist, make sure you provided correct path!" % args.descriptor)
        sys.exit(1)

    run(args.descriptor)

if __name__ == "__main__":
    cli()
