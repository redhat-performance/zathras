# Workflows in this repository

## Update parent issue
The idea behind this workflow is to keep Jira tickets in sync with the current status of their GitHub issue.  A flowchart for how this works can be seen below.

![flow chart for PR labelling workflow](ci/images/pr_labelling.png)

This workflow does not work with forked repositories, since the `GITHUB_TOKEN` provided by GitHub runner will not have write access to the base repository unless the pull request originated from the base repository.
