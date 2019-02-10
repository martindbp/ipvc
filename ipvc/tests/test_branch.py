import os
import shutil
import time
import pytest
from pathlib import Path

from ipvc import IPVC
from helpers import NAMESPACE, REPO, REPO2, get_environment, write_file


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
