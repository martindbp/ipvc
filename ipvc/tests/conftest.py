"""
Configure pytest to take a 'name' parameter for integration test name
"""

def pytest_addoption(parser):
    # NOTE: default values can't be None, so use 'None' string instead
    parser.addoption("--name", action="store", default='None')
    parser.addoption("--tests_dir", action="store", default='ipvc/tests/integration_tests')
    parser.addoption("--stop_command", action="store", default='None')


def pytest_generate_tests(metafunc):
    # This is called for every test. Only get/set command line arguments
    # if the argument is specified in the list of test "fixturenames".
    for arg in ['tests_dir', 'name', 'stop_command']:
        val = getattr(metafunc.config.option, arg)
        if arg in metafunc.fixturenames and val is not None:
            metafunc.parametrize(arg, [val])
