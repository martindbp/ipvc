import os
import shutil
import time
import pytest
from pathlib import Path

from ipvc import IPVC
from helpers import NAMESPACE, REPO, REPO2, get_environment, write_file


def test_init_and_ls():
    cwd = Path('/current/working/dir')
    ipvc = get_environment(cwd, mkdirs=False)
    repos = ipvc.repo.ls()
    assert len(repos) == 0
    ipvc.repo.init()
    repos = ipvc.repo.ls()
    assert len(repos) == 1
    assert repos[0][2] == str(cwd)
    assert repos[0][0] == None

    branch_name = ipvc.ipfs.files_read(
        ipvc.repo.get_mfs_path(cwd, repo_info='active_branch_name')).decode('utf-8')
    assert branch_name == 'master'

    with pytest.raises(RuntimeError):
        ipvc.repo.init()
    with pytest.raises(RuntimeError):
        ipvc.set_cwd(cwd / 'test')
        ipvc.repo.init()

    cwd2 = Path('/somewhere/else')
    ipvc.set_cwd(cwd2)
    assert ipvc.repo.init(name='my_repo') == True
    repos = ipvc.repo.ls()
    assert len(repos) == 2
    assert repos[1][0] == 'my_repo'
    assert repos[0][2] == str(cwd)
    assert repos[1][2] == str(cwd2)


def test_mv_rm():
    ipvc = get_environment()
    ipvc.repo.init()
    test_file = REPO / 'test_file.txt'
    write_file(test_file, 'hello_world')
    ipvc.stage.add(test_file)

    with pytest.raises(RuntimeError):
        ipvc.repo.mv(REPO2, REPO2)
    with pytest.raises(RuntimeError):
        ipvc.repo.mv(REPO, REPO)

    with pytest.raises(RuntimeError):
        IPVC(Path('/'), NAMESPACE).repo.mv(REPO, None)
    assert ipvc.repo.mv(REPO, REPO2) == True
    assert not REPO.exists()
    assert REPO2.exists()

    try:
        h = ipvc.ipfs.files_stat(ipvc.repo.get_mfs_path(REPO2))['Hash']
    except:
        h = None
    assert h is not None


    assert ipvc.repo.rm(REPO2) == True
    assert REPO2.exists() # should still exist on filesystem
    try:
        h = ipvc.ipfs.files_stat(ipvc.repo.get_mfs_path(REPO2))['Hash']
    except:
        h = None
    assert h is None # should not exist on MFS


def test_clone():
    ipvc = get_environment()
    ipvc.repo.init(name='myrepo')
    id1 = ipvc.id.create(key='id1', use=True)
    test_file = REPO / 'test_file.txt'
    write_file(test_file, 'hello world')
    ipvc.stage.add(test_file)
    ipvc.stage.commit(message='msg')
    ipvc.repo.publish()
    ipvc.repo.rm()

    write_file(test_file, 'other text')
    ipvc.repo.clone(f'{id1}/myrepo')
    with open(test_file, 'r') as f:
        assert f.read() == 'hello world'
