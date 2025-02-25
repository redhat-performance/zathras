#!/usr/bin/env python3

import json

def _main(file):
	data = json.load(file)

	for review in data['latestReviews']:
		if review['state'] == "CHANGES_REQUESTED":
			return "inprogress"
	
	if len(data['reviewRequests']) > 0:
		return "review"

	if len(data['latestReviews']) > 0:
		return "approved"
	
	return "inprogress" #No PR Requests and no reviews

if __name__ == "__main__":
	import sys
	in_file = sys.stdin
	if len(sys.argv) > 1:
		in_file = open(sys.argv[1], 'r')
	print(_main(in_file))
	in_file.close()
