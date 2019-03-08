"""
Configure pytest to take a 'name' parameter for integration test name
"""

def pytest_addoption(parser):
    parser.addoption("--name", action="store", default=None)
    parser.addoption("--tests_dir", default='ipvc/tests/integration_tests')


def pytest_generate_tests(metafunc):
    # This is called for every test. Only get/set command line arguments
    # if the argument is specified in the list of test "fixturenames".
    name_value = metafunc.config.option.name
    if 'name' in metafunc.fixturenames and name_value is not None:
        metafunc.parametrize("name", [name_value])

    tests_dir_value = metafunc.config.option.tests_dir
    if 'tests_dir' in metafunc.fixturenames and tests_dir_value is not None:
        metafunc.parametrize("tests_dir", [tests_dir_value])
