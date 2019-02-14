import os
import pytest
from pathlib import Path

from ipvc import IPVC
from helpers import NAMESPACE, REPO, REPO2, get_environment, write_file, Profile

def assert_list_equals(l1, l2):
    for item1, item2 in zip(l1, l2):
        assert item1 == item2

def test_pull():
    ipvc = get_environment()
    ipvc.repo.init()
    write_file(REPO / 'test_file.txt', 'line1\nline2\nline3\nline4')
    ipvc.stage.add()
    ipvc.stage.commit('msg1')

    os.rename(REPO / 'test_file.txt', REPO / 'test_file2.txt')
    ipvc.diff.run()
    os.rename(REPO / 'test_file2.txt', REPO / 'test_file.txt')

    ipvc.branch.create('other', no_checkout=True)

    write_file(REPO / 'test_file.txt', 'line1\nother\nline3\nline4')
    ipvc.stage.add()
    ipvc.stage.commit('msg2')

    ipvc.branch.checkout('other')
    write_file(REPO / 'test_file.txt', 'line1\nline2\nblerg\nline4')
    with pytest.raises(RuntimeError):
        ipvc.branch.pull('master')

    ipvc.stage.add()
    with pytest.raises(RuntimeError):
        ipvc.branch.pull('master')

    ipvc.stage.commit('msg2other')
    conflict_files = ipvc.branch.pull('master')
    assert conflict_files == set(['test_file.txt'])
    correct_lines = [
        'line1',
        '>>>>>>> ours',
        'line2',
        'blerg',
        '======= theirs',
        'other',
        'line3',
        '<<<<<<<',
        'line4'
    ]
    file_lines = open(REPO / 'test_file.txt', 'r').read().splitlines()
    assert_list_equals(file_lines, correct_lines)


def test_create_and_checkout():
    ipvc = get_environment()
    ipvc.repo.init()

    write_file(REPO / 'test_file.txt', 'hello world')

    ipvc.stage.add()
    assert ipvc.branch.status(name=True) == 'master'

    write_file(REPO / 'test_file2.txt', 'hello world2')

    with pytest.raises(RuntimeError):
        ipvc.branch.create('master')

    branches = set(ipvc.branch.ls())
    assert branches == set(['master'])

    ipvc.branch.create('develop')
    assert ipvc.branch.status(name=True) == 'develop'

    branches = set(ipvc.branch.ls())
    assert branches == set(['master', 'develop'])

    head_stage, stage_workspace = ipvc.stage.status()
    assert len(head_stage) == 1 and len(stage_workspace) == 1

    test_file3 = REPO / 'test_file3.txt'
    write_file(test_file3, 'hello world3')
    t1 = test_file3.stat().st_mtime_ns

    head_stage, stage_workspace = ipvc.stage.status()
    assert len(head_stage) == 1 and len(stage_workspace) == 2

    ipvc.branch.checkout('master')
    head_stage, stage_workspace = ipvc.stage.status()
    assert len(head_stage) == 1 and len(stage_workspace) == 1

    with pytest.raises(FileNotFoundError):
        test_file3.stat()

    ipvc.branch.checkout('develop')
    head_stage, stage_workspace = ipvc.stage.status()
    assert len(head_stage) == 1 and len(stage_workspace) == 2

    # Test that timestamps are checked out correctly
    t2 = test_file3.stat().st_mtime_ns
    assert t1 == t2


def test_create_from():
    ipvc = get_environment()
    ipvc.repo.init()

    filename1 = REPO / 'test_file.txt'
    write_file(filename1, 'hello world')
    ipvc.stage.add()
    ipvc.stage.commit('msg1')

    filename2 = REPO / 'test_file2.txt'
    write_file(filename2, 'hello world2')
    ipvc.stage.add()
    ipvc.stage.commit('msg2')

    ipvc.branch.create('test', from_commit='@head~')
    commits = ipvc.branch.history()
    assert len(commits) == 1

    filename1.stat()
    with pytest.raises(FileNotFoundError):
        filename2.stat()

    os.remove(filename1)
    ret = ipvc.diff.run()



def test_history():
    ipvc = get_environment()
    ipvc.repo.init()

    ipvc.param.param(author='Bob')

    write_file(REPO / 'test_file.txt', 'hello world')
    ipvc.stage.add()

    ipvc.stage.commit('commit message')
    try:
        ipvc.ipfs.files_stat(ipvc.repo.get_mfs_path(REPO, 'master', branch_info='head/bundle'))
    except:
        assert False

    try:
        ipvc.ipfs.files_stat(ipvc.repo.get_mfs_path(REPO, 'master', branch_info='head/parent1'))
    except:
        assert False

    try:
        metadata = ipvc.repo.mfs_read_json(
            ipvc.repo.get_mfs_path(REPO, 'master', branch_info='head/commit_metadata'))
    except:
        assert False

    commits = ipvc.branch.history()
    assert len(commits) == 1

    assert ipvc.branch.show(Path('@head')) == 'test_file.txt'
    assert ipvc.branch.show(Path('@head/test_file.txt')) == 'hello world'
