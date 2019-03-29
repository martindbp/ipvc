# Inter-Planetary Version Control (System)

IPVC is a distributed version control system similar to git, but built on IPFS (Inter-Planetary File System). It is suitable for any kind of data, not only human readable content. It is also particularly suitable for versioning large files. The underlying concepts are heavily influenced by git and [gitless](gitless.com).

## Caveats
* The project is purely experimental at this stage, with many missing features (see the TODO section)
* Due to the [public nature](https://github.com/ipfs/notes/issues/270) of IPFS data, IPVC might not be suitable for private repositories, unless it is hosted on a private network.
* Due to the interaction with the IPFS daemon (and possibly Python), IPVC commands are quite slow, unlike snappy git commands

## Why IPFS?
IPFS with its content addressable merkle-dags is the perfect technology for hosting repositories of data as well as commit graphs.

### Why not just use git?
While there is a [git remote helper for ipfs](https://github.com/magik6k/git-remote-ipld) that translates the git file formats to traversable hash links, there is currently no way of getting interoperability for large files since IPFS has a maximum block size of ~4 Mb and git stores files as single blobs. While a workaround may be available in the future we can therefore not currently recreate compatible hashes using ipld.

## What does it do?
* The implementation leverages IPFS's merkle-dag data structure for the commit graph, object storage and decentralized bit-torrent-like sharing
  * Supports large files out of the box, with no need for plugins, manually triggering file packing etc
  * Enables sharing the burden of seeding (pinning) large versioned datasets, just like bit-torrent
  * Decentralized publishing using ipns (Inter-Planetary Naming System), no need for a centralized git server (as longs as repostories are pinned (seeded) by anyone else)
  * Easy browsing of commits and repository content using go-ipfs gateway server
* Similar to gitless, each branch keeps track of its own workspace and the staging index. This allows for switching branches without having to commit or stash changes first. It also means that while being in the middle of resolving conflicts, you can switch to another branch to do some other work and return to resolve them later
* Unlike gitless, the staging area is kept the same as in git to allow for gradual building of commits and picking individual lines from certain files
* Automatically update any hash links in the repository content when a file changes
* Ability to check out only the parts of a large repository you care about

## Installation
NOTE: not recommended right now, not regularly updated and contains bugs.
```
pip install ipvc
```

Note: Python >=3.6 and go-ipfs is required to run IPVC

## Usage
Initialize a repository
```
$ ipvc repo init
Successfully created repository
```

Create and add a file to the staging area
```
$ echo "hello world" > myfile.txt
$ ipvc stage add myfile.txt
Changes:
+  QmT78zSuBmuS4z925WZfrqQ1qHaJ56DQaTfyMUF7F8ff5o

```

See what you've added to stage so far (status)
```
$ ipvc stage
Staged:
+ myfile.txt QmT78zSuBmuS4z925WZfrqQ1qHaJ56DQaTfyMUF7F8ff5o
```

Commit the staged changes
```
$ ipvc stage commit "My first commit"
```

See the commit history
```
$ ipvc branch history
* 2018-03-17T14:43:22.254582           My first commit
```

Make a change to myfile.txt
```
$ echo "dont panic" > myfile.txt
$ ipvc stage add myfile.txt
Changes:
 QmT78zSuBmuS4z925WZfrqQ1qHaJ56DQaTfyMUF7F8ff5o --> QmbG1mR6m7KeJ3z2MB3t85VXxHUhD65kw3Yw3hGzStyEcW
```

See what changed
```
$ ipvc stage diff
--- 
+++ 
@@ -1,2 +1,2 @@
-hello world
+dont panic
```

Commit the change
```
$ ipvc stage commit "Update my file"
```

Go back to the previous commit by creating a new branch
```
$ ipvc branch create --from-commit @head~ my_new_branch
$ ipvc branch
my_new_branch
```

NOTE: usage is incomplete as many important commands are not yet implemented

# Prerequisites
* go-ipfs
* Python >=3.6

## Commands and Examples
Note: commands not yet implemented are "commented" out

* `ipvc repo init`
* `ipvc repo mv <path1> [<path2>]`
* `ipvc repo # alias for ls`
* `ipvc repo rm [<path>]`
* `ipvc repo ls # list all repos in ipvc`
* `ipvc repo mv [<from>] <to> - move a repository`
* `//ipvc repo publish [--name] <path> # publish the repo to IPNS with a name
* `//ipvc repo unpublish <path> # unpublish the repo from IPNS
* `//ipvc repo clone [--name] <IPFS/IPNS> # clone a repo as name
* `//ipvc repo remote [<IPNS>] # show/set remote destination of repo
* `ipvc branch # status`
* `ipvc branch create [--from-commit <hash>] <name>`
* `//ipvc branch rm <branch name>`
* `//ipvc branch mv [<from>] <to>`
* `//ipvc branch reset [<path>] # reset workspace at path`
* `ipvc branch checkout <name>`
* `ipvc branch history # log`
* `//ipvc branch rewrite # analagous to git rebase -i
* `ipvc branch show <refpath> # shows content of refpath`
* `ipvc branch ls # list branches`
* `ipvc branch merge [--abort] [--resolve [<message>]] [--no-ff] <branch> # analagous to git merge`
* `ipvc branch replay [--abort] [--resolve] <branch> # analagous to git rebase`
* `//ipvc branch fetch` # download the latest remote of this branch
* `//ipvc branch pull` # fetch and merge
* `//ipvc branch publish # publish branch to IPNS`
* `//ipvc branch unpublish`
* `ipvc stage # status`
* `ipvc stage add <path>`
* `ipvc stage remove <path>`
* `ipvc stage commit <msg>`
* `ipvc stage diff # alias for ipvc diff stage workspace`
* `//ipvc stage uncommit`
* `ipvc diff files <to-refpath> <from-refpath>`
* `ipvc diff content <to-refpath> <from-refpath>`

## How
* Uses Python 3.6, with go-ipfs as the IPFS server
* Keeps track of the current state of the workspace, the staging area and the head of each branch. The workspace state is updated before every IPVC command is carried out
* Leverages the IPFS mutable files system (MFS) for easy book-keeping of repositories and branches and commits
* Stores repositories and branches as folder and subfolders on the MFS as well as global settings
* The refs to workspace, staging area and head of each branch is stored as subfolders within each branch
* Each ref has a `bundle` subfolder which contains the reference to the actual file hierarchy and metadata which contains the timestamps and permissions of the files (this is not currently stored in the IPFS files ipld format)
* Individual commit objects are stored as folders where there are links to the parent commit and the repository ref, as well as a metadata file with author information and a timestamp

## TODO and Ideas
In no particular order of importance

### Features
* Downloading branches from other people (git pull)
* Branch rewrite, similar to rebase -i
* Publishing to IPNS
* Export/import from/to git/mercurial
* Fix handling of file permissions, so that such changes can be seen and added
* Tags
* Follow + store symlinks in metadata
* Picking lines when adding to stage, similar to git's `git add -p`
* Virtual repos (in IPFS/MFS only, not on the filesystem)
* Partial branch checkout
* Encryption of data/commits?
* Issues, pull requests, discussions etc via pubsub and CRDTs
* Equivalent of ignore file
* Generate a browsable static website for a repo like a github project

### Other
* Optimize! Currently things are way too slow
* Use aiohttp for async data transfer between ipfs and files

## Testing
There are two levels of tests, in pytest, and a command line test.

To run pytest, run
> python3 -m pytest -s
in the ipvc folder

To run the command line tests, create an empty folder and from it, run
> {path to ipvc}/tests/test_cli.sh

In both cases, make sure that ipfs is running

## Release / PyPI

Notes for maintainers on how to release ipvc as a package on PyPI

1. Bump the version in "ipvc/__init__.py", using semver notation (major.minor.patch)
2. Commit and tag using "git tag {major.minor.patch}"
3. Build the distribution: "python setup.py sdist"
4. Upload to twine test end-point: "twine upload --repository-url https://test.pypi.org/legacy/ dist/ipvc-{major.minor.patch}.tar.gz"
5. Install and test from pip: "pip install --index-url https://test.pypi.org/simple/ ipvc"
6. When tested, upload to real twine (without --repository-url)

Version numbers can't be reused, so if there are problems then the version number has to be bumped. Because of this, the version numbers used on test end-point are not the same as in normal end-point. Therefore, it's best to test using a fake version number, and only commit and release when there are no problems on test.
