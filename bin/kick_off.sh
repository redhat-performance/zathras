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

top_dir=`pwd`

#
# Set up the headrs for the log files
#
add_log_header()
{
	log_info=$1/$2
	if [[ ! -f $log_info ]]; then
		printf "%10s %50s %10s %24s %6s %12s %6s %8s\n" "User" "Run label" "Instance" "Date" "Price" "Test" "Time" "Cost" > $log_info
	fi
}

#
# Lock the file and then record the info
#
update_log_file()
{
	flock -x $1 -c "printf \"%10s %50s %10s %24s %6s %12s %6s %8s\n\" $2 $3 $4 $5 $6 $7 $8 $9" >> $1
}

#
# Generate the report information  for the test executed on.
# 
report_usage()
{
	#
	# Obtain information common to all runs.
	#
	instance_type=`grep system_type:  ansible_vars_main.yml | awk '{print $2}'`
	run_label=`grep run_label:  ansible_vars_main.yml | awk '{print $2}'`
	instance=`grep host_or_cloud_inst  ansible_vars_main.yml | awk '{print $2}'`
	user=`id -un`
	#
	# Add log header for the various usage files.
	# Note, that zathras_log_file either exist or doesn't, we do not create it here.
	#
	add_log_header `pwd` test_system_usage
	if [[ $top_dir != "none" ]]; then
		add_log_header $top_dir test_system_usage
	fi
	#
	# Get the instance price.
	#
	inst_price=`cat instance_cost`
	if [[ $inst_price == "0" ]]; then
		inst_price=`grep cur_spot_price ansible_spot_price.yml | awk '{print $2}'`
	fi
	while IFS= read -r line
	do
		test=`echo "${line}" | cut -d' ' -f2`
		time=`echo "${line}" | cut -d' ' -f5`
		cost=`echo "scale=4;($time*$inst_price)/3600" | bc`
		#
		# Only one test at a time at the lowest level.
		#
		update_log_file test_system_usage $user $run_label $instance $run_date $inst_price $test $time $cost
		if [[ $top_dir != "none" ]]; then
			update_log_file $top_dir/test_system_usage $user $run_label $instance $run_date $inst_price $test $time $cost
		fi
		if [[ -f /home/zathras_log/zathras_log_file ]]; then
			update_log_file /home/zathras_log/zathras_log_file $user $run_label $instance $run_date $inst_price $test $time $cost
		fi
	done < "test_times"
}

spot_recover=1
create_attempts=5
remove_dirs=0
ssh_key_file=""
while getopts "a:c:d:f:s:r:S:t:" o; do
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
		t)
			top_dir=${OPTARG}
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
	run_date=`date "+%Y.%m.%d-%H.%M.%S"`
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
					echo Need to update the test list, do not execute the tests we already executed.
					tests_list=`grep ^test: test_times | awk '{ print $2 }'`
					test_rm=""
					seper=""
					for i in $tests_list; do
						test_rm=$test_rm${seper}$i
						seper=","
					done
					test_rm=${test_rm}${seper}
					cp ansible_vars_main.yml ansible_vars_main.yml_back
					sed "s/${test_rm}//g" < ansible_vars_main.yml > update
					mv update ansible_vars_main.yml
					cp ansible_vars.yml ansible_vars.yml_back
					sed "s/${test_rm}//g" < ansible_vars.yml > update
					mv update ansible_vars.yml
					if [[ -f test_times ]]; then
        					report_usage
					fi
					mv test_times test_times_spot
					mv if_spot_fail instance_cost
					rm -rf tf
					rm tf.rtc
					#
					# Next attempt it without spot pricing.
					#
					mv ansible_run_vars.yml ansible_run_vars.yml_spot_died
					grep -v "spot_range:" ansible_vars_main.yml | grep -v spot_start_price > spot_repair
					echo "  spot_start_price: 0" >> spot_repair
					echo "  spot_range: 0" >> spot_repair
					mv  spot_repair ansible_vars_main.yml
					grep -v "spot_range:" ansible_vars.yml  | grep -v  spot_start_price > spot_repair
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

#
# Only if the test actually ran.
#
if [[ -f test_times ]]; then
        report_usage
fi

for i in `ls results*tar`; do
	check_file=`tar tvf $i | grep "_tuned\.status"` 
	echo ============ >> tuned_run_info
	echo $i >> tuned_run_info
	cat $check_file >> tuned_run_info
done
