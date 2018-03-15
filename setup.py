import re
from setuptools import setup
from pip.req import parse_requirements
import pypandoc


version = re.search('^__version__\s*=\s*"(.*)"',
                    open('ipvc/__init__.py').read(),
                    re.M).group(1)

long_description = pypandoc.convert('README.md', 'rst')

# parse_requirements() returns generator of pip.req.InstallRequirement objects
install_reqs = parse_requirements('requirements.txt', session='hack')
reqs = [str(ir.req) for ir in install_reqs]

setup(
    name="ipvc",
    packages=["ipvc"],
    entry_points={"console_scripts": ['ipvc = ipvc:main']},
    version=version,
    description="Inter-Planetary Version Control (System)",
    long_description=long_description,
    author="Martin Pettersson",
    author_email="martin@rememberberry.com",
    url="https://github.com/rememberberry/ipvc",
    install_requires=reqs
)
