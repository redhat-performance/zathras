#!/usr/bin/env python3

import json

def _main(file):
	data = json.load(file)
	approved = False
	for review in data['latestReviews']:
		if review['state'] == "CHANGES_REQUESTED":
			return "inprogress"
		elif review['state'] == 'APPROVED':
			approved = True
	
	if len(data['reviewRequests']) > 0:
		return "review"

	if len(data['latestReviews']) > 0 and approved:
		return "approved"
	
	return "inprogress" #No PR Requests and no reviews, or only comments

if __name__ == "__main__":
	import sys
	in_file = sys.stdin
	if len(sys.argv) > 1:
		in_file = open(sys.argv[1], 'r')
	print(_main(in_file))
	in_file.close()
