#!/usr/bin/python
import argparse
import os
import shutil
import re

def parse_args():
    parser = argparse.ArgumentParser(description="execute requests to spa server")
    parser.add_argument("f1", help="from where to move file: full path, or task, or url, or scp")
    parser.add_argument("f2", help="where to move file: full path, or task, or url, or scp")
    return parser.parse_args()

if __name__ == '__main__':
    args = parse_args()
    f1 = args.f1
    f2 = args.f2
    filename=""

    if re.match(r'^task:.*',f1) : #file in task directory in same workflow
        #format <task>:<path>
        filename = f1.split(":")[1]
        cwd = os.getcwd()
        if not re.match(r'\/opt\/spa\/data\/\w*\/\w*\/\w*', cwd): #we assue, that we are running from task of same workflow - othervise we can't locate needed workflow
            print("not in task dir: " + cwd)
            exit(1)
        f1 = cwd + "/../" + filename
    
    if not os.path.isfile(f1) and not os.path.isdir(f1):
        print("no file " + f1)
        exit(1)
    
    if re.match(r'^task:.*',f2) : #file in task directory in same workflow
        filename = f2.split(":")[1]
        cwd = os.getcwd()
        if not re.match(r'\/opt\/spa\/data\/\w*\/\w*\/\w*',cwd):
            print("not in task dir: " + cwd)
            exit(1)
        f2 = cwd + "/../" + filename

    try:
        print("cp ", f1, " ", f2)
        if os.path.isdir(f1):
            shutil.copytree(f1, f2, dirs_exist_ok=True)
        elif os.path.isfile(f1):
            shutil.copy(f1,f2)
    except OSError as err:
        print("can not copy file: " + str(err))
    
