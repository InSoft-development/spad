#!/usr/bin/python
import datetime
import re
import requests
import argparse
import json
import shutil

def parse_args():
    parser = argparse.ArgumentParser(description="execute requests to spa server")
    parser.add_argument("action", choices=["create", "recreate", "delete", "update", "run", "start", "log", "stop", "status", "set_status", "dump",
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
    with open("srv.conf","r") as conf:
        server_address = conf.read()
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

    if args.action == "log":
        if args.task is not None:
            if args.project is None:
                print("specify project")
                exit()
            if args.workflow is None:
                print("specify workflow")
                exit()
            log = "/opt/spa/data/"+args.project+"/"+args.workflow+"/"+args.task+"/log"
        elif args.workflow is not None:
            if args.project is None:
                print("specify project")
                exit()
            log = "/opt/spa/data/" + args.project + "/" + args.workflow + "/log"
        elif args.project is not None:
            print("no logs for project, specify workflow")
            exit()
        else:
            log = "/opt/spa/log/srv.log"
        print(log, " would be downloaded")
        data = {"jsonrpc": "2.0", "method": "cp_file", "id": 1, "params": [log, "file_buf/log"]}
        r = requests.post(server_address, json=data)
        print(r.text + "\nlog cp to server temp folder")
        with requests.get(server_address + "/file_buf/log", stream=True) as r:
            if r.status_code != requests.codes.ok:
                print("Error " + str(r.status_code))
            else:
                with open("log_"+datetime.datetime.now().isoformat(), 'wb') as f:
                    for chunk in r.iter_content(chunk_size=1024):
                        f.write(chunk)
                print("file downloaded: ", "log_"+datetime.datetime.now().isoformat())
        data = {"jsonrpc": "2.0", "method": "rm_file", "id": 1, "params": ["file_buf/log"]}
        r = requests.post(server_address, json=data)
        print(r.text + "\nlog rm from server temp folder")

    elif args.action == "file":
        if args.upload is not None:
            if args.project is None:
                print("specify project")
            if args.workflow is None:
                print("specify workflow")
            if args.task is None:
                print("specify task")
            if args.project is not None and args.workflow is not None and args.task is not None:
                upload_files = {'file': open(args.upload,"rb")}
                local_filename = str(re.search("[^/]*$",args.upload).group())
                r = requests.post(server_address, files=upload_files)
                print(r.text + "\nfile uploaded: " + local_filename)
                task_path = "/opt/spa/data/" + args.project + "/" + args.workflow + "/" + args.task\
                            + "/" + local_filename
                data = {"jsonrpc": "2.0", "method": "move_file", "id": 1, "params": [local_filename, task_path]}
                r = requests.post(server_address, json=data)
                print(r.text + "\nfile moved: " + task_path)
        elif args.download is not None:
            local_filename = str(re.search("[^/]*$",args.download).group())
            data = {"jsonrpc": "2.0", "method": "cp_file", "id": 1, "params": [args.download,
                                                                               "file_buf/"+local_filename]}
            r = requests.post(server_address, json=data)
            print(r.text + "\nfile cp to server folder: " + args.download)
            with requests.get(server_address + "/file_buf/" + local_filename, stream=True) as r:
                if r.status_code != requests.codes.ok:
                    print("Error " + str(r.status_code))
                else:
                    with open(local_filename, 'wb') as f:
                        for chunk in r.iter_content(chunk_size=1024):
                            f.write(chunk)
                    print("file downloaded: ", local_filename)
            data = {"jsonrpc": "2.0", "method": "rm_file", "id": 1, "params": ["file_buf/"+local_filename]}
            r = requests.post(server_address, json=data)
            print(r.text + "\nfile rm from server folder: " + local_filename)
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
