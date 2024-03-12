#!/bin/bash
#                         License
#
# Copyright (C) 2024 Greg Dumas gdumas@redhat.com
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.


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
echo "dnf config-manager --add-repo " $repo_url


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

