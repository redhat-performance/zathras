#!/bin/bash
#
# Welcome to kickoff.  We run as a background process from burden, and operate
# in the working directory created by burden.   The purpose of kickoff is to
# finish prepping the working directory, and then invoking the ansible playbook.
# Burden will hang around waiting for us to finish.
#
# File dependencies:
#   ansible_vars_main.yml file is present in the directory passed via -d
#
# Files created:
#  ansible_vars.yml: contains the contents of ansible_vars_main.yml and has the following
#                    addeded.
#			sys_config: File containing system variables to be set.  For none, file
#                                   name="none"
#			init_system: Indicates if we need to set the VM up.
#			term_system: Indicates if we are to terminate the VM when the last test
#			             in this pass is completed.
#			
#
spot_recover=1
create_attempts=5
remove_dirs=0
ssh_key_file=""
while getopts "a:c:d:f:s:r:S:" o; do
        case "${o}" in
		a)
			create_attempts=${OPTARG}
		;;
		c)
			config_dir=${OPTARG}
		;;
		d)
			direct=${OPTARG}
		;;
		f)
			tune_file=${OPTARG}
		;;
		r)
			remove_dirs=1
		;;
		S)
			spot_recover=${OPTARG}
		;;
		s)
			ssh_key_file=${OPTARG}
		;;
	esac
done
shift $((OPTIND-1))

#
# Clean house, populate, and set permissions
#
ln -s `pwd`/bin/aws_network_create $direct/aws_network_create
ln -s `pwd`/bin/remove_wrong_cpus $direct/remove_wrong_cpus
ln -s `pwd`/bin/aws_set_term_flags $direct/aws_set_term_flags
ln -s `pwd`/tools_bin/update_system $direct/update_system
ln -s `pwd`/tools_bin/update_repo.file $direct/update_repo.file
ln -s `pwd`/ansible_roles/roles $direct/roles
ln -s `pwd`/bin/ten_of_us.yml $direct/ten_of_us.yml
ln -s ${config_dir}/inventory $direct/inventory

top_dir=`pwd`

cd $direct

mkdir config
curdir=`pwd`
individual=`echo $tune_file | sed "s/,/ /g" | sed "s/\[//g" | sed "s/\]//g"`
init_system="\"yes\""
term_system="\"no\""
tests=0
#
# If required check the config settings to make sure we have possible valid data.
# Also chmod user.pem_test to be 500.
#
if [[ $ssh_key_file != "" ]]; then
	cp $ssh_key_file config/user.pem_test
	if [ ! -s $ssh_key_file ]; then
		echo "${ssh_key_file} is zero length, please fix.  Test is exiting"
		exit
	fi
	chmod 500 config/user.pem_test
fi

#
# figure out how many files we have to set /proc/* etc. This allows us to only terminate the
# VM when we have done all of them (tuneds are changed in ansible, in ten_of_us.yml).
#
for sys_config in ${individual};
do
	let "tests=$tests+1"
done

#
# Cycle through all the files setting system values.
#
export ANSIBLE_HOST_KEY_CHECKING=False
echo "[defaults]" >> ansible.cfg
echo "roles_path = ~/.ansible/roles:/usr/share/ansible/roles:/etc/ansible/roles:~/.ansible/collections/ansible_collections/pbench/agent/roles" >> ansible.cfg
current_test=0
for sys_config in ${individual};
do
	let "current_test=$current_test+1"
	if [ $current_test -eq $tests ]; then
		term_system="\"yes\""
	fi
	#
	# Set up the standard test options.
	#
	cp ansible_vars_main.yml ansible_vars.yml
	#
	# Now add in stuff that changes during execution
	#
	echo "  sys_config: ${sys_config}" >> ansible_vars.yml
	echo "  init_system: ${init_system}" >> ansible_vars.yml
	echo "  term_system: ${term_system}" >> ansible_vars.yml
	system_type=`grep system_type  ansible_vars_main.yml | cut -d':' -f 2 | cut -d' ' -f 2`
	attempts=1
	while [ $attempts -ne $create_attempts ]
	do
		mkdir tf
		echo ansible-playbook -i ./inventory --extra-vars "working_dir=${curdir} ansible_python_interpreter=/usr/bin/python3" ten_of_us.yml
		ansible-playbook -i ./inventory --extra-vars "working_dir=${curdir} ansible_python_interpreter=/usr/bin/python3 delete_tf=none" ten_of_us.yml
		#
		if [ $spot_recover -eq 1 ] &&[[ ! -f "test_returned" ]]; then
			#
			# Check to see if we used spot, and we are to recover if the system goes away.
			#
			if [[ -f test_started ]]; then
				sp_check=`grep spot_range: ansible_vars_main.yml`
				if [[ $sp_check == *","* ]]; then
					rm -rf tf
					#
					# Next attempt it without spot pricing.
					#
					grep -v "spot_range:" ansible_vars_main.yml > spot_repair
					echo "  spot_start_price: 0" >> spot_repair
					echo "  spot_range: 0" >> spot_repair
					mv spot_repair ansible_vars_main.yml
					grep -v "spot_range:" ansible_vars.yml > spot_repair
					echo "  spot_start_price: 0" >> spot_repair
					echo "  spot_range: 0" >> spot_repair
					mv spot_repair ansible_main.yml
					mkdir tf
					echo ansible-playbook -i ./inventory --extra-vars "working_dir=${curdir} ansible_python_interpreter=/usr/bin/python3" ten_of_us.yml
					ansible-playbook -i ./inventory --extra-vars "working_dir=${curdir} ansible_python_interpreter=/usr/bin/python3 delete_tf=none" ten_of_us.yml
				else
					#
					# Not spot, test started, system died.
					#
					echo Error: test started, system died.
					exit
				fi
			else
				#
				# Rarely will happen.
				#
				echo Error: did not start the test. >>  test_start_failure
				exit
			fi
		fi
		if [[ ! -f "cpu_type_failure" ]]; then
			break;
		fi
		#
		# We need to handle incrementing the resource group.
		# Expected format is the last field is the increment.
		#
		if [[ $system_type == "azure" ]]; then
			cloud_string=`grep "cloud_resource_group:" ansible_vars.yml | cut -d':' -f 2 | cut -d' ' -f 2`
			if [ $attempts -eq 1 ]; then
				text_string=`echo $cloud_string | rev | cut -d'-' -f2- | rev`
			else
				text_string=$cloud_string
			fi
			grep -v cloud_resource_group: ansible_vars.yml > main.temp
			echo "  cloud_resource_group: ${text_string}-${attempts}" >> main.temp
			mv main.temp ansible_vars.yml
		fi
		let "attempts=${attempts}+1"
		rm -rf ansible_install_group ansible_test_group boot_info cloud_timings copy_git_file_status cr_status cpu_type_failure
		rm -rf dev_env_status install_status meta_data.yml tar_status terraform_data.yml test_defs.yml test_info test_times tf_results
		mv tf tf_delete_${attempts}
	done
	$top_dir/bin/remove_wrong_cpus $top_dir/$direct
	init_system=\""no\""
	if [ $remove_dirs -eq 1 ]; then
		rm -rf tf
	fi
done

for i in `ls results*tar`; do
	check_file=`tar tvf $i | grep "_tuned\.status"` 
	echo ============ >> tuned_run_info
	echo $i >> tuned_run_info
	cat $check_file >> tuned_run_info
done
