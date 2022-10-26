#!/bin/bash
curdev=$1
add_on=""

#
# another way.
#
#read -a ARRAY <<< $(echo $curdev)
read -a ARRAY <<< $(echo $curdev | sed 's/./& /g')

array_lgth="${#ARRAY[@]}"
let "array_lgth=$array_lgth - 1"

for index in  `seq -s' ' $array_lgth -1 0`
do
	new_val="$(echo ${ARRAY[$index]} | tr '[a-y]z' '[b-z]a')"
	if [ "$new_val" == "a" ]; then
	# We wrapped it.
	# If we are at the head, then need to add another letter
	#
		ARRAY[$index]=$new_val
		if [ $index == 0 ]; then
			add_on="a"
			break;
		fi
	else
		ARRAY[$index]=$new_val
		break
	fi
done
val=`echo ${ARRAY[@]} | sed "s/ //g"`
echo ${val}${add_on}
