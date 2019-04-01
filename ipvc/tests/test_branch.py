import os
import pytest
import time
from pathlib import Path

from ipvc import IPVC
from helpers import NAMESPACE, REPO, REPO2, get_environment, write_file, Profile


def assert_list_equals(l1, l2):
    for item1, item2 in zip(l1, l2):
        assert item1 == item2


def test_merge_replay():
    ipvc = get_environment()
    ipvc.repo.init()
    test_file_content = 'line1\nline2\nline3\nline4'
    write_file(REPO / 'test_file.txt', test_file_content)
    write_file(REPO / 'test_file3.txt', test_file_content)
    ipvc.stage.add()
    ipvc.stage.commit('msg1')

    ipvc.branch.create('other', no_checkout=True)

    time.sleep(1) # resolution of modification timestamp is a second
    write_file(REPO / 'test_file.txt', 'line1\nother\nline3\nline4')
    write_file(REPO / 'test_file3.txt', 'line1\nline2\nline3\nline4\nappended')
    write_file(REPO / 'other_file.txt', 'hello world')
    ipvc.stage.add()
    ipvc.stage.commit('msg2')

    ipvc.branch.checkout('other')
    time.sleep(1) # resolution of modification timestamp is a second
    write_file(REPO / 'test_file.txt', 'line1\nline2\nblerg\nline4')
    write_file(REPO / 'test_file3.txt', 'prepended\nline1\nline2\nline3\nline4')
    with pytest.raises(RuntimeError):
        ipvc.branch.merge('master')

    ipvc.stage.add()
    with pytest.raises(RuntimeError):
        ipvc.branch.merge('master')

    ipvc.stage.commit('msg2other')
    _, merged_files, conflict_files = ipvc.branch.replay('master')
    assert conflict_files == set(['test_file.txt'])
    assert merged_files == set(['test_file3.txt'])
    ipvc.branch.replay(abort=True)

    pulled_files, merged_files, conflict_files = ipvc.branch.merge('master')
    assert conflict_files == set(['test_file.txt'])
    assert pulled_files == set(['other_file.txt'])
    assert merged_files == set(['test_file3.txt'])
    conflict_lines = [
        'line1',
        '>>>>>>> other (ours)',
        'line2',
        'blerg',
        '======= master (theirs)',
        'other',
        'line3',
        '<<<<<<<',
        'line4'
    ]
    pulled_lines = ['hello world']
    merged_lines = [
        'prepended',
        'line1',
        'line2',
        'line3',
        'line4',
        'appended'
    ]

    assert_list_equals(open(REPO / 'test_file.txt', 'r').read().splitlines(),
                       conflict_lines)
    assert_list_equals(open(REPO / 'other_file.txt', 'r').read().splitlines(),
                       pulled_lines)
    assert_list_equals(open(REPO / 'test_file3.txt', 'r').read().splitlines(),
                       merged_lines)

    head_stage, stage_workspace = ipvc.stage.status()
    # Two files should be staged (other_file.txt and test_file3.txt)
    # and one file (test_file.txt) has a conflict and should not be staged
    assert len(head_stage) == 2 and len(stage_workspace) == 1

    ipvc.branch.merge(abort=True)
    head_stage, stage_workspace = ipvc.stage.status()
    assert len(head_stage) == 0 and len(stage_workspace) == 0

    with pytest.raises(FileNotFoundError):
        (REPO / 'other_file.txt').stat()

    assert open(REPO / 'test_file.txt', 'r').read() == 'line1\nline2\nblerg\nline4'
    assert open(REPO / 'test_file3.txt', 'r').read() == 'prepended\nline1\nline2\nline3\nline4'

    # Pull again and fix the merge and commit this time
    ipvc.branch.merge('master')

    with pytest.raises(RuntimeError):
        # Should raise because conflict markers are still there
        ipvc.branch.merge(resolve='msg')

    # "Fix"
    write_file(REPO / 'test_file.txt', '\n'.join(merged_lines))
    ipvc.branch.merge(resolve='msg')

    # Latest commit must have a merge parent
    assert ipvc.branch.history()[0][-1] is not None

    # Test fast-forward merges
    write_file(REPO / 'ff_file.txt', 'hello world')
    ipvc.stage.add(REPO / 'ff_file.txt')
    ff_hash = ipvc.stage.commit('ff')
    ipvc.branch.checkout('master')
    ipvc.branch.merge('other')
    history = ipvc.branch.history()
    assert history[0][0] == ff_hash
    # Doesn't have a merge parent
    assert history[0][-1] == None

    ipvc.print_ipfs_profile_info()


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

    ipvc.print_ipfs_profile_info()


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

    ipvc.print_ipfs_profile_info()

def test_history():
    ipvc = get_environment()
    ipvc.repo.init()

    write_file(REPO / 'test_file.txt', 'hello world')
    ipvc.stage.add()

    ipvc.stage.commit('commit message')
    try:
        ipvc.ipfs.files_stat(ipvc.repo.get_mfs_path(REPO, 'master', branch_info='head/data/bundle'))
    except:
        assert False

    try:
        ipvc.ipfs.files_stat(ipvc.repo.get_mfs_path(REPO, 'master', branch_info='head/data/parent'))
    except:
        assert False

    try:
        metadata = ipvc.repo.mfs_read_json(
            ipvc.repo.get_mfs_path(REPO, 'master', branch_info='head/data/commit_metadata'))
    except:
        assert False

    commits = ipvc.branch.history()
    assert len(commits) == 1

    assert ipvc.branch.show(Path('@head')) == 'test_file.txt'
    assert ipvc.branch.show(Path('@head/test_file.txt')) == 'hello world'

    ipvc.print_ipfs_profile_info()
