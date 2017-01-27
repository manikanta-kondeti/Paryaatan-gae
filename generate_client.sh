#!/bin/bash
path_to_endpointscfg=$(which endpointscfg.py)
 if [ -x "$path_to_endpointscfg" ] ; then
    endpointscfg.py get_client_lib java -bs gradle -o . v1.samosa.SamosaApi
    echo " Successfully Generated "

 else
    echo "Missing symlinks! Create from Google Appengine Launcher and try again."
 fi

