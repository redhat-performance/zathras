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

# Arrays to track what gets installed during script execution
# Format: "package_name:version"
installed_system_packages=()
installed_python_packages=()
installed_ansible_collections=()

# Check if dnf package manager is available
# Note: [[ ]] brackets are NOT needed here because:
# - 'if' statements work directly with command exit codes (0 = success, non-zero = failure)
# - 'command -v dnf' returns exit code 0 if dnf exists, non-zero if not found
# - The '!' negates the exit code result
# - '&> /dev/null' suppresses output while preserving the exit status
# - Test brackets are only needed for comparisons like [[ "$a" == "$b" ]] or [[ -f "$file" ]]
if ! command -v dnf &> /dev/null; then
    echo "Error: This script requires the DNF package manager."
    echo "Installer supported distributions: RHEL 8+, Fedora"
    echo "For other distributions, please install the required packages manually:"
    echo "  ansible-core, git, jq, python, python3-pip, terraform, unzip, wget"
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
# We expect EPEL to be installed, which contains gh.
#
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
        elif [[ "$os_release_clean" == "centos" ]]; then
            release='RHEL'
        elif [[ "$os_release_clean" == "fedora" ]]; then
            release='fedora'
        else
            echo "Error: Terraform installation is only supported on RHEL, CentOS, and Fedora distributions."
            echo "Detected OS: $os_release_clean"
            echo "Please install Terraform manually from https://developer.hashicorp.com/terraform/install"
            exit 1
        fi

        # repo URL for terraform
        repo_url="https://rpm.releases.hashicorp.com/${release}/hashicorp.repo"

        # Validate repo URL format before attempting to add it
        if [[ ! "$repo_url" =~ ^https://rpm\.releases\.hashicorp\.com/(RHEL|fedora)/hashicorp\.repo$ ]]; then
            echo "Error: Invalid HashiCorp repository URL format: $repo_url"
            echo "Please verify the OS detection or install Terraform manually"
            exit 1
        fi

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
        installed_system_packages+=("terraform:1.9.8-1")
    else
        echo "Installing $package..."
        sudo dnf install -y "$package" || {
            exit 1
        }
        # Get the installed version
        package_version=$(dnf list installed "$package" 2>/dev/null | tail -n 1 | awk '{print $2}' || echo "unknown")
        installed_system_packages+=("$package:$package_version")
    fi

done


# pip install requirements
python_packages=(boto boto3 'yq==2.10.0')
for package in "${python_packages[@]}"; do
    pip3 install "$package" --user || {
        exit 1
    }
    # Extract package name (remove version specifier if present)
    package_name=$(echo "$package" | sed 's/[<>=!].*//')
    # Get the installed version
    package_version=$(pip3 show "$package_name" 2>/dev/null | grep "Version:" | awk '{print $2}' || echo "unknown")
    installed_python_packages+=("$package_name:$package_version")
done


# install AWS collection and POSIX collection for ansible
ansible_collections=(ansible.posix community.aws community.general)
for collection in "${ansible_collections[@]}"; do
        ansible-galaxy collection install "$collection" || {
                exit 1
        }
        # Get the installed version
        collection_version=$(ansible-galaxy collection list "$collection" 2>/dev/null | grep "$collection" | awk '{print $2}' || echo "unknown")
        installed_ansible_collections+=("$collection:$collection_version")
done

# Pin amazon.aws to version 9.1.0 for compatibility reasons
ansible-galaxy collection install "amazon.aws:==9.1.0" || {
        exit 1
}
# Get the installed version for amazon.aws
amazon_aws_version=$(ansible-galaxy collection list "amazon.aws" 2>/dev/null | grep "amazon.aws" | awk '{print $2}' || echo "unknown")
installed_ansible_collections+=("amazon.aws:$amazon_aws_version")

# Function to write installation record
write_installation_record() {
    local install_log="zathras_install_$(date +%Y%m%d_%H%M%S).log"
    
    echo "=== Zathras Installation Record ===" > "$install_log"
    echo "Installation Date: $(date)" >> "$install_log"
    echo "User: $(whoami)" >> "$install_log"
    echo "Hostname: $(hostname)" >> "$install_log"
    echo "" >> "$install_log"
    
    echo "=== System Packages Installed ===" >> "$install_log"
    if [ ${#installed_system_packages[@]} -eq 0 ]; then
        echo "No new system packages were installed (all were already present)" >> "$install_log"
    else
        for package_info in "${installed_system_packages[@]}"; do
            package_name=$(echo "$package_info" | cut -d':' -f1)
            package_version=$(echo "$package_info" | cut -d':' -f2)
            echo "  - $package_name (version: $package_version)" >> "$install_log"
        done
    fi
    echo "" >> "$install_log"
    
    echo "=== Python Packages Installed ===" >> "$install_log"
    if [ ${#installed_python_packages[@]} -eq 0 ]; then
        echo "No Python packages were installed" >> "$install_log"
    else
        for package_info in "${installed_python_packages[@]}"; do
            package_name=$(echo "$package_info" | cut -d':' -f1)
            package_version=$(echo "$package_info" | cut -d':' -f2)
            echo "  - $package_name (version: $package_version)" >> "$install_log"
        done
    fi
    echo "" >> "$install_log"
    
    echo "=== Ansible Collections Installed ===" >> "$install_log"
    if [ ${#installed_ansible_collections[@]} -eq 0 ]; then
        echo "No Ansible collections were installed" >> "$install_log"
    else
        for collection_info in "${installed_ansible_collections[@]}"; do
            collection_name=$(echo "$collection_info" | cut -d':' -f1)
            collection_version=$(echo "$collection_info" | cut -d':' -f2)
            echo "  - $collection_name (version: $collection_version)" >> "$install_log"
        done
    fi
    echo "" >> "$install_log"
    
    echo "Installation record saved to: $install_log"
}

# Write installation record
write_installation_record

# Validate kit directories specified in templates
echo ""
echo "Validating kit directories..."

missing_kits=()
config_dir=$(readlink -f "config")

for template_file in config/*_template.yml; do
    # Skip if no files match the pattern
    [ -e "$template_file" ] || continue

    template_name=$(basename "$template_file")

    # Extract upload_extra value using yq
    upload_extra=$(yq -r '.upload_extra // "none"' "$template_file" 2>/dev/null || echo "none")

    # Skip if upload_extra is 'none', empty, or null
    if [[ "$upload_extra" == "none" ]] || [[ -z "$upload_extra" ]] || [[ "$upload_extra" == "null" ]]; then
        continue
    fi

    # Check if upload_extra is an array or a string
    is_array=$(yq -r '.upload_extra | type' "$template_file" 2>/dev/null || echo "null")

    if [[ "$is_array" == "array" ]]; then
        # It's an array, process each element
        while IFS= read -r path; do
            if [[ "$path" != "none" ]] && [[ -n "$path" ]]; then
                if [[ ! -e "$path" ]]; then
                    missing_kits+=("$template_name:$path")
                fi
            fi
        done < <(yq -r '.upload_extra[]' "$template_file" 2>/dev/null)
    else
        # It's a string, split by spaces
        IFS=' ' read -ra paths <<< "$upload_extra"
        for path in "${paths[@]}"; do
            if [[ "$path" != "none" ]] && [[ -n "$path" ]]; then
                if [[ ! -e "$path" ]]; then
                    missing_kits+=("$template_name:$path")
                fi
            fi
        done
    fi
done

# Display warning if there are missing kits
if [ ${#missing_kits[@]} -gt 0 ]; then
    echo ""
    echo "======================================================================"
    echo "WARNING: Missing Kit Directories"
    echo "======================================================================"
    echo ""
    echo "The following kit files/directories specified in templates do not exist:"
    echo ""
    for entry in "${missing_kits[@]}"; do
        template=$(echo "$entry" | cut -d':' -f1)
        path=$(echo "$entry" | cut -d':' -f2-)
        echo "  - $template: $path"
    done
    echo ""
    echo "These kits are required for certain benchmarks to run properly."
    echo "Wrappers depending on these kits may fail until they are provided."
    echo ""
    echo "Please ensure the required kits are placed at the specified locations"
    echo "or update the template files in $config_dir to reflect the correct paths."
    echo "======================================================================"
    echo ""
fi

echo "Before you can run Zathras:"
echo "****Ensure ~/.local/bin is in your path"
echo "****Set up a scenario file"
echo "****If running a local system, create the local config file for the system under test (SUT)"
echo "****If using an existing system, ssh-copy-id between the system Zathras is installed on and the SUT."
echo "****If working in a cloud environment do not perform the ssh-copy-id."
echo "****Update/create the test configuration files in /zathras/config/ to reflect your requirements."
