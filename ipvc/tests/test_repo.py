import os
import shutil
import time
import pytest
from pathlib import Path

from ipvc import IPVC
from helpers import NAMESPACE, REPO, REPO2, get_environment, write_file


def test_init():
    cwd = Path('/current/working/dir')
    ipvc = get_environment(cwd, mkdirs=False)
    ipvc.repo.init()

    branch_name = ipvc.ipfs.files_read(
        ipvc.repo.get_mfs_path(cwd, repo_info='active_branch_name')).decode('utf-8')
    assert branch_name == 'master'

    with pytest.raises(RuntimeError):
        ipvc.repo.init()
    with pytest.raises(RuntimeError):
        ipvc.set_cwd(cwd / 'test')
        ipvc.repo.init()

    ipvc.set_cwd(Path('/somewhere/else'))
    assert ipvc.repo.init() == True


def test_mv():
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


