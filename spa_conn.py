#!/usr/bin/python
import re
import requests
import argparse
import json
import shutil

def parse_args():
    parser = argparse.ArgumentParser(description="execute requests to spa server")
    parser.add_argument("action", choices=["create", "delete", "update", "run", "stop", "status", "set_status", "dump",
                                           "select_project", "file", "kill_all"],
                        help="choose needed action")
    parser.add_argument("--json", "-j", type=str, help="parameters in json format")
    parser.add_argument("--json_file","--json-file", "-f", type=str, help="parameters in json file")
    parser.add_argument("--project", "-p", type=str, help="specify project name")
    parser.add_argument("--workflow","--wf", "-w", type=str, help="specify workflow name")
    parser.add_argument("--task", "-t", type=str, help="specify task name")
    parser.add_argument("--upload", "-u", type=str, help="local file to upload to server (for using with file only)")
    parser.add_argument("--download", "-d", type=str,
                        help="remote file to download to local machine (for using with file only)")
    parser.add_argument("--move", "-m", type=str, nargs=2,
                        help="move remote file into /opt/spa/data/<project>/<wf>/<task> or /opt/spa/bin folder")
    parser.add_argument("--link", "-l", type=str, nargs=2,
                        help="create symlink of remote file into /opt/spa/data/<project>/<wf>/<task> or /opt/spa/bin folder")

    return parser.parse_args()


if __name__ == '__main__':
    args = parse_args()
    server_address = "http://10.23.0.87:5000"
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
            print("You can't specify project, if using json-file")
        if args.json is not None:
            print("You can't specify json, if using json-file")
        if args.workflow is not None:
            print("You can't specify workflow, if using json-file")
        if args.task is not None:
            print("You can't specify task, if using json-file")
        with open(args.json_file, "r") as fp:
            params = json.load(fp)
    else:
        if args.project is not None:
            params["project"] = args.project
        if args.workflow is not None:
            params["workflow"] = args.workflow
        if args.task is not None:
            params["task"] = args.task

    if args.action == "file":
        if args.upload is not None:
            if args.project is None:
                print("specify project")
            if args.workflow is None:
                print("specify workflow")
            if args.task is None:
                print("specify task")
            if args.project is not None and args.workflow is not None and args.task is not None:
                upload_files = {'file': open(args.upload,"rb")}
                file_name = args.download.split('/')[-1]
                r = requests.post(server_address, files=upload_files)
                task_path = "/opt/spa/data" + args.project + "/" + args.workflow + "/" + args.task + "/" + file_name
                data = {"jsonrpc": "2.0", "method": "move_file", "id": 1, "params": [filename, task_path]}
                r = requests.post(server_address, json=data)
                print(r.text + "\nfile uploaded: " + task_path + file_name)
        elif args.download is not None:
            local_filename = args.download.split('/')[-1]
            data = {"jsonrpc": "2.0", "method": "cp_file", "id": 1, "params": [args.download, local_filename]}
            r = requests.post(server_address, json=data)
            with requests.get(server_address + "/" + args.download, stream=True) as r:
                if r.status_code != requests.codes.ok:
                    print("Error " + str(r.status_code))
                else:
                    with open(local_filename, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=1024):
                            f.write(chunk)
                    print("file downloaded: ", local_filename)
            data = {"jsonrpc": "2.0", "method": "rm_file", "id": 1, "params": [local_filename]}
            r = requests.post(server_address, json=data)
        elif args.move is not None:
            data = {"jsonrpc": "2.0", "method": "move_file", "id": 1, "params": [args.move[0],args.move[1]]}
            r = requests.post(server_address, json=data)
            print(json.dumps(r.json(), indent=3))
        elif args.link is not None:
            data = {"jsonrpc": "2.0", "method": "link_file", "id": 1, "params": [args.link[0],args.link[1]]}
            r = requests.post(server_address, json=data)
            print(json.dumps(r.json(), indent=3))
    elif args.action == "kill_all":
        data = {"jsonrpc": "2.0", "method": args.action, "id": 1, "params": []}
        r = requests.post(server_address, json=data)
        print(json.dumps(r.json(), indent=3))
    else:
        data = {"jsonrpc": "2.0", "method": args.action, "id": 1, "params": [params]}
        r = requests.post(server_address, json=data)
        print(json.dumps(r.json(), indent=3))
