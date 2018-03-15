import os
import argparse
import cProfile
from pathlib import Path

from .ipvc_api import IPVC

def main():
    cwd = Path.cwd()
    desc = 'Inter-Planetary Versioning Control (System)'

    parser = argparse.ArgumentParser(description=desc)
    parser.add_argument(
        '-v', '--verbose', action='store_true', help='Verbose output')
    parser.add_argument(
        '-q', '--quiet', action='store_true', help='No printing')
    parser.add_argument(
        '-p', '--profile', action='store_true', help='Profile the program')
    parser.set_defaults(command='help', subcommand='')
    subparsers = parser.add_subparsers()

    # ------------- HELP --------------
    help_parser = subparsers.add_parser('help', description='Display help')
    help_parser.set_defaults(command='help', subcommand='')

    # ------------- REPO --------------
    repo_parser = subparsers.add_parser('repo', description='Repository functions')
    repo_parser.set_defaults(command='repo', subcommand='status')
    repo_subparsers = repo_parser.add_subparsers()

    repo_status_parser = repo_subparsers.add_parser(
        'status', description='Status of repo at this path')
    repo_status_parser.set_defaults(subcommand='status')

    repo_init_parser = repo_subparsers.add_parser('init', description='Initialize a repo')
    repo_init_parser.set_defaults(subcommand='init')

    repo_mv_parser = repo_subparsers.add_parser('mv', description='Move a repo')
    repo_mv_parser.set_defaults(subcommand='mv')
    repo_mv_parser.add_argument(
        'path1', help='from path if narg=2 otherwise to path', default=cwd)
    repo_mv_parser.add_argument('path2', help='to path', default=None)

    # ------------- PARAM --------------
    param_parser = subparsers.add_parser('param')
    param_parser.set_defaults(command='param', subcommand='set_param')
    param_parser.add_argument('--author')

    # ------------- BRANCH --------------
    branch_parser = subparsers.add_parser(
        'branch', description='Handle branches')
    branch_parser.set_defaults(command='branch', subcommand='status')
    branch_subparsers = branch_parser.add_subparsers()

    branch_create_parser = branch_subparsers.add_parser(
        'create', description='Create a new branch from current point')
    branch_create_parser.set_defaults(subcommand='create')
    branch_create_parser.add_argument('name', help='branch name')
    branch_create_parser.add_argument('-f', '--from-commit', default=None)

    branch_checkout_parser = branch_subparsers.add_parser(
        'checkout', description='Checkout a branch')
    branch_checkout_parser.set_defaults(subcommand='checkout')
    branch_checkout_parser.add_argument('name', help='branch name')
    branch_checkout_parser.add_argument(
        '--without-timestamps', action='store_true', help='Checkout files without timestamps (note this will slow down ipvc in the subsequent commands')

    branch_history_parser = branch_subparsers.add_parser(
        'history', description='Show branch commit history')
    branch_history_parser.set_defaults(subcommand='history')
    branch_history_parser.add_argument(
        '-s', '--show-ref', action='store_true', help='Shows ref hashes to files')

    branch_show_parser = branch_subparsers.add_parser(
        'show', description='Show a ref in the browser')
    branch_show_parser.set_defaults(subcommand='show')
    branch_show_parser.add_argument(
        'ref', nargs='?', help='The ref (e.g. head or head~', default='@head')

    # ------------- STAGE --------------
    stage_parser = subparsers.add_parser(
        'stage', description='Add/remove changes to stage and handle commits')
    stage_parser.set_defaults(command='stage', subcommand='status')
    stage_subparsers = stage_parser.add_subparsers()

    stage_add_parser = stage_subparsers.add_parser(
        'add', description='Stage changes in a folder or file')
    stage_add_parser.set_defaults(subcommand='add')
    stage_add_parser.add_argument('fs_paths', nargs='*', help='path to add', default=cwd)

    stage_remove_parser = stage_subparsers.add_parser(
        'remove', description='Unstage changes in a folder or file')
    stage_remove_parser.set_defaults(subcommand='remove')
    stage_remove_parser.add_argument('fs_paths', nargs='*', help='path to remove', default=cwd)

    stage_status_parser = stage_subparsers.add_parser(
        'status', description='Show changed files between workspace, stage and head')
    stage_status_parser.set_defaults(subcommand='status')

    stage_commit_parser = stage_subparsers.add_parser(
        'commit', description='Commit staged changes')
    stage_commit_parser.set_defaults(subcommand='commit')
    stage_commit_parser.add_argument('message', help='commit message')

    stage_uncommit_parser = stage_subparsers.add_parser(
        'uncommit', description='Uncommit last commit and leave the changes staged')
    stage_uncommit_parser.set_defaults(subcommand='uncommit')

    stage_diff_parser = stage_subparsers.add_parser(
        'diff', description='Display diff between head and stage')
    stage_diff_parser.set_defaults(subcommand='diff')

    # ------------- DIFF --------------
    diff_parser = subparsers.add_parser(
        'diff', description='Display a diff between two ref paths, defaults to stage and workspace')
    diff_parser.set_defaults(command='diff')
    diff_subparsers = diff_parser.add_subparsers()

    diff_files_parser = diff_subparsers.add_parser(
        'files', description='Display list of changed files')
    diff_files_parser.set_defaults(subcommand='files')
    diff_files_parser.add_argument('to_refpath', nargs='?', help='to refpath', default='@stage')
    diff_files_parser.add_argument('from_refpath', nargs='?', help='from refpath', default='@head')

    diff_content_parser = diff_subparsers.add_parser(
        'content', description='Display content diff')
    diff_content_parser.set_defaults(subcommand='content')
    diff_content_parser.add_argument('to_refpath', nargs='?', help='to refpath', default='@stage')
    diff_content_parser.add_argument('from_refpath', nargs='?', help='from refpath', default='@head')

    args = parser.parse_args()
    kwargs = dict(args._get_kwargs())
    kwargs.pop('command')
    kwargs.pop('subcommand')
    kwargs.pop('profile')
    quiet = kwargs.pop('quiet')
    verbose = kwargs.pop('verbose')
    # Replace dashes with underscores in option names
    kwargs = {key.replace('-', '_'): val for key, val in kwargs.items()}

    if args.command == 'help':
        print('Use the --help option for help')
        exit(0)

    ipvc = IPVC(quiet=quiet, verbose=verbose)
    route = getattr(getattr(ipvc, args.command), args.subcommand)
    if args.profile:
        cProfile.run('route(**kwargs)')
    else:
        try:
            route(**kwargs)
        except RuntimeError:
            exit(1)
