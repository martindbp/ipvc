#! /bin/bash

# Run this test script in an empty folder, and against a ipfs repo without /ipvc in MFS

#Initialize a repository
OUT=$(ipvc repo init)
CORRECT="Successfully created repository"
if [ "$OUT" != "$CORRECT" ]; then
  echo "Error ipvc repo init:"
  printf "%s\n" "$OUT"
  printf "%s\n" "$CORRECT"
  exit 1
fi

#Create and add a file to the staging area
echo "hello world" > myfile.txt
OUT=$(ipvc stage add myfile.txt)
CORRECT="Changes:
+ QmT78zSuBmuS4z925WZfrqQ1qHaJ56DQaTfyMUF7F8ff5o"
if [ "$OUT" != "$CORRECT" ]; then
  echo "Error ipvc stage add 1:"
  printf "%s\n" "$OUT"
  printf "%s\n" "$CORRECT"
  exit 1
fi

#See what you've added to stage so far (status)
OUT=$(ipvc stage)
CORRECT="Staged:
+ myfile.txt QmT78zSuBmuS4z925WZfrqQ1qHaJ56DQaTfyMUF7F8ff5o
--------------------------------------------------------------------------------
No unstaged changes"
if [ "$OUT" != "$CORRECT" ]; then
  echo "Error ipvc stage:"
  printf "%s\n" "$OUT"
  printf "%s\n" "$CORRECT"
  exit 1
fi

#Commit the staged changes
ipvc stage commit "My first commit"

#See the commit history
OUT=$(ipvc branch history)
if [[ $OUT != *"My first commit"* ]]; then
  echo "Error ipvc branch history:"
  printf "%s\n" "$OUT"
  exit 1
fi

#Make a change to myfile.txt
sleep 1
echo "dont panic" > myfile.txt
OUT=$(ipvc stage add myfile.txt)
CORRECT="Changes:
QmT78zSuBmuS4z925WZfrqQ1qHaJ56DQaTfyMUF7F8ff5o --> QmbG1mR6m7KeJ3z2MB3t85VXxHUhD65kw3Yw3hGzStyEcW"
if [ "$OUT" != "$CORRECT" ]; then
  echo "Error ipvc stage add 2:"
  printf "%s\n" "$OUT"
  printf "%s\n" "$CORRECT"
  exit 1
fi

#See what changed
OUT=$(ipvc stage diff)
CORRECT="--- 
+++ 
@@ -1,2 +1,2 @@
-hello world
+dont panic"
if [ "$OUT" != "$CORRECT" ]; then
  echo "Error ipvc stage diff:"
  printf "%s\n" "$OUT"
  printf "%s\n" "$CORRECT"
  exit 1
fi

#Commit the change
ipvc stage commit "Update my file"

#Go back to the previous commit by creating a new branch
ipvc branch create --from-commit @head~ my_new_branch
OUT=$(ipvc branch)
CORRECT="my_new_branch"
if [ "$OUT" != "$CORRECT" ]; then
  echo "Error ipvc branch:"
  printf "%s\n" "$OUT"
  printf "%s\n" "$CORRECT"
  exit 1
fi

echo "All passed"
