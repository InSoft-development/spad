#!/usr/bin/python
import atexit
import cgi
import datetime
import io
import json
import os
import re
import shutil
import signal
import subprocess
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
import logging

import oslash
from jsonrpcserver import method, Result, Success, dispatch, Error

workflow_processes = {}
logs={}
errs={}
project_name = ""

class ExecutionQueue(object):
    """очередь исполнения workflow"""

    def __init__(self, pr_name, wf_name):
        self.tasks = []
        self.wf_name = wf_name  # одна очередь - один воркфлоу

    def load(self):
        path = "/opt/spa/data/" + project_name + "/" + self.wf_name
        with open(path + "/workflow.json", "r") as fp:
            self.tasks = json.load(fp)
        return self.tasks

    # Добавление
    def add_task(self, new_task: dict):
        if self.wf_name in workflow_processes.keys():
            logging.info(datetime.datetime.now().isoformat()+ "ERROR: This workflow is currently executed, can't add task")
            return
        new_task["status"] = "new"
        if len(self.tasks) == 0:
            self.tasks = [new_task]
        else:
            places = [t["place"] for t in self.tasks]
            places.append(new_task["place"])
            # uniq places
            if len(places) == len(set(places)):
                self.tasks = sorted([new_task] + self.tasks, key=lambda d: d["place"])

            else:
                new_task_place = new_task["place"]
                i = [t["place"] for t in self.tasks].index(new_task_place)
                for correction_task in self.tasks[i:]:
                    correction_task["place"] += 1
                self.tasks = self.tasks[:i] + [new_task] + self.tasks[i:]
        self.save_wf_file()

        path = "/opt/spa/data/" + project_name + "/" + self.wf_name + "/" + new_task["name"]

        os.makedirs(path)

        if "description" not in new_task:
            new_task["description"] = ""

        task_json = {
            "info":
                {
                    "id": new_task["id"],
                    "name": new_task["name"],
                    "description": new_task["description"],
                    "create_time": datetime.datetime.now().isoformat(),
                    "last_update": datetime.datetime.now().isoformat(),
                    "path": path,  # Нужно ли?
                    # "place": new_task["place"], #хранится в workflow
                    "type": "task",
                    "status": "created"
                },
            "task":
                {
                    "exec": new_task["exec"],
                    "function": new_task["function"],
                    "params": new_task["params"]
                }
        }
        with open(path + "/task.json", "w") as task_json_file:
            json.dump(task_json, task_json_file, indent=3)
        # return self.tasks

    # Добавление
    def delete_task(self, rm_task: dict):
        if self.wf_name in workflow_processes.keys():
            logging.info(datetime.datetime.now().isoformat()+ "ERROR: This workflow is currently executed, can't delete task")
            return 1
        if "pid" in os.listdir("/opt/spa/data/" + project_name + "/" + self.wf_name + "/" + str(rm_task)):
            logging.info(datetime.datetime.now().isoformat()+ "ERROR: PID file exists, can't delete task, inconsistent state may occur")
            return 1
        i = 0
        for i in range(len(self.tasks)):
            if self.tasks[i]["name"] == rm_task:
                break
        if i == len(self.tasks):
            return 1
        #task = next(t for t in self.tasks if t["name"] == rm_task)
        logging.info(datetime.datetime.now().isoformat()+ "del:"+ str(i))
        del self.tasks[i]
        i = 0
        for task in self.tasks:
            task["place"] = i
            i += 1
        logging.info(datetime.datetime.now().isoformat()+ "remained"+ str(self.tasks))
        path = "/opt/spa/data/" + project_name + "/" + self.wf_name + "/" + rm_task
        logging.info(datetime.datetime.now().isoformat()+ "delete dir")
        try:
            shutil.rmtree(path)
        except Exception:
            return 1
        self.save_wf_file()
        return 0


    # def change_status(self, task_name, status):
    #     for task in self.tasks:
    #         if task["name"] == task_name:
    #             task["status"] = status

    def save_wf_file(self):
        logging.info(datetime.datetime.now().isoformat()+ "save wf")
        with open("/opt/spa/data/" + project_name + "/" + self.wf_name + "/workflow.json", "w") as wf_json_file:
            json.dump(self.tasks, wf_json_file, indent=3)
        logging.info(datetime.datetime.now().isoformat()+ "wf saved")

@method
def select_project(project) -> Result:
    global project_name
    if len(workflow_processes) > 0 and project_name != "":
        return Error(1, {"message": "project " + project_name + " is executing now"})
    if type(project) is dict:
        if "project" in project:
            project = project["project"]
            if type(project) is dict:
                if "name" in project:
                    project = project["name"]

    path = "/opt/spa/data/" + project
    if not os.path.exists(path):
        return Error(1, {"message": "project doesn't exist"})

    project_name = project
    return Success({"answer": "project " + project_name + " selected"})

@method
def create(data) -> Result:
    logging.info(datetime.datetime.now().isoformat()+ "CREATE DATA:"+ str(data))
    # data = data[0]
    global project_name
    project_name = data["project"]["name"]
    project = data["project"]
    # for now only one project exists
    # with data["context"]["projects"][0] as project:
    path = "/opt/spa/data/" + project_name

    if not os.path.exists(path):
        try:
            os.makedirs(path)
        except OSError:
            return Error(1, {"message": "project tree not created"})
    workflows_q = {}
    for workflow_json in project["workflows"]:
        if workflow_json["name"] in workflow_processes.keys() is None:
            return Error(1, {"message": "this workflow is executing now"})
    for workflow_json in project["workflows"]:
        path = "/opt/spa/data/" + project_name + "/" + workflow_json["name"]
        old_tasks = []
        if not os.path.exists(path):
            try:
                os.makedirs(path)
                workflows_q[workflow_json["name"]] = ExecutionQueue(project_name, workflow_json["name"])
            except OSError:
                return Error(1, {"message": "wf tree not created"})
            # queue file construction
        else:
            with open(path + "/workflow.json", "r") as fp:
                old_tasks = json.load(fp)
            workflows_q[workflow_json["name"]] = ExecutionQueue(project_name, workflow_json["name"])
            workflows_q[workflow_json["name"]].load()
        if "tasks" in workflow_json:
            new_tasks = workflow_json["tasks"]
            names = [t["name"] for t in new_tasks + old_tasks]
            if len(names) > len(set(names)):
                return Error(1, {"message": "not uniq task names"})
            # На данный момент функционал id выполняют name - id долженб быть инкрементальным у нас внутри системы, не задаваться в json
            # ids = [t["id"] for t in new_tasks+old_tasks]
            # if len(ids) > len(set(ids)):
            #    return Error(1,{"message": "not uniq task ids"})
            places = [t["place"] for t in new_tasks]
            if len(places) > len(set(places)):
                return Error(1, {"message": "not uniq places in new tasks"})

    # если успешно прошли все проверки - физически создаем таски на диске
    for workflow_json in project["workflows"]:
        if "tasks" in workflow_json:
            new_tasks = workflow_json["tasks"]
            try:
                for task in new_tasks:
                    workflows_q[workflow_json["name"]].add_task(task)
            except OSError:
                return Error(1, {"message": "task can not be created"})

    return Success({"answer": "file tree created"})


@method
def delete(data) -> Result:
    logging.info(datetime.datetime.now().isoformat()+ "DELETE DATA:"+ str(data))
    data_new = data
    if "project" in data:
        if type(data["project"]) is str: #short form of call
            if "workflow" in data and type(data["workflow"]) is str:
                if "task" in data and type(data["task"]) is str:
                    data_new = \
                        {
                            "project": {
                                "name": data["project"],
                                "workflows": [
                                    {
                                        "name": data["workflow"],
                                        "tasks": [
                                            {
                                                "name": data["task"],
                                            }
                                        ]
                                    }
                                ]
                            }
                        }
                else:
                    data_new = \
                        {
                            "project": {
                                "name": data["project"],
                                "workflows": [
                                    {
                                        "name": data["workflow"]
                                    }
                                ]
                            }
                        }

            else:
                return Error(1, {"answer": "Specify workflow. It is not supported, to delete project"})
        #elif type(data["project"]) is dict: continue
    else:
        return Error(1, {"answer": "Specify project and workflow"})
    data = data_new

    workflows_to_delete = []
    tasks_to_delete = {}
    workflows_q = {}
    global project_name
    project_name = data["project"]["name"]
    project = data["project"]
    # for now only one project exists
    # with data["context"]["projects"][0] as project:
    path = "/opt/spa/data/" + project_name

    if not os.path.exists(path):
        return Error(1, {"message": "project " + project_name + " not exists"})
    #Whole project delete
    if "workflow" not in project and "workflows" not in project:  # synonymous
        if len(workflow_processes) > 0:
            return Error(1, {"message": "project " + project_name + "has executing workflows, can not be deleted"})
        try:
            #os.rmdir(path)
            return Success({"answer": "project " + project_name +
                                      " can be successfully deleted, but for now it is not supported, to delete project from disk permanently..."})
        except OSError:
            return Error(1, {"message": "project " + project_name + " can not be deleted"})

    #  workflows and tasks delete
    else:
        # logging.info(datetime.datetime.now().isoformat()+ "wf del")
        if "workflows" not in project:  # synonymous
            project["workflows"] = project["workflow"]

        for workflow_json in project["workflows"]:
            workflow_name = workflow_json["name"]
            logging.info(datetime.datetime.now().isoformat()+ workflow_name+ "delete")
            path = "/opt/spa/data/" + project_name + "/" + workflow_name
            if not os.path.exists(path):
                logging.info(datetime.datetime.now().isoformat()+ "workflow " + workflow_name + " not exists")
                continue

            #whole workflow for delete
            if "tasks" not in workflow_json and "task" not in workflow_json:
                logging.info(datetime.datetime.now().isoformat()+ "delete whole wf")
                workflows_to_delete.append(workflow_name)
                # try:
                #     return Success({"answer": "workflow " + workflow_json["name"] + " successfully deleted"})
                # except OSError:
                #     return Error(1, {"message": "workflow " + workflow_json["name"] + " can not be deleted"})
            else:
                logging.info(datetime.datetime.now().isoformat()+ "delete some tasks")
                workflows_q[workflow_name] = ExecutionQueue(project_name, workflow_json["name"])
                workflows_q[workflow_name].load()

                if "tasks" not in workflow_json:  # synonymous
                    workflow_json["tasks"] = workflow_json["task"]
                tasks_to_delete[workflow_name] = []
                for task in workflow_json["tasks"]:
                    task_name = task["name"]
                    logging.info(datetime.datetime.now().isoformat()+ "delete qu add task"+task_name)

                    path = "/opt/spa/data/" + project_name + "/" + workflow_json["name"] + "/" + task_name
                    if not os.path.exists(path):
                        logging.info(datetime.datetime.now().isoformat()+ "task " + task_name + " not exists")
                    else:
                        tasks_to_delete[workflow_name].append(task_name)
    # если успешно прошли все проверки - удаляем таск на диске
    for workflow_json in project["workflows"]:
        if workflow_json["name"] not in workflows_to_delete:
            for task_name in tasks_to_delete[workflow_json["name"]]:
                logging.info(datetime.datetime.now().isoformat()+ "remove task"+ task_name+str(workflow_json["name"]))
                if workflows_q[workflow_json["name"]].delete_task(task_name) == 1:
                    return Error(1, {"message": "task " + task_name + "can not be deleted"})
                # else:
                #     return Success({"answer": "task " + task_name + " successfully deleted"})

    # если успешно прошли все проверки - удаляем помеченные к удалению целиком воркфлоу на диске
    for workflow_name in workflows_to_delete:
        logging.info(datetime.datetime.now().isoformat()+ "delete wf"+ workflow_name)
        if workflow_name in workflow_processes:
            if workflow_processes[data["workflow"]].poll() is None:
                return Error(1, {"message": "this workflow is executing now"})
            else:
                if "pid" in os.listdir(path):
                    os.remove(path + "/pid")
                workflow_processes.pop(wf)
                #logs[wf].close()
                #errs[wf].close()
                #logs.pop(wf)
                #errs.pop(wf)

        path = "/opt/spa/data/" + project_name + "/" + workflow_name
        try:
            shutil.rmtree(path)
        except Exception as err:
            return Error(1, {"message": "workflow " + workflow_name + " can not be deleted " + str(err)})
        #return Success({"answer": "workflow " + workflow_name + " successfully deleted"})
    return Success({"answer": "Successfully deleted " + str(workflows_to_delete) + str(tasks_to_delete)})


@method()
def update(data) -> Result:
    ret = delete(data)
    if isinstance(ret, oslash.either.Right):
        ret = create(data)
        if isinstance(ret, oslash.either.Right):
            return Success({"answer": "file tree updated"})
    return ret

@method()
def recreate(data) -> Result:
    if "project" in data and type(data["project"]) is dict:  # json tree as input
        if len(data["project"]["workflows"]) > 0:
            for wf in data["project"]["workflows"]:
                ret = delete({"project": data["project"]["name"], "workflow": wf["name"]})
                if not isinstance(ret, oslash.either.Right):
                    return Error(1, ret)
        else:
            return Error(1, "Specify workflow")
    ret = create(data)
    if isinstance(ret, oslash.either.Right):
        return Success({"answer": "file tree updated"})
    return ret

@method
def run(data) -> Result:
    if "project" in data and type(data["project"]) is dict: #json tree as input
        if len(data["project"]["workflows"]) != 1:
            return Error(1, {"message": "run not single one workflow"})
        data = { "project" : data["project"]["name"],
                 "workflow":data["project"]["workflows"][0]["name"]}

    global project_name
    if project_name == "":
        if "project" in data:
            project_name = data["project"]
        else:
            return Error(1, {"message": "project not specified"})
    elif project_name != data["project"]:
        Error(1, {"message": "Only "+project_name + " project"})

    path = "/opt/spa/data/" + data["project"] + "/" + data["workflow"]
    if data["workflow"] in workflow_processes:
        if workflow_processes[data["workflow"]].poll() is None:
            return Error(1, {"message": "this workflow is executing now"})
        else:
            if "pid" in os.listdir(path):
                os.remove(path + "/pid")
            # logs[data["workflow"]].close()
            # errs[data["workflow"]].close()
            # logs.pop(data["workflow"])
            # errs.pop(data["workflow"])
            workflow_processes.pop(data["workflow"])
    #else:
    # Запоминаем субпроцес
    json_string = json.dumps(data)
    # logs[data["workflow"]]= open(path + "/out", "w")
    # errs[data["workflow"]]= open(path + "/err", "w")
    p = subprocess.Popen(["/opt/spa/bin/run.py", json_string], encoding='utf-8') #stdout=logs[data["workflow"]], stderr=errs[data["workflow"]],
    open(path + "/pid", "w").write(str(p.pid))
    workflow_processes[data["workflow"]] = p
    return Success({"answer": "running in subprocess"})

@method
def start(data) -> Result:
    return(run(data))

def kill_wf(wf,keep_pid=False):
    logging.info(datetime.datetime.now().isoformat()+ "Stopping:"+ str(wf))
    logging.info(datetime.datetime.now().isoformat()+ str(workflow_processes))
    if wf not in workflow_processes:
        return Success({"answer": "workflow is not running"})

    p = workflow_processes[wf]

    path = "/opt/spa/data/" + project_name + "/" + wf
    number_of_tasks = len(os.listdir(path))
    ret_code = p.poll()
    if ret_code is None:
        logging.info(datetime.datetime.now().isoformat()+ "INFO: terminating "+ str(wf))
        p.send_signal(signal.SIGUSR1)
        # p.terminate()
        time.sleep(number_of_tasks)
        ret_code = p.poll()
        if ret_code is None:
            logging.info(datetime.datetime.now().isoformat()+ "ERROR: can't stop workflow within "+ str(number_of_tasks)
                         + " sec"+ str(wf))
            time.sleep(number_of_tasks * 5)
            ret_code = p.poll()
            if ret_code is None:
                logging.info(datetime.datetime.now().isoformat()+ "ERROR: can't stop workflow within "+
                             str(number_of_tasks * 6)+ " sec"+ str(wf))
                time.sleep(number_of_tasks * 5)
                ret_code = p.poll()
                if ret_code is None:
                    logging.info(datetime.datetime.now().isoformat()+ "ERROR: can't stop workflow within "+
                                 str(number_of_tasks * 11)+ " sec, trying to kill"+ str(wf))
                    # !FIXME может не надо килять прям?
                    p.terminate()
                    time.sleep(number_of_tasks * 10)
                    ret_code = p.poll()
                    if ret_code is None:
                        logging.info(datetime.datetime.now().isoformat()+ "ERROR: can't terminate workflow!"+ str(wf))
                        p.kill()
                        # logs[wf].close()
                        # errs[wf].close()
                        # logs.pop(wf)
                        # errs.pop(wf)
                        return Error(1, {"message": "ERROR: can't stop workflow, killing it"})
    if not keep_pid:
        if ret_code is not None:
            if "pid" in os.listdir(path):
                os.remove(path + "/pid")
    # logs[wf].close()
    # errs[wf].close()
    # logs.pop(wf)
    # errs.pop(wf)
    return Success({"answer": "workflow stopped"})


@method
def stop(data) -> Result:
    if "project" in data and type(data["project"]) is dict:  # json tree as input
        if len(data["project"]["workflows"]) != 1:
            return Error(1, {"message": "stop not single one workflow"})
        data = {"project": data["project"]["name"],
                "workflow": data["project"]["workflows"][0]["name"]}

    logging.info(datetime.datetime.now().isoformat()+ "current wfs:"+ str(workflow_processes.keys()))

    global project_name
    if "workflow" not in data and "project" in data:
        if project_name == "" or project_name == data["project"]:
            kill_all()
            return Success({"answer": "everything is stopped"})

    if data["workflow"] not in workflow_processes:
        return Error(1, {"message": "this workflow is not executing now"})
    else:
        ret = kill_wf(data["workflow"])
        if data["workflow"] in workflow_processes: #it can still be there
            workflow_processes.pop(data["workflow"])
        return ret

@method
def status(data) -> Result:
    if "project" in data and type(data["project"]) is dict: #json tree as input
        if len(data["project"]["workflows"]) > 1:
            return Error(1, {"message": "status not of single workflow"})
        data_new = {"project": data["project"]["name"],
                "workflow": data["project"]["workflows"][0]["name"]}
        if "tasks" in data["project"]["workflows"][0] and len(data["project"]["workflows"][0]["tasks"]) != 1:
            return Error(1, {"message": "status not of single task"})
        else:
            data_new["task"] = data["project"]["workflows"][0]["tasks"][0]["name"]
        data = data_new

    global project_name
    if "project" not in data:
        if project_name != "":
            data["project"] = project_name
        else:
            return Error(1, {"message": "project not specified"})

    path = "/opt/spa/data/" + data["project"]
    if "task" in data:
        if type(data["task"]) is not list:
            data["task"] = [data["task"]]
        st = []
        for task in data["task"]:
            p = path + "/" + data["workflow"] + "/" + task
            with open(p + "/task.json", "r") as fp:
                st.append(json.load(fp)["info"]["status"])
        return Success({"answer": st})
    elif "workflow" in data:
        path += "/" + data["workflow"]
        with open(path + "/workflow.json", "r") as fp:
            wf_tasks = json.load(fp)
        st = {}
        for t in wf_tasks:
            st[t["name"]] = t["status"]
        return Success({"answer": st})
    else:
        path = "/opt/spa/data/" + data["project"]
        wfs = os.listdir(path)
        wf_status = []
        for wf in wfs:
            files = os.listdir(path + "/" + wf)
            if "pid" in files:
                wf_status.append({wf: "running"})
            else:
                wf_status.append({wf: "not run"})
        return Success({"answer": wf_status})

@method
def set_status(data) -> Result:
    if "project" in data and type(data["project"]) is dict: #json tree as input
        if len(data["project"]["workflows"]) != 1:
            return Error(1, {"message": "set_status not in single workflow"})
        if "tasks" in data["project"]["workflows"][0]:
            if len(data["project"]["workflows"][0]["tasks"]) != 1:
                return Error(1, {"message": "set_status not in single task"})
            data = {"project": data["project"]["name"],
                "workflow": data["project"]["workflows"][0]["name"],
                "task": data["project"]["workflows"][0]["tasks"][0]["name"],
                "status":data["project"]["workflows"][0]["tasks"][0]["status"]}
        else:
            return Error(1, {"message": "define task for status set"})

    global project_name
    if "project" not in data:
        if project_name != "":
            data["project"] = project_name
        else:
            return Error(1, {"message": "project not specified"})

    path = "/opt/spa/data/" + data["project"]
    if "task" in data:
        path += "/" + data["workflow"] + "/" + data["task"]
        with open(path + "/task.json", "r") as task_json_file:
            task_json = json.load(task_json_file)
            task_json["info"]["status"] = data["status"]
        with open(path + "/task.json", "w") as task_json_file:
            json.dump(task_json, task_json_file, indent=3)
        path = "/opt/spa/data/" + data["project"]
        path += "/" + data["workflow"]
        with open(path + "/workflow.json", "r") as wf_json_file:
            wf_json = json.load(wf_json_file)
            i = [i for i in range(len(wf_json)) if wf_json[i]["name"] == data["task"]][0]
            wf_json[i]["status"] = data["status"]
        with open(path + "/workflow.json", "w") as wf_json_file:
            json.dump(wf_json, wf_json_file, indent=3)
        return Success({"answer": task_json})
    else:
        return Error(1, {"message": "define task for status set"})

@method
def dump(data) -> Result:
    if "project" in data and type(data["project"]) is dict: #json tree as input
        if len(data["project"]["workflows"]) != 1:
            return Error(1, {"message": "dump not single workflow"})
        data_new = {"project": data["project"]["name"],
                "workflow": data["project"]["workflows"][0]["name"]}
        if "tasks" in data["project"]["workflows"][0] and len(data["project"]["workflows"][0]["tasks"]) != 1:
            return Error(1, {"message": "dump not single task"})
        else:
            data_new["task"] = data["project"]["workflows"][0]["tasks"][0]["name"]
        data = data_new

    global project_name
    if "project" not in data:
        if project_name != "":
            data["project"] = project_name
        else:
            return Error(1, {"message": "project not specified"})

    path = "/opt/spa/data/" + data["project"]
    if "workflow" in data:
        if "task" in data:
            path += "/" + data["workflow"] + "/" + data["task"] + "/"
            with open(path + "task.json", "r") as fp:
                st = json.load(fp)
            return Success({"answer": st})
        else:
            path += "/" + data["workflow"]
            with open(path + "/workflow.json", "r") as fp:
                wf_tasks = json.load(fp)
            return Success({"answer": wf_tasks})
    else:
        pr_j = {}
        wfs = os.listdir(path)
        for wf in wfs:
            path_w = path + "/" + wf
            with open(path_w + "/workflow.json", "r") as fp:
                pr_j[wf] = json.load(fp)
        return Success({"answer": pr_j})

@method
def move_file(f1,f2) -> Result:
    m1 = re.match(r'/opt/spa/data/[^/]+/[^/]+/[^/]+/',f2)
    m2 = re.match(r'/opt/spa/bin/',f2)
    m3 = re.match(r'/home/', f2)
    m4 = re.match(r'file_buf',f2)
    if not m1 and not m2 and not m3 and not m4:
        return Error(1, {"message": "move only into existing task dirs: /opt/spa/data/<project>/<wf>/<task>/"
                                    " or into /opt/spa/bin or home"})
    try:
        if not os.path.isfile(f1):
            return Error(1, {"message": "no file " + f1})
        m1 = re.match(r'/opt/spa/data/[^/]+/[^/]+/[^/]+/.+', f2)
        m2 = re.match(r'/opt/spa/bin/.+',f2)
        m3 = re.match(r'/home/.+', f2)
        m4 = re.match(r'file_buf/.+',f2)
        if not m1 and not m2 and not m3 and not m4:
            f2 += f1 #mv to folder
        logging.info(datetime.datetime.now().isoformat()+ "move "+ f1+" "+f2)
        os.rename(f1, f2)
        return Success({"answer": f1 + " moved to " + f2})
    except OSError as err:
        return Error(1, {"message": "can not move file: " + str(err)})

@method
def cp_file(f1,f2) -> Result:
    try:
        if not os.path.isfile(f1):
            return Error(1, {"message": "no file " + f1})
        logging.info(datetime.datetime.now().isoformat()+ "cp "+ f1+" "+f2)
        shutil.copyfile(f1, f2)
        return Success({"answer": f1 + " moved to " + f2})
    except OSError as err:
        return Error(1, {"message": "can not move file: " + str(err)})

@method
def rm_file(f2) -> Result:
    m1 = re.match(r'/opt/spa/data/[^/]+/[^/]+/[^/]+/',f2)
    m2 = re.match(r'/opt/spa/bin/',f2)
    m3 = re.match(r'/home', f2)
    m4 = re.match(r'file_buf',f2)
    if not m1 and not m2 and not m3 and not m4:
        return Error(1, {"message": "rm only from existing task dirs: /opt/spa/data/<project>/<wf>/<task>/"
                                    " or from /opt/spa/bin or home"})
    try:
        if not os.path.isfile(f2):
            return Error(1, {"message": "no file " + f2})
        logging.info(datetime.datetime.now().isoformat()+ "rm "+ f2)
        os.remove(f2)
        return Success({"answer": f2 + " removed"})
    except OSError as err:
        return Error(1, {"message": "can not remove file: " + str(err)})

@method
def link_file(f1,f2) -> Result:
    m1 = re.match(r'/opt/spa/data/[^/]+/[^/]+/[^/]+/',f2)
    m2 = re.match(r'/opt/spa/bin/',f2)
    m3 = re.match(r'/home',f2)
    if not m1 and not m2 and not m3:
        return Error(1, {"message": "link only into existing task dirs: /opt/spa/data/<project>/<wf>/<task>/"
                                    " or into /opt/spa/bin or into home"})
    try:
        if not os.path.isfile(f1):
            return Error(1, {"message": "no file " + f1})
        m1 = re.match(r'/opt/spa/data/[^/]+/[^/]+/[^/]+/.+', f2)
        m2 = re.match(r'/opt/spa/bin/.+',f2)
        m3 = re.match(r'/home.+', f2)
        if not m1 and not m2 and not m3:
            f2 += f1
        logging.info(datetime.datetime.now().isoformat()+ "move "+f1+" "+f2)
        os.symlink(f1, f2)
        return Success({"answer": f2 + " -> " + f1})
    except OSError as err:
        return Error(1, {"message": "can not link file: " + str(err)})

# !FIXME Тут делаем метод записи статуса в Queue
# Хмм... А он не нужен: такого файла нет. Это файл воркфлоу, и им после создания владеет процесс, исполняющий воркфлоу
# def status_set(data) -> Result:
#     project = data["project"]
#     workflow = data["workflow"]
#     task = data["task"]
#     path = "/opt/spa/data/" + project + "/" + workflow + "/" + task + ""
#      logging.info(datetime.datetime.now().isoformat()+ str(command))
#     #time.sleep(10)
#     global a
#     p = subprocess.Popen([str(command),str(args)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,encoding = 'utf-8')
#     stdout,stderr = p.communicate()
#     logging.info(datetime.datetime.now().isoformat()+ str(stdout))
#     #p.wait()
#     a += 1
#     return Success({"answer": stdout})

class TestHttpServer(SimpleHTTPRequestHandler):
    # !FIXME Может быть добавить асинхронность, чтобы запросы обрабатывались параллельно
    def do_POST(self):
        ctype, pdict = cgi.parse_header(self.headers['Content-Type'])
        logging.info(datetime.datetime.now().isoformat()+ "CTYPE:"+ str(ctype))
        if ctype == 'multipart/form-data':
            logging.info(datetime.datetime.now().isoformat()+ "file upload")
            pdict['boundary'] = bytes(pdict['boundary'], "utf-8")
            pdict['CONTENT-LENGTH'] = int(self.headers['Content-Length'])

            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={'REQUEST_METHOD': 'POST',
                                                                                  'CONTENT_TYPE': self.headers[
                                                                                      'Content-Type'], })
            logging.info(datetime.datetime.now().isoformat()+ str(type(form)))
            try:
                if isinstance(form["file"], list):
                    for record in form["file"]:
                        open("./%s" % record.filename, "wb").write(record.file.read())
                else:
                    open("./%s" % form["file"].filename, "wb").write(form["file"].file.read())
            except IOError:
                return (False, "Can't create file to write, do you have permission to write?")
            f = io.BytesIO()
            length = f.tell()
            f.seek(0)
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.send_header("Content-Length", str(length))
            self.end_headers()
            if f:
                self.copyfile(f, self.wfile)
                f.close()
        else:
            # Process request
            logging.info(datetime.datetime.now().isoformat()+ str(self.headers["Content-Length"]))
            request = self.rfile.read(int(self.headers["Content-Length"])).decode()
            logging.info(datetime.datetime.now().isoformat()+ "REQUEST:"+str(request))
            response = dispatch(request)
            # Return response
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(response.encode())

@method
def kill_all(restart=False):
    logging.info(datetime.datetime.now().isoformat()+ str(workflow_processes))
    wf_list = set(workflow_processes.keys())
    for key in wf_list:
        kill_wf(key,keep_pid=restart)
    return Success({"answer": "everything is stopped"})

def restart_after_death():
    path = "/opt/spa/data/"
    projects = os.listdir(path)
    for project in projects: #Непонятно, что будет, если у нас был упавший проект на файловой системе - а другой был запущен на момент выключения - и теперь у на сдва упавших проекта
        wfs = os.listdir(path+project)
        for wf in wfs:
            files = os.listdir(path+project+"/"+wf)
            if "pid" in files:
                logging.info(datetime.datetime.now().isoformat()+ "Restart workflow in"+ path+str(project)+"/"+str(wf)+"/pid")
                run({"project":project, "workflow":wf})

def handler_child_death(signum, frame):
    wf = ""
    for wf in workflow_processes.keys():
        p = workflow_processes[wf].poll()
        if p is not None:
            logging.info(datetime.datetime.now().isoformat()+ str(wf) + " is status "+ str(p))
            break
    logging.info(datetime.datetime.now().isoformat()+ str(kill_wf(wf)))
    workflow_processes.pop(wf)

signal.signal(signal.SIGCHLD,handler_child_death)
if __name__ == "__main__":
    #atexit.register(kill_all)
    logging.basicConfig(filename="/opt/spa/log/srv.log",level=logging.DEBUG)
    restart_after_death()
    try:
        HTTPServer(("", 5000), TestHttpServer).serve_forever()
    except Exception as exc:
        logging.critical(str(exc))
    finally:
        kill_all(restart=True)#restart after reboot
