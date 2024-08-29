#!/bin/bash
#                         License
#
# Copyright (C) 2024  Keith Valin kvalin@redhat.com
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
#

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
