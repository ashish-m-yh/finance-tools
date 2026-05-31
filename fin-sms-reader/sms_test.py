import os

os.environ['SMS_APP_MODE'] = 'demo'

import rule_engine
import sys
import re

rules_path ="./rules/rules.meta"

filename = sys.argv[1]

fh = open(filename, "r")
lines = fh.readlines()
fh.close()

engine = rule_engine.RuleEngine(rules_path, bank_file=None, acct_types_file="./rules/acct_types.json", override_file='./rules/override.json')

for line in lines:
    info = engine.run(line)

    print ( line ),
    print ( info )
    print
