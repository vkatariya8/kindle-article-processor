#!/bin/bash
# Remove all question marks from filenames in current directory

for file in *\?*; do
    [ -e "$file" ] || continue
    newname="${file//\?/}"
    mv -i "$file" "$newname"
    echo "Renamed: $file -> $newname"
done
