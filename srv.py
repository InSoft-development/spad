#!/usr/bin/python
import datetime
import time
from http.server import HTTPServer, SimpleHTTPRequestHandler
from jsonrpcserver import method, Result, Success, dispatch, Error
import json
import subprocess
import cgi
import io
import os
import atexit

workflow_processes = {}

class ExecutionQueue(object):
    """очередь исполнения workflow"""

    def __init__(self, pr_name, wf_name):
        self.tasks = []
        self.project_name = pr_name
        self.wf_name = wf_name  # одна очередь - один воркфлоу

    def load(self):
        path = "/opt/spa/data/" + self.project_name + "/" + self.wf_name
        with open(path + "/workflow.json", "r") as fp:
            self.tasks = json.load(fp)
        return self.tasks

    # Добавление
    def add_task(self, new_task: dict):
        if self.wf_name in workflow_processes.keys():
            print("ERROR: This workflow is currently executed, can't add task")
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

        path = "/opt/spa/data/" + self.project_name + "/" + self.wf_name + "/" + new_task["name"]

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

    # def change_status(self, task_name, status):
    #     for task in self.tasks:
    #         if task["name"] == task_name:
    #             task["status"] = status

    def save_wf_file(self):
        with open("/opt/spa/data/" + self.project_name + "/" + self.wf_name + "/workflow.json", "w") as wf_json_file:
            json.dump(self.tasks, wf_json_file, indent=3)


@method
def create(data) -> Result:
    print("DATA:", data)
    # data = data[0]
    project_name = data["context"]["project"]["name"]
    project = data["context"]["project"]
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
        new_tasks = workflow_json["tasks"]
        try:
            for task in new_tasks:
                workflows_q[workflow_json["name"]].add_task(task)
        except OSError:
            return Error(1, {"message": "task can not be created"})

    return Success({"answer": "file tree created"})


@method
def run(data) -> Result:
    if data["workflow"] in workflow_processes:
        return Error(1, {"message": "this workflow is executing now"})
    else:
        # Запоминаем субпроцесс
        json_string = json.dumps(data)
        p = subprocess.Popen(["/opt/spa/bin/run.py", json_string])
        path = "/opt/spa/data/" + data["project"] + "/" + data["workflow"]
        open(path + "/pid","w").write(str(p.pid))
        workflow_processes[data["workflow"]] = p
        return Success({"answer": "running in subprocess"})


def kill_wf(pr,wf):
    print("Stopping:", wf)
    print(workflow_processes)
    if wf not in workflow_processes:
        return Success({"answer": "workflow is not running"})

    p = workflow_processes[wf]
    path = "/opt/spa/data/" + pr + "/" + wf
    number_of_tasks = len(os.listdir(path))
    ret_code = p.poll()
    if ret_code is None:
        print("INFO: terminating ", wf)
        p.terminate()
        time.sleep(number_of_tasks)
        ret_code = p.poll()
        if ret_code is None:
            print("ERROR: can't terminate workflow within ", number_of_tasks, " sec", wf)
            #p.terminate()
            time.sleep(number_of_tasks*5)
            ret_code = p.poll()
            if ret_code is None:
                print("ERROR: can't terminate workflow within ", number_of_tasks*6, " sec", wf)
                #p.terminate()
                time.sleep(number_of_tasks*5)
                ret_code = p.poll()
                if ret_code is None:
                    print("ERROR: can't terminate workflow within ", number_of_tasks*11 , " sec, trying to kill", wf)
                    # !FIXME может не надо килять прям?
                    return Error(1, {"message": "ERROR: can't kill workflow"})
                    #p.kill()
                    # time.sleep(5)
                    # ret_code = p.poll()
                    # if ret_code is None:
                    #     print("ERROR: can't kill workflow!", wf)
                    #     return Error(1, {"message": "ERROR: can't kill workflow"})
    if ret_code is not None:
        if "pid" in os.listdir(path):
            os.remove(path + "/pid")
        workflow_processes.pop(wf)
    return Success({"answer": "workflow stopped"})


@method
def stop(data) -> Result:
    if data["workflow"] not in workflow_processes:
        return Error(1, {"message": "this workflow is not executing now"})
    else:
        return kill_wf(data["project"], data["workflow"])


@method
def status(data) -> Result:
    path = "/opt/spa/data/" + data["project"]
    if "task" in data:
        path+= "/" + data["workflow"] + "/" + data["task"]
        with open(path + "task.json", "r") as fp:
            st = json.load(fp)["task"]["info"]["status"]
        return Success({"answer": st})
    elif "workflow" in data:
        path += "/" + data["workflow"]
        with open(path + "/workflow.json", "r") as fp:
            wf_tasks = json.load(fp)
        st = {}
        for t in wf_tasks:
            st[t["name"]]= t["status"]
        return Success({"answer": json.dumps(st)})
    else:
        return Error(1, {"message": "define workflow for status examination"})

@method
def dump(data) -> Result:
    path = "/opt/spa/data/" + data["project"]
    if "workflow" in data:
        if "task" in data:
            path += "/" + data["workflow"] + "/" + data["task"]
            with open(path + "task.json", "r") as fp:
                st = json.load(fp)
            return Success({"answer": st})
        else:
            path += "/" + data["workflow"]
            with open(path + "/workflow.json", "r") as fp:
                wf_tasks = json.load(fp)
            return Success({"answer": json.dumps(wf_tasks)})
    else:
        pr_j = {}
        wfs = os.listdir(path)
        for wf in wfs:
            path += "/" + wf
            with open(path + "/workflow.json", "r") as fp:
                pr_j[wf] = json.load(fp)
        return Success({"answer": json.dumps(pr_j)})

# !FIXME Тут делаем метод записи статуса в Queue
# Хмм... А он не нужен: такого файла нет. Это файл воркфлоу, и им после создания владеет процесс, исполняющий воркфлоу
# def status_set(data) -> Result:
#     project = data["project"]
#     workflow = data["workflow"]
#     task = data["task"]
#     path = "/opt/spa/data/" + project + "/" + workflow + "/" + task + ""
#      print(command)
#     #time.sleep(10)
#     global a
#     p = subprocess.Popen([str(command),str(args)],stdout=subprocess.PIPE,stderr=subprocess.PIPE,encoding = 'utf-8')
#     stdout,stderr = p.communicate()
#     print(stdout)
#     #p.wait()
#     a += 1
#     return Success({"answer": stdout})

class TestHttpServer(SimpleHTTPRequestHandler):
    # !FIXME Может быть добавить асинхронность, чтобы запросы обрабатывались параллельно
    def do_POST(self):
        ctype, pdict = cgi.parse_header(self.headers['Content-Type'])
        print("CTYPE:", ctype)
        if ctype == 'multipart/form-data':
            print("file upload")
            pdict['boundary'] = bytes(pdict['boundary'], "utf-8")
            pdict['CONTENT-LENGTH'] = int(self.headers['Content-Length'])

            form = cgi.FieldStorage(fp=self.rfile, headers=self.headers, environ={'REQUEST_METHOD': 'POST',
                                                                                  'CONTENT_TYPE': self.headers[
                                                                                      'Content-Type'], })
            print(type(form))
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
            print(self.headers["Content-Length"])
            request = self.rfile.read(int(self.headers["Content-Length"])).decode()
            print("REQUEST:", request)
            response = dispatch(request)
            # Return response
            self.send_response(200)
            self.send_header("Content-type", "application/json")
            self.end_headers()
            self.wfile.write(response.encode())



def kill_all():
    print(workflow_processes)
    for key, value in workflow_processes:
        kill_wf(key)

if __name__ == "__main__":
    # !FIXME зарегить atend функцию по убийству воркфлоу всех и сделать
    atexit.register(kill_all)

    try:
        HTTPServer(("localhost", 5000), TestHttpServer).serve_forever()
    finally:
        kill_all()
