#!/bin/bash

mentioned_issues=$(gh -R "$1" pr view "$2" --json body | jq -r .body | grep -Eo '#[0-9]+' | sed -e 's/#//g')

for issue in $mentioned_issues; do
	if gh -R "$1" issue view "$issue" --json id > /dev/null; then
		echo -n  "$issue "
	fi
done
