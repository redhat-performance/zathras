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

set -eu

# Check if dnf package manager is available
# Note: [[ ]] brackets are NOT needed here because:
# - 'if' statements work directly with command exit codes (0 = success, non-zero = failure)
# - 'command -v dnf' returns exit code 0 if dnf exists, non-zero if not found
# - The '!' negates the exit code result
# - '&> /dev/null' suppresses output while preserving the exit status
# - Test brackets are only needed for comparisons like [[ "$a" == "$b" ]] or [[ -f "$file" ]]
if ! command -v dnf &> /dev/null; then
    echo "Error: This script requires the DNF package manager."
    echo "Supported distributions: RHEL 8+, Fedora, CentOS 8+, Rocky Linux, AlmaLinux"
    echo "For other distributions, please install the required packages manually:"
    echo "  - ansible-core, git, jq, python, python3-pip, terraform, unzip, wget"
    exit 1
fi

# Check if script is being run as root
if (( $EUID == 0 )); then
    read -p "For most use cases, running this script as root is NOT recommended. Are you sure? Y/N " yesno

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
packages=(ansible-core git jq python python3-pip terraform unzip wget)

for package in "${packages[@]}"; do 
    if dnf list installed "$package" &> /dev/null; then
        echo "$package is installed."
    elif [ $package == "terraform" ]; then
        # Add the terraform repository from HashiCorp
        # currently supported distros: fedora, RHEL
        # reference: https://developer.hashicorp.com/terraform/cli/install/yum

        # Get operating system distribution
        os_release=$(grep "^ID=" /etc/os-release | awk -F'=' '{print $2}')

        # Sometimes the $release contains quotes that need to be removed
        os_release_clean=$(echo "$os_release" | tr -d '"')

        # HashiCorp repo urls are case-sensitive
        if [[ "$os_release_clean" == "rhel" ]]; then
            release='RHEL'
        elif [[ "$os_release_clean" == "fedora" ]]; then
            release='fedora'
        else
            echo "Error: Terraform installation is only supported on RHEL and Fedora distributions."
            echo "Detected OS: $os_release_clean"
            echo "Please install Terraform manually from https://developer.hashicorp.com/terraform/install"
            exit 1
        fi

        # repo URL for terraform
        repo_url="https://rpm.releases.hashicorp.com/${release}/hashicorp.repo"

        # run dnf config-manager
        sudo dnf config-manager --add-repo "$repo_url" || {
            echo "Error: Failed to add HashiCorp repository"
            exit 1
        }

        # install the package
        sudo dnf install terraform-1.9.8-1 -y || {
            echo "Error: Failed to install Terraform"
            exit 1
        }
    else
        echo "Installing $package..."
        sudo dnf install -y "$package" || {
            exit 1
        }
    fi

done


# pip install requirements
python_packages=(boto boto3 'yq==2.10.0')
for package in "${python_packages[@]}"; do
    pip3 install "$package" --user || {
        exit 1
    }
done


# install AWS collection for ansible
ansible_collections=(amazon.aws)
for collection in "${ansible_collections[@]}"; do
        ansible-galaxy collection install "$collection" || {
                exit 1
        }
done


echo "Before you can run Zathras:"
echo "****Ensure ~/.local/bin is in your path"
echo "****Set up a scenario file"
echo "****If running a local system, create the local config file for the system under test (SUT)"
echo "****If using an existing system, ssh-copy-id between the system Zathras is installed on and the SUT."
echo "****If working in a cloud environment do not perform the ssh-copy-id."
echo "****Update/create the test configuration files in /zathras/config/ to reflect your requirements."