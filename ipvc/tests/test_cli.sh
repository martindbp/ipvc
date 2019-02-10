#! /bin/bash

# Run this test script in an empty folder, and against a ipfs repo without /ipvc in MFS
# If you have valuable things in /ipvc then first move it somewhere else with e.g.
# > ipfs files mv /ipvc /tmp

# Also requires this shell script in /usr/local/bin/ to run commands:
#   #! /bin/bash
#   python3 -m ipvc "$@"


run_test () {
  OUT=$(eval $COMMAND)
  if [ "$OUT" != "$CORRECT" ]; then
    echo "Error running '$COMMAND':"
    printf "%s\n" "$OUT"
    printf "%s\n" "$CORRECT"
    exit 1
  else
    echo "Successfully ran '$COMMAND'"
  fi
}

run_test_like () {
  OUT=$(eval $COMMAND)
  if [[ "$OUT" != *"$CORRECT"* ]]; then
    echo "Error running '$COMMAND':"
    printf "%s\n" "$OUT"
    printf "%s\n" "$CORRECT"
    exit 1
  else
    echo "Successfully ran '$COMMAND'"
  fi
}


#Initialize a repository
COMMAND="ipvc repo init"
CORRECT="Successfully created repository"
run_test

#Create and add a file to the staging area
echo "hello world" > myfile.txt
COMMAND="ipvc stage add myfile.txt"
CORRECT="Changes:
+ QmT78zSuBmuS4z925WZfrqQ1qHaJ56DQaTfyMUF7F8ff5o"
run_test

#See what you've added to stage so far (status)
COMMAND="ipvc stage"
CORRECT="Staged:
+ myfile.txt QmT78zSuBmuS4z925WZfrqQ1qHaJ56DQaTfyMUF7F8ff5o
--------------------------------------------------------------------------------
No unstaged changes"
run_test

COMMAND="ipvc stage diff"
CORRECT="--- /dev/null
+++ myfile.txt
@@ -0,0 +1,2 @@
+hello world"
run_test

#Commit the staged changes
ipvc stage commit "My first commit"

#See the commit history
COMMAND="ipvc branch history"
CORRECT="My first commit"
run_test_like

#Make a change to myfile.txt
echo "Sleeping 1 second"
sleep 1
echo "dont panic" > myfile.txt
COMMAND="ipvc stage add myfile.txt"
CORRECT="Changes:
QmT78zSuBmuS4z925WZfrqQ1qHaJ56DQaTfyMUF7F8ff5o --> QmbG1mR6m7KeJ3z2MB3t85VXxHUhD65kw3Yw3hGzStyEcW"
run_test

COMMAND="ipvc stage diff"
CORRECT="--- myfile.txt
+++ myfile.txt
@@ -1,2 +1,2 @@
-hello world
+dont panic"
run_test

#Commit the change
ipvc stage commit "Update my file"

#Go back to the previous commit by creating a new branch
ipvc branch create --from-commit @head~ my_new_branch
COMMAND="ipvc branch"
CORRECT="my_new_branch"
run_test

COMMAND="ipvc branch ls"
CORRECT="master
my_new_branch"
run_test

COMMAND="ipvc branch history"
CORRECT="My first commit"
run_test_like

rm myfile.txt
COMMAND="ipvc diff"
CORRECT="--- myfile.txt
+++ /dev/null
@@ -1,2 +0,0 @@
-hello world"
run_test


COMMAND="ipvc repo rm"
CORRECT="Repository successfully removed"
run_test

echo "All passed"
