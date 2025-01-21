# Workflows in this repository

## Verify PR has JIRA ticket and issue number
This workflow is designed to enforce requirements for PR descriptions.  At bare minimum it requires the PR to mention a related issue and mention the Jira Ticket number.  Both of these are required since Sync2Jira does not know how to associate a PR with a Jira Ticket from the originating GitHub issue.


## Update parent issue
The idea behind this workflow is to keep Jira tickets in sync with the current status of their GitHub issue.  A flowchart for how this works can be seen below.

![flow chart for PR labelling workflow](images/pr_labelling.jpg)

This workflow does not work with forked repositories, since the `GITHUB_TOKEN` provided by GitHub runner will not have write access to the base repository unless the pull request originated from the base repository.
