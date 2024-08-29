#!/bin/bash

# m6a.16xlarge:Disks;type=gp3;throughput=1000;disk_iops=1600;size=3000;number=4&XYZ

parse_optline() {
    indents=""
    key_name=$(echo "$1" | grep -Eo "(^|;)[A-Za-z]+;" | sed -e 's/;//g')
    if [ -n "$key_name" ]; then
        echo "${key_name}:"
        indents="  "
    fi

    for i in $(echo "$1" | tr ";" "\n"); do
        case $i in
            *=*)
                key=$(echo $i | cut -d= -f1)
                val=$(echo $i | cut -d= -f2)

                echo -e "$indents$key: $val"
            ;;
        esac
    done
}


opts=$(echo "$1" | tr "&" "\n")

for opt in $opts; do
    parse_optline "$opt" 0
done
