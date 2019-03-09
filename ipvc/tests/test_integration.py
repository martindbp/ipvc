"""
This pytest runs IPVC as a command line program and checks the output against
the correct stored output

Tests can be recorded by adding the "--record <path>" option to IPVC. It records
the command itself, the resulting stdout and stderr, and a copy of the repository (cwd)
folder before the command and after, stored in a "pre" and "post" directory respectively.
For example:
> ipvc --delete-mfs --mfs-namespace /test --record path/to/tests/test_repo repo init
This command puts the recorded outputs in the 'test_repo' directory. Each command
in a sequence of commands recorded to this location will be indexed by an integer
starting from 0.
The --mfs-namespace argument sets the prefix of where to keep IPVC files in MFS
The --delete-mfs option deletes the previous ipvc directory in MFS, this should be
added for the first command to ensure a clean environment

These tests can then be editied manually (or created manually from the start).

To run a test from the command line, from the ipvc repository base:
> python3 -m pytest -s ipvc/tests/test_integration.py --name test_branch --tests_dir ipvc/tests/integration_tests
The --name argument specifies the test name to run. If unspecified all tests are run.
The --tests_dir specifies where all the tests are. By default it is set to 'ipvc/tests/integration_tests'

NOTE:
Tests including commit hash outputs and commit logs will differ from recorded
output, since the timestamp will differ. In these cases, replace the differing
characters with an asterix (*), for wildcard matching.

"""
import os
import time
import glob
import pytest
import shutil
import subprocess
from subprocess import PIPE
from pathlib import Path
from ipvc import IPVC

def setup_state(dir_path):
    # Delete everything in cwd
    cwd = Path(os.getcwd())
    for f in glob.glob(str(cwd / '*')):
        if os.path.isfile(f):
            os.remove(f)
        else:
            shutil.rmtree(f)

    # Copy everything from dir_path to cwd
    for f in glob.glob(str(dir_path / '*')):
        shutil.copy(f, cwd / os.path.basename(f))


def assert_state(dir_path):
    for (r1, d1, f1), (r2, d2, f2) in zip(os.walk('.'), os.walk(dir_path)):
        d1.sort()
        d2.sort()
        f1.sort()
        f2.sort()
        for dd1, dd2 in zip(d1, d2):
            assert dd1 == dd2

        for ff1, ff2 in zip(f1, f2):
            with open(ff1, 'r') as fff1, open(ff2, 'r') as fff2:
                assert fff1.read() == fff2.read()


def assert_output(correct, actual):
    for c1, c2 in zip(correct, actual):
        assert c1 == c2 or c1 == '*', (correct, actual)


def run_assert_command(test_command_root):
    command = None
    with open(test_command_root / 'command.txt', 'r') as f:
        command = f.read()
    stdout, stderr = None, None
    with  open(test_command_root / 'stdout.txt', 'r') as f:
        stdout = f.read()
    with  open(test_command_root / 'stderr.txt', 'r') as f:
        stderr = f.read()
    print(f'Running command: {command}')

    ret = subprocess.run(command, shell=True, stderr=PIPE, stdout=PIPE)
    assert_output(stdout, str(ret.stdout, 'utf-8'))
    assert_output(stderr, str(ret.stderr, 'utf-8'))
    if len(stdout) > 0:
        print('stdout ---------------------')
        print(stdout)
    if len(stderr) > 0:
        print('stdeerr ---------------------')
        print(stderr)
    if len(stdout) + len(stderr) > 0:
        print('-----------------------------')


def test_integration(tests_dir, name):
    tests_dir = os.path.abspath(tests_dir)
    cwd = os.getcwd()
    ipvc_test_dir = '/tmp/ipvc_integration_tests'
    try:
        os.makedirs(ipvc_test_dir)
    except:
        pass
    os.chdir(ipvc_test_dir)

    for tests_root, test_dirs, _ in os.walk(tests_dir):
        for test_dir in test_dirs:
            if name is not None and name != test_dir:
                continue
            test_root = Path(tests_root) / test_dir

            num_states = 0
            for _, dirs, _ in os.walk(test_root):
                for d in dirs:
                    if d.isnumeric():
                        num_states += 1
                break

            print(f'Testing {test_dir}')
            for i in range(num_states):
                print(f'Testing command {i}')
                setup_state(test_root / str(i) / 'pre')
                run_assert_command(test_root / str(i))
                assert_state(test_root / str(i) / 'post')
