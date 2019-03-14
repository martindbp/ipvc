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
from time import time, sleep
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
        if os.path.isfile(f):
            shutil.copy(f, cwd / os.path.basename(f))
        else:
            shutil.copytree(f, cwd / os.path.basename(f))


def assert_state(dir_path):
    file_roots1 = []
    files1 = []
    file_roots2 = []
    files2 = []
    dirs1 = []
    dirs2 = []

    for r, dirs, files in os.walk('.'):
        for d in dirs:
            dirs1.append(d)
        for f in files:
            files1.append(f)
            file_roots1.append(Path(r))

    for r, dirs, files in os.walk(dir_path):
        for d in dirs:
            dirs2.append(d)
        for f in files:
            files2.append(f)
            file_roots2.append(Path(r))

    assert set(dirs1) == set(dirs2)
    for d1, d2 in zip(dirs1, dirs2):
        assert d1 == d2

    assert set(files1) == set(files2)
    for f1, r1, f2, r2 in zip(files1, file_roots1, files2, file_roots2):
        assert f1 == f2
        with open(r1 / f1) as ff1, open(r2 / f2) as ff2:
            assert ff1.read() == ff2.read()


def assert_output(correct, actual):
    assert len(correct) == len(actual)
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


def test_integration(tests_dir, name, stop_command):
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
            if name is not 'None' and name != test_dir:
                continue
            test_root = Path(tests_root) / test_dir

            num_states = 0
            for _, dirs, _ in os.walk(test_root):
                for d in dirs:
                    if d.isnumeric():
                        num_states += 1
                break

            print('######################################')
            print(f'Testing {test_dir}')
            print('######################################')
            last_command_time = 0
            for i in range(num_states):
                print(f'Testing command {i}')
                setup_state(test_root / str(i) / 'pre')
                if (name is None or test_dir == name) and str(i) == stop_command:
                    import pdb; pdb.set_trace()
                t = time()
                # Make sure there is always at least a second between commands
                # since unix file timestamp resolution is a second and we
                # need the files to have new timestamps
                if t - last_command_time < 1:
                    s = 1 - (t - last_command_time)
                    print(f'Sleeping {s:.2f}s')
                    sleep(s)
                last_command_time = t
                run_assert_command(test_root / str(i))
                assert_state(test_root / str(i) / 'post')
        break
