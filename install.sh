#
# Copyright (C) 2024 Greg Dumas gdumas@redhat.com
#
#!/bin/bash

# Add the terraform repository from HashiCorp
# for reference: https://developer.hashicorp.com/terraform/cli/install/yum
# Currently supported distros: fedora, RHEL

# Get the operating system distribution
os_release=$(grep "^ID=" /etc/os-release | awk -F'=' '{print $2}')

# Sometimes $release contains quotes that need to be removed
os_release_clean=$(echo $os_release | tr -d '"')

# The HashiCorp repository urls are case-sensitive
if [ $os_release_clean = 'rhel' ]; then
    release='RHEL'
fi

# fedora
if [ $os_release_clean = 'fedora' ]; then
    release='fedora'
fi

# repo URL for terraform
repo_url="https://rpm.releases.hashicorp.com/${release}/hashicorp.repo"

# run dnf config-manager
dnf config-manager --add-repo $repo_url


# install other required packages
dnf update -y
dnf install ansible git jq python python3-pip terraform wget -y


# pip install requirements
pip3 install -U boto --user
pip3 install yq --user

# add yq install to path
export PATH=/usr/local/bin:$PATH


# Before you can run Zathras:
#   *Setup a scenario file 
#   *Create the local config file for the system under test (SUT)
#   *ssh-copy-id between the system you installed Zathras on and the SUT

