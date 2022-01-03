IMPORTANT: this project is not active and further development is not considered at this time, but it may serve as inspiration for future implementations.

# Inter-Planetary Version Control (System)

IPVC is a distributed version control system similar to git, but built on IPFS (Inter-Planetary File System). It is suitable for any kind of data, not only human readable content. It is also particularly suitable for versioning large files. The underlying concepts are heavily influenced by git and [gitless](gitless.com).

## Caveats
* The project is purely experimental at this stage, with many missing features (see the TODO section)
* Due to the [public nature](https://github.com/ipfs/notes/issues/270) of IPFS data, IPVC might not be suitable for private repositories, unless it is hosted on a private network.
* Due to the interaction with the IPFS daemon (and possibly Python), IPVC commands are quite slow, unlike snappy git commands

## Why IPFS?
IPFS with its content addressable Merkle-DAGs is the perfect technology for hosting repositories of data as well as commit graphs.

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

* `ipvc repo init [<name>]`
* `ipvc repo mv <path1> [<path2>]`
* `ipvc repo # alias for ls`
* `ipvc repo rm [<path>]`
* `ipvc repo ls # list all repos in ipvc`
* `ipvc repo mv [<from>] <to> # move a repository`
* `ipvc repo id [<key>] # get/set id for repository`
* `ipvc repo name [<name>] # get/set name for repository`
* `ipvc repo publish # publish the repo to IPNS`
* `ipvc repo unpublish # unpublish the repo from IPNS`
* `ipvc repo clone [--as-name <name>] <PeerID> <peer-repo> # clone a repo as name`
* `//ipvc repo remote <PeerID> <peer-repo> # show/set remote destination of repo`
* `ipvc branch # status`
* `ipvc branch create [--from-commit <hash>] <name>`
* `ipvc branch checkout <name>`
* `ipvc branch history # git log`
* `ipvc branch show <refpath> # shows content of refpath`
* `ipvc branch ls # list branches`
* `ipvc branch merge [--abort] [--resolve [<message>]] [--no-ff] <branch> # analagous to git merge`
* `ipvc branch replay [--abort] [--resume] <branch> # analagous to git rebase`
* `//ipvc branch rm <branch name>`
* `//ipvc branch mv [<from>] <to>`
* `//ipvc branch reset [<path>] # reset workspace at path`
* `//ipvc branch rewrite # analagous to git rebase -i`
* `//ipvc branch fetch # download the latest remote of this branch`
* `//ipvc branch pull # fetch and merge`
* `//ipvc branch remote [<PeerID>] [<peer-repo>] [<peer-branch>] # show/set remote destination for branch
* `ipvc branch publish [<branch>] # publish branch to IPNS`
* `ipvc branch unpublish`
* `ipvc stage # status`
* `ipvc stage add <path>`
* `ipvc stage remove <path>`
* `ipvc stage commit <msg>`
* `ipvc stage diff # alias for ipvc diff stage workspace, equivalent to git diff --cached`
* `//ipvc stage uncommit`
* `ipvc diff [--files] [<to-refpath>] [<from-refpath>] # defaults to @workspace -> @stage, equivalent to git diff`
* `ipvc id # list`
* `ipvc id list [--unused] # List all local and remote ids`
* `ipvc id create <key> # Creates a new key/id`
* `ipvc id get [--key <key>] # Show identity used for repo or key`
* `ipvc id set [--name <name>] [--email <email>] [--desc <desc>] [--img <img_hash>] <key> # Create identity for ipfs key / repo`
* `ipvc id publish [--key <key>] # Publish id data on IPNS
* `//ipvc id resolve [--peer_id <peer_id>] [--name <name>] # Resolve remote ids from IPNS`

## How
* Uses Python 3.6, with go-ipfs as the IPFS server
* Keeps track of the current state of the workspace, the staging area and the head of each branch. The workspace state is updated before every IPVC command is carried out
* Leverages the IPFS mutable files system (MFS) for easy book-keeping of repositories and branches and commits
* Stores repositories and branches as folder and subfolders on the MFS as well as other settings
* The refs to workspace, staging area and head of each branch is stored as subfolders within each branch
* Each ref has a `bundle` subfolder which contains the reference to the actual file hierarchy and metadata which contains the timestamps and permissions of the files (this is not currently stored in the IPFS files ipld format)
* Individual commit objects are stored as folders where there are links to the parent commit and the repository ref, as well as a metadata file with author information and a timestamp

## TODO and Ideas
In no particular order of importance

### Features
* Downloading branches from other people (git pull)
* Branch rewrite, similar to rebase -i
* Export/import from/to git/mercurial
* Fix handling of file permissions, so that such changes can be seen and added
* Tags
* Follow + store symlinks in metadata
* Picking lines when adding to stage, similar to git's `git add -p`
* Virtual repos (in IPFS/MFS only, not on the filesystem)
* Partial branch checkout
* For large read-only files, link to IPFS fs mount?
* Encryption of data/commits?
* Issues, pull requests, discussions etc via pubsub and CRDTs
* Equivalent of ignore file
* Generate a browsable static website for a repo like a github project
* A --keep-workpace flag for branch checkout, for bringing workspace changes to new branch

### Other
* Optimize! Currently things are way too slow
* Use aiohttp for async data transfer between ipfs and files for progress information
  (also for pinnig)

## Testing
There are two levels of tests, in pytest, and a command line test.

To run pytest, run
> python3 -m pytest -s -x
in the ipvc folder

Integration tests recorded in the CLI itself can be run separately by
> python3 -m pytest -x -s ipvc/tests/test_integration.py [--name <name>]
For more information, read test_integration.py

Make sure that ipfs is running on standard port.

## Release / PyPI

Notes for maintainers on how to release ipvc as a package on PyPI

1. Bump the version in "ipvc/__init__.py", using semver notation (major.minor.patch)
2. Commit and tag using "git tag {major.minor.patch}"
3. Build the distribution: "python setup.py sdist"
4. Upload to twine test end-point: "twine upload --repository-url https://test.pypi.org/legacy/ dist/ipvc-{major.minor.patch}.tar.gz"
5. Install and test from pip: "pip install --index-url https://test.pypi.org/simple/ ipvc"
6. When tested, upload to real twine (without --repository-url)

Version numbers can't be reused, so if there are problems then the version number has to be bumped. Because of this, the version numbers used on test end-point are not the same as in normal end-point. Therefore, it's best to test using a fake version number, and only commit and release when there are no problems on test.
