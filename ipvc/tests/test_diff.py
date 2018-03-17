import os
import time
import pytest

from ipvc import IPVC
from helpers import NAMESPACE, REPO, REPO2, get_environment, write_file


def test_stage_diff():
    ipvc = get_environment()
    ipvc.repo.init()

    test_file = REPO / 'test_file.txt'
    write_file(test_file, 'hello world')

    ipvc.stage.add(test_file)
    ipvc.stage.commit('my commit')

    time.sleep(1) # sleep to make sure we get another time stamp
    write_file(test_file, 'hello world2')
    diff = ipvc.stage.diff()
    assert len(diff) == 0

    diff = ipvc.diff.run(files=True)
    assert len(diff) == 0

    changes = ipvc.stage.add(test_file)
    assert len(changes) == 1
    diff = ipvc.stage.diff()
    assert len(diff) == 1

    diff = ipvc.diff.run(files=True)
    assert len(diff) == 1
