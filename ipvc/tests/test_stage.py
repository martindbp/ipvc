import os
import time
import pytest

from ipvc import IPVC
from helpers import NAMESPACE, REPO, REPO2, get_environment, write_file


def test_status():
    ipvc = get_environment()
    ipvc.repo.init()

    test_file = REPO / 'test_file.txt'
    write_file(test_file, 'hello world')

    head_stage, stage_workspace = ipvc.stage.status()
    assert len(head_stage) == 0
    assert len(stage_workspace) == 1 and stage_workspace[0]['Type'] == 0

    ipvc.stage.add()

    head_stage, stage_workspace = ipvc.stage.status()
    assert len(head_stage) == 1 and head_stage[0]['Type'] == 0
    assert len(stage_workspace) == 0 


def test_add_commit():
    ipvc = get_environment()
    ipvc.repo.init()

    with pytest.raises(RuntimeError):
        ipvc.stage.commit('asd')

    with pytest.raises(ValueError):
        ipvc.stage.add('/notrepo')

    testdir = REPO / 'testdir1' / 'testdir2'
    testdir.mkdir(parents=True)

    test_file = testdir / 'test_file.txt'
    write_file(test_file, 'hello world')

    changes = ipvc.stage.add(test_file)
    assert isinstance(changes, list) and len(changes) == 1 and changes[0]['Type'] == 0
    assert changes[0]['Path'] == ''

    test_file = REPO / 'test_file.txt'
    write_file(test_file, 'hello world')

    changes = ipvc.stage.add(test_file)
    assert isinstance(changes, list) and len(changes) == 1 and changes[0]['Type'] == 0
    assert changes[0]['Path'] == ''

    test_file1 = testdir / 'test_file1'
    write_file(test_file1, 'hello world1')

    test_file2 = testdir / 'test_file2'
    write_file(test_file2, 'hello world2')

    changes = ipvc.stage.add()
    assert isinstance(changes, list) and len(changes) == 2
    assert changes[0]['Type'] == 0 and changes[1]['Type'] == 0
    assert changes[0]['Path'] == 'testdir1/testdir2/test_file1'
    assert changes[1]['Path'] == 'testdir1/testdir2/test_file2'

    test_file3 = testdir / 'test_file3'
    test_file4 = testdir / 'test_file4'
    write_file(test_file3, 'hello world3')
    write_file(test_file4, 'hello world4')

    changes = ipvc.stage.add(testdir)
    assert isinstance(changes, list) and len(changes) == 2
    assert changes[0]['Type'] == 0
    assert changes[0]['Path'] == 'test_file3'
    assert changes[1]['Type'] == 0
    assert changes[1]['Path'] == 'test_file4'

    os.remove(test_file2)
    changes = ipvc.stage.add(REPO / 'notafolder/')
    assert isinstance(changes, list) and len(changes) == 0

    changes = ipvc.stage.add(test_file2)
    assert isinstance(changes, list) and len(changes) == 1
    assert changes[0]['Type'] == 1
    assert changes[0]['Path'] == ''

    time.sleep(1) # resolution of modification timestamp is a second
    write_file(test_file4, 'hello world5')

    changes = ipvc.stage.add(testdir)
    assert isinstance(changes, list) and len(changes) == 1
    assert changes[0]['Type'] == 2
    assert changes[0]['Path'] == 'test_file4'


def test_remove():
    ipvc = get_environment()
    ipvc.repo.init()

    testdir = REPO / 'testdir1' / 'testdir2'
    testdir.mkdir(parents=True)

    test_file = testdir / 'test_file.txt'
    write_file(test_file, 'hello world')

    changes = ipvc.stage.add(test_file)
    assert isinstance(changes, list) and len(changes) == 1 and changes[0]['Type'] == 0
    assert changes[0]['Path'] == ''

    ipvc.stage.commit('msg')

    time.sleep(1) # resolution of modification timestamp is a second
    write_file(test_file, 'hello world2')

    changes = ipvc.stage.add(test_file)
    assert isinstance(changes, list) and len(changes) == 1 and changes[0]['Type'] == 2
    assert changes[0]['Path'] == ''

    changes = ipvc.stage.remove(test_file)
    assert isinstance(changes, list) and len(changes) == 1 and changes[0]['Type'] == 2
    assert changes[0]['Path'] == ''

    head_stage, stage_workspace = ipvc.stage.status()
    assert isinstance(head_stage , list) and len(head_stage) == 0 and len(stage_workspace) == 1
