#!/bin/bash
set -eu -o pipefail

pip install -r requirements.txt
pip install -r ../requirements.txt
sed -i 's/from CommonMark import DocParser, HTMLRenderer/from CommonMark import Parser, HtmlRenderer/' $VIRTUAL_ENV/local/lib/python2.7/site-packages/recommonmark/parser.py
