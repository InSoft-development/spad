#!/usr/bin/python
import requests
import argparse
import json

def parse_args():
    parser = argparse.ArgumentParser(description="execute requests to spa server")
    parser.add_argument("action", choices=["create", "delete", "update", "run", "stop", "status", "set_status", "dump", "select_project", "file"],
                        help="choose needed action")
    parser.add_argument("--json", "-j", type=str, help="parameters in json format")
    parser.add_argument("--json_file","--json-file", "-f", type=str, help="parameters in json file")
    parser.add_argument("--project", "-p", type=str, help="specify project name")
    parser.add_argument("--workflow","--wf", "-w", type=str, help="specify workflow name")
    parser.add_argument("--task", "-t", type=str, help="specify task name")

    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    server_address = "http://localhost:5000"
    params = dict()
    if args.json is not None:
        if args.project is not None:
            print("You can't specify project, if using json")
        if args.json_file is not None:
            print("You can't specify json-file, if using json")
        if args.workflow is not None:
            print("You can't specify workflow, if using json")
        if args.task is not None:
            print("You can't specify task, if using json")
        params = json.loads(args.json)
    elif args.json_file is not None:
        if args.project is not None:
            print("You can't specify project, if using json")
        if args.json_file is not None:
            print("You can't specify json-file, if using json")
        if args.workflow is not None:
            print("You can't specify workflow, if using json")
        if args.task is not None:
            print("You can't specify task, if using json")
        params = json.load(args.json_file)
    else:
        if args.project is not None:
            params["project"] = args.project
        if args.workflow is not None:
            params["workflow"] = args.workflow
        if args.task is not None:
            params["task"] = args.task
    print(params)
    data = {"jsonrpc": "2.0", "method": args.action, "id": 1, "params": [params]}
    print(data)
    r = requests.post(server_address, json=data)
    print(r.text)
