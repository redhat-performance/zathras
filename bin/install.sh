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

# Check if script is being run as root
if (( $EUID == 0 )); then
    read -p "For most use cases, running this script as root is NOT recommended. Are you sure? Y/N" yesno

    case $yesno in
        [Yy]* )
            echo "You answered yes, continuing install as root." ;;
        [Nn]* )
            echo "You answered no, exiting"; exit 1 ;; 
        *) 
            echo "Unknown input, exiting"; exit 1 ;;
    esac
else
    echo "Not running as root, proceed."
fi

# check for and install system packages
packages=(ansible git jq python python3-pip terraform wget)

for package in "${packages[@]}"; do 
    if dnf list installed "$package" &> /dev/null; then
        echo "$package is installed."
    elif dnf list "$package" &> /dev/null; then
        echo "$package is not installed but available. Installing..."
        sudo dnf install -y "$package"
    elif [ $package == "terraform" ]; then
        # Add the terraform repository from HashiCorp
        # currently supported distros: fedora, RHEL
        # reference: https://developer.hashicorp.com/terraform/cli/install/yum

        # Get operating system distribution
        os_release=$(grep "^ID=" /etc/os-release | awk -F'=' '{print $2}')

        # Sometimes the $release contains quotes that need to be removed
        os_release_clean=$(echo $os_release | tr -d '"')

        # HashiCorp repo urls are case-sensitive
        if [ $os_release_clean = 'rhel' ]; then
            release='RHEL'
        elif [ $os_release_clean = 'fedora' ]; then
            release='fedora'
        fi

        # repo URL for terraform
        repo_url="https://rpm.releases.hashicorp.com/${release}/hashicorp.repo"

        # run dnf config-manager
        sudo dnf config-manager --add-repo $repo_url

        # install the package
        sudo dnf install terraform -y
    else
        echo "package $package is not installed and not available."
    fi

done


# pip install requirements
pip3 install boto boto3 --user
pip3 install 'yq==2.10.0' 


echo "Before you can run Zathras:"
echo "****Ensure ~/.local/bin is in your path"
echo "****Set up a scenario file"
echo "****If running a local system, create the local config file for the system under test (SUT)"
echo "****If using an existing system, ssh-copy-id between the system Zathras is installed on and the SUT."
echo "****If working in a cloud environment do not perform the ssh-copy-id."
echo "****Update/create the test configuration files in /zathras/config/ to reflect your requirements."
