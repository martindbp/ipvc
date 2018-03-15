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

## What
* The implementation leverages IPFS's merkle-dag data structure for the commit graph, object storage and decentralized bit-torrent-like sharing
  * Supports large files out of the box, with no need for plugins, manually triggering file packing etc
  * Enables sharing the burden of seeding (pinning) large versioned datasets, just like bit-torrent
  * Decentralized publishing using ipns (Inter-Planetary Naming System), no need for a centralized git server (as longs as repostories are pinned (seeded) by anyone else)
  * Easy browsing of commits and repository content using go-ipfs gateway server
* Similar to gitless, each branch keeps track of its own workspace and the staging index. This allows for switching branches without having to commit or stash changes first. It also means that while being middle of resolving conflicts, you can switch to another branch to do some other work and return to resolve them later
* Unlike gitless, the staging area is kept the same as in git to allow for gradual building of commits and picking individual lines from certain files
* Automatically update any hash links in the repository content when a file changes
* Ability to check out only the parts of a large repository you care about

## Installation
`pip install ipvc`
Note: Python >=3.6 is required to run IPVC

# Prerequisites
* go
* go-ipfs
* Python >=3.6

## Commands and Examples
Note: commands not yet implemented are "commented" out

* `ipvc repo init`
* `ipvc repo mv <path1> [<path2>]`
* `//ipvc repo rm [<path>]`
* `//ipvc repo # status`
* `//ipvc repo ls - list all repos in ipvc`
* `ipvc branch # status`
* `ipvc branch create [--from-commit <hash>] <name>`
* `ipvc branch rm <name>`
* `ipvc branch mv <name>`
* `ipvc branch checkout <name>`
* `ipvc branch history # log`
* `ipvc branch show <refpath> # open refpath in browser`
* `//ipvc branch cat <refpath> # cat refpath`
* `//ipvc branch ls # list branches`
* `//ipvc branch merge <refpath> # analagous to git merge`
* `//ipvc branch replay <refpath> # analagous to git rebase`
* `//ipvc branch publish [--all] # publish branch to ipns`
* `//ipvc branch unpublish [--all]`
* `ipvc stage # status`
* `ipvc stage add <path>`
* `ipvc stage remove <path>`
* `ipvc stage commit <msg>`
* `ipvc stage diff # alias for ipvc diff content stage workspace`
* `//ipvc stage uncommit`
* `ipvc diff files <to-refpath> <from-refpath>`
* `ipvc diff content <to-refpath> <from-refpath>`

## How
* Uses in Python 3.6, with go-ipfs as the IPFS server
* Keeps track of the current state of the workspace, the staging area and the head of each branch. The workspace state is updated before every IPVC command is carried out
* Leverages the IPFS mutable files system (MFS) for easy book-keeping of repositories and branches and commits
* Stores repositories and branches as folder and subfolders on the MFS as well as global settings
* The refs to workspace, staging area and head of each branch is stores as subfolders within each branch
* Each ref has a `bundle` subfolder which stores the reference to the actual file hierarchy and metadata which stores the timestamps and permissions of the files (this is not currently stored in the IPFS files ipld format)
* Individual commit objects are stored as folders where there are links to the parent commit and the repository ref, as well as a metadata file with author information and a timestamp

## TODO
* Merging/rebase
* Partial branch checkout 
* Encryption of data/commits?
* Export/import from/to git/mercurial
* Permissions in metadata
* Follow + store symlinks in metadata
* Virtual repos (IPFS only, not on the filesystem)
* A server with GUI
