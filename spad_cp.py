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
    if re.match(r'^task:.*',f1) : #local file in nearby task directory
        task = f1.split(":/",3)[1]
        filename = f1.split(":/", 3)[2]
        cwd = os.getcwd()
        if not re.match(r'\/opt\/spa\/data\/\w*\/\w*\/\w*'):
            print("not in task dir: " + cwd)
            exit(1)
        f1 = cwd + "/../"+task + "/" + filename
        if not os.path.isfile(f1):
            print("no file " + f1)
            exit(1)
    else:
        if not os.path.isfile(f1):
            print("no file " + f1)
            exit(1)

    if re.match(r'^task:.*',f2) : #local file in nearby task directory
        task = f2.split(":/", 3)[1]
        if len(f2.split(":/", 3)) < 3:
            filename = "."
        else:
            filename = f2.split(":/", 3)[2]
        cwd = os.getcwd()
        if not re.match(r'\/opt\/spa\/data\/\w*\/\w*\/\w*'):
            print("not in task dir: " + cwd)
            exit(1)
        f2 = cwd + "/../" + task + "/" + filename
        try:
            shutil.copyfile(f1, f2)
            print("cp ", f1, " ", f2)
        except OSError as err:
            print("can not move file: " + str(err))
    else:
        try:
            shutil.copyfile(f1, f2)
            print("cp ", f1, " ", f2)
        except OSError as err:
            print("can not move file: " + str(err))