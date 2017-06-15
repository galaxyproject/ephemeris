#!/bin/bash
#set -eu -o pipefail

if [ -z $VIRTUAL_ENV ]
  then
    echo "Sphinx for ephemeris must be installed in a virtual environment"
  else
    echo "Installing ephemeris's required sphinx packages in virtual environment: $VIRTUAL_ENV"
    pip install -r requirements.txt
    pip install -r ../requirements.txt
    sed -i 's/from CommonMark import DocParser, HTMLRenderer/from CommonMark import Parser, HtmlRenderer/' $VIRTUAL_ENV/local/lib/python2.7/site-packages/recommonmark/parser.py
fi
